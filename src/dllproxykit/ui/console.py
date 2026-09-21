from __future__ import annotations

import ctypes
import sys

_USE = False
_VERBOSE = False

_RESET = "\033[0m"
_BOLD = "\033[1m"
_DIM = "\033[2m"
_RED = "\033[31m"
_GREEN = "\033[32m"
_YELLOW = "\033[33m"
_CYAN = "\033[36m"
_HOT = "\033[4;30;48;2;232;90;80m"
_YELL = "\033[30;43m"
_UNDER = "\033[4m"


def setup(*, verbose: bool = False) -> None:
    global _USE, _VERBOSE
    _VERBOSE = verbose
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    _USE = sys.stdout.isatty()
    if not _USE or sys.platform != "win32":
        return
    try:
        handle = ctypes.windll.kernel32.GetStdHandle(-11)
        mode = ctypes.c_uint32()
        if ctypes.windll.kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
            ctypes.windll.kernel32.SetConsoleMode(handle, mode.value | 0x0004)
    except Exception:
        _USE = False


def _paint(code: str, text: str) -> str:
    if not _USE:
        return text
    return f"{code}{text}{_RESET}"


def bold(text: str) -> str:
    return _paint(_BOLD, text)


def dim(text: str) -> str:
    return _paint(_DIM, text)


def hot(text: str) -> str:
    return _paint(_HOT, text)


def yell(text: str) -> str:
    return _paint(_YELL, text)


def green(text: str) -> str:
    return _paint(_GREEN, text)


def under(text: str) -> str:
    return _paint(_BOLD + _UNDER, text)


def section(title: str) -> None:
    print()
    print(f"  {_paint(_CYAN + _BOLD, title)}")


def ok(msg: str, indent: int = 2) -> None:
    print(f"{' ' * indent}{_paint(_GREEN, '✓')}  {msg}")


def warn(msg: str, indent: int = 2) -> None:
    print(f"{' ' * indent}{_paint(_YELLOW, '!')}  {msg}")


def fail(msg: str, indent: int = 2) -> None:
    print(f"{' ' * indent}{_paint(_RED, '✗')}  {msg}")


def info(msg: str, indent: int = 2) -> None:
    print(f"{' ' * indent}{dim('·')}  {msg}")


def item(msg: str, indent: int = 4) -> None:
    print(f"{' ' * indent}{msg}")


def is_verbose() -> bool:
    return _VERBOSE


def debug(msg: str, indent: int = 2) -> None:
    if not _VERBOSE:
        return
    print(f"{' ' * indent}{dim('…')}  {msg}")


def debug_exc() -> None:
    if not _VERBOSE:
        return
    import traceback

    for line in traceback.format_exc().splitlines():
        debug(line)
