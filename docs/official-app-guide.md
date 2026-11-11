# Using the official ANT BMS Android app

> Guía en español: [official-app-guide.es.md](official-app-guide.es.md)

The official app ships with **Chinese as the default language**, and a lot of
people never find the switch. This guide covers the handful of things most
users actually need: changing the language, connecting, reading the main
screen, and understanding the app's quirks.

> Written against app version **2.3.5 (build 20240925)** — the same APK this
> repository's [protocol spec](../PROTOCOL.md) was extracted from. The menu
> locations below were **verified by inspecting that APK's code**; they may
> move in other versions. The few things code inspection cannot confirm are
> marked **[VERIFY]**.
>
> This project is not affiliated with the ANT BMS vendor; this is independent
> user documentation.

## 1. Switching the language from Chinese to English

**Why it starts in Chinese:** the app only contains two languages, Simplified
Chinese and English. It follows your phone's system language — and for *any*
unsupported language (Spanish, French, …) it falls back to **Chinese**, not
English. That is why most non-English phones get a Chinese app.

**Where the switch is** (verified in the app code):

1. On the main screen, go to the **last section** (the settings/"more" list
   at the end — reached by the last tab or by swiping to the final page
   **[VERIFY]** which gesture your version uses).
2. Tap the row **切换语言** ("Switch language"). It sits in the same list as
   **切换版本** ("Switch versions") and the privacy-policy rows.
3. A page titled 切换语言 opens with exactly two options:
   **简体中文** (Simplified Chinese) and **English**. Tap **English**.
4. The choice takes effect immediately and is remembered.

Characters cheat-sheet:

| You see | It means |
|---|---|
| 切换语言 | Switch language |
| 简体中文 | Simplified Chinese |
| 切换版本 | Switch versions (app mode) |
| 绑定设备 | Bind device |

## 2. Connecting to your battery

1. Turn on Bluetooth and location (Android requires location permission for
   BLE scanning).
2. The battery advertises as **`ANT-BLE…`** (for example
   `ANT-BLE22AAUB-YCE7`). Pick it from the scan list.
3. **Old vs new protocol**: with some device names the app shows a dialog
   asking whether to use the *old protocol*.
   - Modern packs (longer names, like the example above) speak the **new**
     protocol — answer **No/Cancel**.
   - Only confirm "old protocol" if you own a legacy pack and the live data
     looks wrong with the new one.
4. Only **one device can be connected at a time** — BLE allows a single
   active connection to the BMS. If another phone (or a PC) is connected, the
   battery will not show up or will refuse to connect.
5. **Bluetooth mode vs cloud mode**: the app has separate modes (direct BLE,
   and an internet/cloud mode with login, maps and device binding). If you
   are being asked to log in or bind a device just to see your battery, you
   are in the wrong mode — use the **切换版本 / Switch versions** row in the
   same settings list as the language switch.

## 3. Reading the main screen

The live screen refreshes twice per second and shows, among other values:

- **SOC** (state of charge, %) and **SOH** (state of health, %).
- **Pack voltage, current and power.** Current sign tells the direction
  (charging vs discharging).
- **Per-cell voltages**, with the highest and lowest cell and their
  difference. On a healthy pack at rest the difference is small (tens of mV).
- **Temperatures** (battery sensors, MOSFET, balancer).
- **MOS states** (charge/discharge switches) and **balancing** state.
- **Remaining charge/discharge time**, when the firmware provides it — the
  app shows `--` when it does not.

## 4. The settings password

- The default level-1 password is **`12345678`**.
- Entering it only **unlocks reading/accessing the parameter pages**; it does
  not change anything by itself.
- Higher levels (2–5) exist for factory use and have no password set by
  default.
- **Be careful past this point**: the settings pages can write protection
  thresholds, cell count and capacity to the BMS. A wrong value can disable
  charging/discharging or mislead the protections. If you only want to
  *monitor* the battery, you never need to change a setting (that is what
  this repository's read-only tools are for).

## 5. Why settings pages look empty or strange

On many packs, most protection/warning thresholds are **not configured at the
factory**: the BMS stores `0xFFFF` ("no value") and the app renders that as
blank or as a nonsense number. This is normal and documented in detail in the
[protocol spec](../PROTOCOL.md#why-many-blocks-return-0xffff). It is not a
connection problem, and entering the password does not change it.

## 6. Known app bugs and quirks

Found while reverse engineering the app (details in the spec):

- **Absurd power while charging**: the app reads the power field as an
  unsigned number, so while charging it can display a huge bogus wattage.
  The real value is negative (e.g. `-354 W`). Voltage × current is the number
  to trust.
- **Old protocol, first frame**: the app reads the cell count *after* using
  it, so the very first readout after connecting can show the wrong number of
  cells for a moment.
- **Remaining time**: computed by the BMS, not the app. If your firmware does
  not send it, the app shows `--` forever — nothing to configure.

## 7. Connection troubleshooting

- **The pack goes to sleep**: after a while without activity it can stop
  advertising entirely. Wait for it to reappear, or wake the BMS by applying
  a brief charge or load **[VERIFY]**.
- **Weak link**: the BMS radio is not strong (our reference pack measured
  −92…−99 dBm from a few meters). Get closer; walls matter.
- **It never appears in the scan**: check that no other phone/PC is
  connected, that location permission is granted, and give the scan a couple
  of retries — the pack advertises intermittently.

## 8. The Windows app

ANT also distributes a Windows application with the same Chinese-first
interface and a harder-to-navigate layout. If you are comfortable with a
terminal, this repository's CLI is a simpler alternative on Windows:

```bash
pip install ant-bms-ble
antbms live      # live dashboard
antbms demo      # try it without a battery
```

A zero-install browser dashboard (Android & Windows, English/Spanish) is on
the [roadmap](../README.md#roadmap).
