<div align="center">

<img width="736" height="304" alt="banner" src="banner.jpg" />


# DLLProxyKit

**DLL proxies that forward every export but they allow a payload to be executed.**

[![C](https://img.shields.io/badge/C-MSVC%20%7C%20MinGW%20%7C%20tcc-blue)](#)
[![Platform](https://img.shields.io/badge/platform-Windows-blue)](#)

</div>

---

Generates a drop-in DLL replacement that forwards every named export to
`<name>.original.dll` and runs `payload.txt` on load (local file first, else
`C:\Windows\Temp\payload.txt`). Architecture-matched (x86 / x64 / ARM64).

---
<div align="center">
<img width="600" height="607" alt="image" src="https://github.com/user-attachments/assets/8a2f5b12-f882-42b3-b6ac-901fdb2cf0b1" />
</div>

## Usage

### Build a binary
```
./build.cmd
```
### Automatic exploit Path Hijacking for DLL,Exe & scripting langs
```
./dist/DLLProxyKit --auto
```

### DLL proxy a specific folder
```cmd
proxykit <input> <?output?> [options]
python ./src/dllproxykit tests\dlls-test tests\dlls-output --keep-going
```
Output:
```text
dll-test/
  ├── vfcompat.dll          
  └── appverifUI.dll          
dll-output/
  ├── vfcompat.dll            ← proxy
  ├── vfcompat.original.dll   ← original
  ├── appverifUI.dll          ← proxy
  └── appverifUI.original.dll ← original
```
Payload is written to `C:\Windows\Temp\payload.txt` (not overwritten if it
already exists). A `payload.txt` next to the proxy wins if present. Default payload in `src/DLLProxyKit/core/common.py`.

You can change the payload.txt every time you want, without recompile everything.

## Notes
One C stub per export; lazily forwards to the original via LoadLibraryW + GetProcAddress.

Ordinal-only exports are not forwarded.
Args assumed to be up to ten usize values (covers most Win32 APIs).
API set stubs (api-ms-win-*, ext-ms-win-*) are skipped.

# For authorised security testing and CTFs only.
