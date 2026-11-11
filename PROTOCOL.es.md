# Protocolo ANT BMS — Especificación (solo lectura)

> English version: [PROTOCOL.md](PROTOCOL.md)

Especificación del protocolo BLE de la app **ANT_BMS 20240925.apk**, extraída por
ingeniería inversa estática. Objetivo: implementar un cliente de **solo lectura**
(voltajes de celda, SOC, voltaje de pack, corriente, temperaturas, etc.). No
cubre comandos de escritura de ajustes.

Implementación de referencia en este repo (Python + `bleak`):

| Archivo | Contenido |
|---|---|
| `src/antbms/protocol.py` | CRC16, construcción de peticiones, reensamblado y decodificadores |
| `src/antbms/cli.py` | CLI `antbms`: `scan`, `live`, `demo`, `info`, `params`, `report`, `log`, `decode` |
| `src/antbms/params.py` | mapa de parámetros (186 entradas, 11 bloques) |
| `src/antbms/params_full.json` | volcado completo del mapa (todos los campos) |
| `tools/gen_params.py` | generador del mapa a partir del APK |
| `tests/` | tests unitarios (sin hardware) |

## Resumen de los hallazgos clave

1. **Trama**: `7E A1 cmd addr_lo addr_hi len payload crc_hi crc_lo AA 55`, CRC16
   proprietary sobre `bytes[1 .. 5+len]`. Las respuestas largas pueden llevar una
   **sección extra** entre el CRC y la cola (`AA 55`).
2. **Lecturas**: `cmd 0x01` → `0x11` (tiempo real, cada 500 ms),
   `cmd 0x02` → `0x12` (bloques de parámetros), `cmd 0x04` → `0x14` (chip ID),
   `cmd 0x05` → `0x15` (info).
3. **`0x02` no devuelve mediciones**, sino **ajustes** (umbrales de protección,
   IDs, identificadores). `0xFFFF` = parámetro **no configurado** en el pack, no
   un error de decodificación.
4. Los **valores en vivo** (voltajes de celda, SOC, corriente, temperaturas) solo
   vienen por `cmd 0x11`.
5. La **sección extra** es un marcador de posición del BMS (última dirección
   servida + página de 32 bytes + id de grupo). No la usa la app.
6. El enlace BLE es **frágil**: hay que reintentar y trocear las lecturas largas.

## Uso del cliente

```bash
pip install ant-bms-ble

antbms scan                  # busca packs (nombre empieza por ANT-BLE)
antbms live                  # tiempo real, dashboard TUI
antbms info                  # HW, SW, Pack ID, Chip ID, SysID2, info
antbms params --block voltage        # un bloque de parámetros
antbms params --block battery --auth # con petición de permiso
antbms decode <hex>          # decodifica una trama capturada
```

Opciones comunes: `--address <MAC>` (no escanea), `--name ANT-BLE`, `--timeout`.
Los bloques disponibles en `params --block` son: `voltage`, `temperature`,
`current`, `balance`, `battery`, `system`, `other`, `customize`,
`manufacturer`, `sysid`, `version`.

> `params` **trocea** los bloques de más de 64 bytes y **reintenta** hasta 4
> veces cada lectura; con un enlace BLE débil es normal algún reintento.

## Origen de los datos

La app es un híbrido **uni-app (DCloud)**. Toda la lógica BLE está en JavaScript
legible dentro del APK:

- `assets/apps/__UNI__8BF5A80/www/app-service.js`

Funciones de referencia (nombres tal cual aparecen en el bundle):

| Función | Rol |
|---|---|
| `WriteData(addr, len, cmd, data)` | Construye una trama con payload |
| `ReadData(addr, len, cmd)` | Construye una trama de lectura (sin payload) |
| `CheckCrc16(buf, start, len)` | CRC16 de la trama |
| `AntProtocol_RxBufFindBmsPort` | Reensambla y valida tramas entrantes |
| `jiexi(msg)` | Decodifica la respuesta de tiempo real (protocolo nuevo) |
| `jiexi1(msg)` | Decodifica la respuesta de tiempo real (protocolo viejo) |
| `BatteryRread(msg)` | Decodifica la respuesta de parámetros (`cmd 0x12`) |
| `CheckAuth(msg)` | Decodifica la respuesta de permiso (`cmd 0x43`) |
| `UnsignToSign(v)` | Convierte u16 a entero con signo |
| `StrToLenUint8Array(s, n)` | Convierte string a bytes ASCII, rellena con 0 hasta `n` |
| `intToByteArray(v)` / `intTo4ByteArray(v)` | u16 / u32 little-endian |
| `Hourss(t)` | segundos → `Xd Xh Xm Xs` (tiempo restante) |
| `Hourmin(t)` | minutos → `Xd Xh Xm` (tiempo restante) |

> Nota: el APK no requiere decompilar `classes.dex`; el protocolo está en JS.

## BLE GATT

| Elemento | UUID |
|---|---|
| Servicio | `0000FFE0-0000-1000-8000-00805F9B34FB` |
| Característica (notify + write) | `0000FFE1-0000-1000-8000-00805F9B34FB` |

- Nombre de dispositivo: empieza por `ANT-BLE` (10 caracteres, o con `-` en el
  índice 10).
- Se escribe en `FFE1` y se recibe por notificación de la misma `FFE1`.
- La app envía la petición de tiempo real cada **500 ms**.

### Conexión BLE (parámetros de la app)

- Tras conectar, la app fija **MTU = 512** (`uni.setBLEMTU`).
- Escritura con `writeType: "write"` (con respuesta), no `writeNoResponse`.
- Descubre servicios/características con `getBLEDeviceServices` /
  `getBLEDeviceCharacteristics` y se suscribe con
  `notifyBLECharacteristicValueChange(state:true)`.
- Ordena los dispositivos por calidad de señal con
  `score = 10^((|RSSI| - 70) / 20)` y conecta al mejor; reintenta con un contador
  (`sum`). El `SCMac` evita reconectar al mismo dispositivo en bucle.

### Selección de protocolo (nuevo vs viejo)

La app decide según el nombre del dispositivo:

- Si `len(name) == 10` y empieza por `ANT-BLE`, **o** el carácter en el índice 10
  es `-` y empieza por `ANT-BLE` → muestra un modal "¿usar protocolo viejo?".
  - Confirmar → `Ver = true` (**protocolo viejo**).
  - Cancelar → `Ver = false` (**protocolo nuevo**).
- En cualquier otro caso → `Ver = false` (**protocolo nuevo**).

El protocolo nuevo es el principal y el que se documenta en detalle. El viejo
está en el apéndice.

## Formato de trama (protocolo nuevo)

```
+------+------+------+---------+---------+------+-----------+-----------+------+------+
| 0x7E | 0xA1 | cmd  | addr_lo | addr_hi | len  | payload…  | crc_hi    | crc_lo    | 0xAA | 0x55 |
+------+------+------+---------+---------+------+-----------+-----------+------+------+
   [0]    [1]    [2]     [3]       [4]      [5]   [6..]      [6+len]     [7+len]    …     …
```

- `addr` es **little-endian** (`addr_lo` primero).
- `len` = número de bytes de payload.
- `crc` = CRC16 sobre `bytes[1 .. 5+len]` (desde el índice 1, contando `5+len`
  bytes), almacenado **big-endian** en `[6+len]` (alto) y `[7+len]` (bajo).
- Cola fija `0xAA 0x55`.
- En las **respuestas** con `cmd >= 0x10` puede haber una *sección extra* entre
  el CRC y la cola `AA 55`; ver "Layout de trama larga" en la sección de
  respuestas `0x12`.

### Construcción de peticiones

`ReadData(addr, len, cmd)`:

```
7E A1 cmd addr_lo addr_hi len crc_hi crc_lo AA 55
```

`WriteData(addr, len, cmd, data)`:

```
7E A1 cmd addr_lo addr_hi len data[0..len-1] crc_hi crc_lo AA 55
```

En ambos, el CRC se calcula sobre `[1 .. 5+len]`.

## CRC16

Algoritmo exacto (init `0xFFFF`, dos tablas de 256, sin XOR final):

```js
const R = [ /* tabla R, 256 bytes */ ];
const O = [ /* tabla O, 256 bytes */ ];

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

### Tablas (copiadas del APK)

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

### Ejemplo verificado

Petición de tiempo real: `ReadData(0, 190, 0x01)`.

CRC sobre `[0xA1, 0x01, 0x00, 0x00, 0xBE]` = **`0x1855`**, que coincide con la
trama fija del APK:

```
7E A1 01 00 00 BE 18 55 AA 55
```

## Petición de tiempo real

Enviar cada 500 ms:

```
7E A1 01 00 00 BE 18 55 AA 55
```

- `cmd = 0x01`, `addr = 0x0000`, `len = 0xBE` (190).
- La batería responde con `cmd = 0x11` (17). El payload se decodifica con la
  tabla siguiente.

## Decodificación de la respuesta `0x11` (protocolo nuevo)

Todos los offsets son **absolutos desde el byte 0 de la trama** (el `0x7E`).
Multi-byte en **little-endian**. `u16s` = u16 con signo (`UnsignToSign`).

`UnsignToSign(v)`: si `v > 32767.5` entonces `v -= 65536`.

| Offset | Campo | Tipo | Escala / notas |
|---|---|---|---|
| 6 | `sysOperatingAut` | u8 | nivel de permiso |
| 7 | `systemState` | u8 | ver enum estado del sistema |
| 8 | `temperatureNum` | u8 | nº de temperaturas |
| 9 | `cellCount` | u8 | nº de celdas |
| 10 | `protectMask` | u32 | bits de protección (ver enum) |
| 14 | `protectMask1` | u32 | bits de protección (2ª palabra) |
| 18 | `warningMask` | u32 | bits de alarma |
| 22 | `warningMask1` | u32 | bits de alarma (2ª palabra) |
| 26 | reservado | 8 bytes | ignorar |
| 34 | `cellVoltages[cellCount]` | u16 × n | `/1000` → V |
| 34 + 2·n | `temperatures[temperatureNum]` | u16s × m | °C |
| … | `temperatureMos` | u16s | °C |
| … | `temperatureBalance` | u16s | °C |
| … | `packVoltage` | u16 | `/100` → V |
| … | `current` | u16s | `/10` → A (signo = carga/descarga) |
| … | `soc` | u16 | % |
| … | `soh` | u16 | % |
| … | `disMosState` | u8 | índice enum MOS descarga |
| … | `chMosState` | u8 | índice enum MOS carga |
| … | `balanceState` | u16 | índice enum balanceo |
| … | `packPhysicsAh` | u32 | `/1e6` → Ah |
| … | `packRemainAh` | u32 | `/1e6` → Ah |
| … | `packAllAh` | u32 | `/1e3` → Ah |
| … | `packPower` | i32 | potencia (W, con signo) |
| … | `allTimerMs` | u32 | segundos |
| … | `balanceStateBit` | u32 | bits de balanceo |
| … | `cellVoltageMax` | u16 | `/1000` → V |
| … | `cellVoltageMaxPos` | u16 | índice de celda |
| … | `cellVoltageMin` | u16 | `/1000` → V |
| … | `cellVoltageMinPos` | u16 | índice de celda |
| … | `cellVoltageDiff` | u16 | `/1000` → V |
| … | `cellVoltageAvg` | u16 | `/1000` → V |
| … | `voltageDS` | u16 | V |
| … | `voltageDisMos` | u16 | V |
| … | `voltageChMos` | u16 | V |
| … | `voltageNhMos` | u16 | V |
| … | `batteryType` | u16 | ver enum tipo de batería |
| … | `packAllDisAh` | u32 | Ah descargados totales |
| … | `packAllChAh` | u32 | Ah cargados totales |
| … | `allDisTimerS` | u32 | segundos |
| … | `allChTimerS` | u32 | segundos |
| … | `newChTime`* | u32 | segundos (condicional) |
| … | `chTimeInterval`* | u32 | segundos (condicional) |
| … | `chTimeRemain`* | u16 | minutos (condicional) |
| … | `disTimeRemain`* | u16 | minutos (condicional) |

\* Los cuatro últimos campos solo existen si
`frame[5] > 2·temperatureNum + 2·cellCount + 106`.

> `cellVoltageDiff` en el protocolo nuevo se calcula como
> `max - min` (no se lee del frame), aunque el frame también trae un valor.

> `packPower` es un entero **con signo** de 32 bits (la app lo lee sin signo y
> muestra valores absurdos; el valor real es p. ej. `-354` W al cargar).
> `packAllAh`, `packAllDisAh` y `packAllChAh` son **contadores acumulados de por
> vida** (no la capacidad actual); la capacidad actual está en `packPhysicsAh`.

### Enums

**Estado del sistema** (`systemState`, offset 7):

| Valor | Significado |
|---|---|
| 0 | ninguno |
| 1 | idle (reposo) |
| 2 | carga |
| 3 | standby |
| 4 | descarga |
| 5 | excepción/fallo |

**Tipo de batería** (`batteryType`):

| Valor | Tipo |
|---|---|
| 64241 | Litio ternario |
| 64242 | LiFePO4 |
| 64243 | Titanato de litio (LTO) |
| 64244 | Personalizada |
| 64245 | Ninguna |
| 64246 | Sodio |

**Estado MOS de descarga** (`disMosState`):

| Índice | Significado |
|---|---|
| 0 | cerrado |
| 1 | abierto |
| 2 | celda bajo voltaje |
| 3 | protección de corriente |
| 4 | exceso de corriente (2) |
| 5 | subtensión total |
| 6 | temperatura batería excedida |
| 7 | temperatura de potencia excedida |
| 8 | corriente anómala |
| 9 | balanceo suelto |
| 10 | placa sobrecalentada |
| 11 | carga abierta |
| 12 | protección cortocircuito |
| 13 | tubo de descarga anómalo |
| 14 | fallo de apertura |
| 15 | cierre manual |
| 16 | bajo voltaje (2) |
| 17 | protección baja temperatura |
| 18 | diferencia de voltaje excedida |
| 19 | error de autodiagnóstico |

**Estado MOS de carga** (`chMosState`):

| Índice | Significado |
|---|---|
| 0 | cerrado |
| 1 | abierto |
| 2 | celda sobre voltaje |
| 3 | protección de corriente |
| 4 | batería llena |
| 5 | voltaje total excedido |
| 6 | temperatura batería excedida |
| 7 | temperatura de potencia excedida |
| 8 | corriente anómala |
| 9 | balanceo suelto |
| 10 | placa sobrecalentada |
| 11 | fallo de apertura |
| 12 | tubo de descarga anómalo |
| 13 | en espera |
| 14 | cierre manual |
| 15 | sobre voltaje de 2º nivel |
| 16 | protección baja temperatura |
| 17 | diferencia de voltaje excedida |
| 18 | error de autodiagnóstico |

**Estado de balanceo** (`balanceState`):

| Índice | Significado |
|---|---|
| 0 | cerrado |
| 1 | balanceo extremo |
| 2 | diferencia de voltaje en carga |
| 3 | temperatura de balanceo excedida |
| 4 | balanceo automático |
| 5 | balanceo manual |

**Bits de protección** (`protectMask` + `protectMask1`, 64 bits):

| Bit | Significado |
|---|---|
| 0 | tipo de celda |
| 1 | sobre voltaje de celda |
| 2 | sobre voltaje de celda (2º nivel) |
| 3 | sobre voltaje de pack |
| 4 | bajo voltaje de celda |
| 5 | bajo voltaje de celda (2º nivel) |
| 6 | bajo voltaje de pack |
| 7 | diferencia de celdas |
| 8 | alta temperatura en carga |
| 9 | alta temperatura en descarga |
| 10 | alta temperatura MOS |
| 11 | baja temperatura en carga |
| 12 | baja temperatura en descarga |
| 13 | sobrecorriente de carga |
| 14 | sobrecorriente de descarga |
| 15 | sobrecorriente de descarga (2) |
| 16 | cortocircuito |
| 17-20 | apagado manual MOS descarga 1-4 |
| 21-24 | apagado manual MOS carga 1-4 |
| 25 | línea abierta |
| 26 | error de corriente |
| 27 | error MOS descarga |
| 28 | error MOS carga |
| 29 | error de comunicación interna |
| 30 | fallo de precarga |
| 31 | arrancando |
| 32 | check1 |
| 33 | check2 |
| 34 | cargador conectado |
| 35 | pérdida DTU |
| 36 | prevención de ignición |
| 37 | check3 |
| 38 | actualizar firmware |
| 39 | fallo precarga relé |
| 40 | relé pegado |
| 41 | fusible descarga/carga anómalo |
| 42 | fusible de carga anómalo |
| 43 | pérdida de módulo |
| 44 | dispositivo caducado |

**Bits de alarma** (`warningMask` + `warningMask1`, 64 bits):

| Bit | Significado |
|---|---|
| 0 | sobre voltaje de celda |
| 1 | sobre voltaje de pack |
| 2 | bajo voltaje de celda |
| 3 | bajo voltaje de pack |
| 4 | diferencia de celdas |
| 5 | alta temperatura en carga |
| 6 | alta temperatura en descarga |
| 7 | baja temperatura en carga |
| 8 | baja temperatura en descarga |
| 9 | alta temperatura MOS |
| 10 | sobrecorriente de carga |
| 11 | sobrecorriente de descarga |
| 12 | SOC bajo nivel 1 |
| 13 | SOC bajo nivel 2 |
| 14 | voltaje de celda incorrecto |
| 15 | número de celdas incorrecto |
| 16 | fallo de precarga |
| 17 | batería llena |
| 18 | cargando |
| 19 | descargando |
| 20 | entrada cargador CAN |
| 21 | entrada cargador RS485 |
| 22 | entrada cargador |
| 23 | MOS carga encendido |
| 24 | MOS descarga encendido |
| 25 | balanceo encendido |
| 26 | reposo (sleep) |
| 27 | límite de balanceo |
| 28 | diferencia de balanceo |
| 29 | balanceo automático |
| 30 | alta temperatura de balanceo |
| 31 | protección voltaje celda/pack |
| 32 | protección de temperatura |
| 33 | error de sistema |
| 34 | pérdida DTU |
| 35 | test de balanceo |
| 36 | calefacción eléctrica |
| 37 | salida forzada |
| 38 | Bluetooth apagado |
| 39 | precarga de relé |
| 40 | precarga MOS |
| 41 | relé de carga encendido |
| 42 | relé de descarga encendido |
| 43 | error de cristal (XTAL) |
| 44 | carga forzada |

## Tiempo restante (carga/descarga)

El BMS **envía el tiempo restante ya calculado** en la trama de tiempo real
(`cmd 0x11`); la app no lo calcula a partir de capacidad/corriente, solo lo
formatea. Los campos son **condicionales**: solo existen si

```
frame[5] > 2*temperatureNum + 2*cellCount + 106
```

y van al final del payload, en este orden:

| Campo | Tipo | Unidad | Formato |
|---|---|---|---|
| `newChTime` (`NewCHtime`) | u32 | segundos | `Hourss` |
| `chTimeInterval` (`CHtimeintervar`) | u32 | segundos | `Hourss` |
| `chTimeRemain` (`CHtimeremain`) | u16 | **minutos** | `Hourmin` |
| `disTimeRemain` (`DIStimeremain`) | u16 | **minutos** | `Hourmin` |

- `chTimeRemain` = tiempo restante de **carga** (min).
- `disTimeRemain` = tiempo restante de **descarga** (min).
- `newChTime` / `chTimeInterval` = tiempos de carga en **segundos**.

### Funciones de formato

`Hourss(t)` — segundos → `Xd Xh Xm Xs`:

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

`Hourmin(t)` — minutos → `Xd Xh Xm`:

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

> **Quirk:** las comparaciones usan `> 60` (no `>= 60`), así que exactamente 60
> segundos/minutos se muestran como `60s`/`60m` en vez de `1m`/`1h`. Replícalo si
> quieres paridad exacta con la app.

### Cálculo alternativo (si el BMS no envía los campos)

Si `frame[5]` no supera el umbral (firmware sin esos campos), un cliente puede
estimarlo con la capacidad y la corriente del snapshot:

- Descarga: `horas = packRemainAh / |current|`
- Carga: `horas = (packPhysicsAh - packRemainAh) / |current|`

Solo válido con `|current| > 0`; en reposo no hay tiempo estimable. La app **no**
usa esta fórmula: muestra `--` cuando los campos no vienen.

## Comandos de lectura adicionales

Además del tiempo real (`0x01` → `0x11`), la app usa estos comandos de lectura.
Todos comparten el mismo formato de trama y CRC.

| Petición | Respuesta | Uso |
|---|---|---|
| `ReadData(addr, len, 0x02)` | `cmd 0x12` | leer un bloque de parámetros |
| `ReadData(addr, len, 0x04)` | `cmd 0x14` | leer chip ID / SysID2 |
| `ReadData(addr, len, 0x05)` | `cmd 0x15` | leer bloque de información |

### Respuesta `0x12` (bloque de parámetros)

Mismo layout que la petición: `addr` en `[3..4]`, `len` en `[5]`, y `len` bytes de
payload en `[6..]` (pares u16 little-endian). Cada par es un parámetro en
`addr + i`.

#### Layout de trama larga (descubierto en hardware, 2026-11)

Las respuestas con `cmd >= 0x10` (realmente `0x11`, `0x12`, `0x14`, `0x15`,
`0x43`) tienen **dos layouts posibles**. El parser de la app
(`AntProtocol_RxBufFindBmsPort`, `pagesBle/blueshebeidata/index.vue`) los
distingue así:

- **Caso A — trama corta** (`cmd < 16`): 10 bytes fijos, sin payload.
  `header(6) + crc(2) + AA 55`. CRC sobre `[1..5]`.

- **Caso B — trama larga simple**: `header(6) + payload(r) + crc(2) + AA 55`,
  total `10 + r` bytes, donde `r = frame[5]`.
  El CRC cubre `frame[1 .. 5+r]` y está en `frame[6+r..7+r]`.

- **Caso C — trama larga con sección extra**:
  `header(6) + payload(r) + crc(2) + extra(4+h) + crc(2) + AA 55`,
  total `16 + r + h` bytes.
  - `h = frame[11+r]` (longitud de los datos extra).
  - Cabecera extra = `frame[8+r .. 11+r]`; el byte `frame[11+r]` es `h`.
  - Datos extra = `frame[12+r .. 12+r+h)`.
  - CRC extra sobre `frame[8+r .. 8+r+4+h]`, situado en `frame[p-4..p-3]`
    con `p = 16 + r + h`.
  - `AA 55` en `frame[p-2..p-1]`.

> **Corrección importante:** la nota anterior de este documento ("las respuestas
> `0x12` no terminan en `AA 55`") era **incorrecta**. Lo que se veía (`FF 01 00 04
> …`) es la **cabecera de la sección extra del Caso C**, no una cola corrupta.
> El frame siempre termina en `AA 55`; lo que cambia es el tamaño total.
> `find_frames()` en `protocol.py` implementa los tres casos.

Tramas reales capturadas del BMS `ANT-BLE22AAUB-YCE7`:

| Caso | addr | len | Tamaño total | Extra |
|---|---|---|---|---|
| B/C | 620 | 32 | 48 | `FF 0B 00 00` + 0 bytes (`h=0`) |
| C | 0 | 52 | 72 | `FF 01 00 04` + `[32 01 03 00]` |
| C | 576 | 16 | 36 | `FF 01 00 04` + `[4E 12 09 00]` |
| C | 528 | 184 | 204 | `FF 01 00 04` + `[BA 15 05 00]` |

El primer byte de la cabecera extra siempre es `0xFF`; el segundo varía
(`0x01` en la mayoría de bloques, `0x0B` cuando el rango cae fuera del área de
parámetros). La decodificación completa está en la sección siguiente.

#### Sección extra descifrada (verificado con barridos)

La sección extra es un **marcador de posición/metadata** que el BMS añade al
final de la respuesta. Se decodifica así (`decode_extra()` en `protocol.py`):

| Byte | Significado |
|---|---|
| `header[0]` | siempre `0xFF` |
| `header[1]` | estado: `0x01` = hay datos, `0x0B` = rango fuera del área de parámetros (y entonces **no** hay datos: `h = 0`) |
| `header[2]` | siempre `0x00` |
| `header[3]` | longitud de los datos extra (`h`) |
| `data[0]` | byte bajo de la **última dirección de parámetro servida** |
| `data[1]` | índice de la **página de 32 bytes** que la contiene (`lastAddr >> 5`) |
| `data[2]` | id de grupo asignado por el BMS (`3`, `5` o `9`) |
| `data[3]` | siempre `0x00` |

Reglas comprobadas empíricamente:

1. La dirección servida es `start + len - 2` (la dirección del último
   parámetro), **alineada a un par** (se redondea hacia abajo a múltiplo de 2).
2. El BMS **recorta** el rango al final del grupo de parámetros: pedir
   `(152, 142)` devuelve el grupo de batería cortado en la dirección **260**, no
   292. Lo mismo con `(216, 64)`, `(240, 54)` y `(256, 38)`.
3. `data[0]` = `lastAddr & 0xFF` y `data[1]` = `lastAddr >> 5` (con lo que
   `lastAddr` se reconstruye de forma única: está en `[page*32, page*32+32)`).
4. El valor es **estable en el tiempo**: dos lecturas del mismo rango separadas
   10 s dan exactamente la misma sección extra. No es un reloj.
5. Si el rango pedido cae en una zona que el firmware **no implementa**, el BMS
   responde con `header[1] = 0x0B` y `h = 0` (sin datos extra). Con rangos más
   largos el BMS puede servir la zona parcialmente y recortarla
   (p. ej. `(592, 64)` se sirve con `lastAddr = 610`), así que la respuesta
   depende del rango completo, no solo del inicio.

Ejemplos medidos:

| Rango pedido | `lastAddr` servido | `page` | `groupId` |
|---|---|---|---|
| `(0, 8)` | 6 | 0 | 3 |
| `(0, 52)` | 50 | 1 | 3 |
| `(56, 44)` | 98 | 3 | 3 |
| `(104, 32)` | 134 | 4 | 3 |
| `(152, 64)` | 214 | 6 | 3 |
| `(152, 142)` | **260** (recortado) | 8 | 3 |
| `(300, 16)` | 314 | 9 | 5 |
| `(470, 32)` | 500 | 15 | 3 |
| `(576, 16)` | 590 | 18 | 9 |
| `(620, 32)` | — | — | estado `0x0B`, sin datos |

> `groupId` es un identificador interno del firmware; se puede usar para
> saber a qué grupo de la app pertenece un rango, pero no hace falta para
> decodificar los valores.


#### Por qué muchos bloques devuelven `0xFFFF`

Los bloques leídos con `cmd 0x02` **no son mediciones, son ajustes (umbrales)**
del BMS. Por ejemplo, el bloque `addr=0` (52 bytes, 26 parámetros) es:

```
0  cell_exceed_vol_protect      32 cell_exceed_vol_warning
2  cell_exceed_vol_recover      34 cell_exceed_vol_warning_recover
4  level2_exceed_vol_protect    36 packed_vol_exceed_warning
...                            ...
12 cell_lower_vol_protect       40 cell_lower_vol_warning
```

Es decir, límites de protección/advertencia de voltaje, no los voltajes de las
celdas (que llegan por `cmd 0x11`, tiempo real).

`0xFFFF` es el valor que el BMS devuelve para **un parámetro no configurado** en
ese pack. No es un error de decodificación ni falta de permisos:

- El mismo BMS devuelve `0xFFFF` en los bloques de `voltage`, `temperature`,
  `current`, `balance`, `system`, `other` y `customize`.
- Devuelve **datos reales** en `version` (620), `manufacturer` (528) y `battery`
  (152), que incluyen cadenas ASCII (Pack ID, versión de boot, etc.).
- La autenticación no cambia nada: `WriteData(330|338|346|354|362, …, 0x23, …)`
  responde **siempre nivel 1** con la contraseña conocida; los niveles 2–5 usan
  `pwd2`–`pwd5`, que la app deja vacíos por defecto.

> Conclusión: el cliente está bien; el pack simplemente no tiene esos umbrales
> configurados. La app oficial mostraría los mismos `0xFFFF`.

Bloques conocidos (addr, len):

| Bloque | addr | len |
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

#### Área de parámetros del BMS: huecos y recortes

Barriendo el espacio de direcciones se ven zonas que el BMS **no tiene**
(responde `0x0B`, sin sección extra y datos `0xFFFF`):

| Rango pedido | Respuesta |
|---|---|
| `(268, 26)`, `(276, 18)`, `(280, 4…14)` | `0x0B` (hueco tras el grupo de batería) |
| `(528, 8)`, `(536, 8)`, `(560, 8)`, `(568, 8)` | `0x0B` |
| `(592, 8)`, `(616, 8)` | `0x0B` |
| `(620, 8…32)`, `(636, 16)`, `(652, 8)`, `(660, 8)`, `(700, 8)` | `0x0B` |
| `(512, 8)`, `(520, 8)`, `(576, 8)`, `(584, 8)`, `(608, 8)` | servido (`groupId = 9`) |

Y zonas donde el BMS **recorta** el rango pedido al final del grupo:

- el grupo de batería termina en la dirección **260**, así que `(152, 142)`,
  `(216, 64)`, `(240, 54)` y `(256, 38)` devuelven todos la misma posición
  (260), aunque el rango pedido sea distinto.
- el grupo `manufacturer` se recorta a `lastAddr = 590` con `(528, 64)`, a
  `610` con `(592, 64)` y a `698` con `(656, 56)`.

> Consecuencia: **leer un bloque largo puede devolver menos datos de los
> pedidos**. Conviene trocear y comprobar `lastAddr` en la sección extra.
>
> También significa que este firmware implementa **menos parámetros de los que
> define la app**: los `uart_*_baud_rate`, `CAN_baud_rate`, `function_config_*`
> y `bms_current_info` (592–607) y `verify_current_sensor`/`dttu_serial`
> (616–618) del bloque `manufacturer` no existen en el pack. Sus nombres del
> mapa no se pueden validar con este hardware.



### Respuesta `0x14` (chip ID)

`addr` en `[3..4]`, `count` en `[5]`, `count` bytes en `[6..]`. Se muestra como
bytes separados por puntos. Usado con `addr=0` (chip ID) y `addr=4096` (SysID2).

### Respuesta `0x15` (bloque de información)

`addr` en `[3..4]`, `len` en `[5]`, `len` bytes en `[6..]`. Usado con
`ReadData(0, 40, 0x05)`.

### Autenticación `0x23` → `0x43`

La app desbloquea la lectura de parámetros con `WriteData(330, 8, 0x23, pwd)`,
donde `pwd` son 8 bytes ASCII (contraseña por defecto `12345678`). La respuesta
es `cmd 0x43` con el nivel de permiso en `[6]` (bajo) y `[7]` (alto).

```
Petición:  7E A1 23 4A 01 08 31 32 33 34 35 36 37 38 DB 50 AA 55
Respuesta: 7E A1 43 4A 01 02 <nivel_lo> <nivel_hi> <crc> AA 55
```

> La autenticación **no cambia ningún parámetro**; solo habilita la lectura de
> los bloques. Aun así, este cliente la envía únicamente con `--auth` explícito.

#### Flujo de la app (`request_version`, `pagesBle/components/bleIndex.vue`)

```js
request_version: function () {
  if (this.sysOperatingAut < 1) {
    var e = WriteData(330, 8, 35, StrToLenUint8Array(pwd1, 8));
    setTimeout(function () { sendBlebuff(e); }, 100);   // auth a los 100 ms
  }
  setTimeout(function () { sendBlebuff(ReadData(620, 32, 2)); }, 200); // lectura a los 200 ms
}
```

- La petición de permiso sale **100 ms** después de conectar y la lectura de
  versiones **200 ms** después (en paralelo con el auth, no encadenada).
- `WriteData(330, 8, 35, …)`: el `35` es **0x23** escrito en decimal.
- Los niveles 2–5 usan `WriteData(338|346|354, 8, 35, pwd)` y
  `WriteData(362, 12, 35, pwd)`, con `pwd2`…`pwd5` **vacíos** por defecto en la
  app. En este pack el BMS concede **siempre nivel 1** con la contraseña
  conocida, para las cinco direcciones.

### Nota: bug del parser de la app

En `AntProtocol_RxBufFindBmsPort`, la rama del **Caso C** calcula bien el
tamaño `p = 16 + r + h`, pero al avanzar el buffer usa `iFAddress += 10 + r`
(en vez de `p`). Tras una trama Caso C la app queda desalineada `6 + h` bytes y
se resincroniza buscando el siguiente `7E A1`. No afecta a la decodificación
porque el parser salta la sección extra de todas formas: **la app nunca usa
la sección extra**, es metadata interna del firmware del BMS.

## Comandos de escritura (referencia y riesgo)

Todos usan el mismo formato de trama. Se listan para **saber qué NO enviar** y
para documentar los pocos que son de bajo riesgo.

### Bajo riesgo (documentables / implementables con cuidado)

| Comando | Trama | Efecto | Riesgo |
|---|---|---|---|
| Auth nivel 1 | `WriteData(330,8,0x23,pwd)` | desbloquea lectura | nulo (no cambia nada) |
| Guardar params | `WriteData(7,0,0x51,0)` | persiste los valores actuales | bajo (si no cambiaste nada) |
| Battery ID | `WriteData(262,32,0x22,id)` | escribe el ID de la batería | bajo (solo identificador) |
| Contraseñas | `WriteData(330/338/346/354/362/374,8/12,0x22/0x23,pwd)` | cambia contraseñas de nivel 1–5 | bajo (solo credenciales) |

> "Guardar params" solo reescribe lo que ya está en RAM; no modifica valores por
> sí mismo. Aun así es una escritura: úsalo solo tras un cambio intencionado.

### Alto riesgo (NO implementar sin intención explícita)

**Control MOS — `cmd 0x51`, `addr` = acción, `len 0`:**

| addr | Acción |
|---|---|
| 1 | cerrar descarga (apagar MOS de descarga) |
| 3 | abrir descarga (encender MOS de descarga) |
| 4 | cerrar carga (apagar MOS de carga) |
| 6 | abrir carga (encender MOS de carga) |
| 11 | stop (parada) |

**Reset de fábrica — `cmd 0x53`, `addr 1`, `len 0`:** restaura valores por defecto.

**Escritura de parámetros — `cmd 0x22`:**

| addr | len | Parámetro |
|---|---|---|
| 0–150 | 2 | umbrales de protección/alarma (voltaje, corriente, temperatura) |
| 154 | 2 | número de celdas |
| 162 | 4 | capacidad física (Ah) |
| 262 | 32 | battery ID |
| 330–374 | 8/12 | contraseñas de nivel 1–5 |

**Firmware — `cmd 0x51` addr 10 y `cmd 0x57` addr 61700:** actualización de
firmware. Nunca enviar.

> Regla práctica: cualquier `0x22` sobre addr < 262, cualquier `0x51` con addr
> 1/3/4/6/10/11 y cualquier `0x53`/`0x57` pueden alterar el comportamiento o
> cortar la batería. El cliente de solo lectura no los envía.

## Estado actual (verificado en hardware)

### Dispositivo de referencia

| Dato | Valor |
|---|---|
| Nombre | `ANT-BLE22AAUB-YCE7` |
| MAC | `D9:95:61:xx:xx:xx` |
| RSSI observado | −92 … −99 dBm |
| Hardware version (620) | `22PHA1TB080A` |
| Software version (636 y 620) | `22AAUB00-240510A` |
| Boot version (528) | `BT22AAUB-240606A` |
| Pack ID / battery ID (262) | `220S031AH080V000…` (32 caracteres ASCII) |
| Chip ID (cmd 0x14, addr 0) | `232.252.248.…` (12 bytes separados por puntos) |
| SysID2 (cmd 0x14, addr 4096) | `87.14.80.…` (12 bytes separados por puntos) |
| Bloque info (cmd 0x15) | `0100010001000000000000000000000000000000000000000000c0041b0100000000010000000000` |
| Celdas | 20 |
| Umbrales de protección | **todos sin configurar** (`0xFFFF`) |

> La MAC, el Pack ID y los seriales del chip están parcialmente enmascarados:
> identifican esta unidad concreta, no el modelo. Las longitudes y formatos
> son reales.

### Estado de cada comando

- `live` (tiempo real, `cmd 0x11`): **funciona** (celdas, SOC, pack, corriente,
  potencia, temperaturas).
- `info` (versiones, pack ID, chip ID, SysID2, bloque info): **funciona**.
- `params`: **funciona**. Los bloques de *ajustes* (voltage, temperature,
  current, balance, system, other, customize) devuelven `0xFFFF` en todos sus
  parámetros porque **no están configurados en el pack** (ver sección
  "Por qué muchos bloques devuelven 0xFFFF"). Los bloques `version` (620),
  `manufacturer` (528) y `battery` (152) devuelven **datos reales**, incluidas
  cadenas ASCII.
- Bloques `sysid` (576) y `version` (636) leen `0xFFFF`; el primero es el
  "código de verificación del sistema" y el segundo la versión de usuario.
- Autenticación `0x23`: el BMS concede **nivel 1** con `12345678`. Los niveles
  2–5 (addr 338/346/354/362) responden nivel 1 con cualquier contraseña
  conocida; `pwd2`–`pwd5` están vacíos en la app.
- Cobertura del mapa: 186 parámetros en 11 bloques. Sigue sin mapear el
  contenido de los rangos "hueco" (528–543, 560–575, 592–607, 616+) que el
  firmware de este pack no implementa.


### Pérdida de paquetes BLE (importante en la práctica)

El enlace con el pack es frágil (RSSI ≈ −93…−99 dBm). Las notificaciones BLE se
pierden con facilidad y una trama con bytes perdidos **falla el CRC**, así que
la trama nunca aparece. Se observó el mismo bloque `battery` (142 bytes)
llegando con 144 bytes en una lectura y con 162 en otra.

Por eso el cliente:

- reintenta cada lectura hasta 4 veces (`_request(..., attempts=4)`),
- descarta el buffer de reassamblado cuando una lectura expira
  (`reset_buffer()`), para no quedar atascado con una cabecera corrupta,
- exige `AA 55` **y** CRC válido en `find_frames()`, en vez de aceptar tramas
  solo por CRC,
- **trocea** los bloques de más de 64 bytes en lecturas de 64 bytes
  (`_read_block()`) y las une: tramas cortas se reassamblan mucho mejor que una
  ráfaga de 8 notificaciones. Está verificado que el BMS acepta subrangos
  arbitrarios (`ReadData(184, 32, 2)`, `ReadData(280, 14, 2)`, …).

El paquete Android de la app fuerza MTU 512; en Windows el MTU negociado por
WinRT es menor y el periférico sigue mandando notificaciones de 20 bytes.

> Además, el pack **se duerme**: al final de una sesión larga dejó de
> anunciarse por completo y hubo que esperar a que volviera. Si `scan` no
> encuentra nada, no es un fallo del cliente.

### Cadenas ASCII dentro de los bloques

 algunos bloques guardan texto como pares u16 little-endian. El helper
`decode_ascii()` (descarta `0x00` y `0xFF`) extrae el texto:

| Bloque | Offset | Contenido | Valor real en este pack |
|---|---|---|---|
| `version` (636, 16) | 0–16 | versión de software | `22AAUB00-240510A` |
| `manufacturer` (528, 184) | 0–16 | versión de boot | `BT22AAUB-240606A` |
| `manufacturer` (528, 184) | 16–32 | código de verificación (binario) | `—` |
| `battery` (152, 142) | 110–142 | Pack ID / battery ID | `220S031AH080V000…` (32 caracteres) |
| `version` (620, 32) | 0–16 / 16–32 | HW / SW version | `22PHA1TB080A` / `22AAUB00-240510A` |



## Mapa de parámetros (extracción completa)

La app define los parámetros en `app-service.js` en varias estructuras:

- **`param_list` de 164 entradas** (la que lleva `startaddress`): campos
  `id`, `name` (chino), `startaddress` (dirección real del BMS), `unit`,
  `iTimes` (escala), `decimal_len`, `datatype`, `value` (por defecto).
  Cubre direcciones 0–326 (voltaje, corriente, balanceo, batería, SOC,
  resistencias internas, battery ID, sistema).
- **`dianta` de la página de temperatura** (ids 28–49): no trae `startaddress`;
  la dirección es `56 + 2*datatype` (bloque 56, 44 bytes). Los ids 26,27,38,39,
  50,51 son reservados.
- **`dianta` de la página de sistema** (ids 149–164): direcciones 298–328
  (incluye `Auto_OFF_Time` en 328).
- **`dianta` de la página "otros"** (ids 189–197): direcciones 378–394.

Los nombres en inglés salen de las claves `$t("...")` de los `dianta`; el
`param_list` principal solo trae nombres en chino.

### Generador

`tools/gen_params.py` lee el APK, combina las cuatro fuentes y escribe:

- `src/antbms/params.py` — `PARAM_BLOCKS`, `PARAM_MAP` (addr → name, iTimes, dec)
  y `PARAM_META` (unit, datatype, default, name_zh, id).
- `src/antbms/params_full.json` — volcado completo con todos los campos.

Estado: regenerado con **186 parámetros** en 11 bloques. Decimals derivados de
`iTimes` cuando el APK no los trae. **Validado en hardware**: los bloques
`version` (636) y `manufacturer` (528) devuelven las cadenas ASCII esperadas
(`22AAUB00-240510A` y `BT22AAUB-240606A` respectivamente), lo que confirma que
las direcciones y escalas del mapa son correctas. `customize` (470) y `sysid`
(576) devuelven `0xFFFF` en este pack; no hay forma de validar sus nombres con
este hardware.

### Bloques de lectura extra (cmd 0x02)

| Bloque | addr | len | Contenido |
|---|---|---|---|
| customize | 470 | 32 | parámetros personalizados (sin params definidos en la app) |
| manufacturer | 528 | 184 | UART/CAN baud, function config, MAC, etc. (params 592–618 y 700–706 en `PARAM_MAP`; este firmware solo implementa 608–614) |
| sysid | 576 | 16 | system ID (en este pack devuelve `0xFFFF`) |
| version | 636 | 16 | versión (ASCII: `22AAUB00-240510A`) |

> Nota: la página `customize.vue` lee `ReadData(470,32,2)` pero su `dianta`
> declara `startaddress` 378–388 (bloque "otros"); hay una inconsistencia en la
> app que conviene verificar en hardware.

### Campos de un parámetro

Cada entrada de `param_list` / `dianta` tiene:

| Campo | Significado |
|---|---|
| `id` | índice lógico del parámetro |
| `startaddress` | dirección real en el BMS (u16) |
| `name` | nombre (chino en `param_list`, clave `$t()` en `dianta`) |
| `value` | valor por defecto |
| `input` | valor de entrada en la UI |
| `step` | incremento de edición |
| `iTimes` | escala: valor real = `raw / iTimes` (`1e3`, `1e6`, `10`, `1`) |
| `decimal_len` | decimales a mostrar (a veces `decimaLen`, typo) |
| `unit` | unidad (`V`, `A`, `AH`, `℃`, `MR`, `S`, `M`, `H`, `US`, `N`) |
| `datatype` | en `param_list` = 0 (u16); en la página de temperatura = índice del bloque |

> `iTimes` es la escala de lectura: `raw / iTimes`. `decimal_len` es solo para
> presentación. Cuando el APK omite `decimal_len`, se deriva de `iTimes`
> (`1e3→3`, `1e6→1`, `10→1`, `1→0`).

### Contraseñas (`qita`)

La app guarda las contraseñas de nivel 1–5 en el array `qita`:

| Nivel | addr | len |
|---|---|---|
| 1 | 330 | 8 |
| 2 | 338 | 8 |
| 3 | 346 | 8 |
| 4 | 354 | 8 |
| 5 | 362 | 12 |

Se escriben con `cmd 0x22` (cambio) o `cmd 0x23` (auth). La de nivel 1 por
defecto es `12345678`.

### Identificadores de dispositivo

| Campo | Origen |
|---|---|
| `SocId` | chip ID (cmd 0x14, addr 0), string con puntos |
| `SysID2` | chip ID (cmd 0x14, addr 4096), string con puntos |
| `SYS_Code_Key` | parámetros (cmd 0x12, addr 288), string con puntos |
| `gpsid` | `GpsId` (ID de la nube) |
| `shebeiid` | ID de dispositivo introducido por el usuario (nube) |
| `xinpianid` | `dtuId` devuelto por la nube |
| `Pack_Cell_Num` | nº de celdas (tiempo real, offset 9) |
| `Pack_Physics_AH` | capacidad física (tiempo real, `packPhysicsAh`) |

### Nube (referencia, no BLE)

La app usa DCloud uniCloud y servicios externos:

- `https://api.bspapp.com`, `https://api.next.bspapp.com` (uniCloud)
- `https://www.antbms.com`, `https://doc.antbms.com/web/`
- `https://www.mayibms.com/xieyi.html` (página de documentación del protocolo)
- Mapas: `apis.map.qq.com`, `apilocate.amap.com`
- OCR: `aip.baidubce.com`

### Actualización de firmware (alto riesgo, no usar)

- `WriteData(10, 24, 0x51, data)`: comando de upgrade (16 bytes del fichero en
  offset 2048 + 4 bytes de longitud + …).
- `WriteData(61700, 24, 0x57, data)`: envío de bloques de firmware.
- La página `shengji.vue` gestiona el proceso. **Nunca enviar** desde un cliente
  de solo lectura.

## Notas para Node.js / noble

- Escribir en la característica `FFE1` con `write` (la app usa `writeType:"write"`).
- Suscribirse a notificaciones de `FFE1` (`notify: true`) antes de enviar.
- La app reensambla tramas en un buffer circular de 1024 bytes y busca la
  cabecera `7E A1`; valida `len`, CRC y cola `AA 55`. Replica ese reensamblado:
  las notificaciones BLE pueden llegar fragmentadas.
- Enviar la petición `0x01` cada 500 ms; cada respuesta `0x11` es un snapshot
  completo de tiempo real.
- Para tiempo real solo se necesita la petición `0x01`. No se envían comandos de
  escritura de parámetros. La autenticación (`cmd 0x23`) es opcional y solo
  desbloquea lectura; este cliente la envía únicamente con `--auth`.
- El reensamblador debe implementar los **tres layouts** (Casos A/B/C): una
  respuesta Caso C no termina tras el CRC del payload, lleva sección extra y su
  propio CRC antes de la cola `AA 55` (ver "Layout de trama larga").
- El MTU por defecto puede fragmentar; la app fija **MTU 512**. Ajusta el MTU
  según tu adaptador o usa `write` sin respuesta.
- Ordena los dispositivos por `10^((|RSSI|-70)/20)` y conecta al mejor.

## Apéndice: protocolo viejo (`Ver == 1`)

Trama:

```
AA 55 <b2> <b3> <data…> <sum_hi> <sum_lo>
```

- Checksum = suma de `bytes[4 .. len-3]` (16 bits), almacenado **big-endian** en
  los dos últimos bytes.
- `b2`, `b3` no los usa el parser.
- Multi-byte en **big-endian**.
- Decodificado por `jiexi1`, que empieza en el offset 4:

| Offset | Campo | Tipo | Escala |
|---|---|---|---|
| 4 | `packVoltage` | u16 | `/10` → V |
| 6 | `cellVoltages[32]` | u16 × 32 | `/1000` → V (solo se usan `cellCount`) |
| 70 | `current` | u32s | `/10` → A |
| 74 | `soc` | u8 | % |
| 75 | `packPhysicsAh` | u32 | `/1e6` → Ah |
| 79 | `packRemainAh` | u32 | `/1e6` → Ah |
| 83 | `packAllAh` | u32 | `/1e3` → Ah |
| 87 | `allTimerMs` | u32 | segundos |
| 91 | `temperatureMos` | u16s | °C |
| 93 | `temperatureBalance` | u16s | °C |
| 95 | `temperatures[4]` | u16s × 4 | °C |
| 103 | `chMosState` | u8 | índice |
| 104 | `disMosState` | u8 | índice |
| 105 | `balanceState` | u8 | índice |
| 106 | `voltageDS` | u16 | V |
| 108 | `voltageDisMos` | u16 | V |
| 110 | (1 byte ignorado) | u8 | — |
| 111 | `packPower` | u32 | potencia |
| 115 | `cellVoltageMaxPos` | u8 | índice |
| 116 | `cellVoltageMax` | u16 | `/1000` → V |
| 118 | `cellVoltageMinPos` | u8 | índice |
| 119 | `cellVoltageMin` | u16 | `/1000` → V |
| 121 | `cellVoltageAvg` | u16 | `/1000` → V |
| 123 | `cellCount` | u8 | nº de celdas |

> Quirk del APK: en `jiexi1` el `cellCount` se lee al final, así que en la
> primera trama usa el valor previo. Para un cliente propio, lee `cellCount` del
> offset 123 antes de interpretar las celdas, o usa el número de celdas
> configurado.
