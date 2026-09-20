from __future__ import annotations

from ..core.compiler import Compiler


def for_compiler(compiler: Compiler):
    if compiler.kind == "rustc":
        from . import rust
        return rust
    from . import c
    return c
