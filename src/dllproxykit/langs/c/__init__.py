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
    return (
        _load("dll_stub.c")
        .replace("__IDX__", str(idx))
        .replace("__EXPORT_NAME__", escape_c_string(name))
    )


def _def_export_name(name: str) -> str:
    if name.isidentifier():
        return name
    return '"' + name.replace('"', "") + '"'


def _write_compat(proj: Path) -> None:
    (proj / "tcc_compat.h").write_text(_load("tcc_compat.h"), encoding="utf-8")


def write_dll(proj: Path, original_name: str, exports: Iterable[str]) -> tuple[Path, Path | None]:
    exports = list(exports)
    stubs = "".join(_stub(i, n) for i, n in enumerate(exports))
    if not stubs:
        stubs = "/* no named exports */\n"
    _write_compat(proj)
    src = proj / "proxy.c"
    src.write_text(
        _payload(_load("dll.c"))
        .replace("__ORIGINAL_DLL__", escape_c_string(original_name))
        .replace("__STUBS__", stubs),
        encoding="utf-8",
    )
    def_path = None
    if exports:
        lines = ["LIBRARY proxy", "EXPORTS"]
        for idx, name in enumerate(exports):
            lines.append(f"    {_def_export_name(name)}=stub_{idx}")
        def_path = proj / "proxy.def"
        def_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return src, def_path


def write_exe(proj: Path, original_name: str) -> Path:
    _write_compat(proj)
    src = proj / "proxy.c"
    src.write_text(
        _payload(_load("exe.c")).replace("__ORIGINAL_EXE__", escape_c_string(original_name)),
        encoding="utf-8",
    )
    return src
