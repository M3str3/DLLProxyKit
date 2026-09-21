from __future__ import annotations

from . import art
from .console import (
    bold,
    debug,
    debug_exc,
    dim,
    fail,
    green,
    hot,
    info,
    is_verbose,
    item,
    ok,
    section,
    setup,
    under,
    warn,
    yell,
)


def _compose_rows(icon: str, text: str, gap: int = 4) -> tuple[int, list[tuple[str, str]]]:
    left = [line.rstrip() for line in icon.strip("\n").splitlines()]
    right = [line.rstrip() for line in text.strip("\n").splitlines()]
    width = max((len(line) for line in left), default=0) + gap
    offset = max(0, (len(left) - len(right)) // 2)
    rows: list[tuple[str, str]] = []
    n = max(len(left), offset + len(right))
    for i in range(n):
        l = left[i] if i < len(left) else ""
        ri = i - offset
        r = right[ri] if 0 <= ri < len(right) else ""
        rows.append((l, r))
    return width, rows




def _banner_text() -> str:
    meta = f"Author: {art.AUTHOR}    Version: {art.VERSION}"
    return art.BANNER.rstrip() + "\n" + meta


def banner() -> None:
    print()
    width, rows = _compose_rows(art.ASCII_ART, _banner_text())
    for left, right in rows:
        if right.startswith("Author:"):
            print(f"  {bold(f'{left:<{width}}')}{dim(right)}")
        else:
            print(f"  {bold(f'{left:<{width}}{right}'.rstrip())}")
    print()
