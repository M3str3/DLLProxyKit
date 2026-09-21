import sys
from pathlib import Path

_src = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_src))

from dllproxykit.cli import main

if __name__ == "__main__":
    raise SystemExit(main())
