# Cómo usar la app oficial de ANT BMS (Android)

> English version: [official-app-guide.md](official-app-guide.md)

La app oficial viene con el **chino como idioma por defecto**, y mucha gente
no encuentra nunca dónde cambiarlo. Esta guía cubre lo que la mayoría
realmente necesita: cambiar el idioma, conectar, leer la pantalla principal y
entender las rarezas de la app.

> Escrita contra la versión **20240925** de la app (el mismo APK del que se
> extrajo la [especificación del protocolo](../PROTOCOL.es.md) de este
> repositorio). Los menús pueden cambiar en otras versiones. Las rutas
> marcadas **[VERIFICAR]** están pendientes de confirmar en un dispositivo
> real.
>
> Este proyecto no está afiliado al fabricante de ANT BMS; esto es
> documentación de usuario independiente.

## 1. Cambiar el idioma de chino a inglés

Si la app abrió en chino, estos son los caracteres que hay que buscar:

| Ves | Significa |
|---|---|
| 设置 | Ajustes |
| 语言 | Idioma |
| 中文 / 简体中文 | Chino / Chino simplificado |
| English | Inglés |
| 我的 | Pestaña "Mío" / perfil |

Pasos **[VERIFICAR]**: abre la zona de perfil/ajustes (busca **设置** o la
pestaña **我的**) → toca la fila con **语言** → elige **English** → puede
hacer falta reabrir la app.

## 2. Conectar con tu batería

1. Activa Bluetooth y la ubicación (Android exige el permiso de ubicación
   para escanear BLE).
2. La batería se anuncia como **`ANT-BLE…`** (por ejemplo
   `ANT-BLE22AAUB-YCE7`). Elígela en la lista del escaneo.
3. **Protocolo viejo vs nuevo**: con algunos nombres de dispositivo la app
   muestra un diálogo preguntando si usar el *protocolo viejo*.
   - Los packs modernos (nombres largos, como el del ejemplo) hablan el
     protocolo **nuevo** — responde **No/Cancelar**.
   - Confirma "protocolo viejo" solo si tienes un pack antiguo y los datos en
     vivo salen mal con el nuevo.
4. Solo puede haber **un dispositivo conectado a la vez** — BLE permite una
   única conexión activa con el BMS. Si otro teléfono (o un PC) está
   conectado, la batería no aparecerá o rechazará la conexión.

## 3. Leer la pantalla principal

La pantalla en vivo se refresca dos veces por segundo y muestra, entre otros:

- **SOC** (nivel de carga, %) y **SOH** (salud, %).
- **Voltaje, corriente y potencia del pack.** El signo de la corriente indica
  el sentido (cargando vs descargando).
- **Voltajes por celda**, con la celda más alta, la más baja y su
  diferencia. En un pack sano en reposo la diferencia es pequeña (decenas de
  mV).
- **Temperaturas** (sensores de batería, MOSFET, balanceador).
- **Estados MOS** (interruptores de carga/descarga) y estado de **balanceo**.
- **Tiempo restante de carga/descarga**, cuando el firmware lo envía — la app
  muestra `--` cuando no.

## 4. La contraseña de ajustes

- La contraseña de nivel 1 por defecto es **`12345678`**.
- Introducirla solo **desbloquea leer/entrar a las páginas de parámetros**;
  no cambia nada por sí misma.
- Los niveles superiores (2–5) existen para uso de fábrica y no tienen
  contraseña por defecto.
- **Cuidado a partir de ahí**: las páginas de ajustes pueden escribir en el
  BMS umbrales de protección, número de celdas y capacidad. Un valor mal
  puesto puede inhabilitar la carga/descarga o desvirtuar las protecciones.
  Si solo quieres *monitorizar* la batería, nunca necesitas cambiar un ajuste
  (para eso están las herramientas de solo lectura de este repositorio).

## 5. Por qué las páginas de ajustes salen vacías o raras

En muchos packs, la mayoría de umbrales de protección/alarma **no vienen
configurados de fábrica**: el BMS guarda `0xFFFF` ("sin valor") y la app lo
pinta en blanco o como un número sin sentido. Es normal y está documentado en
detalle en la [spec del protocolo](../PROTOCOL.es.md). No es un problema de
conexión, y meter la contraseña no lo cambia.

## 6. Bugs y rarezas conocidas de la app

Encontradas durante la ingeniería inversa (detalles en la spec):

- **Potencia absurda al cargar**: la app lee el campo de potencia sin signo,
  así que cargando puede mostrar un vataje gigante falso. El valor real es
  negativo (p. ej. `-354 W`). Voltaje × corriente es el número fiable.
- **Protocolo viejo, primera trama**: la app lee el número de celdas
  *después* de usarlo, así que la primera lectura tras conectar puede mostrar
  por un momento un número de celdas incorrecto.
- **Tiempo restante**: lo calcula el BMS, no la app. Si tu firmware no lo
  envía, la app muestra `--` para siempre — no hay nada que configurar.

## 7. Problemas de conexión

- **El pack se duerme**: tras un rato sin actividad puede dejar de anunciarse
  por completo. Espera a que reaparezca, o despierta el BMS aplicando
  brevemente carga o consumo **[VERIFICAR]**.
- **Enlace débil**: la radio del BMS no es potente (nuestro pack de
  referencia midió −92…−99 dBm a pocos metros). Acércate; las paredes
  importan.
- **No aparece en el escaneo**: comprueba que ningún otro teléfono/PC esté
  conectado, que el permiso de ubicación esté concedido, y dale un par de
  reintentos al escaneo — el pack se anuncia de forma intermitente.

## 8. La app de Windows

ANT también distribuye una aplicación de Windows con la misma interfaz en
chino por defecto y menús aún más difíciles de navegar. Si te manejas con una
terminal, el CLI de este repositorio es una alternativa más simple en
Windows:

```bash
pip install ant-bms-ble
antbms live      # dashboard en vivo
antbms demo      # pruébalo sin batería
```

Un dashboard de navegador sin instalación (Android y Windows, inglés/español)
está en el [roadmap](../README.md#roadmap).
