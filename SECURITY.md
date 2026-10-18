# Security & privacy

AirDops is a small local utility. This page lists everything it touches so you
can check it, and explains why it is safe for the source to be public.

## What AirDops does on your PC

| Area | Access | Why |
|---|---|---|
| Windows sound devices | Changes default playback/recording device; disables/re-enables the AirPods' hands-free endpoints | The core feature. Every change is recorded in `state.json` and undone on disconnect, on quit, from the menu, or with `--restore`. Endpoints you disabled yourself are never touched. |
| Registry `HKCU\Software\Microsoft\Multimedia\Audio\UserDuckingPreference` | Set to "do nothing" while AirPods are connected in Game mode, original value restored afterwards | Stop game audio being turned down during voice chat |
| Registry `HKCU\...\CurrentVersion\Run\AirDops` | Only when you tick *Start with Windows* | Auto-start (per-user, no admin) |
| Microphone | Reads the mic you chose and plays the cleaned audio into VB-Cable, only while noise suppression is on | Noise suppression. Audio is processed in memory 10 ms at a time and never saved or sent anywhere. |
| Bluetooth LE | Listens (passively decodes) for AirPods broadcast packets while your AirPods are connected | Battery level and ear detection. Never pairs, connects or sends anything. |
| Media sessions | Pauses/resumes apps that were playing | Ear-detection auto-pause |
| Files | `%APPDATA%\AirDops\settings.json`, `%LOCALAPPDATA%\AirDops\` (state, logs, diagnostics) | Settings and undo information |

## What it never does

* **No network access at all.** No telemetry, analytics, update checks,
  accounts or cloud. You can block it in your firewall and nothing changes.
* **No admin rights** required. No drivers or services are installed.
* **No personal data in logs or reports.** Logs and the diagnostics report
  contain sound-device *names* and states only. Bluetooth addresses, device ids,
  serial numbers and raw Bluetooth payloads are never logged or stored. Windows
  endpoint ids (opaque GUIDs) are kept in local `state.json` only, so changes
  can be undone.
* **Other people's AirPods**: AirPods broadcasts are public radio packets.
  AirDops ignores weak signals (`ble_min_rssi`), only accepts the same product
  family as the AirPods connected to your PC, and only uses them for the battery
  display. Nothing is recorded.

## Why the public repository is safe

* No secrets, keys, tokens or personal information are in the repository, and
  `.gitignore` excludes runtime files (`settings.json`, `state.json`, logs,
  diagnostics) and common secret file types.
* Commits contain no personal e-mail addresses.
* CI runs with read-only repository permissions; only the release job, which
  runs on version tags you push, gets permission to publish a release. Workflow
  actions are pinned to exact commit SHAs and checkout does not persist
  credentials. There is no `pull_request_target` trigger, so forks cannot run
  code with write access.
* The RNNoise DLL is not committed. It is downloaded at build time from a
  pinned PyPI wheel (`pyrnnoise==0.4.5`) and **its SHA-256 is verified**, so a
  swapped file fails the build.
* Python dependencies are pinned to exact versions, and Dependabot proposes
  updates as pull requests you review.
* Each build publishes `SHA256SUMS.txt` next to the exe and runs a self-test of
  the packaged exe before uploading it.

## Reporting a problem

Please open a GitHub issue. For anything sensitive, use GitHub's
*Security → Report a vulnerability* (private advisory) on this repository.
