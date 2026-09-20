from __future__ import annotations

from functools import partial
from typing import Callable, NamedTuple

from .dll import run as run_dlls
from .exe import run as run_exes
from .script import run as run_scripts


class Kind(NamedTuple):
    ext: str
    proxy: Callable[..., int]
    compile: bool = True


KINDS = (
    Kind(ext=".dll", proxy=run_dlls, compile=True),
    Kind(ext=".exe", proxy=run_exes, compile=True),
    Kind(ext=".bat", proxy=partial(run_scripts, ext=".bat"), compile=False),
    Kind(ext=".cmd", proxy=partial(run_scripts, ext=".cmd"), compile=False),
    Kind(ext=".ps1", proxy=partial(run_scripts, ext=".ps1"), compile=False),
    Kind(ext=".pl", proxy=partial(run_scripts, ext=".pl"), compile=False),
    Kind(ext=".py", proxy=partial(run_scripts, ext=".py"), compile=False),
)


def parse_kinds(spec: str | None) -> list[Kind]:
    if not spec:
        return list(KINDS)
    out: list[Kind] = []
    seen: set[str] = set()
    for raw in spec.split(","):
        token = raw.strip().lower().lstrip(".")
        if not token:
            continue
        kind = next((k for k in KINDS if k.ext[1:] == token), None)
        if kind is None:
            known = ",".join(k.ext[1:] for k in KINDS)
            raise ValueError(f"unknown kind {raw.strip()!r}  (want {known})")
        if kind.ext not in seen:
            seen.add(kind.ext)
            out.append(kind)
    if not out:
        raise ValueError("no kinds selected")
    return out
