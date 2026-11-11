"""ANT BMS read-only CLI (Python + bleak).

Usage:
    antbms scan
    antbms live [--name ANT-BLE] [--address XX:XX:...] [--plain] [--json]
    antbms demo [--save-svg docs/demo.svg]
    antbms info [--address XX:XX:...]
    antbms params --block voltage [--address XX:XX:...] [--auth]
    antbms report [--json | --md] [--out FILE] [--auth]
    antbms log --csv out.csv [--interval 1]
    antbms decode <hex-frame>

This client is READ-ONLY. It only sends read commands (0x01 real-time,
0x02 read parameter block, 0x04 read chip id, 0x05 read info). It never sends
write/control commands, so it cannot change any BMS setting.

Parameter blocks return 0xFFFF until the BMS is unlocked. Pass --auth to send
the level-1 permission request (cmd 0x23, default password 12345678). That
request only unlocks read access; it does not change any parameter.
"""

import argparse
import asyncio
import json
import sys
import time

from . import protocol as p
from .params import PARAM_BLOCKS, PARAM_MAP, PARAM_META

REALTIME_REQUEST = p.build_read_request(0, 190, 0x01)


def format_snapshot(s):
    lines = []
    lines.append("=" * 60)
    lines.append(
        "state=%s  soc=%d%%  soh=%d%%  pack=%.2fV  current=%.2fA  power=%dW"
        % (s["systemStateName"], s["soc"], s["soh"], s["packVoltage"],
           s["current"], s["packPower"])
    )
    lines.append(
        "cells=%d  Vmax=%.3f(#%d)  Vmin=%.3f(#%d)  diff=%.3f  avg=%.3f"
        % (s["cellCount"], s["cellVoltageMax"], s["cellVoltageMaxPos"],
           s["cellVoltageMin"], s["cellVoltageMinPos"], s["cellVoltageDiff"],
           s["cellVoltageAvg"])
    )
    lines.append(
        "temps=%s  mos=%.1fC  balance=%.1fC"
        % (s["temperatures"], s["temperatureMos"], s["temperatureBalance"])
    )
    lines.append(
        "Ah: physical=%.2f  remain=%.2f  life=%.2f  lifeDis=%d  lifeCh=%d"
        % (s["packPhysicsAh"], s["packRemainAh"], s["packAllAh"],
           s["packAllDisAh"], s["packAllChAh"])
    )
    lines.append(
        "MOS: dis=%s  ch=%s  balance=%s  type=%s"
        % (s["disMosStateName"], s["chMosStateName"], s["balanceStateName"],
           s["batteryTypeName"])
    )
    if s["cellVoltages"]:
        lines.append("cell voltages (V):")
        for i in range(0, len(s["cellVoltages"]), 8):
            chunk = s["cellVoltages"][i:i + 8]
            lines.append("  " + "  ".join("%.3f" % v for v in chunk))
    if s["protections"]:
        lines.append("protections: " + ", ".join(s["protections"]))
    if s["warnings"]:
        lines.append("warnings: " + ", ".join(s["warnings"]))
    return "\n".join(lines)


def format_snapshot_old(s):
    """Plain-text summary of an old-protocol (AA 55) snapshot."""
    lines = []
    lines.append("=" * 60)
    lines.append(
        "(old protocol)  soc=%d%%  pack=%.2fV  current=%.2fA  power=%dW"
        % (s["soc"], s["packVoltage"], s["current"], s["packPower"])
    )
    lines.append(
        "cells=%d  Vmax=%.3f(#%d)  Vmin=%.3f(#%d)  avg=%.3f"
        % (s["cellCount"], s["cellVoltageMax"], s["cellVoltageMaxPos"],
           s["cellVoltageMin"], s["cellVoltageMinPos"], s["cellVoltageAvg"])
    )
    lines.append(
        "temps=%s  mos=%.1fC  balance=%.1fC"
        % (s["temperatures"], s["temperatureMos"], s["temperatureBalance"])
    )
    lines.append(
        "Ah: physical=%.2f  remain=%.2f  life=%.2f"
        % (s["packPhysicsAh"], s["packRemainAh"], s["packAllAh"])
    )
    if s["cellVoltages"]:
        lines.append("cell voltages (V):")
        for i in range(0, len(s["cellVoltages"]), 8):
            chunk = s["cellVoltages"][i:i + 8]
            lines.append("  " + "  ".join("%.3f" % v for v in chunk))
    return "\n".join(lines)


async def _resolve_address(args):
    if args.address:
        return args.address
    from bleak import BleakScanner

    print("Scanning for %r..." % args.name)
    # The BMS advertises intermittently, so a single short scan often misses it.
    for attempt in range(4):
        result = await BleakScanner.discover(timeout=args.timeout, return_adv=True)
        for addr, (device, adv) in result.items():
            name = device.name or adv.local_name or ""
            if name.startswith(args.name):
                print("Found %s [%s] RSSI=%s" % (name, addr, adv.rssi))
                return addr
        if attempt < 3:
            print("  not found, retrying scan...")
    print("No device starting with %r found." % args.name)
    return None


async def _request(client, queue, addr, length, cmd, expected_cmd, timeout=3.0,
                   response=True, attempts=4, reset=None):
    """Send a read request and wait for the matching response frame.

    BLE notifications can be lost when the link is weak, which corrupts the
    frame CRC.  In that case the frame never shows up, so the request is
    simply retried.
    """
    loop = asyncio.get_event_loop()
    for attempt in range(attempts):
        req = p.build_read_request(addr, length, cmd)
        await client.write_gatt_char(p.CHAR_UUID, req, response=response)
        deadline = loop.time() + timeout
        while True:
            remaining = deadline - loop.time()
            if remaining <= 0:
                break
            try:
                frame = await asyncio.wait_for(queue.get(), timeout=remaining)
            except asyncio.TimeoutError:
                break
            if frame[2] == expected_cmd:
                start = frame[3] | (frame[4] << 8)
                if start == addr:
                    return frame
        if reset is not None:
            reset()
        await asyncio.sleep(0.2)
    raise TimeoutError(
        "no valid response for cmd 0x%02X addr %d after %d attempts"
        % (expected_cmd, addr, attempts)
    )


async def _send_auth(client, queue, password, timeout=3.0):
    """Send the level-1 permission request and return the granted level."""
    req = p.build_auth_request(password)
    await client.write_gatt_char(p.CHAR_UUID, req, response=True)
    loop = asyncio.get_event_loop()
    deadline = loop.time() + timeout
    while True:
        remaining = deadline - loop.time()
        if remaining <= 0:
            raise TimeoutError("no auth response (cmd 0x43)")
        try:
            frame = await asyncio.wait_for(queue.get(), timeout=remaining)
        except asyncio.TimeoutError:
            raise TimeoutError("no auth response (cmd 0x43)")
        if frame[2] == 0x43:
            return p.decode_auth(frame)


async def _read_block(client, queue, addr, length, cmd, reset, chunk=64):
    """Read a parameter block, splitting it into small chunks when needed.

    Long blocks produce long BLE notification bursts that are easily
    corrupted on a weak link, so they are read in small pieces and merged.
    Returns (payload, chunks) where chunks holds the per-request metadata
    (extra section) returned by the BMS.
    """
    payload = bytearray()
    chunks = []
    offset = 0
    while offset < length:
        size = min(chunk, length - offset)
        frame = await _request(client, queue, addr + offset, size, cmd, 0x12,
                               reset=reset)
        payload.extend(_raw_data(frame))
        chunks.append((addr + offset, size, p.decode_extra(frame)))
        offset += size
    return bytes(payload), chunks


def _raw_data(frame):
    return bytes(frame[6:6 + frame[5]])


async def cmd_scan(args):
    from bleak import BleakScanner

    print("Scanning for %.1fs..." % args.timeout)
    result = await BleakScanner.discover(timeout=args.timeout, return_adv=True)
    found = 0
    for address, (device, adv) in result.items():
        name = device.name or adv.local_name or ""
        if name.startswith(args.name):
            found += 1
            print("  %-24s %s  RSSI=%s" % (name, address, adv.rssi))
    if not found:
        print("No device starting with %r found." % args.name)


async def cmd_live(args):
    if args.demo:
        return await _run_demo(args)
    from bleak import BleakClient

    address = await _resolve_address(args)
    if not address:
        return

    use_tui = not (args.json or args.plain)
    live = None
    if use_tui:
        from rich.console import Console
        from rich.live import Live
        from rich.text import Text

        live = Live(Text("connecting to %s ..." % address, style="dim"),
                    console=Console(), refresh_per_second=4)
        live.start()

    buffer = bytearray()

    def on_notify(_sender, data):
        buffer.extend(data)
        frames, remaining = p.find_frames(buffer)
        buffer[:] = remaining
        for frame in frames:
            if frame[2] != 0x11:
                continue
            if args.raw and not use_tui:
                print("RAW", frame.hex())
            try:
                snap = p.decode_realtime(frame)
            except ValueError as exc:
                if not use_tui:
                    print("decode error:", exc)
                continue
            if args.json:
                print(json.dumps(snap))
            elif args.plain:
                print(format_snapshot(snap))
            else:
                from .ui import render_snapshot

                live.update(render_snapshot(snap, title="ANT BMS · %s" % address))

    client = BleakClient(address)
    try:
        if not use_tui:
            print("Connecting to %s..." % address)
        await client.connect()
        await client.start_notify(p.CHAR_UUID, on_notify)
        if not use_tui:
            print("Sending real-time request every 500 ms (Ctrl+C to stop).")
        loop = asyncio.get_event_loop()
        deadline = loop.time() + args.seconds if args.seconds else None
        while client.is_connected:
            await client.write_gatt_char(
                p.CHAR_UUID, REALTIME_REQUEST, response=args.with_response
            )
            await asyncio.sleep(0.5)
            if deadline is not None and loop.time() >= deadline:
                break
    except (KeyboardInterrupt, asyncio.CancelledError):
        pass
    finally:
        if live is not None:
            live.stop()
        try:
            await client.stop_notify(p.CHAR_UUID)
        except Exception:
            pass
        try:
            await client.disconnect()
        except Exception:
            pass
        if not use_tui:
            print("Disconnected.")


async def _run_demo(args):
    """Run the dashboard on synthetic data — no hardware, no BLE imports."""
    from .demo import DemoBattery

    battery = DemoBattery()
    frames = getattr(args, "frames", 0) or 0
    interval = getattr(args, "interval", 0.5)
    save_svg = getattr(args, "save_svg", None)

    if save_svg:
        import io

        from rich.console import Console

        from .ui import render_snapshot

        console = Console(record=True, width=96, force_terminal=True,
                          legacy_windows=False, file=io.StringIO())
        console.print(render_snapshot(battery.snapshot(90), title="antbms demo"))
        console.save_svg(save_svg, title="antbms demo")
        print("saved %s" % save_svg)
        return

    if args.json or args.plain:
        tick = 0
        try:
            while True:
                snap = battery.snapshot(tick)
                print(json.dumps(snap) if args.json else format_snapshot(snap))
                tick += 1
                if frames and tick >= frames:
                    break
                await asyncio.sleep(interval)
        except (KeyboardInterrupt, asyncio.CancelledError):
            pass
        return

    from rich.console import Console
    from rich.live import Live

    from .ui import render_snapshot

    tick = 0
    try:
        with Live(render_snapshot(battery.snapshot(0), title="ANT BMS · demo"),
                  console=Console(), refresh_per_second=8) as live:
            while True:
                tick += 1
                if frames and tick >= frames:
                    break
                await asyncio.sleep(interval)
                live.update(render_snapshot(battery.snapshot(tick),
                                            title="ANT BMS · demo"))
    except (KeyboardInterrupt, asyncio.CancelledError):
        pass


async def _with_client(args, work):
    from bleak import BleakClient

    address = await _resolve_address(args)
    if not address:
        return
    buffer = bytearray()
    queue = asyncio.Queue()

    def on_notify(_sender, data):
        buffer.extend(data)
        frames, remaining = p.find_frames(buffer)
        buffer[:] = remaining
        for frame in frames:
            queue.put_nowait(frame)

    def reset_buffer():
        buffer.clear()

    client = BleakClient(address)
    print("Connecting to %s..." % address)
    for attempt in range(5):
        try:
            await client.connect()
            break
        except BaseException as exc:  # WinRT raises CancelledError on timeouts
            if attempt == 4:
                print("Connection failed: %s: %s"
                      % (type(exc).__name__, exc))
                return
            print("  connect attempt %d failed (%s), retrying..."
                  % (attempt + 1, type(exc).__name__))
            await asyncio.sleep(3)
    await client.start_notify(p.CHAR_UUID, on_notify)
    try:
        await work(client, queue, reset_buffer)
    finally:
        try:
            await client.stop_notify(p.CHAR_UUID)
        except Exception:
            pass
        await client.disconnect()
        print("Disconnected.")


async def _gather_device(client, queue, reset):
    """Read the identity blocks; shared by `info` and `report`."""
    device = {}
    f = await _request(client, queue, 620, 32, 0x02, 0x12, reset=reset)
    raw = _raw_data(f)
    device["hardware_version"] = p.decode_ascii(raw[0:16])
    device["software_version"] = p.decode_ascii(raw[16:32])
    f = await _request(client, queue, 262, 32, 0x02, 0x12, reset=reset)
    device["pack_id"] = p.decode_ascii(_raw_data(f))
    f = await _request(client, queue, 0, 12, 0x04, 0x14, reset=reset)
    device["chip_id"] = p.decode_chip_id(f)["id"]
    f = await _request(client, queue, 4096, 12, 0x04, 0x14, reset=reset)
    device["sys_id2"] = p.decode_chip_id(f)["id"]
    f = await _request(client, queue, 0, 40, 0x05, 0x15, reset=reset)
    device["info_block"] = bytes(p.decode_info(f)["data"]).hex()
    return device


async def cmd_info(args):
    async def work(client, queue, reset):
        device = await _gather_device(client, queue, reset)
        if args.json:
            print(json.dumps(device, indent=2))
        else:
            for key, value in device.items():
                print("%-17s: %s" % (key.replace("_", " "), value))

    await _with_client(args, work)


async def cmd_params(args):
    block = PARAM_BLOCKS[args.block]

    async def work(client, queue, reset):
        if args.auth:
            level = await _send_auth(client, queue, args.password)
            print("Auth level       : %d" % level)
        payload, chunks = await _read_block(client, queue, block["addr"],
                                            block["len"], block["cmd"], reset)
        if args.json:
            from .report import decode_block_values

            print(json.dumps({
                "block": args.block,
                "addr": block["addr"],
                "len": block["len"],
                "chunks": [{"start": s, "size": z, "extra": e}
                           for s, z, e in chunks],
                "values": decode_block_values(args.block, payload),
            }, indent=2))
            return
        values = []
        for i in range(0, len(payload) - 1, 2):
            values.append((block["addr"] + i, payload[i] | (payload[i + 1] << 8)))
        print("Block %r (addr %d, %d bytes)" % (args.block, block["addr"],
                                                block["len"]))
        for start, size, extra in chunks:
            if extra:
                print("  chunk %4d+%3d  status=0x%02X group=%s lastAddr=%s%s"
                      % (start, size, extra["status"], extra.get("groupId"),
                         extra.get("lastAddr"),
                         " (clamped)" if extra.get("clamped") else ""))
            else:
                print("  chunk %4d+%3d  no extra section" % (start, size))
        unset = 0
        for addr, value in values:
            info = PARAM_MAP.get(addr)
            if value == 0xFFFF:
                unset += 1
                name = info[0] if info else "addr %d" % addr
                print("  %-46s = <not configured>  (raw 0xFFFF @ %d)"
                      % (name, addr))
                continue
            if info:
                name, it, dec = info
                scaled = value / float(it)
                print("  %-46s = %.*f  (raw %d @ %d)" % (name, dec, scaled,
                                                         value, addr))
            else:
                print("  addr %-4d = %d" % (addr, value))
        if unset:
            print("  (%d of %d values are 0xFFFF: parameter not configured "
                  "on the BMS)" % (unset, len(values)))
        ascii_parts = []
        if args.block == "battery":
            off = 262 - block["addr"]
            ascii_parts.append(("Pack ID", p.decode_ascii(payload[off:off + 32])))
        elif args.block == "version":
            ascii_parts.append(("Software version", p.decode_ascii(payload[0:16])))
        elif args.block == "manufacturer":
            ascii_parts.append(("Boot version", p.decode_ascii(payload[0:16])))
            ascii_parts.append(("System check code",
                                ".".join(str(b) for b in payload[16:32])))
        elif args.block == "sysid":
            ascii_parts.append(("System code", ".".join(str(b) for b in payload)))
        for label, text in ascii_parts:
            if text:
                print("  %-46s : %s" % (label, text))

    await _with_client(args, work)


def cmd_decode(args):
    raw = args.hex.replace(" ", "").replace(":", "").replace("\n", "")
    try:
        data = bytes.fromhex(raw)
    except ValueError as exc:
        print("Invalid hex:", exc)
        return 1
    objs = []
    if data[:2] == b"\x7e\xa1":
        frames, _ = p.find_frames(data)
        if not frames:
            print("No valid frame found (bad CRC/length/tail).")
            return 1
        for frame in frames:
            if frame[2] == 0x11:
                snap = p.decode_realtime(frame)
                objs.append({"type": "realtime", **snap})
                if not args.json:
                    print(format_snapshot(snap))
            elif frame[2] == 0x12:
                d = p.decode_params(frame)
                extra = p.decode_extra(frame)
                objs.append({"type": "params", **d, "extra": extra})
                if args.json:
                    continue
                print("params start=%d len=%d" % (d["startAddr"], d["length"]))
                if extra:
                    print("  extra: status=0x%02X group=%s lastAddr=%s%s"
                          % (extra["status"], extra.get("groupId"),
                             extra.get("lastAddr"),
                             " (clamped)" if extra.get("clamped") else ""))
                for addr, value in d["values"]:
                    info = PARAM_MAP.get(addr)
                    if value == 0xFFFF:
                        name = info[0] if info else "addr %d" % addr
                        print("  %-46s = <not configured>  (raw 0xFFFF @ %d)"
                              % (name, addr))
                        continue
                    if info:
                        name, it, dec = info
                        print("  %-46s = %.*f  (raw %d @ %d)"
                              % (name, dec, value / float(it), value, addr))
                    else:
                        print("  addr %-4d = %d" % (addr, value))
            elif frame[2] == 0x14:
                d = p.decode_chip_id(frame)
                objs.append({"type": "chip_id", **d})
                if not args.json:
                    print("chip id:", d["id"])
            elif frame[2] == 0x15:
                d = p.decode_info(frame)
                objs.append({"type": "info", **d})
                if not args.json:
                    print("info:", bytes(d["data"]).hex())
            else:
                objs.append({"type": "unknown", "cmd": frame[2],
                             "hex": frame.hex()})
                if not args.json:
                    print("frame cmd=0x%02X len=%d: %s"
                          % (frame[2], frame[5], frame.hex()))
    elif data[:2] == b"\xaa\x55":
        snap = p.decode_old(data)
        objs.append({"type": "realtime_old", **snap})
        if not args.json:
            print(format_snapshot_old(snap))
    else:
        print("Unknown frame header:", data[:2].hex())
        return 1
    if args.json:
        print(json.dumps(objs if len(objs) != 1 else objs[0], indent=2))
    return 0


async def _read_snapshot(client, queue, reset):
    frame = await _request(client, queue, 0, 190, 0x01, 0x11, reset=reset)
    return p.decode_realtime(frame)


def _print_report_rich(rep):
    from rich.console import Console
    from rich.table import Table

    console = Console()
    dev = Table(title="Device", show_header=False, title_justify="left")
    dev.add_column(style="dim")
    dev.add_column()
    for key, value in rep["device"].items():
        dev.add_row(key.replace("_", " "), str(value))
    console.print(dev)

    for block, entries in rep["settings"].items():
        table = Table(title="Settings — %s" % block, title_justify="left")
        table.add_column("addr", justify="right", style="dim")
        table.add_column("parameter")
        table.add_column("value", justify="right")
        table.add_column("raw", justify="right", style="dim")
        for e in entries:
            if e["value"] is None:
                value = "[dim]not configured[/dim]"
            else:
                value = "%s%s" % (e["value"], (" " + e["unit"]) if e["unit"] else "")
            table.add_row(str(e["addr"]), e["name"], value, "0x%04X" % e["raw"])
        console.print(table)

    if rep.get("realtime"):
        from .ui import render_snapshot

        console.print(render_snapshot(rep["realtime"], title="Real-time snapshot"))


async def cmd_report(args):
    from . import __version__
    from . import report as report_mod

    async def work(client, queue, reset):
        device = await _gather_device(client, queue, reset)
        if args.auth:
            device["auth_level"] = await _send_auth(client, queue, args.password)
        blocks = {}
        for name in sorted(PARAM_BLOCKS):
            block = PARAM_BLOCKS[name]
            if not args.json and not args.md:
                print("reading block %r..." % name)
            payload, _chunks = await _read_block(client, queue, block["addr"],
                                                 block["len"], block["cmd"], reset)
            blocks[name] = payload
        snapshot = await _read_snapshot(client, queue, reset)
        rep = report_mod.build_report(device, blocks, snapshot,
                                      version=__version__)
        if args.json:
            text = report_mod.to_json(rep)
        elif args.md:
            text = report_mod.to_markdown(rep)
        else:
            text = None
        if args.out:
            with open(args.out, "w", encoding="utf-8") as f:
                f.write(text if text is not None else report_mod.to_markdown(rep))
            print("wrote %s" % args.out)
        elif text is not None:
            print(text)
        else:
            _print_report_rich(rep)

    await _with_client(args, work)


def _csv_row(snap, ts):
    fixed = [ts, snap["systemStateName"], snap["soc"], snap["soh"],
             snap["packVoltage"], snap["current"], snap["packPower"],
             snap["cellVoltageMin"], snap["cellVoltageMax"],
             round(snap["cellVoltageDiff"], 3), snap["cellVoltageAvg"],
             snap["temperatureMos"], snap["temperatureBalance"],
             snap["packRemainAh"]]
    cells = list(snap["cellVoltages"])
    temps = list(snap["temperatures"])
    flags = ["|".join(snap["protections"]), "|".join(snap["warnings"])]
    return fixed + cells + temps + flags


def _csv_header(snap):
    fixed = ["timestamp", "state", "soc", "soh", "packVoltage", "current",
             "packPower", "cellVoltageMin", "cellVoltageMax", "cellVoltageDiff",
             "cellVoltageAvg", "temperatureMos", "temperatureBalance",
             "packRemainAh"]
    cells = ["cell_%d" % (i + 1) for i in range(len(snap["cellVoltages"]))]
    temps = ["temp_%d" % (i + 1) for i in range(len(snap["temperatures"]))]
    return fixed + cells + temps + ["protections", "warnings"]


async def cmd_log(args):
    import csv

    path = args.csv or args.jsonl
    fh = open(path, "a", newline="", encoding="utf-8")
    writer = csv.writer(fh) if args.csv else None
    wrote_header = fh.tell() != 0
    count = 0

    async def work(client, queue, reset):
        nonlocal wrote_header, count
        loop = asyncio.get_event_loop()
        deadline = loop.time() + args.seconds if args.seconds else None
        print("logging to %s every %.1fs (Ctrl+C to stop)" % (path, args.interval))
        while True:
            try:
                snap = await _read_snapshot(client, queue, reset)
            except TimeoutError:
                continue
            ts = time.strftime("%Y-%m-%dT%H:%M:%S")
            if writer is not None:
                if not wrote_header:
                    writer.writerow(_csv_header(snap))
                    wrote_header = True
                writer.writerow(_csv_row(snap, ts))
            else:
                fh.write(json.dumps({"timestamp": ts, **snap}) + "\n")
            fh.flush()
            count += 1
            print("\r%d snapshots" % count, end="", flush=True)
            if deadline is not None and loop.time() >= deadline:
                break
            await asyncio.sleep(args.interval)

    try:
        await _with_client(args, work)
    except (KeyboardInterrupt, asyncio.CancelledError):
        pass
    finally:
        fh.close()
        print()


EXAMPLES = """\
examples:
  antbms demo                           live dashboard with synthetic data (no hardware)
  antbms demo --save-svg docs/demo.svg  render one demo frame to an SVG
  antbms scan                           list nearby ANT-BLE devices
  antbms live                           auto-discover and show the live dashboard
  antbms live --plain --seconds 10      classic text output for 10 seconds
  antbms live --json | jq .soc          one JSON object per snapshot
  antbms info                           firmware versions, pack id, chip id
  antbms params --block voltage --auth  read + decode one settings block
  antbms report --md --out my-pack.md   full config/state backup as Markdown
  antbms log --csv pack.csv --interval 5
  antbms decode 7ea101000...            decode a captured hex frame offline
"""


def main(argv=None):
    from . import __version__

    parser = argparse.ArgumentParser(
        prog="antbms",
        description="ANT BMS read-only CLI: live TUI dashboard, settings "
                    "reader, config backup and data logger.",
        epilog=EXAMPLES,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--version", action="version",
                        version="%(prog)s " + __version__)
    sub = parser.add_subparsers(dest="command", required=True)

    def add_conn(sp):
        sp.add_argument("--name", default="ANT-BLE",
                        help="device name prefix (default ANT-BLE)")
        sp.add_argument("--address", default=None,
                        help="connect to this BLE address, skip scanning")
        sp.add_argument("--timeout", type=float, default=10.0)

    ps = sub.add_parser("scan", help="list nearby ANT-BLE devices")
    ps.add_argument("--name", default="ANT-BLE")
    ps.add_argument("--timeout", type=float, default=10.0)
    ps.set_defaults(func=lambda a: asyncio.run(cmd_scan(a)))

    pl = sub.add_parser("live", help="live dashboard (rich TUI by default)")
    add_conn(pl)
    pl.add_argument("--plain", action="store_true",
                    help="classic text output instead of the TUI")
    pl.add_argument("--json", action="store_true",
                    help="one JSON object per snapshot (JSONL)")
    pl.add_argument("--demo", action="store_true",
                    help="synthetic data, no hardware needed")
    pl.add_argument("--interval", type=float, default=0.5,
                    help="demo refresh interval in seconds (default 0.5)")
    pl.add_argument("--frames", type=int, default=0,
                    help="demo: stop after N frames (0 = endless)")
    pl.add_argument("--with-response", action="store_true",
                    help="use write-with-response instead of write-without-response")
    pl.add_argument("--seconds", type=float, default=0,
                    help="stop after N seconds (0 = run until Ctrl+C)")
    pl.add_argument("--raw", action="store_true",
                    help="print raw frame hex (with --plain/--json)")
    pl.set_defaults(func=lambda a: asyncio.run(cmd_live(a)))

    pm = sub.add_parser("demo", help="live dashboard with synthetic data "
                                     "(no hardware, no Bluetooth)")
    pm.add_argument("--plain", action="store_true")
    pm.add_argument("--json", action="store_true")
    pm.add_argument("--interval", type=float, default=0.5)
    pm.add_argument("--frames", type=int, default=0,
                    help="stop after N frames (0 = endless)")
    pm.add_argument("--save-svg", dest="save_svg", metavar="FILE",
                    help="render one frame to an SVG file and exit")
    pm.set_defaults(func=lambda a: asyncio.run(_run_demo(a)))

    pi = sub.add_parser("info", help="read versions, pack id and chip id")
    add_conn(pi)
    pi.add_argument("--json", action="store_true")
    pi.set_defaults(func=lambda a: asyncio.run(cmd_info(a)))

    pp = sub.add_parser("params", help="read and decode a settings block")
    add_conn(pp)
    pp.add_argument("--block", required=True, choices=sorted(PARAM_BLOCKS))
    pp.add_argument("--auth", action="store_true",
                    help="send level-1 permission request first (unlocks read; "
                         "does not change any setting)")
    pp.add_argument("--password", default=p.DEFAULT_PASSWORD,
                    help="permission password (default %s)" % p.DEFAULT_PASSWORD)
    pp.add_argument("--json", action="store_true")
    pp.set_defaults(func=lambda a: asyncio.run(cmd_params(a)))

    pr = sub.add_parser("report", help="full device report: identity, every "
                                       "settings block, real-time snapshot")
    add_conn(pr)
    pr.add_argument("--auth", action="store_true",
                    help="unlock settings read first (read-only, see params)")
    pr.add_argument("--password", default=p.DEFAULT_PASSWORD)
    pr.add_argument("--json", action="store_true", help="JSON output")
    pr.add_argument("--md", action="store_true", help="Markdown output")
    pr.add_argument("--out", metavar="FILE", help="write to a file")
    pr.set_defaults(func=lambda a: asyncio.run(cmd_report(a)))

    pg = sub.add_parser("log", help="periodic CSV/JSONL data logger")
    add_conn(pg)
    group = pg.add_mutually_exclusive_group(required=True)
    group.add_argument("--csv", metavar="FILE")
    group.add_argument("--jsonl", metavar="FILE")
    pg.add_argument("--interval", type=float, default=1.0,
                    help="seconds between snapshots (default 1)")
    pg.add_argument("--seconds", type=float, default=0,
                    help="stop after N seconds (0 = run until Ctrl+C)")
    pg.set_defaults(func=lambda a: asyncio.run(cmd_log(a)))

    pd = sub.add_parser("decode", help="decode a hex frame offline")
    pd.add_argument("hex")
    pd.add_argument("--json", action="store_true")
    pd.set_defaults(func=cmd_decode)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
