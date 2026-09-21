from __future__ import annotations

from typing import NamedTuple

from ..pathscan import PathDir


class Finding(NamedTuple):
    kind: str
    source: str
    title: str
    account: str
    command: str
    target: str
    dest: PathDir
    scope: str
    why: str
