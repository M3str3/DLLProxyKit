<div align="center">

<img width="736" height="304" alt="banner" src="banner.jpg" />


# DLLProxyKit

**DLL proxies that forward every export but they allow a payload to be executed.**

[![Rust](https://img.shields.io/badge/rust-1.74+-orange?logo=rust)](https://www.rust-lang.org/)
[![Platform](https://img.shields.io/badge/platform-Windows-blue)](#)

</div>

---

Generates a drop-in DLL replacement that forwards every named export to
`<name>_orig.dll` and runs `payload.txt` on load. Architecture-matched
(x86 / x64 / ARM64).

---

## Attacker Setup

```cmd
pip install pefile                         :: To run the DLL generator
rustup target add i686-pc-windows-msvc     :: To compile x86 DLLs
```

## Usage
```cmd
python src\dllproxymaker.py <input_dir> <output_dir> [--payload CMD] [--skip LIST] [--keep-going]

# Example
python src\dllproxymaker.py tests\dll-test tests\dll-output --payload "whoami > C:\Windows\Temp\pwned.txt" --keep-going
```
Output:
```text
dll-test/
  ├── vfcompat.dll          
  └── appverifUI.dll          
dll-output/
  ├── vfcompat.dll            ← proxy
  ├── vfcompat_orig.dll       ← original
  ├── appverifUI.dll          ← proxy
  ├── appverifUI_orig.dll     ← original
  └── payload.txt             ← runs on every DLL load
```
Deploy by copying *.dll and payload.txt together. Default payload:
```
whoami >> C:\Windows\Temp\pwned.txt.
```
You can change the payload.txt every time you want, without recompile everything

## Notes
One Rust stub per export; lazily forwards to the original via LoadLibraryW + GetProcAddress.

Ordinal-only exports are not forwarded.
Args assumed to be up to ten usize values (covers most Win32 APIs).
API set stubs (api-ms-win-*, ext-ms-win-*) are skipped.

# For authorised security testing and CTFs only.
