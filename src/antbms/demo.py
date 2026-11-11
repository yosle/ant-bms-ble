"""Synthetic ANT BMS data for the demo mode.

Builds protocol-correct cmd 0x11 frames (CRC included) so the whole
pipeline — reassembly, decoding, TUI — runs without any hardware.
The simulation is deterministic: the same tick always produces the
same frame, which keeps tests and the README screenshot stable.
"""

import math

from . import protocol as p


def _u16le(v):
    v = int(round(v)) & 0xFFFF
    return bytes([v & 0xFF, (v >> 8) & 0xFF])


def _u32le(v):
    v = int(round(v)) & 0xFFFFFFFF
    return bytes([v & 0xFF, (v >> 8) & 0xFF, (v >> 16) & 0xFF, (v >> 24) & 0xFF])


def build_realtime_frame(
    cells,
    temps,
    *,
    system_state=4,
    protect_mask=0,
    protect_mask1=0,
    warning_mask=0,
    warning_mask1=0,
    temp_mos=32,
    temp_balance=29,
    current=-12.3,
    soc=87,
    soh=99,
    dis_mos=1,
    ch_mos=1,
    balance_state=0,
    physics_ah=105.0,
    remain_ah=87.5,
    all_ah=2450.0,
    power=0,
    timer_s=3600,
    balance_bit=0,
    battery_type=64242,
    all_dis_ah=4120,
    all_ch_ah=4180,
    dis_timer_s=2_250_000,
    ch_timer_s=1_980_000,
    ch_time_remain_min=0,
    dis_time_remain_min=0,
):
    """Build a valid new-protocol real-time frame (cmd 0x11)."""
    vmax = max(cells)
    vmin = min(cells)
    payload = bytearray()
    payload += bytes([1, system_state, len(temps), len(cells)])
    payload += _u32le(protect_mask) + _u32le(protect_mask1)
    payload += _u32le(warning_mask) + _u32le(warning_mask1)
    payload += bytes(8)
    for v in cells:
        payload += _u16le(v * 1000)
    for t in temps:
        payload += _u16le(t if t >= 0 else t + 65536)
    payload += _u16le(temp_mos)
    payload += _u16le(temp_balance)
    payload += _u16le(sum(cells) * 100)
    payload += _u16le(current * 10 if current >= 0 else current * 10 + 65536)
    payload += _u16le(soc)
    payload += _u16le(soh)
    payload += bytes([dis_mos, ch_mos])
    payload += _u16le(balance_state)
    payload += _u32le(physics_ah * 1e6)
    payload += _u32le(remain_ah * 1e6)
    payload += _u32le(all_ah * 1e3)
    payload += _u32le(power)
    payload += _u32le(timer_s)
    payload += _u32le(balance_bit)
    payload += _u16le(vmax * 1000)
    payload += _u16le(cells.index(vmax) + 1)
    payload += _u16le(vmin * 1000)
    payload += _u16le(cells.index(vmin) + 1)
    payload += _u16le((vmax - vmin) * 1000)
    payload += _u16le(sum(cells) / len(cells) * 1000)
    payload += _u16le(int(sum(cells)))
    payload += _u16le(int(sum(cells)))
    payload += _u16le(0)
    payload += _u16le(0)
    payload += _u16le(battery_type)
    payload += _u32le(all_dis_ah)
    payload += _u32le(all_ch_ah)
    payload += _u32le(dis_timer_s)
    payload += _u32le(ch_timer_s)
    payload += _u32le(0)
    payload += _u32le(0)
    payload += _u16le(ch_time_remain_min)
    payload += _u16le(dis_time_remain_min)

    frame = bytearray([0x7E, 0xA1, 0x11, 0x00, 0x00, len(payload)]) + payload
    crc = p.crc16(frame, 1, 5 + len(payload))
    frame += bytes([(crc >> 8) & 0xFF, crc & 0xFF, 0xAA, 0x55])
    return bytes(frame)


class DemoBattery:
    """A simulated 16S LiFePO4 pack cycling through charge and discharge."""

    CELLS = 16
    PERIOD = 120  # ticks per full charge/discharge cycle

    # Per-cell voltage offsets in mV: cell 11 is the "weak" one.
    OFFSETS = [4, -2, 1, 6, -1, 3, -3, 2, 5, -2, -14, 1, 4, -4, 2, -1]

    def frame(self, tick):
        phase = 2 * math.pi * (tick % self.PERIOD) / self.PERIOD
        current = -18.0 * math.sin(phase)  # <0 charging, >0 discharging
        charging = current < -0.5
        discharging = current > 0.5

        soc = 72 + 14 * math.cos(phase)
        base = 3.285 + 0.00055 * (soc - 70)
        sag = -current * 0.0009  # IR drop/rise with load
        cells = []
        for i in range(self.CELLS):
            v = base + self.OFFSETS[i] / 1000.0 + sag
            if discharging and i == 10:  # the weak cell sags harder
                v -= current * 0.0016
            cells.append(round(v, 3))

        vdiff = max(cells) - min(cells)
        balancing = charging and vdiff > 0.010
        load = abs(current)
        warnings = 0
        if charging:
            warnings |= 1 << 18  # battery_charging
        if discharging:
            warnings |= 1 << 19  # discharging
        warnings |= 1 << 23 | 1 << 24  # both MOS on
        if balancing:
            warnings |= 1 << 25 | 1 << 29  # balance_on, auto_balance
        if vdiff > 0.028:
            warnings |= 1 << 4  # cell_diff_warning
        if soc < 61:
            warnings |= 1 << 12  # soc_low_level1_warning

        if charging:
            state = 2
        elif discharging:
            state = 4
        else:
            state = 3

        pack_v = sum(cells)
        remain = 105.0 * soc / 100.0
        ch_remain = int((105.0 - remain) / 17.0 * 60) if charging else 0
        dis_remain = int(remain / max(load, 0.1) * 60) if discharging else 0

        return build_realtime_frame(
            cells,
            [24 + load * 0.15, 25 + load * 0.2, 23 + load * 0.1, 26 + load * 0.25],
            system_state=state,
            warning_mask=warnings,
            temp_mos=30 + load * 0.9,
            temp_balance=28 + (3 if balancing else 0),
            current=round(current, 1),
            soc=int(soc),
            soh=98,
            balance_state=4 if balancing else 0,
            balance_bit=0b0000010000100100 if balancing else 0,
            remain_ah=remain,
            power=int(pack_v * current),
            timer_s=86400 * 212 + tick,
            ch_time_remain_min=min(ch_remain, 65535),
            dis_time_remain_min=min(dis_remain, 65535),
        )

    def snapshot(self, tick):
        return p.decode_realtime(self.frame(tick))
