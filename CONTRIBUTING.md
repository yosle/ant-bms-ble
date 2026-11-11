# Contributing

Thanks for helping document the ANT BMS protocol!

## The most valuable contribution: frames from your BMS

The spec is verified against one device (ANT-BLE22AAUB-YCE7). If you own a
different model or firmware, captures are gold:

1. Run `antbms live --plain --raw --seconds 10` and copy a few `RAW ...` lines.
2. Run `antbms info` and `antbms params --block version`.
3. Open an issue titled `Device report: <your model>` with the output and
   your device name / firmware string. Strip the pack id if you consider it
   sensitive.

If a field decodes wrong on your hardware, include the raw frame plus what the
official app shows — that is exactly how the quirks in PROTOCOL.md were found.

## Code

- Run the tests: `pip install -e .` then `python -m unittest discover -s tests -v`.
- The decoder (`src/antbms/protocol.py`) must stay pure Python with zero
  dependencies; `bleak`/`rich` are imported only by the CLI.
- This project is read-only by design: PRs that send write/control commands to
  the BMS will not be merged. Documenting write commands in PROTOCOL.md is
  welcome.
- `src/antbms/params.py` is generated: edit `tools/gen_params.py` and
  regenerate (requires the official APK in the repo root; it is never
  committed) instead of editing the file by hand.

## Spec changes

PROTOCOL.md (English) is the reference; please mirror meaningful changes in
PROTOCOL.es.md (Spanish) when you can, or note in the PR that the translation
needs a sync.
