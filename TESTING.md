# Testing checklist

Hardware testing on a real PC with real AirPods. Takes about 15 minutes.
If anything fails, open the panel, choose **More → Run Diagnostics**, and attach
`diagnostics.txt` (device names only, safe to share) plus
`%LOCALAPPDATA%\AirDops\logs\airdops.log` to an issue.

## 0. Setup
- [ ] Download `AirDops-portable.zip` (Releases or the latest Actions run) and unzip it. Optional: install [VB-Cable](https://vb-audio.com/Cable/) and reboot.
- [ ] Start `AirDops.exe` from the unzipped folder. An "AirDops is running" banner slides in and an AirPods glyph appears in the tray (check the `^` overflow and drag it onto the taskbar).
- [ ] Run `AirDops.exe` again: no second copy starts; the panel opens instead.

## 0b. Installer
- [ ] Run `AirDops-Setup.exe`: no admin prompt; it installs, offers "Open AirDops now", and adds *AirDops* to the Start menu.
- [ ] First launch shows the **Welcome** sheet (it correctly says whether VB-Cable is installed). *Continue* opens the panel.

## 1. Look and feel
- [ ] Click the tray icon: the panel fades in just above the tray, with rounded corners and a shadow. Click elsewhere or press Esc to close it.
- [ ] Switch Windows to dark mode (*Settings → Personalization → Colors*): within a few seconds the panel turns dark, and the tray glyph matches the taskbar.
- [ ] Right-click the tray icon: a rounded quick menu with Game/Call Mode and Quit appears.

## 2. Connection
- [ ] Connect the AirPods: a "AirPods Pro … Connected · Game Mode" banner appears, and the tray glyph turns solid.
- [ ] The panel shows the name, a green "Connected" dot, and battery rings for left, right and case within about 10 s (open the lid if the case shows "–").
- [ ] Put the AirPods away: within about 2 s the panel says "Not Connected" with a *Bluetooth Settings…* link.

## 3. The main fix: game audio stays full quality
- [ ] Play music or a game. In Discord (input device = Default), join a voice channel or open *Settings → Voice → Mic Test*.
- [ ] **The music must stay full quality (stereo, not muffled).** This is the whole point.
- [ ] *Sound settings → Input* shows the laptop mic (or "CABLE Output") as the default.
- [ ] *Sound control panel → Recording* (right-click → *Show Disabled Devices*) lists the AirPods "Headset" mic as **Disabled**.

## 4. Mic
- [ ] The panel's *Input* shows your laptop mic. Choose another one from the list if you have it, and it's used.
- [ ] With VB-Cable, *Noise Suppression* says "On · cleaning up your voice". Type hard while talking in the Discord mic test: clicks are mostly gone.
- [ ] Turn on **Voice Gate**: clicks between words disappear completely, and speech isn't cut off.
- [ ] Without VB-Cable, the switches are greyed out and a "Get VB-Cable (free)" link is shown.

## 5. Ducking, ear detection and battery
- [ ] With music playing, start a Discord call: the music volume does **not** drop.
- [ ] Play a YouTube video or Spotify and take one AirPod out: playback **pauses** within 1-2 s. Put it back: it **resumes**. The status line shows "In Use" while worn.
- [ ] Low battery (≤ 20%): a "Low Battery" banner appears once, and the tray glyph gets an orange dot (red at 10% or below).

## 5b. Mic meter, boost and hotkey
- [ ] With noise suppression on, the panel shows **Input Level** bars that move when you talk, and a **Mic Boost** slider; raising it makes you louder in the Discord mic test.
- [ ] In a game, press **Ctrl+Alt+M**: a "Call Mode" banner appears and the mode switches; press it again to go back to Game Mode.

## 6. Call Mode
- [ ] Choose **Call Mode**: the pill slides over, the AirPods mic is re-enabled and becomes the default input. Audio drops to call quality while the mic is in use, which is expected.
- [ ] Back to **Game Mode**: the AirPods mic is disabled again.

## 6b. Speed (optional)
- [ ] Quit AirDops, then run `AirDops.exe --bench %TEMP%\airdops-bench.txt` from the install folder (`%LOCALAPPDATA%\Programs\AirDops`). It runs for about 45 seconds and writes startup time, CPU and memory to that file. Share it to compare with the numbers in the README.

## 7. Undo
- [ ] **Quit**: the AirPods mic is re-enabled, your normal mic is the default again, and ducking is back to what it was.
- [ ] **Open at Login**: turn it on, sign out and back in, and AirDops starts quietly in the tray.
- [ ] Uninstall from *Settings → Apps*: Windows audio is put back, and the login item and app files are removed.
