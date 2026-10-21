"""Entry point: ``python -m airdops`` or the packaged AirDops.exe."""

from __future__ import annotations

import argparse
import ctypes
import logging
import sys
from logging.handlers import RotatingFileHandler


def _setup_logging(verbose: bool) -> None:
    from . import config

    config.log_dir().mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(config.log_dir() / "airdops.log", maxBytes=512_000, backupCount=3, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)-7s %(name)s: %(message)s"))
    root = logging.getLogger()
    root.addHandler(handler)
    root.setLevel(logging.DEBUG if verbose else logging.INFO)
    if sys.stderr is not None:
        root.addHandler(logging.StreamHandler())
    _install_crash_handlers(handler)
    # Quiet chatty libraries.
    for name in ("bleak", "comtypes", "PIL"):
        logging.getLogger(name).setLevel(logging.WARNING)


_fault_file = None


def _install_crash_handlers(handler) -> None:
    """Log every uncaught exception (any thread) and native crashes."""
    import faulthandler
    import threading

    log = logging.getLogger("airdops.crash")

    def excepthook(exc_type, exc, tb):
        log.critical("uncaught exception", exc_info=(exc_type, exc, tb))

    def thread_hook(args):
        if args.exc_type is not SystemExit:
            log.critical("uncaught exception in thread %s", getattr(args.thread, "name", "?"),
                         exc_info=(args.exc_type, args.exc_value, args.exc_traceback))

    sys.excepthook = excepthook
    threading.excepthook = thread_hook
    global _fault_file
    try:
        from . import config

        _fault_file = open(config.log_dir() / "crash.log", "a", encoding="utf-8")  # noqa: SIM115
        faulthandler.enable(file=_fault_file)
    except OSError:
        pass


def _message_box(text: str, title: str = "AirDops") -> None:
    if sys.platform == "win32":
        ctypes.windll.user32.MessageBoxW(None, text, title, 0x40)
    elif sys.stderr is not None:
        print(text, file=sys.stderr)


_mutex = None


def _single_instance() -> bool:
    global _mutex
    if sys.platform != "win32":
        return True
    kernel32 = ctypes.windll.kernel32
    _mutex = kernel32.CreateMutexW(None, False, "Local\\AirDops-single-instance")
    return kernel32.GetLastError() != 183  # ERROR_ALREADY_EXISTS


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="AirDops", description="Full-quality AirPods audio for gaming on Windows.")
    parser.add_argument("--background", action="store_true", help="start quietly (used by 'Start with Windows')")
    parser.add_argument("--diagnose", action="store_true", help="write a diagnostics report and open it")
    parser.add_argument("--restore", action="store_true", help="undo every change AirDops made, then exit")
    parser.add_argument("--self-test", metavar="REPORT", help="(CI) check the build and write a report")
    parser.add_argument("--uninstall", action="store_true", help="(installer) restore audio and remove the login item")
    parser.add_argument("--quiet", action="store_true", help="no message boxes (used by the uninstaller)")
    parser.add_argument("--verbose", action="store_true", help="debug logging")
    args = parser.parse_args(argv)

    if args.self_test:
        from .diagnostics import self_test

        return self_test(args.self_test)

    _setup_logging(args.verbose)

    if sys.platform != "win32":
        _message_box("AirDops runs on Windows only.")
        return 2

    if args.diagnose:
        from .diagnostics import run_and_open

        run_and_open()
        return 0

    if not _single_instance():
        if args.restore or args.uninstall:
            if not args.quiet:
                _message_box("Quit AirDops from the tray first, then run --restore.")
            return 1
        if not args.background:
            from .instance import signal_running_instance

            if not signal_running_instance():
                _message_box("AirDops is already running - click the AirPods icon in the system tray.")
        return 0

    if args.uninstall:
        args.restore = True
    if args.restore:
        from . import config
        from .audio.endpoints import com_init
        from .core import make_controller

        com_init()
        make_controller(config.load_settings(), config.load_state()).restore_all()
        if args.uninstall:
            from . import startup

            startup.set_enabled(False)
        if not args.quiet:
            _message_box("AirDops changes have been undone.")
        return 0

    try:
        from .core import Core
        from .ui.shell import Shell

        return Shell(Core(), background=args.background).run()
    except Exception:
        logging.getLogger("airdops").exception("fatal error")
        _message_box("AirDops hit an error and closed. Details are in the log folder.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
