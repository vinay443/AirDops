"""On GitHub Actions, report test failures as annotations (visible without the raw log)."""

from __future__ import annotations

import os
import sys


def _escape(text: str) -> str:
    return text.replace("%", "%25").replace("\r", "").replace("\n", "%0A")


def pytest_runtest_logreport(report):
    if not os.environ.get("GITHUB_ACTIONS") or not report.failed:
        return
    detail = str(report.longrepr)[-3000:]
    sys.__stdout__.write(f"::error title=Test failed: {report.nodeid}::{_escape(detail)}\n")
    sys.__stdout__.flush()


def pytest_collectreport(report):
    pytest_runtest_logreport(report)
