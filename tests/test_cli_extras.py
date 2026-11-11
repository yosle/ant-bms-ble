"""Tests for the demo generator, the report builder and the TUI renderer.

Everything here runs without hardware and without Bluetooth.
"""

import json
import unittest

from antbms import protocol as p
from antbms.demo import DemoBattery, build_realtime_frame
from antbms.report import build_report, decode_block_values, to_json, to_markdown


class TestDemoFrames(unittest.TestCase):
    def test_every_phase_decodes(self):
        battery = DemoBattery()
        for tick in (0, 15, 30, 45, 60, 75, 90, 105, 119, 120, 500):
            snap = battery.snapshot(tick)
            self.assertEqual(snap["cellCount"], 16)
            self.assertEqual(len(snap["cellVoltages"]), 16)
            self.assertEqual(len(snap["temperatures"]), 4)
            self.assertTrue(50.0 < snap["packVoltage"] < 56.0, snap["packVoltage"])
            self.assertTrue(0 <= snap["soc"] <= 100)
            self.assertEqual(snap["batteryTypeName"], "LiFePO4")

    def test_deterministic(self):
        self.assertEqual(DemoBattery().frame(42), DemoBattery().frame(42))

    def test_charge_and_discharge_phases_exist(self):
        battery = DemoBattery()
        states = {battery.snapshot(t)["systemStateName"] for t in range(120)}
        self.assertIn("charge", states)
        self.assertIn("discharge", states)

    def test_power_sign_matches_current(self):
        battery = DemoBattery()
        for tick in (20, 90):
            snap = battery.snapshot(tick)
            if snap["current"] < -1:
                self.assertLess(snap["packPower"], 0)
            elif snap["current"] > 1:
                self.assertGreater(snap["packPower"], 0)

    def test_reassembly_roundtrip(self):
        frame = DemoBattery().frame(7)
        frames, remaining = p.find_frames(b"\x00\x7e" + frame + frame[:6])
        self.assertEqual(frames, [frame])
        self.assertEqual(remaining, frame[:6])

    def test_builder_signed_values(self):
        frame = build_realtime_frame(
            [3.3] * 4, [25, -8], current=-12.3, power=-650)
        snap = p.decode_realtime(frame)
        self.assertAlmostEqual(snap["current"], -12.3, places=1)
        self.assertEqual(snap["packPower"], -650)
        self.assertEqual(snap["temperatures"], [25, -8])


class TestReport(unittest.TestCase):
    def _payload_voltage(self):
        # 52 bytes for the 'voltage' block: first value 3650 (-> 3.65 V),
        # the rest unset (0xFFFF).
        payload = bytearray([0x42, 0x0E])  # 3650 little-endian
        payload += b"\xff" * 50
        return bytes(payload)

    def test_decode_block_values(self):
        entries = decode_block_values("voltage", self._payload_voltage())
        self.assertEqual(entries[0]["addr"], 0)
        self.assertEqual(entries[0]["name"], "cell_exceed_vol_protect")
        self.assertAlmostEqual(entries[0]["value"], 3.65, places=3)
        self.assertIsNone(entries[1]["value"])
        self.assertEqual(entries[1]["raw"], 0xFFFF)

    def test_build_report_json_and_md(self):
        snapshot = DemoBattery().snapshot(90)
        report = build_report(
            {"hardware_version": "22PHA1TB080A",
             "software_version": "22AAUB00-240510A"},
            {"voltage": self._payload_voltage()},
            snapshot,
            version="0.1.0",
            now=0,
        )
        text = to_json(report)
        parsed = json.loads(text)
        self.assertEqual(parsed["device"]["software_version"], "22AAUB00-240510A")
        self.assertEqual(parsed["settings"]["voltage"][0]["value"], 3.65)
        self.assertEqual(parsed["realtime"]["cellCount"], 16)

        md = to_markdown(report)
        self.assertIn("# ANT BMS report", md)
        self.assertIn("cell_exceed_vol_protect", md)
        self.assertIn("22AAUB00-240510A", md)
        self.assertIn("not configured", md)


class TestUI(unittest.TestCase):
    @staticmethod
    def _console():
        import io

        from rich.console import Console

        return Console(record=True, width=100, force_terminal=True,
                       legacy_windows=False, file=io.StringIO())

    def test_render_smoke(self):
        from antbms.ui import render_snapshot

        console = self._console()
        console.print(render_snapshot(DemoBattery().snapshot(90), title="test"))
        text = console.export_text()
        self.assertIn("SOC", text)
        self.assertIn("16 cells", text)
        self.assertIn("DISCHARGE", text)

    def test_render_all_phases(self):
        from antbms.ui import render_snapshot

        console = self._console()
        for tick in range(0, 120, 10):
            console.print(render_snapshot(DemoBattery().snapshot(tick)))
        self.assertTrue(console.export_text())


if __name__ == "__main__":
    unittest.main(verbosity=2)
