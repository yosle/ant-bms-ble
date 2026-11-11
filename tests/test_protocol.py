"""Tests for the ANT BMS protocol decoder (no hardware, no BLE)."""

import unittest

from antbms import protocol as p


def u16le(v):
    v &= 0xFFFF
    return bytes([v & 0xFF, (v >> 8) & 0xFF])


def u32le(v):
    v &= 0xFFFFFFFF
    return bytes([v & 0xFF, (v >> 8) & 0xFF, (v >> 16) & 0xFF, (v >> 24) & 0xFF])


def u16be(v):
    v &= 0xFFFF
    return bytes([(v >> 8) & 0xFF, v & 0xFF])


def u32be(v):
    v &= 0xFFFFFFFF
    return bytes([(v >> 24) & 0xFF, (v >> 16) & 0xFF, (v >> 8) & 0xFF, v & 0xFF])


def build_realtime_frame(**kw):
    cells = kw.get("cells", [3.301, 3.302, 3.300, 3.303])
    temps = kw.get("temps", [25, -5])
    payload = bytearray()
    payload += bytes([kw.get("sysAut", 1), kw.get("systemState", 4),
                      len(temps), len(cells)])
    payload += u32le(kw.get("protectMask", 0))
    payload += u32le(kw.get("protectMask1", 0))
    payload += u32le(kw.get("warningMask", 0))
    payload += u32le(kw.get("warningMask1", 0))
    payload += bytes(8)
    for v in cells:
        payload += u16le(round(v * 1000))
    for t in temps:
        payload += u16le(t)
    payload += u16le(kw.get("tempMos", 30))
    payload += u16le(kw.get("tempBal", 28))
    payload += u16le(round(kw.get("packVoltage", 13.21) * 100))
    payload += u16le(round(kw.get("current", -12.3) * 10))
    payload += u16le(kw.get("soc", 87))
    payload += u16le(kw.get("soh", 99))
    payload += bytes([kw.get("disMos", 1), kw.get("chMos", 0)])
    payload += u16le(kw.get("balanceState", 4))
    payload += u32le(round(kw.get("physicsAh", 100.0) * 1e6))
    payload += u32le(round(kw.get("remainAh", 87.5) * 1e6))
    payload += u32le(round(kw.get("allAh", 100.0) * 1e3))
    payload += u32le(kw.get("power", 162))
    payload += u32le(kw.get("timer", 3600))
    payload += u32le(kw.get("balanceBit", 0))
    payload += u16le(round(kw.get("maxV", 3.303) * 1000))
    payload += u16le(kw.get("maxPos", 3))
    payload += u16le(round(kw.get("minV", 3.300) * 1000))
    payload += u16le(kw.get("minPos", 2))
    payload += u16le(round(kw.get("diff", 0.003) * 1000))
    payload += u16le(round(kw.get("avgV", 3.3015) * 1000))
    payload += u16le(kw.get("ds", 13))
    payload += u16le(kw.get("disMosV", 13))
    payload += u16le(kw.get("chMosV", 0))
    payload += u16le(kw.get("nhMosV", 0))
    payload += u16le(kw.get("batteryType", 64242))
    payload += u32le(kw.get("allDisAh", 1234))
    payload += u32le(kw.get("allChAh", 1200))
    payload += u32le(kw.get("disTimer", 100))
    payload += u32le(kw.get("chTimer", 200))
    if kw.get("with_remain"):
        payload += u32le(kw.get("newChTime", 3600))
        payload += u32le(kw.get("chTimeInterval", 60))
        payload += u16le(kw.get("chTimeRemain", 90))
        payload += u16le(kw.get("disTimeRemain", 120))

    length = len(payload)
    frame = bytearray([0x7E, 0xA1, 0x11, 0x00, 0x00, length]) + payload
    crc = p.crc16(frame, 1, 5 + length)
    frame += bytes([(crc >> 8) & 0xFF, crc & 0xFF, 0xAA, 0x55])
    return bytes(frame)


def build_old_frame(**kw):
    cells = kw.get("cells", [3.301, 3.302, 3.300, 3.303])
    data = bytearray()
    data += u16be(round(kw.get("packVoltage", 13.2) * 10))
    for i in range(32):
        data += u16be(round(cells[i] * 1000) if i < len(cells) else 0)
    data += u32be(round(kw.get("current", 5.0) * 10))
    data += bytes([kw.get("soc", 87)])
    data += u32be(round(kw.get("physicsAh", 100.0) * 1e6))
    data += u32be(round(kw.get("remainAh", 87.5) * 1e6))
    data += u32be(round(kw.get("allAh", 100.0) * 1e3))
    data += u32be(kw.get("timer", 3600))
    data += u16be(kw.get("tempMos", 30))
    data += u16be(kw.get("tempBal", 28))
    for t in kw.get("temps", [25, 24, 23, 22]):
        data += u16be(t)
    data += bytes([kw.get("chMos", 1), kw.get("disMos", 1),
                   kw.get("balanceState", 0)])
    data += u16be(kw.get("voltageDS", 13))
    data += u16be(kw.get("voltageDisMos", 13))
    data += bytes([0])
    data += u32be(kw.get("power", 66))
    data += bytes([kw.get("maxPos", 3)])
    data += u16be(round(kw.get("maxV", 3.303) * 1000))
    data += bytes([kw.get("minPos", 2)])
    data += u16be(round(kw.get("minV", 3.300) * 1000))
    data += u16be(round(kw.get("avgV", 3.3015) * 1000))
    data += bytes([len(cells)])

    frame = bytearray([0xAA, 0x55, 0x00, 0x00]) + data
    checksum = sum(data) & 0xFFFF
    frame += bytes([(checksum >> 8) & 0xFF, checksum & 0xFF])
    return bytes(frame)


def build_params_frame(addr, values):
    payload = bytearray()
    for v in values:
        payload += u16le(v)
    length = len(payload)
    frame = bytearray([0x7E, 0xA1, 0x12, addr & 0xFF, (addr >> 8) & 0xFF, length])
    frame += payload
    crc = p.crc16(frame, 1, 5 + length)
    frame += bytes([(crc >> 8) & 0xFF, crc & 0xFF, 0xAA, 0x55])
    return bytes(frame)


def build_case_c_frame(addr, payload, extra_data=(4, 8, 3, 0)):
    """Build a cmd 0x12 frame with the Case C layout (extra section)."""
    length = len(payload)
    frame = bytearray([0x7E, 0xA1, 0x12, addr & 0xFF, (addr >> 8) & 0xFF, length])
    frame += payload
    crc = p.crc16(frame, 1, 5 + length)
    frame += bytes([(crc >> 8) & 0xFF, crc & 0xFF])
    extra = bytearray([0xFF, 1, 0, len(extra_data)]) + bytearray(extra_data)
    frame += extra
    extra_crc = p.crc16(frame, 8 + length, 4 + len(extra_data))
    frame += bytes([(extra_crc >> 8) & 0xFF, extra_crc & 0xFF, 0xAA, 0x55])
    return bytes(frame)


def build_chip_frame(addr, data):
    length = len(data)
    frame = bytearray([0x7E, 0xA1, 0x14, addr & 0xFF, (addr >> 8) & 0xFF, length])
    frame += bytes(data)
    crc = p.crc16(frame, 1, 5 + length)
    frame += bytes([(crc >> 8) & 0xFF, crc & 0xFF, 0xAA, 0x55])
    return bytes(frame)


def build_auth_frame(level):
    payload = u16le(level)
    length = len(payload)
    frame = bytearray([0x7E, 0xA1, 0x43, 0x4A, 0x01, length])
    frame += payload
    crc = p.crc16(frame, 1, 5 + length)
    frame += bytes([(crc >> 8) & 0xFF, crc & 0xFF, 0xAA, 0x55])
    return bytes(frame)


class TestCrcAndRequests(unittest.TestCase):
    def test_crc_known_request(self):
        req = [0xA1, 0x01, 0x00, 0x00, 0xBE]
        self.assertEqual(p.crc16(req, 0, 5), 0x1855)

    def test_build_read_request(self):
        self.assertEqual(
            p.build_read_request(0, 190, 0x01),
            bytes([0x7E, 0xA1, 0x01, 0x00, 0x00, 0xBE, 0x18, 0x55, 0xAA, 0x55]),
        )

    def test_read_only_guard(self):
        for cmd in (0x22, 0x23, 0x26, 0x51, 0x53, 0x57, 0x61):
            with self.assertRaises(ValueError):
                p.build_read_request(0, 8, cmd)

    def test_read_commands_allowed(self):
        for cmd in (0x01, 0x02, 0x04, 0x05):
            p.build_read_request(0, 8, cmd)


class TestDecodeParams(unittest.TestCase):
    def test_params(self):
        frame = build_params_frame(0, [4200, 3500, 100])
        d = p.decode_params(frame)
        self.assertEqual(d["startAddr"], 0)
        self.assertEqual(d["length"], 6)
        self.assertEqual(d["values"], [(0, 4200), (2, 3500), (4, 100)])

    def test_params_offset(self):
        frame = build_params_frame(104, [500, 10])
        d = p.decode_params(frame)
        self.assertEqual(d["startAddr"], 104)
        self.assertEqual(d["values"], [(104, 500), (106, 10)])

    def test_wrong_cmd(self):
        with self.assertRaises(ValueError):
            p.decode_params(build_chip_frame(0, [1, 2]))


class TestManufacturerBlock(unittest.TestCase):
    def test_manufacturer_block(self):
        values = [0] * 92
        values[(592 - 528) // 2] = 9600   # uart_1_baud_rate
        values[(600 - 528) // 2] = 500    # CAN_baud_rate
        values[(612 - 528) // 2] = 3300   # verify_sys_base_vol
        values[(706 - 528) // 2] = 7      # ANTAddress
        frame = build_params_frame(528, values)
        d = p.decode_params(frame)
        self.assertEqual(d["startAddr"], 528)
        self.assertEqual(d["length"], 184)
        m = dict(d["values"])
        self.assertEqual(m[592], 9600)
        self.assertEqual(m[600], 500)
        self.assertEqual(m[612], 3300)
        self.assertEqual(m[706], 7)


class TestDecodeChipId(unittest.TestCase):
    def test_chip_id(self):
        frame = build_chip_frame(0, [1, 2, 3, 4])
        d = p.decode_chip_id(frame)
        self.assertEqual(d["startAddr"], 0)
        self.assertEqual(d["bytes"], [1, 2, 3, 4])
        self.assertEqual(d["id"], "1.2.3.4")

    def test_chip_id_4096(self):
        frame = build_chip_frame(4096, [10, 20])
        d = p.decode_chip_id(frame)
        self.assertEqual(d["startAddr"], 4096)
        self.assertEqual(d["id"], "10.20")


class TestAuth(unittest.TestCase):
    def test_build_auth_request(self):
        req = p.build_auth_request()
        self.assertEqual(req[:6], bytes([0x7E, 0xA1, 0x23, 0x4A, 0x01, 0x08]))
        self.assertEqual(req[6:14], b"12345678")
        self.assertEqual(req[14:16], bytes([0xDB, 0x50]))
        self.assertEqual(req[16:18], bytes([0xAA, 0x55]))

    def test_build_auth_request_custom(self):
        req = p.build_auth_request("abcdefgh")
        self.assertEqual(req[6:14], b"abcdefgh")

    def test_decode_auth(self):
        self.assertEqual(p.decode_auth(build_auth_frame(1)), 1)
        self.assertEqual(p.decode_auth(build_auth_frame(2)), 2)

    def test_decode_auth_wrong_cmd(self):
        with self.assertRaises(ValueError):
            p.decode_auth(build_chip_frame(0, [1, 2]))


class TestDecodeAscii(unittest.TestCase):
    def test_ascii(self):
        self.assertEqual(p.decode_ascii(b"ANT-BMS\x00\xff"), "ANT-BMS")
        self.assertEqual(p.decode_ascii(b"\x00\x00"), "")


class TestDecodeRealtime(unittest.TestCase):
    def setUp(self):
        self.frame = build_realtime_frame(
            protectMask=(1 << 1) | (1 << 16),
            warningMask=1 << 18,
        )
        self.s = p.decode_realtime(self.frame)

    def test_header(self):
        self.assertEqual(self.frame[0], 0x7E)
        self.assertEqual(self.frame[1], 0xA1)
        self.assertEqual(self.frame[2], 0x11)

    def test_cells(self):
        self.assertEqual(self.s["cellCount"], 4)
        self.assertEqual(self.s["cellVoltages"], [3.301, 3.302, 3.300, 3.303])

    def test_temperatures(self):
        self.assertEqual(self.s["temperatures"], [25, -5])
        self.assertEqual(self.s["temperatureMos"], 30)
        self.assertEqual(self.s["temperatureBalance"], 28)

    def test_pack_and_current(self):
        self.assertAlmostEqual(self.s["packVoltage"], 13.21, places=2)
        self.assertAlmostEqual(self.s["current"], -12.3, places=2)
        self.assertEqual(self.s["soc"], 87)
        self.assertEqual(self.s["soh"], 99)

    def test_capacity(self):
        self.assertAlmostEqual(self.s["packPhysicsAh"], 100.0, places=3)
        self.assertAlmostEqual(self.s["packRemainAh"], 87.5, places=3)
        self.assertAlmostEqual(self.s["packAllAh"], 100.0, places=3)
        self.assertEqual(self.s["packPower"], 162)

    def test_cell_stats(self):
        self.assertAlmostEqual(self.s["cellVoltageMax"], 3.303, places=3)
        self.assertEqual(self.s["cellVoltageMaxPos"], 3)
        self.assertAlmostEqual(self.s["cellVoltageMin"], 3.300, places=3)
        self.assertEqual(self.s["cellVoltageMinPos"], 2)
        self.assertAlmostEqual(self.s["cellVoltageDiff"], 0.003, places=3)
        self.assertAlmostEqual(self.s["cellVoltageAvg"], 3.3015, delta=0.001)

    def test_enums(self):
        self.assertEqual(self.s["systemStateName"], "discharge")
        self.assertEqual(self.s["batteryTypeName"], "LiFePO4")
        self.assertEqual(self.s["disMosStateName"], "open")
        self.assertEqual(self.s["chMosStateName"], "close")
        self.assertEqual(self.s["balanceStateName"], "auto_balance")

    def test_bits(self):
        self.assertIn("cell_high_protect", self.s["protections"])
        self.assertIn("short_circuit_protect", self.s["protections"])
        self.assertIn("battery_charging", self.s["warnings"])

    def test_negative_power(self):
        s = p.decode_realtime(build_realtime_frame(power=-353))
        self.assertEqual(s["packPower"], -353)

    def test_wrong_cmd(self):
        bad = bytearray(self.frame)
        bad[2] = 0x12
        with self.assertRaises(ValueError):
            p.decode_realtime(bytes(bad))

    def test_remaining_time(self):
        s = p.decode_realtime(build_realtime_frame(
            with_remain=True, newChTime=3600, chTimeInterval=60,
            chTimeRemain=90, disTimeRemain=120))
        self.assertEqual(s["newChTime"], 3600)
        self.assertEqual(s["chTimeInterval"], 60)
        self.assertEqual(s["chTimeRemain"], 90)
        self.assertEqual(s["disTimeRemain"], 120)

    def test_remaining_time_absent(self):
        s = p.decode_realtime(build_realtime_frame())
        self.assertNotIn("chTimeRemain", s)


class TestReassembly(unittest.TestCase):
    def test_split_frame(self):
        frame = build_realtime_frame()
        buffer = bytearray()
        frames = []
        for i in range(0, len(frame), 7):
            buffer.extend(frame[i:i + 7])
            got, remaining = p.find_frames(buffer)
            buffer = bytearray(remaining)
            frames.extend(got)
        self.assertEqual(len(frames), 1)
        self.assertEqual(frames[0], frame)
        self.assertEqual(len(buffer), 0)

    def test_garbage_prefix(self):
        frame = build_realtime_frame()
        got, remaining = p.find_frames(b"\x00\x11\x22" + frame)
        self.assertEqual(len(got), 1)
        self.assertEqual(got[0], frame)
        self.assertEqual(remaining, b"")

    def test_bad_crc_rejected(self):
        frame = bytearray(build_realtime_frame())
        frame[10] ^= 0xFF
        got, _ = p.find_frames(bytes(frame))
        self.assertEqual(got, [])


class TestDecodeOld(unittest.TestCase):
    def test_old_frame(self):
        frame = build_old_frame()
        s = p.decode_old(frame)
        self.assertAlmostEqual(s["packVoltage"], 13.2, places=1)
        self.assertEqual(s["cellCount"], 4)
        self.assertEqual(s["cellVoltages"], [3.301, 3.302, 3.300, 3.303])
        self.assertAlmostEqual(s["current"], 5.0, places=1)
        self.assertEqual(s["soc"], 87)
        self.assertEqual(s["temperatures"], [25, 24, 23, 22])
        self.assertAlmostEqual(s["cellVoltageMax"], 3.303, places=3)
        self.assertAlmostEqual(s["cellVoltageMin"], 3.300, places=3)

    def test_old_bad_checksum(self):
        frame = bytearray(build_old_frame())
        frame[-1] ^= 0xFF
        with self.assertRaises(ValueError):
            p.decode_old(bytes(frame))


class TestLongFrameLayout(unittest.TestCase):
    """Frames captured from a real BMS (ANT-BLE22AAUB-YCE7).

    cmd 0x12 responses come in two layouts:
      Case B: header + payload + crc + AA 55
      Case C: header + payload + crc + extra(4+h) + crc + AA 55
    """

    VERSION = ("7ea1126c02203232504841315442303830410000000032324141554230302d3234303531"
               "3041ede0ff0b000041f2aa55")
    VOLTAGE = ("7ea112000034" + "ff" * 52 + "49a7ff01000432010300b187aa55")
    SYSID = ("7ea112400210" + "ff" * 16 + "f1d3ff0100044e1209005f72aa55")

    def test_case_c_version_frame(self):
        frames, remaining = p.find_frames(bytearray.fromhex(self.VERSION))
        self.assertEqual(len(frames), 1)
        self.assertEqual(remaining, b"")
        self.assertEqual(len(frames[0]), 48)
        data = p.decode_params(frames[0])
        self.assertEqual(data["startAddr"], 620)
        self.assertEqual(data["length"], 32)
        raw = p.raw_payload(frames[0])
        self.assertEqual(p.decode_ascii(raw[0:16]), "22PHA1TB080A")
        self.assertEqual(p.decode_ascii(raw[16:32]), "22AAUB00-240510A")

    def test_case_c_voltage_frame(self):
        frames, remaining = p.find_frames(bytearray.fromhex(self.VOLTAGE))
        self.assertEqual(len(frames), 1)
        self.assertEqual(remaining, b"")
        self.assertEqual(len(frames[0]), 72)
        data = p.decode_params(frames[0])
        self.assertEqual(data["startAddr"], 0)
        self.assertEqual(data["length"], 52)
        self.assertEqual(len(data["values"]), 26)
        self.assertTrue(all(v == 0xFFFF for _, v in data["values"]))

    def test_case_c_extra_section(self):
        frames, _ = p.find_frames(bytearray.fromhex(self.VOLTAGE))
        extra = p.frame_extra(frames[0])
        self.assertEqual(extra["header"], [0xFF, 1, 0, 4])
        self.assertEqual(extra["data"], [50, 1, 3, 0])

    def test_decode_extra_last_address(self):
        frames, _ = p.find_frames(bytearray.fromhex(self.VOLTAGE))
        info = p.decode_extra(frames[0])
        self.assertEqual(info["status"], 1)
        self.assertEqual(info["groupId"], 3)
        self.assertEqual(info["lastAddr"], 50)
        self.assertEqual(info["page"], 1)
        self.assertFalse(info["clamped"])

    def test_decode_extra_clamped(self):
        # addr 152, len 142 -> requested last = 292, but the BMS clamps the
        # battery group at 260 (bytes 4, 8 -> page 8).
        payload = b"\xff" * 142
        frame = build_case_c_frame(152, payload, (4, 8, 3, 0))
        frames, remaining = p.find_frames(bytearray(frame))
        self.assertEqual(len(frames), 1)
        self.assertEqual(remaining, b"")
        info = p.decode_extra(frames[0])
        self.assertEqual(info["requestedLast"], 292)
        self.assertEqual(info["lastAddr"], 260)
        self.assertEqual(info["page"], 8)
        self.assertTrue(info["clamped"])

    def test_decode_extra_status_0x0b(self):
        frames, _ = p.find_frames(bytearray.fromhex(self.VERSION))
        info = p.decode_extra(frames[0])
        self.assertEqual(info["status"], 0x0B)
        self.assertIsNone(info.get("lastAddr"))

    def test_case_c_sysid_frame(self):
        frames, remaining = p.find_frames(bytearray.fromhex(self.SYSID))
        self.assertEqual(len(frames), 1)
        self.assertEqual(remaining, b"")
        self.assertEqual(len(frames[0]), 36)

    def test_case_b_no_extra(self):
        frame = build_params_frame(0, [1, 2, 3])
        frames, remaining = p.find_frames(bytearray(frame))
        self.assertEqual(len(frames), 1)
        self.assertEqual(remaining, b"")
        self.assertIsNone(p.frame_extra(frames[0]))

    def test_incomplete_frame_waits(self):
        raw = bytearray.fromhex(self.VOLTAGE)
        frames, remaining = p.find_frames(raw[:40])
        self.assertEqual(frames, [])
        self.assertEqual(len(remaining), 40)

    def test_corrupted_extra_crc_rejected(self):
        raw = bytearray.fromhex(self.VOLTAGE)
        raw[68] ^= 0xFF
        frames, _ = p.find_frames(bytes(raw))
        self.assertEqual(frames, [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
