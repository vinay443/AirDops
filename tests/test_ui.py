import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
QtWidgets = pytest.importorskip("PySide6.QtWidgets")

from airdops.ui import theme, widgets  # noqa: E402
from airdops.ui.model import ViewState  # noqa: E402
from airdops.ui.preview import CALL, CONNECTED, DISCONNECTED, render_all  # noqa: E402


@pytest.fixture(scope="module")
def app():
    a = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    theme.load_fonts()
    yield a


class Recorder:
    def __init__(self):
        self.calls = []

    def __getattr__(self, name):
        return lambda *a: self.calls.append((name, *a))


def test_renders_every_screen(app, tmp_path):
    paths = render_all(tmp_path)
    assert len(paths) == 10
    for p in paths:
        assert p.stat().st_size > 5000


def test_inter_font_loaded(app):
    from PySide6.QtGui import QFontDatabase

    assert "Inter" in QFontDatabase.families()


def test_panel_reflects_state_and_sends_actions(app):
    from airdops.ui.panel import Panel

    rec = Recorder()
    panel = Panel(rec)
    panel.set_state(CONNECTED)
    assert panel.batteries.isVisibleTo(panel) and not panel.hint.isVisibleTo(panel)
    assert panel.t_left.level == 80 and panel.t_case.charging
    assert panel.sw_ns.isChecked() and panel.row_ns.isEnabled()

    panel.sw_gate.click()  # user flips a switch
    assert ("set_setting", "voice_gate", True) in rec.calls

    panel.mode.set_index(1, animate=False)
    panel.mode.changed.emit(1)
    assert ("set_mode", "call") in rec.calls

    panel.set_state(DISCONNECTED)
    assert panel.hint.isVisibleTo(panel) and not panel.batteries.isVisibleTo(panel)
    assert not panel.row_ns.isEnabled()  # no VB-Cable in this sample
    assert panel.cable_link.isVisibleTo(panel)

    panel.set_state(CALL)
    assert not panel.row_mic.isEnabled()
    assert panel.status.text() == "Connected · Call Mode"


def test_programmatic_switch_does_not_emit(app):
    sw = widgets.Switch()
    fired = []
    sw.toggled.connect(lambda v: fired.append(v))
    sw.setChecked(True)
    assert sw.isChecked() and fired == []


def test_view_state_text():
    st = ViewState(connected=True, name="AirPods Pro", mode="game", left_in_ear=True, hfp_blocked=True)
    assert st.status_line() == "Connected · In Use · Game Mode"
    assert "can't switch" in st.mode_caption()
    assert ViewState().status_line() == "Not Connected"
    assert ViewState(left=40, right=20).lowest == 20


def test_hotkey_parse():
    from airdops.ui.hotkey import MOD_ALT, MOD_CONTROL, MOD_SHIFT, parse

    assert parse("Ctrl+Alt+M") == (MOD_CONTROL | MOD_ALT, ord("M"))
    assert parse("ctrl + shift + f9") == (MOD_CONTROL | MOD_SHIFT, 0x78)
    assert parse("Shift+M") is None  # would steal normal typing
    assert parse("M") is None
    assert parse("") is None
    assert parse("Ctrl+Alt+Space") is None


def test_welcome_and_new_rows(app):
    from airdops.ui.panel import Panel
    from airdops.ui.welcome import Welcome

    done = []
    w = Welcome(True, done.append, lambda: None)
    w.sw_login.setChecked(False)
    w._finish()
    assert done == [False]

    rec = Recorder()
    panel = Panel(rec)
    panel.set_state(CONNECTED)
    assert not panel.row_level.isHidden() and not panel.row_boost.isHidden()
    panel.boost.released.emit(9.0)
    assert ("set_gain", 9.0) in rec.calls
    panel.set_state(DISCONNECTED)
    assert panel.row_level.isHidden()


class FakeCore:
    """Just enough of airdops.core.Core for the shell."""

    def __init__(self):
        import types

        self.settings = types.SimpleNamespace(mode="game", hotkey="", onboarded=True)
        self.controller = types.SimpleNamespace(endpoints=[1])
        self.state = ViewState(name="AirPods Pro", connected=False)
        self.on_change = lambda: None
        self.snapshots = 0

    def snapshot(self):
        self.snapshots += 1
        return self.state

    def pop_notifications(self):
        return []

    def mic_level(self):
        return 0.0


def test_shell_refreshes_on_engine_events_not_a_fast_timer(app):
    import threading
    import time

    from airdops.ui.shell import Shell

    core = FakeCore()
    shell = Shell(core, background=True)
    try:
        assert shell.timer.interval() >= 2000  # housekeeping only
        assert core.on_change is not None
        shell._refresh()
        before = core.snapshots
        core.state = ViewState(name="AirPods Pro", connected=True)
        t = threading.Thread(target=core.on_change)  # engine threads call this
        t.start()
        t.join()
        deadline = time.monotonic() + 2
        while core.snapshots == before and time.monotonic() < deadline:
            app.processEvents()
        assert core.snapshots > before
        assert shell._last.connected
        assert not shell.meter_timer.isActive()  # panel closed: no 50 ms meter
    finally:
        shell.show_listener.stop()
        shell.hotkey.unregister()
        shell.panel.hide()
        shell.toast.hide()
