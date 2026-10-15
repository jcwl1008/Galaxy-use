# Security and privacy

The default bridge permits only four exact ADB argument lists: devices, exec-out screencap -p, shell wm size, and shell dumpsys input. Any other ADB command is rejected before spawning ADB when adb_read_only is true. Optional input has an additional adb_actions gate. ESP32 input uses BLE HID and the owner's manually paired device.

This program does not alter enterprise management controls. Use only operations your organization permits. Administrator authorization is required before optional installation, App pairing, forwarding or ADB action modes are used in a managed environment. Do not use alternative transports to evade a restriction.

bridge.json may contain a pairing token and device identifiers. It and generated OpenCode settings are ignored by Git. Keep API credentials in your model client's normal credential store. Avoid putting sensitive personal or financial screens into a cloud-model session.

The optional companion is a development-signed, debuggable APK so an authorized ADB shell can provision a private pairing token with run-as. It has no Internet permission and uses an authenticated Android abstract socket forwarded over ADB. It is not hardened for hostile co-tenants with shell/root access. Do not use it on an untrusted phone or workstation. See android/BUILD.md for rebuild details.

Snapshots and observed elements can become stale. Input tools do not automatically replay uncertain clicks. Password prompts and consequential actions require owner handling/authorization. No automation can guarantee the outcome of a BLE report or an accepted accessibility action.

Report a suspected bug without posting credentials, tokens, real device identifiers or private screenshots in a public issue. For a sensitive report, contact the repository owner privately using a contact method they provide.
