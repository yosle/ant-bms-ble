"""ANT BMS protocol (read-only) — pure decoder, no BLE dependency.

Extracted from ANT_BMS 20240925.apk (uni-app bundle). See PROTOCOL.md.
"""

SERVICE_UUID = "0000ffe0-0000-1000-8000-00805f9b34fb"
CHAR_UUID = "0000ffe1-0000-1000-8000-00805f9b34fb"

# Read-only client: only these command codes may ever be sent.
# 0x01 real-time, 0x02 read parameter block, 0x04 read chip id, 0x05 read info.
READ_COMMANDS = {0x01, 0x02, 0x04, 0x05}

# Level-1 permission request. It only unlocks read access to the parameter
# blocks; it does NOT change any BMS setting. Sent only when explicitly asked.
AUTH_COMMAND = 0x23
AUTH_ADDR = 330
DEFAULT_PASSWORD = "12345678"

# CRC16 tables copied from the APK (utils/helper.js, module "80d5").
R = [
    0, 193, 129, 64, 1, 192, 128, 65, 1, 192, 128, 65, 0, 193, 129, 64,
    1, 192, 128, 65, 0, 193, 129, 64, 0, 193, 129, 64, 1, 192, 128, 65,
    1, 192, 128, 65, 0, 193, 129, 64, 0, 193, 129, 64, 1, 192, 128, 65,
    0, 193, 129, 64, 1, 192, 128, 65, 1, 192, 128, 65, 0, 193, 129, 64,
    1, 192, 128, 65, 0, 193, 129, 64, 0, 193, 129, 64, 1, 192, 128, 65,
    0, 193, 129, 64, 1, 192, 128, 65, 1, 192, 128, 65, 0, 193, 129, 64,
    0, 193, 129, 64, 1, 192, 128, 65, 1, 192, 128, 65, 0, 193, 129, 64,
    1, 192, 128, 65, 0, 193, 129, 64, 0, 193, 129, 64, 1, 192, 128, 65,
    1, 192, 128, 65, 0, 193, 129, 64, 0, 193, 129, 64, 1, 192, 128, 65,
    0, 193, 129, 64, 1, 192, 128, 65, 1, 192, 128, 65, 0, 193, 129, 64,
    0, 193, 129, 64, 1, 192, 128, 65, 1, 192, 128, 65, 0, 193, 129, 64,
    1, 192, 128, 65, 0, 193, 129, 64, 0, 193, 129, 64, 1, 192, 128, 65,
    0, 193, 129, 64, 1, 192, 128, 65, 1, 192, 128, 65, 0, 193, 129, 64,
    1, 192, 128, 65, 0, 193, 129, 64, 0, 193, 129, 64, 1, 192, 128, 65,
    1, 192, 128, 65, 0, 193, 129, 64, 0, 193, 129, 64, 1, 192, 128, 65,
    0, 193, 129, 64, 1, 192, 128, 65, 1, 192, 128, 65, 0, 193, 129, 64,
]

O = [
    0, 192, 193, 1, 195, 3, 2, 194, 198, 6, 7, 199, 5, 197, 196, 4,
    204, 12, 13, 205, 15, 207, 206, 14, 10, 202, 203, 11, 201, 9, 8, 200,
    216, 24, 25, 217, 27, 219, 218, 26, 30, 222, 223, 31, 221, 29, 28, 220,
    20, 212, 213, 21, 215, 23, 22, 214, 210, 18, 19, 211, 17, 209, 208, 16,
    240, 48, 49, 241, 51, 243, 242, 50, 54, 246, 247, 55, 245, 53, 52, 244,
    60, 252, 253, 61, 255, 63, 62, 254, 250, 58, 59, 251, 57, 249, 248, 56,
    40, 232, 233, 41, 235, 43, 42, 234, 238, 46, 47, 239, 45, 237, 236, 44,
    228, 36, 37, 229, 39, 231, 230, 38, 34, 226, 227, 35, 225, 33, 32, 224,
    160, 96, 97, 161, 99, 163, 162, 98, 102, 166, 167, 103, 165, 101, 100, 164,
    108, 172, 173, 109, 175, 111, 110, 174, 170, 106, 107, 171, 105, 169, 168, 104,
    120, 184, 185, 121, 187, 123, 122, 186, 190, 126, 127, 191, 125, 189, 188, 124,
    180, 116, 117, 181, 119, 183, 182, 118, 114, 178, 179, 115, 177, 113, 112, 176,
    80, 144, 145, 81, 147, 83, 82, 146, 150, 86, 87, 151, 85, 149, 148, 84,
    156, 92, 93, 157, 95, 159, 158, 94, 90, 154, 155, 91, 153, 89, 88, 152,
    136, 72, 73, 137, 75, 139, 138, 74, 78, 142, 143, 79, 141, 77, 76, 140,
    68, 132, 133, 69, 135, 71, 70, 134, 130, 66, 67, 131, 65, 129, 128, 64,
]

SYSTEM_STATE = {
    0: "none", 1: "idle", 2: "charge", 3: "standby", 4: "discharge", 5: "exception",
}

BATTERY_TYPE = {
    64241: "ternary", 64242: "LiFePO4", 64243: "LTO",
    64244: "custom", 64245: "none", 64246: "sodium",
}

DIS_MOS_STATE = [
    "close", "open", "cell_low_vol", "current_protect", "two_current_exceed",
    "all_undervoltage", "battery_exceed_temp", "power_exceed_temp",
    "current_exception", "balance_loose", "board_over_temp", "charge_open",
    "short_circuit_protect", "discharge_tube_exception", "open_failed",
    "manual_close", "discharge_2_low_vol", "low_temp_protect",
    "vol_diff_exceed", "self_detect_error",
]

CH_MOS_STATE = [
    "close", "open", "cell_over_vol", "current_protect", "battery_full",
    "total_vol_exceed", "battery_exceed_temp", "power_exceed_temp",
    "current_exception", "balance_loose", "board_over_temp", "open_failed",
    "discharge_tube_exception", "waiting", "manual_close", "two_level_exceed_vol",
    "low_temp_protect", "vol_diff_exceed", "self_detect_error",
]

BALANCE_STATE = [
    "close", "extreme_bal", "charge_vol_diff", "balance_exceed_temp",
    "auto_balance", "manual_balance",
]

PROTECT_BITS = [
    "set_cell_type", "cell_high_protect", "level2_cell_high_protect",
    "pack_volt_high_protect", "cell_low_protect", "level2_cell_low_protect",
    "pack_volt_low_protect", "cell_diff_protect", "charge_high_temp_protect",
    "discharge_high_temp_protect", "mos_high_temp_protect",
    "charge_low_temp_protect", "discharge_low_temp_protect",
    "charge_overcurrent_protect", "discharge_overcurrent_protect",
    "discharge_overcurrent2_protect", "short_circuit_protect",
    "manual_off_discharge_mos1", "manual_off_discharge_mos2",
    "manual_off_discharge_mos3", "manual_off_discharge_mos4",
    "manual_off_charge_mos1", "manual_off_charge_mos2",
    "manual_off_charge_mos3", "manual_off_charge_mos4", "open_line",
    "current_error", "dis_mos_error", "chg_mos_error", "internal_comm_error",
    "precharge_failure", "starting", "check1", "check2", "charger_connected",
    "dtu_lost_protect", "prevent_ignition", "check3", "please_upgrade_firmware",
    "relay_precharge_failed", "relay_adhesion", "abnormal_dischg_fuse",
    "abnormal_chg_fuse", "module_loss", "device_expiration",
]

WARNING_BITS = [
    "cell_high_warning", "pack_volt_high_warning", "cell_low_warning",
    "pack_volt_low_warning", "cell_diff_warning", "charge_high_temp_warning",
    "discharge_high_temp_warning", "charge_low_temp_warning",
    "discharge_low_temp_warning", "mos_high_temp_warning",
    "charge_overcurrent_warning", "discharge_overcurrent_warning",
    "soc_low_level1_warning", "soc_low_level2_warning", "cell_volt_check_wrong",
    "cell_number_wrong", "precharge_failure", "battery_full", "battery_charging",
    "discharging", "can_charger_in", "rs485_charger_in", "charger_in",
    "charge_mos_on", "discharge_mos_on", "balance_on", "sleep",
    "balance_limit", "balance_diff", "auto_balance", "balance_high_temp",
    "cell_pack_volt_related_protect", "temp_protect", "system_error", "dtu_lost",
    "balance_test", "electric_heating", "forcing_output", "bluetooth_off",
    "relay_precharging", "mos_precharging", "charging_relay_on",
    "discharge_relay_on", "xtal_error", "force_charging",
]


def crc16(buf, start, length):
    s = 0xFF
    n = 0xFF
    c = 0
    for _ in range(length):
        i = (s ^ buf[start + c]) & 0xFF
        s = (n ^ R[i]) & 0xFF
        n = O[i]
        c += 1
    return ((s << 8) | n) & 0xFFFF


def build_read_request(addr, length, cmd):
    if cmd not in READ_COMMANDS:
        raise ValueError(
            "refusing non-read command 0x%02X (this client is read-only)" % cmd
        )
    frame = [0x7E, 0xA1, cmd & 0xFF, addr & 0xFF, (addr >> 8) & 0xFF, length & 0xFF]
    crc = crc16(frame, 1, 5)
    frame += [(crc >> 8) & 0xFF, crc & 0xFF, 0xAA, 0x55]
    return bytes(frame)


def build_write_frame(addr, length, cmd, data):
    frame = [0x7E, 0xA1, cmd & 0xFF, addr & 0xFF, (addr >> 8) & 0xFF, length & 0xFF]
    frame += list(data[:length])
    crc = crc16(frame, 1, 5 + length)
    frame += [(crc >> 8) & 0xFF, crc & 0xFF, 0xAA, 0x55]
    return bytes(frame)


def build_auth_request(password=DEFAULT_PASSWORD):
    """Build the level-1 permission request (cmd 0x23).

    This only unlocks read access to the parameter blocks; it does not
    change any BMS parameter. Callers must opt in explicitly.
    """
    data = [ord(c) for c in password[:8]]
    data += [0] * (8 - len(data))
    return build_write_frame(AUTH_ADDR, 8, AUTH_COMMAND, data)


def find_frames(buffer):
    """Reassemble new-protocol frames from a byte stream.

    Mirrors the vendor app parser (AntProtocol_RxBufFindBmsPort):

      * cmd < 16  -> short frame, fixed 10 bytes, no payload.
      * cmd >= 16 -> long frame.  ``buf[5]`` is the payload length (r).
        Two layouts exist:
          Case B: header(6) + payload(r) + crc(2) + AA 55   -> 10+r bytes
          Case C: header(6) + payload(r) + crc(2) + extra(4+h)
                  + crc(2) + AA 55                         -> 16+r+h bytes
        where h = buf[11+r] is the length of the extra section payload.
        The CRC of the extra section covers bytes[8+r : 8+r+4+h].

    Returns (frames, remaining) where remaining is the unconsumed tail.
    """
    buf = bytearray(buffer)
    frames = []
    i = 0
    n = len(buf)

    def advance():
        nonlocal i, n
        i += 1
        n -= 1

    while n >= 10:
        if buf[i] != 0x7E or buf[i + 1] != 0xA1:
            advance()
            continue
        cmd = buf[i + 2]
        if cmd < 16:
            # Case A: short frame, 10 bytes, payload length 0.
            if buf[i + 8] != 0xAA or buf[i + 9] != 0x55:
                advance()
                continue
            if crc16(buf, i + 1, 5) != ((buf[i + 6] << 8) | buf[i + 7]):
                advance()
                continue
            total = 10
        else:
            r = buf[i + 5]
            if r > 192 or n < 10 + r:
                break
            if buf[i + 8 + r] == 0xAA and buf[i + 9 + r] == 0x55:
                # Case B: payload + crc + AA 55
                if crc16(buf, i + 1, 5 + r) != ((buf[i + 6 + r] << 8) |
                                                buf[i + 7 + r]):
                    advance()
                    continue
                total = 10 + r
            else:
                # Case C: payload + crc + extra section + crc + AA 55
                if n < 12 + r:
                    break
                h = buf[i + 11 + r]
                total = 16 + r + h
                if n < total:
                    break
                if buf[i + 14 + r + h] != 0xAA or buf[i + 15 + r + h] != 0x55:
                    advance()
                    continue
                if crc16(buf, i + 1, 5 + r) != ((buf[i + 6 + r] << 8) |
                                                buf[i + 7 + r]):
                    advance()
                    continue
                if crc16(buf, i + 8 + r, 4 + h) != ((buf[i + total - 4] << 8) |
                                                    buf[i + total - 3]):
                    advance()
                    continue
        frames.append(bytes(buf[i:i + total]))
        i += total
        n -= total
    return frames, bytes(buf[i:])


def frame_extra(frame):
    """Return the extra section of a Case C frame, or None.

    The section is 4 header bytes (header[0] is always 0xFF, header[3] is
    the data length h) followed by h data bytes.
    """
    b = frame
    if len(b) < 12 or b[2] < 16:
        return None
    r = b[5]
    if r > 192 or len(b) < 12 + r:
        return None
    if len(b) >= 10 + r and b[8 + r] == 0xAA and b[9 + r] == 0x55:
        return None
    h = b[11 + r]
    if len(b) < 16 + r + h:
        return None
    return {
        "header": list(b[8 + r:12 + r]),
        "data": list(b[12 + r:12 + r + h]),
    }


def unsign_to_sign(v):
    return v - 65536 if v > 32767.5 else v


def _u16le(b, o):
    return b[o] | (b[o + 1] << 8)


def _u32le(b, o):
    return b[o] | (b[o + 1] << 8) | (b[o + 2] << 16) | (b[o + 3] << 24)


def _u32le_signed(b, o):
    v = _u32le(b, o)
    return v - 0x100000000 if v > 0x7FFFFFFF else v


def _u16be(b, o):
    return (b[o] << 8) | b[o + 1]


def _u32be(b, o):
    return (b[o] << 24) | (b[o + 1] << 16) | (b[o + 2] << 8) | b[o + 3]


def _u32be_signed(b, o):
    v = _u32be(b, o)
    return v - 0x100000000 if v > 0x7FFFFFFF else v


def _bits(mask, mask1, names):
    out = []
    for bit in range(64):
        value = mask if bit < 32 else mask1
        if (value >> (bit % 32)) & 1:
            if bit < len(names):
                out.append(names[bit])
            else:
                out.append("bit%d" % bit)
    return out


def decode_realtime(frame):
    """Decode a new-protocol real-time response (cmd 0x11)."""
    b = frame
    if len(b) < 10 or b[0] != 0x7E or b[1] != 0xA1:
        raise ValueError("not a new-protocol frame")
    if b[2] != 0x11:
        raise ValueError("unexpected cmd 0x%02X, expected 0x11" % b[2])

    e = 6
    out = {}
    out["sysOperatingAut"] = b[e]; e += 1
    out["systemState"] = b[e]; e += 1
    temp_num = b[e]; e += 1
    cell_count = b[e]; e += 1
    out["temperatureNum"] = temp_num
    out["cellCount"] = cell_count
    out["protectMask"] = _u32le(b, e); e += 4
    out["protectMask1"] = _u32le(b, e); e += 4
    out["warningMask"] = _u32le(b, e); e += 4
    out["warningMask1"] = _u32le(b, e); e += 4
    e += 8  # reserved

    cells = []
    for _ in range(cell_count):
        cells.append(_u16le(b, e) / 1000.0); e += 2
    out["cellVoltages"] = cells

    temps = []
    for _ in range(temp_num):
        temps.append(unsign_to_sign(_u16le(b, e))); e += 2
    out["temperatures"] = temps

    out["temperatureMos"] = unsign_to_sign(_u16le(b, e)); e += 2
    out["temperatureBalance"] = unsign_to_sign(_u16le(b, e)); e += 2
    out["packVoltage"] = _u16le(b, e) / 100.0; e += 2
    out["current"] = unsign_to_sign(_u16le(b, e)) / 10.0; e += 2
    out["soc"] = _u16le(b, e); e += 2
    out["soh"] = _u16le(b, e); e += 2
    out["disMosState"] = b[e]; e += 1
    out["chMosState"] = b[e]; e += 1
    out["balanceState"] = _u16le(b, e); e += 2
    out["packPhysicsAh"] = _u32le(b, e) / 1e6; e += 4
    out["packRemainAh"] = _u32le(b, e) / 1e6; e += 4
    out["packAllAh"] = _u32le(b, e) / 1e3; e += 4
    out["packPower"] = _u32le_signed(b, e); e += 4
    out["allTimerS"] = _u32le(b, e); e += 4
    out["balanceStateBit"] = _u32le(b, e); e += 4
    out["cellVoltageMax"] = _u16le(b, e) / 1000.0; e += 2
    out["cellVoltageMaxPos"] = _u16le(b, e); e += 2
    out["cellVoltageMin"] = _u16le(b, e) / 1000.0; e += 2
    out["cellVoltageMinPos"] = _u16le(b, e); e += 2
    out["cellVoltageDiff"] = _u16le(b, e) / 1000.0; e += 2
    out["cellVoltageAvg"] = _u16le(b, e) / 1000.0; e += 2
    out["voltageDS"] = _u16le(b, e); e += 2
    out["voltageDisMos"] = _u16le(b, e); e += 2
    out["voltageChMos"] = _u16le(b, e); e += 2
    out["voltageNhMos"] = _u16le(b, e); e += 2
    out["batteryType"] = _u16le(b, e); e += 2
    out["packAllDisAh"] = _u32le(b, e); e += 4
    out["packAllChAh"] = _u32le(b, e); e += 4
    out["allDisTimerS"] = _u32le(b, e); e += 4
    out["allChTimerS"] = _u32le(b, e); e += 4

    if b[5] > 2 * temp_num + 2 * cell_count + 106 and e + 12 <= len(b):
        out["newChTime"] = _u32le(b, e); e += 4
        out["chTimeInterval"] = _u32le(b, e); e += 4
        out["chTimeRemain"] = _u16le(b, e); e += 2
        out["disTimeRemain"] = _u16le(b, e); e += 2

    out["systemStateName"] = SYSTEM_STATE.get(out["systemState"], str(out["systemState"]))
    out["batteryTypeName"] = BATTERY_TYPE.get(out["batteryType"], str(out["batteryType"]))
    out["disMosStateName"] = _name(DIS_MOS_STATE, out["disMosState"])
    out["chMosStateName"] = _name(CH_MOS_STATE, out["chMosState"])
    out["balanceStateName"] = _name(BALANCE_STATE, out["balanceState"])
    out["protections"] = _bits(out["protectMask"], out["protectMask1"], PROTECT_BITS)
    out["warnings"] = _bits(out["warningMask"], out["warningMask1"], WARNING_BITS)
    return out


def _name(table, index):
    return table[index] if 0 <= index < len(table) else str(index)


def decode_old(frame):
    """Decode an old-protocol real-time frame (starts with AA 55)."""
    b = frame
    if len(b) < 6 or b[0] != 0xAA or b[1] != 0x55:
        raise ValueError("not an old-protocol frame")
    checksum = (b[-2] << 8) | b[-1]
    if (sum(b[4:len(b) - 2]) & 0xFFFF) != checksum:
        raise ValueError("old-protocol checksum mismatch")

    e = 4
    out = {}
    out["packVoltage"] = _u16be(b, e) / 10.0; e += 2
    cells = []
    for _ in range(32):
        cells.append(_u16be(b, e) / 1000.0); e += 2
    out["cellVoltages"] = cells
    out["current"] = _u32be_signed(b, e) / 10.0; e += 4
    out["soc"] = b[e]; e += 1
    out["packPhysicsAh"] = _u32be(b, e) / 1e6; e += 4
    out["packRemainAh"] = _u32be(b, e) / 1e6; e += 4
    out["packAllAh"] = _u32be(b, e) / 1e3; e += 4
    out["allTimerS"] = _u32be(b, e); e += 4
    out["temperatureMos"] = unsign_to_sign(_u16be(b, e)); e += 2
    out["temperatureBalance"] = unsign_to_sign(_u16be(b, e)); e += 2
    temps = []
    for _ in range(4):
        temps.append(unsign_to_sign(_u16be(b, e))); e += 2
    out["temperatures"] = temps
    out["chMosState"] = b[e]; e += 1
    out["disMosState"] = b[e]; e += 1
    out["balanceState"] = b[e]; e += 1
    out["voltageDS"] = _u16be(b, e); e += 2
    out["voltageDisMos"] = _u16be(b, e); e += 2
    e += 1
    out["packPower"] = _u32be(b, e); e += 4
    out["cellVoltageMaxPos"] = b[e]; e += 1
    out["cellVoltageMax"] = _u16be(b, e) / 1000.0; e += 2
    out["cellVoltageMinPos"] = b[e]; e += 1
    out["cellVoltageMin"] = _u16be(b, e) / 1000.0; e += 2
    out["cellVoltageAvg"] = _u16be(b, e) / 1000.0; e += 2
    out["cellCount"] = b[e]; e += 1
    out["cellVoltages"] = out["cellVoltages"][:out["cellCount"]]
    return out


def _check_frame(frame, expected_cmd):
    b = frame
    if len(b) < 10 or b[0] != 0x7E or b[1] != 0xA1:
        raise ValueError("not a new-protocol frame")
    if b[2] != expected_cmd:
        raise ValueError(
            "unexpected cmd 0x%02X, expected 0x%02X" % (b[2], expected_cmd)
        )
    return b


def decode_params(frame):
    """Decode a parameter-block response (cmd 0x12).

    Returns {"startAddr", "length", "values": [(addr, u16), ...]}.
    """
    b = _check_frame(frame, 0x12)
    start_addr = b[3] | (b[4] << 8)
    length = b[5]
    values = []
    for i in range(0, length - 1, 2):
        values.append((start_addr + i, b[6 + i] | (b[7 + i] << 8)))
    return {"startAddr": start_addr, "length": length, "values": values}


def decode_chip_id(frame):
    """Decode a chip-id response (cmd 0x14)."""
    b = _check_frame(frame, 0x14)
    start_addr = b[3] | (b[4] << 8)
    count = b[5]
    data = list(b[6:6 + count])
    return {
        "startAddr": start_addr,
        "bytes": data,
        "id": ".".join(str(x) for x in data),
    }


def decode_info(frame):
    """Decode an info-block response (cmd 0x15). Returns raw bytes."""
    b = _check_frame(frame, 0x15)
    start_addr = b[3] | (b[4] << 8)
    length = b[5]
    return {"startAddr": start_addr, "length": length, "data": list(b[6:6 + length])}


def decode_auth(frame):
    """Decode a permission response (cmd 0x43). Returns the auth level."""
    b = _check_frame(frame, 0x43)
    return b[6] | (b[7] << 8)


def decode_extra(frame):
    """Interpret the extra section of a Case C frame.

    Empirically determined on a real BMS (ANT-BLE22AAUB-YCE7, firmware
    22AAUB00-240510A).  The section is a position/metadata trailer sent
    after the payload CRC:

      * ``header[0]`` is always 0xFF
      * ``header[1]`` is a status byte: 0x01 when data follows, 0x0B when
        the requested range falls outside the parameter area (and then
        there is no data at all)
      * ``header[3]`` is the length of the data (0 or 4 in practice)
      * ``data[0]`` is the low byte of the last parameter address served
      * ``data[1]`` is the index of the 32-byte page containing it
        (i.e. ``lastAddr >> 5``)
      * ``data[2]`` is a group id assigned by the BMS (3, 5 or 9)
      * ``data[3]`` is always 0

    The last served address is clamped by the BMS to the end of the
    parameter group, so it can be smaller than the end of the request.
    """
    extra = frame_extra(frame)
    if extra is None:
        return None
    b = frame
    start = b[3] | (b[4] << 8)
    length = b[5]
    requested_last = (start + length - 2) & ~1
    data = extra["data"]
    out = {
        "status": extra["header"][1],
        "groupId": data[2] if len(data) > 2 else None,
        "requestedLast": requested_last,
    }
    if len(data) >= 2:
        low = data[0]
        page = data[1]
        # lastAddr is in [page*32, page*32+32) and lastAddr & 0xFF == low
        last = low + 256 * ((page * 32 - low + 255) // 256)
        out["lastAddr"] = last
        out["page"] = page
        out["clamped"] = last != requested_last
    return out


def raw_payload(frame):
    """Return the payload bytes of a response frame (length = frame[5])."""
    return bytes(frame[6:6 + frame[5]])


def decode_ascii(data):
    """Decode a byte sequence as ASCII, skipping NUL/0xFF padding."""
    return "".join(chr(x) for x in data if x not in (0, 0xFF))
