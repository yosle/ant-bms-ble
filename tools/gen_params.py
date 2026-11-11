"""Generate src/antbms/params.py from the APK (read-only analysis).

Sources (all in app-service.js):
  * the 164-entry `param_list` that carries `startaddress` (Chinese names)
  * the temperature page `dianta` (ids 28-49 -> addresses 56-94)
  * the system page `dianta` (ids 149-164 -> addresses 298-328)
  * the "other" page `dianta` (ids 189-197 -> addresses 378-394)

English names come from the `$t()` keys in the page `dianta` arrays, falling
back to the names already present in the current params module.

The APK is NOT distributed with this repository. Obtain the official
"ANT_BMS 20240925.apk" yourself and place it in the repository root to
reproduce the extraction.

Writes src/antbms/params.py and src/antbms/params_full.json.

Run from anywhere: python tools/gen_params.py
"""

import json
import re
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
APK = ROOT / "ANT_BMS 20240925.apk"
JS = "assets/apps/__UNI__8BF5A80/www/app-service.js"
OUT_PY = ROOT / "src" / "antbms" / "params.py"
OUT_JSON = ROOT / "src" / "antbms" / "params_full.json"

EXTRA_BLOCKS = {
    "customize": {"addr": 470, "len": 32, "cmd": 2},
    "manufacturer": {"addr": 528, "len": 184, "cmd": 2},
    "sysid": {"addr": 576, "len": 16, "cmd": 2},
    "version": {"addr": 636, "len": 16, "cmd": 2},
}

EXTRA_NAMES = {}
for i in range(1, 17):
    EXTRA_NAMES[262 + 2 * (i - 1)] = "battery_id_%d" % i


def load_js():
    with zipfile.ZipFile(APK) as z:
        return z.read(JS).decode("utf-8", "replace")


def unescape(s):
    return re.sub(r"\\u([0-9a-fA-F]{4})", lambda m: chr(int(m.group(1), 16)), s)


def field(obj, key):
    m = re.search(key + r':("([^"]*)"|[^,}]*)', obj)
    if not m:
        return None
    if m.group(2) is not None:
        return unescape(m.group(2))
    return m.group(1)


def parse_main(js):
    idx = js.find("param_list:[")
    while idx != -1:
        end = js.find("]", idx)
        seg = js[idx:end]
        if "startaddress:" in seg:
            break
        idx = js.find("param_list:[", idx + 1)
    out = []
    for o in re.findall(r"\{[^{}]*\}", seg):
        out.append({
            "id": int(field(o, "id")),
            "name_zh": field(o, "name"),
            "startaddress": (int(field(o, "startaddress"))
                             if field(o, "startaddress") not in (None, "") else None),
            "unit": field(o, "unit") or "",
            "iTimes": field(o, "iTimes") or "1",
            "decimal_len": (int(field(o, "decimal_len"))
                            if field(o, "decimal_len") not in (None, "") else None),
            "datatype": int(field(o, "datatype") or 0),
            "default": field(o, "value") or "0",
        })
    return out


def parse_dianta(js, anchor, base_addr=None):
    """Parse a page `dianta` array into {address: {...}} using $t() names.

    When an entry has no `startaddress`, its address is base_addr + 2*datatype
    (the temperature page uses `datatype` as the block index).
    """
    i = js.find(anchor)
    if i < 0:
        return {}
    end = js.find("]", i)
    seg = js[i:end]
    out = {}
    for o in re.findall(r"\{[^{}]*\}", seg):
        datatype = int(field(o, "datatype") or 0)
        addr = field(o, "startaddress")
        if addr in (None, ""):
            if base_addr is None:
                continue
            addr = base_addr + 2 * datatype
        nm = re.search(r'name:((?:"[^"]*"|this\.\$t\("[^"]*"\)|\+|\d+)+)', o)
        raw_name = nm.group(1) if nm else (field(o, "name") or "")
        parts = re.findall(r'this\.\$t\("([^"]*)"\)|"([^"]*)"|(\d+)', raw_name)
        if parts:
            name = "_".join((a or b or c) for a, b, c in parts if (a or b or c))
        else:
            name = raw_name
        dec = field(o, "decimal_len")
        if dec in (None, ""):
            dec = field(o, "decimaLen")  # typo used by some pages
        out[int(addr)] = {
            "id": int(field(o, "id")),
            "name": name,
            "iTimes": field(o, "iTimes") or "1",
            "decimal_len": (int(dec) if dec not in (None, "") else None),
            "unit": field(o, "unit") or "",
            "datatype": datatype,
        }
    return out


def derive_decimals(itimes):
    return {"1e3": 3, "1e6": 1, "10": 1, "1": 0}.get(itimes, 0)


def load_old_names():
    try:
        sys.path.insert(0, str(ROOT / "src"))
        from antbms import params as old
        return {addr: v[0] for addr, v in old.PARAM_MAP.items()}
    except Exception:
        return {}


def main():
    js = load_js()
    main_params = parse_main(js)
    temp = parse_dianta(js, '{id:28,name:this.$t("battery_high_temp_charge_protect")',
                        base_addr=56)
    temp_by_id = {v["id"]: (v["name"], addr) for addr, v in temp.items()}
    system = parse_dianta(js, '{id:149,startaddress:298')
    other = parse_dianta(js, '{id:189,startaddress:378')
    manufacturer = parse_dianta(js, '{id:296,startaddress:592')
    old_names = load_old_names()

    combined = {}

    def put(addr, name, name_zh, itimes, dec, unit, datatype, default, pid):
        if dec is None:
            dec = derive_decimals(itimes)
        combined[addr] = {
            "id": pid, "name": name, "name_zh": name_zh,
            "iTimes": itimes, "decimal_len": dec, "unit": unit,
            "datatype": datatype, "default": default,
        }

    # Main param_list (Chinese names, authoritative addresses/scaling).
    for p in main_params:
        addr = p["startaddress"]
        if addr is None:
            if p["id"] in temp_by_id:
                name_en, addr = temp_by_id[p["id"]]
                put(addr, name_en, p["name_zh"], p["iTimes"], p["decimal_len"],
                    p["unit"], p["datatype"], p["default"], p["id"])
            continue
        name_en = old_names.get(addr) or EXTRA_NAMES.get(addr) or p["name_zh"]
        put(addr, name_en, p["name_zh"], p["iTimes"], p["decimal_len"],
            p["unit"], p["datatype"], p["default"], p["id"])

    # Page dianta arrays: fill missing addresses and enrich names/units.
    for src in (system, other, manufacturer):
        for addr, v in src.items():
            if addr in combined:
                combined[addr]["name"] = v["name"] or combined[addr]["name"]
                combined[addr]["unit"] = v["unit"] or combined[addr]["unit"]
                if v["decimal_len"] is not None:
                    combined[addr]["decimal_len"] = v["decimal_len"]
            else:
                put(addr, v["name"], "", v["iTimes"], v["decimal_len"],
                    v["unit"], v["datatype"], "0", v["id"])

    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump([dict(addr=a, **v) for a, v in sorted(combined.items())],
                  f, ensure_ascii=False, indent=1)

    lines = []
    lines.append('"""ANT BMS parameter map (read-only), extracted from the APK.')
    lines.append("")
    lines.append("Generated by gen_params.py from ANT_BMS 20240925.apk.")
    lines.append("PARAM_BLOCKS: block name -> {addr, len, cmd} for cmd 0x02 reads.")
    lines.append("PARAM_MAP: address -> (name, iTimes, decimal_len).")
    lines.append("PARAM_META: address -> {unit, datatype, default, name_zh, id}.")
    lines.append('"""')
    lines.append("")
    lines.append("PARAM_BLOCKS = {")
    for name, b in [
        ("voltage", {"addr": 0, "len": 52, "cmd": 2}),
        ("temperature", {"addr": 56, "len": 44, "cmd": 2}),
        ("current", {"addr": 104, "len": 32, "cmd": 2}),
        ("balance", {"addr": 140, "len": 12, "cmd": 2}),
        ("battery", {"addr": 152, "len": 142, "cmd": 2}),
        ("system", {"addr": 298, "len": 34, "cmd": 2}),
        ("other", {"addr": 378, "len": 18, "cmd": 2}),
    ] + list(EXTRA_BLOCKS.items()):
        lines.append("    %r: %r," % (name, b))
    lines.append("}")
    lines.append("")
    lines.append("PARAM_MAP = {")
    for addr in sorted(combined):
        v = combined[addr]
        lines.append("    %d: (%r, %r, %d)," % (addr, v["name"], v["iTimes"],
                                                v["decimal_len"]))
    lines.append("}")
    lines.append("")
    lines.append("PARAM_META = {")
    for addr in sorted(combined):
        v = combined[addr]
        lines.append(
            "    %d: {'unit': %r, 'datatype': %d, 'default': %r, "
            "'name_zh': %r, 'id': %d},"
            % (addr, v["unit"], v["datatype"], v["default"], v["name_zh"], v["id"]))
    lines.append("}")
    lines.append("")
    with open(OUT_PY, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print("wrote %s with %d params" % (OUT_PY, len(combined)))
    print("wrote %s" % OUT_JSON)


if __name__ == "__main__":
    main()
