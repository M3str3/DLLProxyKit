from __future__ import annotations

from importlib.resources import files
from pathlib import Path
from typing import Iterable

from ...core.common import PAYLOAD_FALLBACK, PAYLOAD_NAME, escape_c_string


def _load(name: str) -> str:
    return files(__package__).joinpath(name).read_text(encoding="utf-8")


def _payload(text: str) -> str:
    return (
        text.replace("__PAYLOAD_NAME__", escape_c_string(PAYLOAD_NAME))
        .replace("__PAYLOAD_FALLBACK__", escape_c_string(str(PAYLOAD_FALLBACK)))
    )


def _stub(idx: int, name: str) -> str:
    escaped = escape_c_string(name)
    return (
        _load("dll_stub.rs")
        .replace("__IDX__", str(idx))
        .replace("__EXPORT_NAME__", escaped)
    )


def write_dll(proj: Path, original_name: str, exports: Iterable[str]) -> tuple[Path, Path | None]:
    exports = list(exports)
    stubs = "".join(_stub(i, n) for i, n in enumerate(exports))
    if not stubs:
        stubs = "// no named exports\n"
    src = proj / "lib.rs"
    src.write_text(
        _payload(_load("dll.rs"))
        .replace("__ORIGINAL_DLL__", escape_c_string(original_name))
        .replace("__STUBS__", stubs),
        encoding="utf-8",
    )
    return src, None


def write_exe(proj: Path, original_name: str) -> Path:
    src = proj / "main.rs"
    src.write_text(
        _payload(_load("exe.rs")).replace("__ORIGINAL_EXE__", escape_c_string(original_name)),
        encoding="utf-8",
    )
    return src
