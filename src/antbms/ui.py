"""Rich TUI rendering for real-time snapshots.

Only this module (and the CLI) import rich; the decoder stays dependency
free. `render_snapshot()` returns a renderable for `rich.live.Live` or a
one-shot print.
"""

from rich.console import Group
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

# Bits of WARNING_BITS that describe normal operation rather than a problem.
STATUS_NAMES = {
    "battery_full",
    "battery_charging",
    "discharging",
    "can_charger_in",
    "rs485_charger_in",
    "charger_in",
    "charge_mos_on",
    "discharge_mos_on",
    "balance_on",
    "sleep",
    "auto_balance",
    "balance_limit",
    "balance_diff",
}

STATE_STYLE = {
    "charge": "bold green",
    "discharge": "bold yellow",
    "idle": "bold blue",
    "standby": "bold blue",
    "exception": "bold red",
    "none": "dim",
}


def _bar(value, lo, hi, width, style):
    span = max(hi - lo, 1e-9)
    filled = int(round((value - lo) / span * width))
    filled = max(0, min(width, filled))
    bar = Text()
    bar.append("█" * filled, style=style)
    bar.append("░" * (width - filled), style="grey37")
    return bar


def _fmt_runtime(seconds):
    days, rem = divmod(int(seconds), 86400)
    hours, rem = divmod(rem, 3600)
    minutes = rem // 60
    if days:
        return "%dd %02dh" % (days, hours)
    return "%02dh %02dm" % (hours, minutes)


def _header(s):
    state = s["systemStateName"]
    line = Text()
    line.append(" %s " % state.upper(), style=STATE_STYLE.get(state, "bold"))
    line.append("  %6.2f V " % s["packVoltage"], style="bold white")
    amps = s["current"]
    line.append(" %+7.2f A " % amps, style="green" if amps < 0 else "yellow")
    line.append(" %+6d W " % s["packPower"], style="green" if s["packPower"] < 0 else "yellow")
    line.append("   SOC ")
    line.append_text(_bar(s["soc"], 0, 100, 20, "cyan"))
    line.append(" %3d%% " % s["soc"], style="bold cyan")
    line.append("  SOH %d%%" % s["soh"], style="dim")
    return line


def _cells_table(s):
    cells = s["cellVoltages"]
    if not cells:
        return Text("no cell data")
    vmin, vmax = min(cells), max(cells)
    lo, hi = vmin - 0.012, vmax + 0.012
    rows = (len(cells) + 1) // 2
    table = Table.grid(padding=(0, 1))
    for _ in range(2):
        table.add_column(justify="right")
        table.add_column()
        table.add_column(justify="right")
    half = [(i, v) for i, v in enumerate(cells)]
    for r in range(rows):
        row = []
        for idx, v in (half[r], half[r + rows]) if r + rows < len(cells) else (half[r],):
            if v == vmax:
                style, vstyle = "green", "bold green"
            elif v == vmin:
                style, vstyle = "red", "bold red"
            else:
                style, vstyle = "bright_blue", "white"
            row += [Text("%2d" % (idx + 1), style="dim"),
                    _bar(v, lo, hi, 16, style),
                    Text("%.3f" % v, style=vstyle)]
        table.add_row(*row)
    caption = Text()
    caption.append("Δ %3.0f mV " % (s["cellVoltageDiff"] * 1000),
                   style="bold red" if s["cellVoltageDiff"] >= 0.030 else "bold")
    caption.append(" avg %.3f V   max #%d   min #%d" %
                   (s["cellVoltageAvg"], s["cellVoltageMaxPos"], s["cellVoltageMinPos"]),
                   style="dim")
    return Group(table, caption)


def _details(s):
    line = Text()
    temps = "  ".join("%.0f°" % t for t in s["temperatures"])
    line.append("Temps %s  MOS %.0f°  Bal %.0f°" %
                (temps, s["temperatureMos"], s["temperatureBalance"]))
    line.append("   |   ", style="dim")
    line.append("MOS dis:", style="dim")
    line.append(s["disMosStateName"], style="green" if s["disMosState"] == 1 else "red")
    line.append(" ch:", style="dim")
    line.append(s["chMosStateName"], style="green" if s["chMosState"] == 1 else "red")
    line.append(" bal:", style="dim")
    line.append(s["balanceStateName"],
                style="cyan" if s["balanceState"] else "dim")
    line2 = Text()
    line2.append("Capacity %.1f / %.1f Ah" % (s["packRemainAh"], s["packPhysicsAh"]))
    line2.append("   lifetime %.0f Ah   uptime %s   %s" %
                 (s["packAllAh"], _fmt_runtime(s["allTimerS"]), s["batteryTypeName"]),
                 style="dim")
    extra = []
    if s.get("chTimeRemain"):
        extra.append("full in ~%dh%02dm" % divmod(s["chTimeRemain"], 60))
    if s.get("disTimeRemain"):
        extra.append("empty in ~%dh%02dm" % divmod(s["disTimeRemain"], 60))
    if extra:
        line2.append("   " + "  ".join(extra), style="bold cyan")
    return Group(line, line2)


def _flags(s):
    parts = []
    protections = s["protections"]
    warnings = [w for w in s["warnings"] if w not in STATUS_NAMES]
    status = [w for w in s["warnings"] if w in STATUS_NAMES]
    if protections:
        parts.append(Text("⚠ PROTECTION: " + "  ".join(protections), style="bold white on red"))
    if warnings:
        parts.append(Text("⚠ warning: " + "  ".join(warnings), style="bold yellow"))
    if status:
        parts.append(Text("status: " + "  ".join(status), style="dim cyan"))
    if not parts:
        parts.append(Text("no active protections or warnings", style="dim green"))
    return Group(*parts)


def render_snapshot(s, title="ANT BMS"):
    """Return a rich renderable for one decoded real-time snapshot."""
    body = Group(
        _header(s),
        Text(),
        _cells_table(s),
        Text(),
        _details(s),
        Text(),
        _flags(s),
    )
    return Panel(body, title="[bold]%s[/bold]" % title,
                 subtitle="[dim]%d cells · read-only[/dim]" % s["cellCount"],
                 border_style="bright_blue", padding=(0, 2))
