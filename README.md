<div align="center">

<img src="docs/banner.png" alt="DLLProxyKit" width="360"/>

# DLLProxyKit

**Rust DLL proxies that forward every export and fire a payload on load.**

[![Rust](https://img.shields.io/badge/rust-1.74+-orange?logo=rust)](https://www.rust-lang.org/)
[![Platform](https://img.shields.io/badge/platform-Windows-blue)](#)
[![License](https://img.shields.io/badge/license-MIT-lightgrey)](#license)

</div>

---

Generates a drop-in DLL replacement that forwards every named export to
`<name>_orig.dll` and runs `payload.txt` on load. Architecture-matched
(x86 / x64 / ARM64), built in Rust.

Typical uses: DLL search-order hijacking, red-team staging, CTF privesc.

---

## Setup

```cmd
pip install pefile
rustup target add i686-pc-windows-msvc     :: only for x86 DLLs

rustc -O src\dllloader.rs -o bin\dllloader.exe
rustc -O --target i686-pc-windows-msvc src\dllloader.rs -o bin\dllloader32.exe
```

## Usage
```cmd
python src\dllproxymaker.py <input_dir> <output_dir> [--payload CMD] [--skip LIST] [--keep-going]
```
Output per DLL:
```text
out/
├── name.dll          ← proxy
├── name_orig.dll     ← original
└── payload.txt       ← runs on load
```
Deploy by copying *.dll and payload.txt together. Default payload:
whoami >> C:\Windows\Temp\pwned.txt.
## Notes
One Rust stub per export; lazily forwards to the original via LoadLibraryW + GetProcAddress.

Ordinal-only exports are not forwarded.
Args assumed to be up to ten usize values (covers most Win32 APIs).
API set stubs (api-ms-win-*, ext-ms-win-*) are skipped.

- For authorised security testing and CTFs only.

MIT.