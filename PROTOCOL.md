# ANT BMS Protocol — Specification (read-only)

> Versión en español: [PROTOCOL.es.md](PROTOCOL.es.md)

Specification of the BLE protocol spoken by the **ANT_BMS 20240925.apk** app,
extracted by static reverse engineering. Goal: implement a **read-only** client
(cell voltages, SOC, pack voltage, current, temperatures, etc.). Settings
write commands are documented for reference but not implemented.

Reference implementation in this repo (Python + `bleak`):

| File | Contents |
|---|---|
| `src/antbms/protocol.py` | CRC16, request builders, frame reassembly and decoders |
| `src/antbms/cli.py` | `antbms` CLI: `scan`, `live`, `demo`, `info`, `params`, `report`, `log`, `decode` |
| `src/antbms/params.py` | parameter map (186 entries, 11 blocks) |
| `src/antbms/params_full.json` | full dump of the map (every field) |
| `tools/gen_params.py` | map generator (reads the APK) |
| `tests/` | unit tests (no hardware) |

## Key findings at a glance

1. **Frame**: `7E A1 cmd addr_lo addr_hi len payload crc_hi crc_lo AA 55`,
   CRC16 over `bytes[1 .. 5+len]`. Long responses may carry an **extra
   section** between the CRC and the `AA 55` tail.
2. **Reads**: `cmd 0x01` → `0x11` (real time, every 500 ms),
   `cmd 0x02` → `0x12` (parameter blocks), `cmd 0x04` → `0x14` (chip ID),
   `cmd 0x05` → `0x15` (info).
3. **`0x02` does not return measurements** but **settings** (protection
   thresholds, IDs, identifiers). `0xFFFF` = parameter **not configured** on
   the pack, not a decoding error.
4. The **live values** (cell voltages, SOC, current, temperatures) only come
   through `cmd 0x11`.
5. The **extra section** is a position marker from the BMS (last served
   address + 32-byte page + group id). The app never uses it.
6. The BLE link is **fragile**: retry reads and split long blocks.

## Using the client

```bash
pip install ant-bms-ble

antbms scan                  # find packs (name starts with ANT-BLE)
antbms live                  # real time, TUI dashboard
antbms info                  # HW, SW, Pack ID, Chip ID, SysID2, info
antbms params --block voltage        # one parameter block
antbms params --block battery --auth # with the permission request
antbms decode <hex>          # decode a captured frame
```

Common options: `--address <MAC>` (skip scanning), `--name ANT-BLE`,
`--timeout`. Blocks available in `params --block`: `voltage`, `temperature`,
`current`, `balance`, `battery`, `system`, `other`, `customize`,
`manufacturer`, `sysid`, `version`.

> `params` **splits** blocks longer than 64 bytes and **retries** each read up
> to 4 times; with a weak BLE link some retries are normal.

## Where the data comes from

The app is a **uni-app (DCloud)** hybrid. All the BLE logic is readable
JavaScript inside the APK:

- `assets/apps/__UNI__8BF5A80/www/app-service.js`

Reference functions (names exactly as they appear in the bundle):

| Function | Role |
|---|---|
| `WriteData(addr, len, cmd, data)` | Builds a frame with payload |
| `ReadData(addr, len, cmd)` | Builds a read frame (no payload) |
| `CheckCrc16(buf, start, len)` | Frame CRC16 |
| `AntProtocol_RxBufFindBmsPort` | Reassembles and validates incoming frames |
| `jiexi(msg)` | Decodes the real-time response (new protocol) |
| `jiexi1(msg)` | Decodes the real-time response (old protocol) |
| `BatteryRread(msg)` | Decodes the parameter response (`cmd 0x12`) |
| `CheckAuth(msg)` | Decodes the permission response (`cmd 0x43`) |
| `UnsignToSign(v)` | Converts u16 to signed integer |
| `StrToLenUint8Array(s, n)` | String to ASCII bytes, zero-padded to `n` |
| `intToByteArray(v)` / `intTo4ByteArray(v)` | u16 / u32 little-endian |
| `Hourss(t)` | seconds → `Xd Xh Xm Xs` (remaining time) |
| `Hourmin(t)` | minutes → `Xd Xh Xm` (remaining time) |

> Note: decompiling `classes.dex` is not needed; the protocol lives in JS.

## BLE GATT

| Element | UUID |
|---|---|
| Service | `0000FFE0-0000-1000-8000-00805F9B34FB` |
| Characteristic (notify + write) | `0000FFE1-0000-1000-8000-00805F9B34FB` |

- Device name: starts with `ANT-BLE` (10 characters, or with `-` at index 10).
- Writes go to `FFE1` and data comes back as notifications on the same `FFE1`.
- The app sends the real-time request every **500 ms**.

### BLE connection (app parameters)

- After connecting, the app sets **MTU = 512** (`uni.setBLEMTU`).
- Writes use `writeType: "write"` (with response), not `writeNoResponse`.
- It discovers services/characteristics with `getBLEDeviceServices` /
  `getBLEDeviceCharacteristics` and subscribes with
  `notifyBLECharacteristicValueChange(state:true)`.
- It ranks devices by signal quality with
  `score = 10^((|RSSI| - 70) / 20)` and connects to the best one; it retries
  with a counter (`sum`). `SCMac` avoids reconnecting to the same device in a
  loop.

### Protocol selection (new vs old)

The app decides based on the device name:

- If `len(name) == 10` and it starts with `ANT-BLE`, **or** the character at
  index 10 is `-` and it starts with `ANT-BLE` → it shows a "use old
  protocol?" modal.
  - Confirm → `Ver = true` (**old protocol**).
  - Cancel → `Ver = false` (**new protocol**).
- In any other case → `Ver = false` (**new protocol**).

The new protocol is the main one and the one documented in detail. The old one
is in the appendix.

## Frame format (new protocol)

```
+------+------+------+---------+---------+------+-----------+-----------+------+------+
| 0x7E | 0xA1 | cmd  | addr_lo | addr_hi | len  | payload…  | crc_hi    | crc_lo    | 0xAA | 0x55 |
+------+------+------+---------+---------+------+-----------+-----------+------+------+
   [0]    [1]    [2]     [3]       [4]      [5]   [6..]      [6+len]     [7+len]    …     …
```

- `addr` is **little-endian** (`addr_lo` first).
- `len` = number of payload bytes.
- `crc` = CRC16 over `bytes[1 .. 5+len]` (starting at index 1, covering
  `5+len` bytes), stored **big-endian** at `[6+len]` (high) and `[7+len]`
  (low).
- Fixed tail `0xAA 0x55`.
- **Responses** with `cmd >= 0x10` may carry an *extra section* between the
  CRC and the `AA 55` tail; see "Long frame layout" in the `0x12` response
  section.

### Building requests

`ReadData(addr, len, cmd)`:

```
7E A1 cmd addr_lo addr_hi len crc_hi crc_lo AA 55
```

`WriteData(addr, len, cmd, data)`:

```
7E A1 cmd addr_lo addr_hi len data[0..len-1] crc_hi crc_lo AA 55
```

In both, the CRC is computed over `[1 .. 5+len]`.

## CRC16

Exact algorithm (init `0xFFFF`, two 256-byte tables, no final XOR):

```js
const R = [ /* table R, 256 bytes */ ];
const O = [ /* table O, 256 bytes */ ];

function crc16(buf, start, len) {
  let s = 0xFF, n = 0xFF, c = 0;
  while (len-- > 0) {
    const i = (s ^ buf[start + c]) & 0xFF;
    s = (n ^ R[i]) & 0xFF;
    n = O[i];
    c++;
  }
  return ((s << 8) | n) & 0xFFFF;
}
```

> The algorithm and both tables are the standard **CRC-16/MODBUS**
> (polynomial 0x8005 reflected, init 0xFFFF, no final XOR); the tables are the
> classic `auchCRCHi`/`auchCRCLo` pair from the Modbus specification, and the
> result is transmitted low-byte-first relative to the usual Modbus register
> order (see the verified example below).

### Tables (copied from the APK)

```js
const R = [
  0,193,129,64,1,192,128,65,1,192,128,65,0,193,129,64,1,192,128,65,0,193,129,64,
  0,193,129,64,1,192,128,65,1,192,128,65,0,193,129,64,0,193,129,64,1,192,128,65,
  0,193,129,64,1,192,128,65,1,192,128,65,0,193,129,64,1,192,128,65,0,193,129,64,
  0,193,129,64,1,192,128,65,0,193,129,64,1,192,128,65,1,192,128,65,0,193,129,64,
  0,193,129,64,1,192,128,65,1,192,128,65,0,193,129,64,1,192,128,65,0,193,129,64,
  0,193,129,64,1,192,128,65,1,192,128,65,0,193,129,64,0,193,129,64,1,192,128,65,
  0,193,129,64,1,192,128,65,1,192,128,65,0,193,129,64,0,193,129,64,1,192,128,65,
  1,192,128,65,0,193,129,64,1,192,128,65,0,193,129,64,0,193,129,64,1,192,128,65,
  0,193,129,64,1,192,128,65,1,192,128,65,0,193,129,64,1,192,128,65,0,193,129,64,
  0,193,129,64,1,192,128,65,1,192,128,65,0,193,129,64,0,193,129,64,1,192,128,65,
  0,193,129,64,1,192,128,65,1,192,128,65,0,193,129,64
];

const O = [
  0,192,193,1,195,3,2,194,198,6,7,199,5,197,196,4,204,12,13,205,15,207,206,14,
  10,202,203,11,201,9,8,200,216,24,25,217,27,219,218,26,30,222,223,31,221,29,28,
  220,20,212,213,21,215,23,22,214,210,18,19,211,17,209,208,16,240,48,49,241,51,
  243,242,50,54,246,247,55,245,53,52,244,60,252,253,61,255,63,62,254,250,58,59,
  251,57,249,248,56,40,232,233,41,235,43,42,234,238,46,47,239,45,237,236,44,228,
  36,37,229,39,231,230,38,34,226,227,35,225,33,32,224,160,96,97,161,99,163,162,
  98,102,166,167,103,165,101,100,164,108,172,173,109,175,111,110,174,170,106,107,
  171,105,169,168,104,120,184,185,121,187,123,122,186,190,126,127,191,125,189,188,
  124,180,116,117,181,119,183,182,118,114,178,179,115,177,113,112,176,80,144,145,
  81,147,83,82,146,150,86,87,151,85,149,148,84,156,92,93,157,95,159,158,94,90,
  154,155,91,153,89,88,152,136,72,73,137,75,139,138,74,78,142,143,79,141,77,76,
  140,68,132,133,69,135,71,70,134,130,66,67,131,65,129,128,64
];
```

### Verified example

Real-time request: `ReadData(0, 190, 0x01)`.

CRC over `[0xA1, 0x01, 0x00, 0x00, 0xBE]` = **`0x1855`**, matching the fixed
frame found in the APK:

```
7E A1 01 00 00 BE 18 55 AA 55
```

## Real-time request

Send every 500 ms:

```
7E A1 01 00 00 BE 18 55 AA 55
```

- `cmd = 0x01`, `addr = 0x0000`, `len = 0xBE` (190).
- The battery answers with `cmd = 0x11` (17). The payload is decoded with the
  table below.

## Decoding the `0x11` response (new protocol)

All offsets are **absolute from byte 0 of the frame** (the `0x7E`).
Multi-byte values are **little-endian**. `u16s` = signed u16
(`UnsignToSign`).

`UnsignToSign(v)`: if `v > 32767.5` then `v -= 65536`.

| Offset | Field | Type | Scale / notes |
|---|---|---|---|
| 6 | `sysOperatingAut` | u8 | permission level |
| 7 | `systemState` | u8 | see system state enum |
| 8 | `temperatureNum` | u8 | number of temperatures |
| 9 | `cellCount` | u8 | number of cells |
| 10 | `protectMask` | u32 | protection bits (see enum) |
| 14 | `protectMask1` | u32 | protection bits (2nd word) |
| 18 | `warningMask` | u32 | warning bits |
| 22 | `warningMask1` | u32 | warning bits (2nd word) |
| 26 | reserved | 8 bytes | ignore |
| 34 | `cellVoltages[cellCount]` | u16 × n | `/1000` → V |
| 34 + 2·n | `temperatures[temperatureNum]` | u16s × m | °C |
| … | `temperatureMos` | u16s | °C |
| … | `temperatureBalance` | u16s | °C |
| … | `packVoltage` | u16 | `/100` → V |
| … | `current` | u16s | `/10` → A (sign = charge/discharge) |
| … | `soc` | u16 | % |
| … | `soh` | u16 | % |
| … | `disMosState` | u8 | discharge MOS enum index |
| … | `chMosState` | u8 | charge MOS enum index |
| … | `balanceState` | u16 | balancing enum index |
| … | `packPhysicsAh` | u32 | `/1e6` → Ah |
| … | `packRemainAh` | u32 | `/1e6` → Ah |
| … | `packAllAh` | u32 | `/1e3` → Ah |
| … | `packPower` | i32 | power (W, signed) |
| … | `allTimerMs` | u32 | seconds |
| … | `balanceStateBit` | u32 | balancing bits |
| … | `cellVoltageMax` | u16 | `/1000` → V |
| … | `cellVoltageMaxPos` | u16 | cell index |
| … | `cellVoltageMin` | u16 | `/1000` → V |
| … | `cellVoltageMinPos` | u16 | cell index |
| … | `cellVoltageDiff` | u16 | `/1000` → V |
| … | `cellVoltageAvg` | u16 | `/1000` → V |
| … | `voltageDS` | u16 | V |
| … | `voltageDisMos` | u16 | V |
| … | `voltageChMos` | u16 | V |
| … | `voltageNhMos` | u16 | V |
| … | `batteryType` | u16 | see battery type enum |
| … | `packAllDisAh` | u32 | total Ah discharged |
| … | `packAllChAh` | u32 | total Ah charged |
| … | `allDisTimerS` | u32 | seconds |
| … | `allChTimerS` | u32 | seconds |
| … | `newChTime`* | u32 | seconds (conditional) |
| … | `chTimeInterval`* | u32 | seconds (conditional) |
| … | `chTimeRemain`* | u16 | minutes (conditional) |
| … | `disTimeRemain`* | u16 | minutes (conditional) |

\* The last four fields only exist if
`frame[5] > 2·temperatureNum + 2·cellCount + 106`.

> In the new protocol `cellVoltageDiff` is computed as `max - min` (not read
> from the frame), although the frame also carries a value.

> `packPower` is a **signed** 32-bit integer (the app reads it unsigned and
> shows absurd values; the real value is e.g. `-354` W while charging).
> `packAllAh`, `packAllDisAh` and `packAllChAh` are **lifetime accumulated
> counters** (not the current capacity); the current capacity is
> `packPhysicsAh`.

### Enums

**System state** (`systemState`, offset 7):

| Value | Meaning |
|---|---|
| 0 | none |
| 1 | idle |
| 2 | charging |
| 3 | standby |
| 4 | discharging |
| 5 | exception/fault |

**Battery type** (`batteryType`):

| Value | Type |
|---|---|
| 64241 | Ternary lithium |
| 64242 | LiFePO4 |
| 64243 | Lithium titanate (LTO) |
| 64244 | Custom |
| 64245 | None |
| 64246 | Sodium |

**Discharge MOS state** (`disMosState`):

| Index | Meaning |
|---|---|
| 0 | closed |
| 1 | open |
| 2 | cell undervoltage |
| 3 | current protection |
| 4 | overcurrent (2) |
| 5 | total undervoltage |
| 6 | battery temperature exceeded |
| 7 | power-stage temperature exceeded |
| 8 | abnormal current |
| 9 | balancing wire loose |
| 10 | board overheated |
| 11 | charger connected (charge open) |
| 12 | short-circuit protection |
| 13 | abnormal discharge tube |
| 14 | failed to open |
| 15 | manual close |
| 16 | undervoltage (2) |
| 17 | low-temperature protection |
| 18 | voltage difference exceeded |
| 19 | self-test error |

**Charge MOS state** (`chMosState`):

| Index | Meaning |
|---|---|
| 0 | closed |
| 1 | open |
| 2 | cell overvoltage |
| 3 | current protection |
| 4 | battery full |
| 5 | total voltage exceeded |
| 6 | battery temperature exceeded |
| 7 | power-stage temperature exceeded |
| 8 | abnormal current |
| 9 | balancing wire loose |
| 10 | board overheated |
| 11 | failed to open |
| 12 | abnormal discharge tube |
| 13 | waiting |
| 14 | manual close |
| 15 | level-2 overvoltage |
| 16 | low-temperature protection |
| 17 | voltage difference exceeded |
| 18 | self-test error |

**Balancing state** (`balanceState`):

| Index | Meaning |
|---|---|
| 0 | off |
| 1 | extreme balancing |
| 2 | voltage difference while charging |
| 3 | balancing temperature exceeded |
| 4 | automatic balancing |
| 5 | manual balancing |

**Protection bits** (`protectMask` + `protectMask1`, 64 bits):

| Bit | Meaning |
|---|---|
| 0 | cell type |
| 1 | cell overvoltage |
| 2 | cell overvoltage (level 2) |
| 3 | pack overvoltage |
| 4 | cell undervoltage |
| 5 | cell undervoltage (level 2) |
| 6 | pack undervoltage |
| 7 | cell difference |
| 8 | high temperature while charging |
| 9 | high temperature while discharging |
| 10 | MOS high temperature |
| 11 | low temperature while charging |
| 12 | low temperature while discharging |
| 13 | charge overcurrent |
| 14 | discharge overcurrent |
| 15 | discharge overcurrent (2) |
| 16 | short circuit |
| 17-20 | manual discharge MOS 1-4 off |
| 21-24 | manual charge MOS 1-4 off |
| 25 | open line |
| 26 | current error |
| 27 | discharge MOS error |
| 28 | charge MOS error |
| 29 | internal communication error |
| 30 | precharge failure |
| 31 | starting |
| 32 | check1 |
| 33 | check2 |
| 34 | charger connected |
| 35 | DTU lost |
| 36 | ignition prevention |
| 37 | check3 |
| 38 | firmware upgrade required |
| 39 | relay precharge failure |
| 40 | relay stuck |
| 41 | abnormal discharge/charge fuse |
| 42 | abnormal charge fuse |
| 43 | module loss |
| 44 | device expired |

**Warning bits** (`warningMask` + `warningMask1`, 64 bits):

| Bit | Meaning |
|---|---|
| 0 | cell overvoltage |
| 1 | pack overvoltage |
| 2 | cell undervoltage |
| 3 | pack undervoltage |
| 4 | cell difference |
| 5 | high temperature while charging |
| 6 | high temperature while discharging |
| 7 | low temperature while charging |
| 8 | low temperature while discharging |
| 9 | MOS high temperature |
| 10 | charge overcurrent |
| 11 | discharge overcurrent |
| 12 | SOC low, level 1 |
| 13 | SOC low, level 2 |
| 14 | wrong cell voltage |
| 15 | wrong cell count |
| 16 | precharge failure |
| 17 | battery full |
| 18 | charging |
| 19 | discharging |
| 20 | CAN charger input |
| 21 | RS485 charger input |
| 22 | charger input |
| 23 | charge MOS on |
| 24 | discharge MOS on |
| 25 | balancing on |
| 26 | sleep |
| 27 | balancing limit |
| 28 | balancing difference |
| 29 | automatic balancing |
| 30 | balancing high temperature |
| 31 | cell/pack voltage protection |
| 32 | temperature protection |
| 33 | system error |
| 34 | DTU lost |
| 35 | balancing test |
| 36 | electric heating |
| 37 | forced output |
| 38 | Bluetooth off |
| 39 | relay precharging |
| 40 | MOS precharging |
| 41 | charge relay on |
| 42 | discharge relay on |
| 43 | crystal (XTAL) error |
| 44 | forced charging |

## Remaining time (charge/discharge)

The BMS **sends the remaining time already computed** in the real-time frame
(`cmd 0x11`); the app does not derive it from capacity/current, it only
formats it. The fields are **conditional**: they only exist if

```
frame[5] > 2*temperatureNum + 2*cellCount + 106
```

and sit at the end of the payload, in this order:

| Field | Type | Unit | Format |
|---|---|---|---|
| `newChTime` (`NewCHtime`) | u32 | seconds | `Hourss` |
| `chTimeInterval` (`CHtimeintervar`) | u32 | seconds | `Hourss` |
| `chTimeRemain` (`CHtimeremain`) | u16 | **minutes** | `Hourmin` |
| `disTimeRemain` (`DIStimeremain`) | u16 | **minutes** | `Hourmin` |

- `chTimeRemain` = remaining **charge** time (min).
- `disTimeRemain` = remaining **discharge** time (min).
- `newChTime` / `chTimeInterval` = charging times in **seconds**.

### Formatting functions

`Hourss(t)` — seconds → `Xd Xh Xm Xs`:

```js
function Hourss(t) {
  let e = 0, a = 0, i = 0, s = parseInt(t);
  if (s > 60) { i = parseInt(s / 60); s = parseInt(s % 60); }
  if (i > 60) { a = parseInt(i / 60); i = parseInt(i % 60); }
  if (a > 24) { e = parseInt(a / 24); a = parseInt(a % 24); }
  return e > 0
    ? e + "d " + a + "h " + i + "m " + s + "s"
    : a + "h " + i + "m " + s + "s";
}
```

`Hourmin(t)` — minutes → `Xd Xh Xm`:

```js
function Hourmin(t) {
  let e = 0, a = 0, i = parseInt(t);
  if (i > 60) { a = parseInt(i / 60); i = parseInt(i % 60); }
  if (a > 24) { e = parseInt(a / 24); a = parseInt(a % 24); }
  return e > 0
    ? e + "d " + a + "h " + i + "m"
    : a + "h " + i + "m";
}
```

> **Quirk:** the comparisons use `> 60` (not `>= 60`), so exactly 60
> seconds/minutes render as `60s`/`60m` instead of `1m`/`1h`. Replicate it if
> you want exact parity with the app.

### Alternative calculation (when the BMS does not send the fields)

If `frame[5]` does not exceed the threshold (firmware without those fields), a
client can estimate from the snapshot's capacity and current:

- Discharging: `hours = packRemainAh / |current|`
- Charging: `hours = (packPhysicsAh - packRemainAh) / |current|`

Only valid with `|current| > 0`; at rest there is nothing to estimate. The app
does **not** use this formula: it shows `--` when the fields are absent.

## Additional read commands

Besides real time (`0x01` → `0x11`), the app uses these read commands. All
share the same frame format and CRC.

| Request | Response | Use |
|---|---|---|
| `ReadData(addr, len, 0x02)` | `cmd 0x12` | read a parameter block |
| `ReadData(addr, len, 0x04)` | `cmd 0x14` | read chip ID / SysID2 |
| `ReadData(addr, len, 0x05)` | `cmd 0x15` | read info block |

### `0x12` response (parameter block)

Same layout as the request: `addr` at `[3..4]`, `len` at `[5]`, and `len`
payload bytes at `[6..]` (little-endian u16 pairs). Each pair is a parameter
at `addr + i`.

#### Long frame layout (discovered on hardware, 2026-11)

Responses with `cmd >= 0x10` (in practice `0x11`, `0x12`, `0x14`, `0x15`,
`0x43`) come in **two possible layouts**. The app parser
(`AntProtocol_RxBufFindBmsPort`, `pagesBle/blueshebeidata/index.vue`) tells
them apart like this:

- **Case A — short frame** (`cmd < 16`): fixed 10 bytes, no payload.
  `header(6) + crc(2) + AA 55`. CRC over `[1..5]`.

- **Case B — plain long frame**: `header(6) + payload(r) + crc(2) + AA 55`,
  `10 + r` bytes total, where `r = frame[5]`.
  The CRC covers `frame[1 .. 5+r]` and sits at `frame[6+r..7+r]`.

- **Case C — long frame with extra section**:
  `header(6) + payload(r) + crc(2) + extra(4+h) + crc(2) + AA 55`,
  `16 + r + h` bytes total.
  - `h = frame[11+r]` (length of the extra data).
  - Extra header = `frame[8+r .. 11+r]`; byte `frame[11+r]` is `h`.
  - Extra data = `frame[12+r .. 12+r+h)`.
  - Extra CRC over `frame[8+r .. 8+r+4+h]`, located at `frame[p-4..p-3]`
    with `p = 16 + r + h`.
  - `AA 55` at `frame[p-2..p-1]`.

> **Important correction:** an earlier note in this document ("`0x12`
> responses do not end in `AA 55`") was **wrong**. What was being seen
> (`FF 01 00 04 …`) is the **Case C extra-section header**, not a corrupted
> tail. The frame always ends in `AA 55`; what changes is the total size.
> `find_frames()` in `src/antbms/protocol.py` implements all three cases.

Real frames captured from the `ANT-BLE22AAUB-YCE7` BMS:

| Case | addr | len | Total size | Extra |
|---|---|---|---|---|
| B/C | 620 | 32 | 48 | `FF 0B 00 00` + 0 bytes (`h=0`) |
| C | 0 | 52 | 72 | `FF 01 00 04` + `[32 01 03 00]` |
| C | 576 | 16 | 36 | `FF 01 00 04` + `[4E 12 09 00]` |
| C | 528 | 184 | 204 | `FF 01 00 04` + `[BA 15 05 00]` |

The first byte of the extra header is always `0xFF`; the second varies
(`0x01` for most blocks, `0x0B` when the range falls outside the parameter
area). The full decoding is in the next section.

#### Extra section, decoded (verified with sweeps)

The extra section is a **position/metadata marker** the BMS appends at the
end of the response. It decodes as follows (`decode_extra()` in
`src/antbms/protocol.py`):

| Byte | Meaning |
|---|---|
| `header[0]` | always `0xFF` |
| `header[1]` | status: `0x01` = data follows, `0x0B` = range outside the parameter area (and then there is **no** data: `h = 0`) |
| `header[2]` | always `0x00` |
| `header[3]` | length of the extra data (`h`) |
| `data[0]` | low byte of the **last parameter address served** |
| `data[1]` | index of the **32-byte page** containing it (`lastAddr >> 5`) |
| `data[2]` | group id assigned by the BMS (`3`, `5` or `9`) |
| `data[3]` | always `0x00` |

Empirically verified rules:

1. The served address is `start + len - 2` (the address of the last
   parameter), **aligned to a pair** (rounded down to a multiple of 2).
2. The BMS **clamps** the range to the end of the parameter group: requesting
   `(152, 142)` returns the battery group cut at address **260**, not 292.
   Same for `(216, 64)`, `(240, 54)` and `(256, 38)`.
3. `data[0]` = `lastAddr & 0xFF` and `data[1]` = `lastAddr >> 5` (so
   `lastAddr` reconstructs uniquely: it lies in `[page*32, page*32+32)`).
4. The value is **stable over time**: two reads of the same range 10 s apart
   return exactly the same extra section. It is not a clock.
5. If the requested range falls in a zone the firmware **does not
   implement**, the BMS answers with `header[1] = 0x0B` and `h = 0` (no extra
   data). With longer ranges the BMS may serve the zone partially and clamp
   it (e.g. `(592, 64)` is served with `lastAddr = 610`), so the response
   depends on the full range, not just the start.

Measured examples:

| Requested range | Served `lastAddr` | `page` | `groupId` |
|---|---|---|---|
| `(0, 8)` | 6 | 0 | 3 |
| `(0, 52)` | 50 | 1 | 3 |
| `(56, 44)` | 98 | 3 | 3 |
| `(104, 32)` | 134 | 4 | 3 |
| `(152, 64)` | 214 | 6 | 3 |
| `(152, 142)` | **260** (clamped) | 8 | 3 |
| `(300, 16)` | 314 | 9 | 5 |
| `(470, 32)` | 500 | 15 | 3 |
| `(576, 16)` | 590 | 18 | 9 |
| `(620, 32)` | — | — | status `0x0B`, no data |

> `groupId` is an internal firmware identifier; it can be used to tell which
> app group a range belongs to, but it is not needed to decode the values.


#### Why many blocks return `0xFFFF`

Blocks read with `cmd 0x02` are **not measurements, they are settings
(thresholds)** of the BMS. For example, block `addr=0` (52 bytes, 26
parameters) is:

```
0  cell_exceed_vol_protect      32 cell_exceed_vol_warning
2  cell_exceed_vol_recover      34 cell_exceed_vol_warning_recover
4  level2_exceed_vol_protect    36 packed_vol_exceed_warning
...                            ...
12 cell_lower_vol_protect       40 cell_lower_vol_warning
```

That is, voltage protection/warning limits, not the cell voltages (those come
through `cmd 0x11`, real time).

`0xFFFF` is what the BMS returns for **a parameter not configured** on that
pack. It is neither a decoding error nor missing permissions:

- The same BMS returns `0xFFFF` across the `voltage`, `temperature`,
  `current`, `balance`, `system`, `other` and `customize` blocks.
- It returns **real data** for `version` (620), `manufacturer` (528) and
  `battery` (152), which include ASCII strings (Pack ID, boot version, etc.).
- Authentication changes nothing: `WriteData(330|338|346|354|362, …, 0x23, …)`
  **always** answers level 1 with the known password; levels 2–5 use
  `pwd2`–`pwd5`, which the app leaves empty by default.

> Conclusion: the client is fine; the pack simply does not have those
> thresholds configured. The official app would show the same `0xFFFF`.

Known blocks (addr, len):

| Block | addr | len |
|---|---|---|
| voltage | 0 | 52 |
| temperature | 56 | 44 |
| current | 104 | 32 |
| balance | 140 | 12 |
| battery | 152 | 142 |
| system | 298 | 34 |
| other | 378 | 18 |
| pack_id | 262 | 32 |
| versions | 620 | 32 |
| customize | 470 | 32 |
| manufacturer | 528 | 184 |
| sysid | 576 | 16 |
| version | 636 | 16 |

#### BMS parameter area: gaps and clamping

Sweeping the address space reveals zones the BMS **does not have** (it
answers `0x0B`, no extra section, data all `0xFFFF`):

| Requested range | Response |
|---|---|
| `(268, 26)`, `(276, 18)`, `(280, 4…14)` | `0x0B` (gap after the battery group) |
| `(528, 8)`, `(536, 8)`, `(560, 8)`, `(568, 8)` | `0x0B` |
| `(592, 8)`, `(616, 8)` | `0x0B` |
| `(620, 8…32)`, `(636, 16)`, `(652, 8)`, `(660, 8)`, `(700, 8)` | `0x0B` |
| `(512, 8)`, `(520, 8)`, `(576, 8)`, `(584, 8)`, `(608, 8)` | served (`groupId = 9`) |

And zones where the BMS **clamps** the requested range to the end of the
group:

- the battery group ends at address **260**, so `(152, 142)`, `(216, 64)`,
  `(240, 54)` and `(256, 38)` all return the same position (260), even though
  the requested ranges differ.
- the `manufacturer` group clamps to `lastAddr = 590` with `(528, 64)`, to
  `610` with `(592, 64)` and to `698` with `(656, 56)`.

> Consequence: **reading a long block can return less data than requested**.
> Split the reads and check `lastAddr` in the extra section.
>
> It also means this firmware implements **fewer parameters than the app
> defines**: the `uart_*_baud_rate`, `CAN_baud_rate`, `function_config_*` and
> `bms_current_info` (592–607) and `verify_current_sensor`/`dtu_serial`
> (616–618) entries of the `manufacturer` block do not exist on the pack.
> Their names in the map cannot be validated with this hardware.



### `0x14` response (chip ID)

`addr` at `[3..4]`, `count` at `[5]`, `count` bytes at `[6..]`. Displayed as
dot-separated bytes. Used with `addr=0` (chip ID) and `addr=4096` (SysID2).

### `0x15` response (info block)

`addr` at `[3..4]`, `len` at `[5]`, `len` bytes at `[6..]`. Used with
`ReadData(0, 40, 0x05)`.

### Authentication `0x23` → `0x43`

The app unlocks parameter reads with `WriteData(330, 8, 0x23, pwd)`, where
`pwd` is 8 ASCII bytes (default password `12345678`). The response is
`cmd 0x43` with the permission level at `[6]` (low) and `[7]` (high).

```
Request:  7E A1 23 4A 01 08 31 32 33 34 35 36 37 38 DB 50 AA 55
Response: 7E A1 43 4A 01 02 <level_lo> <level_hi> <crc> AA 55
```

> Authentication **does not change any parameter**; it only enables reading
> the blocks. Even so, this client only sends it with an explicit `--auth`.

#### App flow (`request_version`, `pagesBle/components/bleIndex.vue`)

```js
request_version: function () {
  if (this.sysOperatingAut < 1) {
    var e = WriteData(330, 8, 35, StrToLenUint8Array(pwd1, 8));
    setTimeout(function () { sendBlebuff(e); }, 100);   // auth at 100 ms
  }
  setTimeout(function () { sendBlebuff(ReadData(620, 32, 2)); }, 200); // read at 200 ms
}
```

- The permission request goes out **100 ms** after connecting and the version
  read **200 ms** after (in parallel with the auth, not chained).
- `WriteData(330, 8, 35, …)`: the `35` is **0x23** written in decimal.
- Levels 2–5 use `WriteData(338|346|354, 8, 35, pwd)` and
  `WriteData(362, 12, 35, pwd)`, with `pwd2`…`pwd5` **empty** by default in
  the app. On this pack the BMS grants **level 1 always** with the known
  password, for all five addresses.

### Note: app parser bug

In `AntProtocol_RxBufFindBmsPort`, the **Case C** branch computes the size
`p = 16 + r + h` correctly, but advances the buffer with `iFAddress += 10 + r`
(instead of `p`). After a Case C frame the app is misaligned by `6 + h` bytes
and resynchronizes by searching for the next `7E A1`. Decoding is unaffected
because the parser skips the extra section anyway: **the app never uses the
extra section** — it is internal metadata from the BMS firmware.

## Write commands (reference and risk)

All use the same frame format. They are listed so you **know what NOT to
send**, and to document the few that are low risk.

### Low risk (documentable / implementable with care)

| Command | Frame | Effect | Risk |
|---|---|---|---|
| Level-1 auth | `WriteData(330,8,0x23,pwd)` | unlocks reads | none (changes nothing) |
| Save params | `WriteData(7,0,0x51,0)` | persists current values | low (if you changed nothing) |
| Battery ID | `WriteData(262,32,0x22,id)` | writes the battery ID | low (identifier only) |
| Passwords | `WriteData(330/338/346/354/362/374,8/12,0x22/0x23,pwd)` | changes level 1–5 passwords | low (credentials only) |

> "Save params" only re-writes what is already in RAM; it does not modify
> values by itself. It is still a write: use it only after an intentional
> change.

### High risk (do NOT implement without explicit intent)

**MOS control — `cmd 0x51`, `addr` = action, `len 0`:**

| addr | Action |
|---|---|
| 1 | close discharge (turn discharge MOS off) |
| 3 | open discharge (turn discharge MOS on) |
| 4 | close charge (turn charge MOS off) |
| 6 | open charge (turn charge MOS on) |
| 11 | stop |

**Factory reset — `cmd 0x53`, `addr 1`, `len 0`:** restores defaults.

**Parameter writes — `cmd 0x22`:**

| addr | len | Parameter |
|---|---|---|
| 0–150 | 2 | protection/warning thresholds (voltage, current, temperature) |
| 154 | 2 | cell count |
| 162 | 4 | physical capacity (Ah) |
| 262 | 32 | battery ID |
| 330–374 | 8/12 | level 1–5 passwords |

**Firmware — `cmd 0x51` addr 10 and `cmd 0x57` addr 61700:** firmware
upgrade. Never send.

> Rule of thumb: any `0x22` on addr < 262, any `0x51` with addr
> 1/3/4/6/10/11 and any `0x53`/`0x57` can alter behavior or cut the battery
> off. The read-only client never sends them.

## Current status (verified on hardware)

### Reference device

| Item | Value |
|---|---|
| Name | `ANT-BLE22AAUB-YCE7` |
| MAC | `D9:95:61:xx:xx:xx` |
| Observed RSSI | −92 … −99 dBm |
| Hardware version (620) | `22PHA1TB080A` |
| Software version (636 and 620) | `22AAUB00-240510A` |
| Boot version (528) | `BT22AAUB-240606A` |
| Pack ID / battery ID (262) | `220S031AH080V000…` (32 ASCII chars) |
| Chip ID (cmd 0x14, addr 0) | `232.252.248.…` (12 dot-separated bytes) |
| SysID2 (cmd 0x14, addr 4096) | `87.14.80.…` (12 dot-separated bytes) |
| Info block (cmd 0x15) | `0100010001000000000000000000000000000000000000000000c0041b0100000000010000000000` |
| Cells | 20 |
| Protection thresholds | **all unconfigured** (`0xFFFF`) |

> The MAC, Pack ID and chip serials are partially redacted: they identify
> this specific unit, not the model. Field lengths and formats are real.

### Status of each command

- `live` (real time, `cmd 0x11`): **works** (cells, SOC, pack, current,
  power, temperatures).
- `info` (versions, pack ID, chip ID, SysID2, info block): **works**.
- `params`: **works**. The *settings* blocks (voltage, temperature, current,
  balance, system, other, customize) return `0xFFFF` for every parameter
  because **they are not configured on the pack** (see "Why many blocks
  return 0xFFFF"). The `version` (620), `manufacturer` (528) and `battery`
  (152) blocks return **real data**, including ASCII strings.
- The `sysid` (576) and `version` (636) blocks read `0xFFFF`; the former is
  the "system check code" and the latter the user-facing version.
- Authentication `0x23`: the BMS grants **level 1** with `12345678`. Levels
  2–5 (addr 338/346/354/362) answer level 1 with any known password;
  `pwd2`–`pwd5` are empty in the app.
- Map coverage: 186 parameters across 11 blocks. The contents of the "gap"
  ranges (528–543, 560–575, 592–607, 616+) that this pack's firmware does not
  implement remain unmapped.


### BLE packet loss (important in practice)

The link to the pack is fragile (RSSI ≈ −93…−99 dBm). BLE notifications get
lost easily and a frame with missing bytes **fails the CRC**, so the frame
never shows up. The same 142-byte `battery` block was observed arriving as
144 bytes in one read and 162 in another.

That is why the client:

- retries every read up to 4 times (`_request(..., attempts=4)`),
- drops the reassembly buffer when a read times out (`reset_buffer()`), to
  avoid getting stuck on a corrupted header,
- requires `AA 55` **and** a valid CRC in `find_frames()`, instead of
  accepting frames on CRC alone,
- **splits** blocks longer than 64 bytes into 64-byte reads
  (`_read_block()`) and merges them: short frames reassemble far better than
  a burst of 8 notifications. The BMS is verified to accept arbitrary
  subranges (`ReadData(184, 32, 2)`, `ReadData(280, 14, 2)`, …).

The app's Android build forces MTU 512; on Windows the MTU negotiated by
WinRT is smaller and the peripheral still sends 20-byte notifications.

> Also, the pack **goes to sleep**: at the end of a long session it stopped
> advertising entirely and only came back later. If `scan` finds nothing, it
> is not a client bug.

### ASCII strings inside the blocks

Some blocks store text as little-endian u16 pairs. The `decode_ascii()`
helper (drops `0x00` and `0xFF`) extracts the text:

| Block | Offset | Contents | Actual value on this pack |
|---|---|---|---|
| `version` (636, 16) | 0–16 | software version | `22AAUB00-240510A` |
| `manufacturer` (528, 184) | 0–16 | boot version | `BT22AAUB-240606A` |
| `manufacturer` (528, 184) | 16–32 | check code (binary) | `—` |
| `battery` (152, 142) | 110–142 | Pack ID / battery ID | `220S031AH080V000…` (32 chars) |
| `version` (620, 32) | 0–16 / 16–32 | HW / SW version | `22PHA1TB080A` / `22AAUB00-240510A` |



## Parameter map (full extraction)

The app defines the parameters in `app-service.js` in several structures:

- **The 164-entry `param_list`** (the one carrying `startaddress`): fields
  `id`, `name` (Chinese), `startaddress` (real BMS address), `unit`,
  `iTimes` (scale), `decimal_len`, `datatype`, `value` (default).
  Covers addresses 0–326 (voltage, current, balancing, battery, SOC,
  internal resistances, battery ID, system).
- **The temperature page `dianta`** (ids 28–49): carries no `startaddress`;
  the address is `56 + 2*datatype` (block 56, 44 bytes). Ids 26,27,38,39,
  50,51 are reserved.
- **The system page `dianta`** (ids 149–164): addresses 298–328 (includes
  `Auto_OFF_Time` at 328).
- **The "other" page `dianta`** (ids 189–197): addresses 378–394.

The English names come from the `$t("...")` keys in the `dianta` arrays; the
main `param_list` only carries Chinese names.

### Generator

`tools/gen_params.py` reads the APK, merges the four sources and writes:

- `src/antbms/params.py` — `PARAM_BLOCKS`, `PARAM_MAP` (addr → name, iTimes,
  dec) and `PARAM_META` (unit, datatype, default, name_zh, id).
- `src/antbms/params_full.json` — full dump with every field.

Status: regenerated with **186 parameters** across 11 blocks. Decimals are
derived from `iTimes` when the APK omits them. **Validated on hardware**: the
`version` (636) and `manufacturer` (528) blocks return the expected ASCII
strings (`22AAUB00-240510A` and `BT22AAUB-240606A` respectively), confirming
the map's addresses and scales. `customize` (470) and `sysid` (576) return
`0xFFFF` on this pack; their names cannot be validated with this hardware.

### Extra read blocks (cmd 0x02)

| Block | addr | len | Contents |
|---|---|---|---|
| customize | 470 | 32 | custom parameters (no params defined in the app) |
| manufacturer | 528 | 184 | UART/CAN baud, function config, MAC, etc. (params 592–618 and 700–706 in `PARAM_MAP`; this firmware only implements 608–614) |
| sysid | 576 | 16 | system ID (returns `0xFFFF` on this pack) |
| version | 636 | 16 | version (ASCII: `22AAUB00-240510A`) |

> Note: the `customize.vue` page reads `ReadData(470,32,2)` but its `dianta`
> declares `startaddress` 378–388 (the "other" block); the app is
> inconsistent here and it is worth verifying on hardware.

### Fields of a parameter

Each `param_list` / `dianta` entry has:

| Field | Meaning |
|---|---|
| `id` | logical parameter index |
| `startaddress` | real BMS address (u16) |
| `name` | name (Chinese in `param_list`, `$t()` key in `dianta`) |
| `value` | default value |
| `input` | UI input value |
| `step` | edit increment |
| `iTimes` | scale: real value = `raw / iTimes` (`1e3`, `1e6`, `10`, `1`) |
| `decimal_len` | display decimals (sometimes `decimaLen`, a typo) |
| `unit` | unit (`V`, `A`, `AH`, `℃`, `MR`, `S`, `M`, `H`, `US`, `N`) |
| `datatype` | in `param_list` = 0 (u16); on the temperature page = block index |

> `iTimes` is the read scale: `raw / iTimes`. `decimal_len` is presentation
> only. When the APK omits `decimal_len`, it is derived from `iTimes`
> (`1e3→3`, `1e6→1`, `10→1`, `1→0`).

### Passwords (`qita`)

The app stores the level 1–5 passwords in the `qita` array:

| Level | addr | len |
|---|---|---|
| 1 | 330 | 8 |
| 2 | 338 | 8 |
| 3 | 346 | 8 |
| 4 | 354 | 8 |
| 5 | 362 | 12 |

They are written with `cmd 0x22` (change) or `cmd 0x23` (auth). The level-1
default is `12345678`.

### Device identifiers

| Field | Source |
|---|---|
| `SocId` | chip ID (cmd 0x14, addr 0), dot-separated string |
| `SysID2` | chip ID (cmd 0x14, addr 4096), dot-separated string |
| `SYS_Code_Key` | parameters (cmd 0x12, addr 288), dot-separated string |
| `gpsid` | `GpsId` (cloud ID) |
| `shebeiid` | user-entered device ID (cloud) |
| `xinpianid` | `dtuId` returned by the cloud |
| `Pack_Cell_Num` | cell count (real time, offset 9) |
| `Pack_Physics_AH` | physical capacity (real time, `packPhysicsAh`) |

### Cloud (reference, not BLE)

The app uses DCloud uniCloud and external services:

- `https://api.bspapp.com`, `https://api.next.bspapp.com` (uniCloud)
- `https://www.antbms.com`, `https://doc.antbms.com/web/`
- `https://www.mayibms.com/xieyi.html` (protocol documentation page)
- Maps: `apis.map.qq.com`, `apilocate.amap.com`
- OCR: `aip.baidubce.com`

### Firmware upgrade (high risk, do not use)

- `WriteData(10, 24, 0x51, data)`: upgrade command (16 bytes of the file at
  offset 2048 + 4 length bytes + …).
- `WriteData(61700, 24, 0x57, data)`: firmware block transfer.
- The `shengji.vue` page drives the process. **Never send** from a read-only
  client.

## Notes for Node.js / noble

- Write to the `FFE1` characteristic with `write` (the app uses
  `writeType:"write"`).
- Subscribe to `FFE1` notifications (`notify: true`) before sending.
- The app reassembles frames in a 1024-byte circular buffer and searches for
  the `7E A1` header; it validates `len`, CRC and the `AA 55` tail. Replicate
  that reassembly: BLE notifications can arrive fragmented.
- Send the `0x01` request every 500 ms; each `0x11` response is a complete
  real-time snapshot.
- For real time only the `0x01` request is needed. No parameter write
  commands are sent. Authentication (`cmd 0x23`) is optional and only unlocks
  reads; this client sends it only with `--auth`.
- The reassembler must implement the **three layouts** (Cases A/B/C): a
  Case C response does not end right after the payload CRC — it carries the
  extra section and its own CRC before the `AA 55` tail (see "Long frame
  layout").
- The default MTU may fragment; the app forces **MTU 512**. Adjust the MTU
  for your adapter or use write without response.
- Rank devices by `10^((|RSSI|-70)/20)` and connect to the best one.

## Appendix: old protocol (`Ver == 1`)

Frame:

```
AA 55 <b2> <b3> <data…> <sum_hi> <sum_lo>
```

- Checksum = sum of `bytes[4 .. len-3]` (16 bits), stored **big-endian** in
  the last two bytes.
- `b2`, `b3` are unused by the parser.
- Multi-byte values are **big-endian**.
- Decoded by `jiexi1`, starting at offset 4:

| Offset | Field | Type | Scale |
|---|---|---|---|
| 4 | `packVoltage` | u16 | `/10` → V |
| 6 | `cellVoltages[32]` | u16 × 32 | `/1000` → V (only `cellCount` are used) |
| 70 | `current` | u32s | `/10` → A |
| 74 | `soc` | u8 | % |
| 75 | `packPhysicsAh` | u32 | `/1e6` → Ah |
| 79 | `packRemainAh` | u32 | `/1e6` → Ah |
| 83 | `packAllAh` | u32 | `/1e3` → Ah |
| 87 | `allTimerMs` | u32 | seconds |
| 91 | `temperatureMos` | u16s | °C |
| 93 | `temperatureBalance` | u16s | °C |
| 95 | `temperatures[4]` | u16s × 4 | °C |
| 103 | `chMosState` | u8 | index |
| 104 | `disMosState` | u8 | index |
| 105 | `balanceState` | u8 | index |
| 106 | `voltageDS` | u16 | V |
| 108 | `voltageDisMos` | u16 | V |
| 110 | (1 ignored byte) | u8 | — |
| 111 | `packPower` | u32 | power |
| 115 | `cellVoltageMaxPos` | u8 | index |
| 116 | `cellVoltageMax` | u16 | `/1000` → V |
| 118 | `cellVoltageMinPos` | u8 | index |
| 119 | `cellVoltageMin` | u16 | `/1000` → V |
| 121 | `cellVoltageAvg` | u16 | `/1000` → V |
| 123 | `cellCount` | u8 | cell count |

> APK quirk: `jiexi1` reads `cellCount` at the end, so the first frame uses
> the previous value. For your own client, read `cellCount` from offset 123
> before interpreting the cells, or use the configured cell count.
