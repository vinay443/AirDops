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
    assert len(paths) == 8
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
