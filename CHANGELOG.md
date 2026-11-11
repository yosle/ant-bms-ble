# Changelog

## 0.1.0 — 2026-11-10

Initial public release.

- Complete specification of the ANT BMS BLE protocol (`PROTOCOL.md`, English;
  `PROTOCOL.es.md`, Spanish): new `7E A1` protocol with CRC-16/MODBUS, frame
  reassembly incl. the undocumented "Case C" extra section, real-time layout,
  ~90 named protection/warning bits, full parameter map (~200 registers),
  read-unlock authentication, and the legacy `AA 55` protocol as an appendix.
- `antbms` CLI: live TUI dashboard (`live`), hardware-free demo mode (`demo`),
  device identity (`info`), settings blocks (`params`), full config/state
  backup (`report`, with `--json`/`--md`), periodic data logger (`log`) and
  offline frame decoder (`decode`).
- Pure-Python decoder (`antbms.protocol`) with no dependencies, read-only by
  design: only read commands can ever be sent.
- Verified against real hardware (ANT-BLE22AAUB-YCE7, firmware
  22AAUB00-240510A), with captured frames in the test suite.
