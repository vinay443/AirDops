"""Thin wrapper over the Windows Core Audio COM APIs (Windows only).

* IMMDeviceEnumerator  - list endpoints and read the current defaults
* IPolicyConfig        - the (undocumented but long-stable) interface the
                         Sound control panel itself uses to change the default
                         device and to enable/disable an endpoint.

Every thread that calls into this module must call ``com_init()`` first.
"""

from __future__ import annotations

import logging
from typing import Optional

from .router import CAPTURE, RENDER, Endpoint

log = logging.getLogger(__name__)

_FLOW = {RENDER: 0, CAPTURE: 1}
ROLE_CONSOLE = 0
ROLE_MULTIMEDIA = 1
ROLE_COMMUNICATIONS = 2
ALL_ROLES = (ROLE_CONSOLE, ROLE_MULTIMEDIA, ROLE_COMMUNICATIONS)
_STATE_MASK_ALL = 0xF
_STGM_READ = 0

_FRIENDLY_NAME_FMTID = "{a45c254e-df1c-4efd-8020-67d146a850e0}"
_FRIENDLY_NAME_PID = 14


def com_init() -> None:
    import comtypes

    try:
        comtypes.CoInitialize()
    except OSError:
        # Already initialised on this thread with a different model - fine.
        pass


def com_uninit() -> None:
    import comtypes

    try:
        comtypes.CoUninitialize()
    except OSError:
        pass


def _enumerator():
    import comtypes
    from pycaw.api.mmdeviceapi import IMMDeviceEnumerator
    from pycaw.constants import CLSID_MMDeviceEnumerator

    return comtypes.CoCreateInstance(
        CLSID_MMDeviceEnumerator, IMMDeviceEnumerator, comtypes.CLSCTX_INPROC_SERVER
    )


def _policy_config():
    import comtypes
    from pycaw.api.policyconfig import IPolicyConfig
    from pycaw.constants import CLSID_CPolicyConfigClient

    return comtypes.CoCreateInstance(CLSID_CPolicyConfigClient, IPolicyConfig, comtypes.CLSCTX_ALL)


def _friendly_name(dev) -> str:
    from comtypes import GUID
    from pycaw.api.mmdeviceapi import PROPERTYKEY

    key = PROPERTYKEY()
    key.fmtid = GUID(_FRIENDLY_NAME_FMTID)
    key.pid = _FRIENDLY_NAME_PID
    try:
        store = dev.OpenPropertyStore(_STGM_READ)
        value = store.GetValue(key)
        name = value.GetValue()
        try:
            value.clear()
        except Exception:  # pragma: no cover - depends on comtypes version
            pass
        return str(name) if name else ""
    except Exception as exc:  # noqa: BLE001 - COM errors vary
        log.debug("friendly name unavailable: %r", exc)
        return ""


def list_endpoints() -> list[Endpoint]:
    result: list[Endpoint] = []
    enum = _enumerator()
    for flow, flow_val in _FLOW.items():
        try:
            coll = enum.EnumAudioEndpoints(flow_val, _STATE_MASK_ALL)
            count = coll.GetCount()
        except Exception as exc:  # noqa: BLE001
            log.warning("EnumAudioEndpoints(%s) failed: %r", flow, exc)
            continue
        for i in range(count):
            try:
                dev = coll.Item(i)
                result.append(
                    Endpoint(id=dev.GetId(), name=_friendly_name(dev), flow=flow, state=int(dev.GetState()))
                )
            except Exception as exc:  # noqa: BLE001
                log.debug("skipping endpoint %d: %r", i, exc)
    return result


def get_default(flow: str, role: int) -> Optional[str]:
    try:
        dev = _enumerator().GetDefaultAudioEndpoint(_FLOW[flow], role)
        return dev.GetId() if dev else None
    except Exception:  # noqa: BLE001 - E_NOTFOUND when there is no device
        return None


def set_default(endpoint_id: str, roles=ALL_ROLES) -> bool:
    try:
        pc = _policy_config()
        for role in roles:
            pc.SetDefaultEndpoint(endpoint_id, role)
        return True
    except Exception as exc:  # noqa: BLE001
        log.warning("SetDefaultEndpoint failed: %r", exc)
        return False


def set_enabled(endpoint_id: str, enabled: bool) -> bool:
    try:
        _policy_config().SetEndpointVisibility(endpoint_id, 1 if enabled else 0)
        return True
    except Exception as exc:  # noqa: BLE001
        log.warning("SetEndpointVisibility(%s) failed: %r", enabled, exc)
        return False


class DeviceWatcher:
    """Calls ``on_change`` the instant Windows reports an audio-device change.

    Windows delivers IMMNotificationClient callbacks on its own worker thread
    and forbids calling back into the device API from inside them, so the
    callback only signals (e.g. sets a threading.Event); the real work happens
    on our worker thread.
    """

    def __init__(self, on_change) -> None:
        self._on_change = on_change
        self._client = None
        self._enum = None

    def start(self) -> bool:
        try:
            # Implemented here against pycaw's interface definition rather than
            # pycaw.callbacks, which would also pull psutil into the build.
            from comtypes import COMObject
            from pycaw.api.mmdeviceapi import IMMNotificationClient

            on_change = self._on_change

            class _Client(COMObject):
                _com_interfaces_ = (IMMNotificationClient,)

                def OnDeviceStateChanged(self, device_id, new_state):
                    on_change()

                def OnDeviceAdded(self, device_id):
                    on_change()

                def OnDeviceRemoved(self, device_id):
                    on_change()

                def OnDefaultDeviceChanged(self, flow, role, device_id):
                    on_change()

                def OnPropertyValueChanged(self, device_id, key):
                    pass  # very chatty, not needed

            self._enum = _enumerator()
            self._client = _Client()
            self._enum.RegisterEndpointNotificationCallback(self._client)
            return True
        except Exception as exc:  # noqa: BLE001
            log.warning("device change notifications unavailable, polling only: %r", exc)
            self._client = None
            return False

    def stop(self) -> None:
        if self._enum is not None and self._client is not None:
            try:
                self._enum.UnregisterEndpointNotificationCallback(self._client)
            except Exception:  # noqa: BLE001
                pass
        self._client = None
        self._enum = None
