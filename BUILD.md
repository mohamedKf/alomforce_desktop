# Building the AlomForce desktop app

The app is packaged with PyInstaller into a **self-contained, relocatable**
build — it can be copied anywhere and double-clicked; no install path is
hardcoded and no Python is required on the target machine.

## Prerequisites
```
python3 -m venv .venv
.venv/bin/pip install -r requirements-build.txt
```
Use Python 3.11–3.14 (tested on 3.14).

## macOS
```
.venv/bin/pyinstaller alomforce.spec --noconfirm
```
Output: **`dist/AlomForce.app`** — drag it to `/Applications` or anywhere; it
runs from any location. (Chromium/WebEngine is bundled for the delivery map, so
the app is ~700 MB — this is expected.)

To ship it, zip the `.app` (`ditto -c -k --keepParent dist/AlomForce.app AlomForce-mac.zip`)
or wrap it in a DMG. For distribution outside your own machines, code-sign and
notarize it, otherwise Gatekeeper warns on first open.

## Windows
PyInstaller does **not** cross-compile — build on a Windows machine with the
same commands:
```
py -m venv .venv
.venv\Scripts\pip install -r requirements-build.txt
.venv\Scripts\pyinstaller alomforce.spec --noconfirm
```
Output: **`dist\AlomForce\AlomForce.exe`** — ship the whole `dist\AlomForce`
folder together (the `.exe` needs the files beside it); the folder can live
anywhere. The Windows icon (`app/assets/alomforce.ico`) is applied
automatically.

## First run
There is no baked-in server. On first launch the app prompts for the server
link you give the shop (typed in, or scanned via the QR shown in Settings).
The app is unusable until that link is set and you have created their account.

## Releasing

Tag the version and GitHub Actions builds both platforms:

```
git tag v1.1.0 && git push origin v1.1.0
```

The Windows job produces `AlomForce-Setup-<version>.exe`, an Inno Setup
installer. It carries a fixed AppId, so installing a new version **upgrades
the existing one in place** -- one entry in Apps & features, one shortcut, one
folder. Hand a customer the setup file and they run it over whatever they have;
their server address and language survive, because those live in the registry
under the app's own key and only an uninstall clears them. The installer also
refuses to go backwards over a newer build.

There is no Windows machine in this; the runner is one. Building by hand on
Windows still works (see above), and `iscc /DMyAppVersion=1.1.0
packaging\windows\alomforce.iss` makes the installer from the PyInstaller
output.

The macOS job signs and notarises only when these repository secrets exist,
and produces an unsigned zip otherwise:

| Secret | What it is |
|---|---|
| `MACOS_CERT_P12` | Developer ID Application certificate, base64 of the .p12 |
| `MACOS_CERT_PASSWORD` | the password that .p12 was exported with |
| `MACOS_SIGN_IDENTITY` | e.g. `Developer ID Application: Your Name (TEAMID)` |
| `MACOS_NOTARY_PROFILE_JSON` | `{"key_id": ..., "issuer": ..., "key": "-----BEGIN PRIVATE KEY-----..."}` from an App Store Connect API key |
