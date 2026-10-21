"""Print what makes up the AirDops download and enforce a size budget (CI).

Usage:  python scripts/size_report.py [--warn-only] dist/AirDops dist/AirDops-Setup.exe dist/AirDops-portable.zip

Lists the biggest bundled files, then the size of each download. Exits with 1
if a download is over its budget, so a dependency that bloats the bundle fails
the build instead of quietly slowing everyone's download. On GitHub Actions
the summary also goes to the job summary and to annotations.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

MIB = 1024 * 1024
# Budgets for each download (MiB). Raise them only on purpose.
BUDGETS = {
    "AirDops-Setup.exe": 20.0,
    "AirDops-portable.zip": 28.0,
}
TOP = 25


def human(n: int) -> str:
    return f"{n / MIB:6.2f} MiB" if n >= 100 * 1024 else f"{n / 1024:6.0f} KiB"


def main(args: list[str]) -> int:
    warn_only = "--warn-only" in args
    args = [a for a in args if a != "--warn-only"]
    lines: list[str] = []
    over: list[str] = []
    for arg in args:
        path = Path(arg)
        if path.is_dir():
            files = [(p.stat().st_size, p.relative_to(path).as_posix()) for p in path.rglob("*") if p.is_file()]
            total = sum(s for s, _ in files)
            lines.append(f"{path.name}/: {len(files)} files, {human(total)} unpacked. Biggest:")
            for size, name in sorted(files, reverse=True)[:TOP]:
                lines.append(f"  {human(size)}  {name}")
        elif path.is_file():
            size = path.stat().st_size
            budget = BUDGETS.get(path.name)
            verdict = ""
            if budget is not None:
                ok = size <= budget * MIB
                verdict = f"  (budget {budget:.0f} MiB: {'OK' if ok else 'OVER'})"
                if not ok:
                    over.append(path.name)
            lines.append(f"download {path.name}: {size:,} bytes = {human(size).strip()}{verdict}")
        else:
            lines.append(f"missing: {arg}")
            over.append(arg)
    report = "\n".join(lines)
    print(report)
    if os.environ.get("GITHUB_ACTIONS"):
        summary = os.environ.get("GITHUB_STEP_SUMMARY")
        if summary:
            with open(summary, "a", encoding="utf-8") as f:
                f.write("### Download sizes\n\n```\n" + report + "\n```\n")
        for line in lines:
            if line.startswith("download "):
                print(f"::notice title=Size::{line}")
        biggest = [line.strip() for line in lines if line.startswith("  ")]
        if biggest:
            print("::notice title=Biggest bundled files::" + "%0A".join(biggest))
        level = "warning" if warn_only else "error"
        for name in over:
            print(f"::{level} title=Size budget::{name} is over its size budget (see scripts/size_report.py)")
    return 1 if over and not warn_only else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
