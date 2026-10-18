"""Pause / resume whatever is playing, via Windows' media session API (SMTC).

This is the same API the volume flyout's media controls use, so it works with
Spotify, browsers, media players, etc. Only sessions that were *playing* get
paused, and only those get resumed.
"""

from __future__ import annotations

import logging

log = logging.getLogger(__name__)

_PLAYING = 4  # GlobalSystemMediaTransportControlsSessionPlaybackStatus.PLAYING


async def pause_playing() -> list[str]:
    from winrt.windows.media.control import (
        GlobalSystemMediaTransportControlsSessionManager as Manager,
    )

    paused: list[str] = []
    manager = await Manager.request_async()
    for session in manager.get_sessions():
        try:
            info = session.get_playback_info()
            if info is not None and int(info.playback_status) == _PLAYING:
                if await session.try_pause_async():
                    paused.append(session.source_app_user_model_id)
        except Exception as exc:  # noqa: BLE001
            log.debug("pause failed for a session: %r", exc)
    return paused


async def resume(app_ids: list[str]) -> None:
    if not app_ids:
        return
    from winrt.windows.media.control import (
        GlobalSystemMediaTransportControlsSessionManager as Manager,
    )

    wanted = set(app_ids)
    manager = await Manager.request_async()
    for session in manager.get_sessions():
        try:
            if session.source_app_user_model_id in wanted:
                await session.try_play_async()
        except Exception as exc:  # noqa: BLE001
            log.debug("resume failed for a session: %r", exc)
