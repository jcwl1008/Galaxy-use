# ESP32-S3 BLE mouse firmware

Source: `firmware/GalaxyMouse/GalaxyMouse.ino`.

The original DNESP32S3B factory firmware should be backed up before replacing it. This project does not contain anyone's factory dump, Bluetooth bonds, Wi-Fi credentials or personal device configuration.

## Known build configuration

- Board: DNESP32S3B / ALIENTEK ESP32-S3 N16R8 (16 MB flash, 8 MB PSRAM).
- Arduino IDE, **esp32 by Espressif Systems 3.3.12**.
- Board menu: ESP32S3 Dev Module.
- Flash Size: 16 MB; PSRAM: OPI PSRAM; compatible 16 MB partition scheme.
- USB CDC On Boot: Disabled; Upload Mode: UART0 / Hardware CDC.
- Upload through the UART connector (CH343 on the known board), 460800 baud if reliable.
- Use the built-in NimBLE backend; no separate BLE mouse library.
- Do not blindly apply N16R8 settings to a board with different memory hardware.

## Connections

1. Board UART USB → Windows PC (set your own COM port in bridge.json).
2. Phone USB → PC for authorized read-only screenshots.
3. Phone Bluetooth → **Jimmy Phone Mouse v2**.

Do not connect the PC to the board's USB HOST socket. On the known enclosed DNESP32S3B, the bottom USB-C is UART; verify board labels before connecting. The upper USB-C is labelled SLAVE and is not used by this UART bridge.

## Serial test

115200 baud, New Line. Commands: `status`, `help`, `left`, `right`, `up`, `down`, `click`, `scrollup`, `scrolldown`, `pair` (see source for command handling).

Close Arduino Serial Monitor before launching the MCP bridge. The board must report ready=1 before mouse input. Reports are gated by link, encryption and the active protocol's HID subscription. Report and boot mouse formats are supported; advertising restarts after disconnect.

This is a relative BLE mouse. Android pointer acceleration applies. A 40-unit movement must never be interpreted as a 40-pixel movement. Firmware acknowledgements cannot prove a visible UI action succeeded.
