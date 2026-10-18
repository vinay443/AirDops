"""PyInstaller entry point (keeps the package's relative imports working)."""

import sys

from airdops.__main__ import main

if __name__ == "__main__":
    sys.exit(main())
