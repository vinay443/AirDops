# Testing checklist

Hardware testing on a real PC with real AirPods. Takes about 15 minutes.
If anything fails, run **More → Run diagnostics** and attach
`diagnostics.txt` (device names only, safe to share) plus
`%LOCALAPPDATA%\AirDops\logs\airdops.log` to an issue.

## 0. Setup
- [ ] Download `AirDops.exe` (Releases or the latest Actions run). Optional: install [VB-Cable](https://vb-audio.com/Cable/) and reboot.
- [ ] Connect the AirPods, then start `AirDops.exe`. A tray icon appears and a "running" notification shows.

## 1. Detection
- [ ] The icon is **green**; the menu's first line names your AirPods and says "connected".
- [ ] Disconnect the AirPods (put them in the case). Within ~2 s the icon turns **grey**. Reconnect: it turns green again.

## 2. The main fix: game audio stays full quality
- [ ] Play music or a game. In Discord (input device = Default), join a voice channel or open *Settings → Voice → Mic test*.
- [ ] **The music must stay full quality (stereo, not muffled).** This is the whole point.
- [ ] Windows *Sound settings → Input* shows the laptop mic (or "CABLE Output") as the default, not the AirPods.
- [ ] *Sound control panel → Recording* (right-click → show disabled devices) lists the AirPods "Headset" mic as **Disabled**.

## 3. Mic quality
- [ ] Discord mic test: your voice is heard through the laptop mic.
- [ ] With VB-Cable: the menu shows "Mic: Clean mic (via …)". Type hard on the keyboard while talking: clicks are mostly gone.
- [ ] Turn on **Voice gate**: clicks between words disappear completely; speech is not cut off.

## 4. Ducking
- [ ] With music playing, start a Discord call. The music volume does **not** drop.

## 5. Battery and ear detection
- [ ] Menu shows `L xx%  R xx%  Case xx%` within ~10 s (open the case lid near the PC if the case shows `--`).
- [ ] Play a YouTube video or Spotify, take one bud out: playback **pauses** within ~1-2 s. Put it back: it **resumes**.

## 6. Call mode
- [ ] Choose **Call mode**: the icon turns blue, the AirPods mic is enabled and becomes the default input (audio drops to call quality while it's in use, which is expected).
- [ ] Back to **Game mode**: the AirPods mic is disabled again.

## 7. Undo
- [ ] **Quit** AirDops: the AirPods mic is re-enabled in the Recording tab, your normal mic is default again, ducking is back to what it was.
- [ ] **Start with Windows**: tick it, sign out and in, and AirDops starts quietly in the tray.
