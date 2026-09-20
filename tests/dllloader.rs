// dllloader.rs — loads a DLL and optionally resolves an exported symbol.
//
// Compile for the host architecture (x64 by default):
//   rustc -O dllloader.rs -o dllloader.exe
//
// Compile for 32-bit (to test x86 DLLs):
//   rustup target add i686-pc-windows-msvc
//   rustc -O --target i686-pc-windows-msvc dllloader.rs -o dllloader32.exe
//
// Usage:
//   dllloader.exe <path_to_dll> [export_name]
//
// Exit codes:
//   0  success
//   1  load failure (path, GetLastError, etc.)
//   2  bad usage
//   3  architecture mismatch (detected before load)

use std::env;
use std::ffi::c_void;
use std::fs;
use std::path::Path;

type HMODULE = *mut c_void;
type FARPROC = *const c_void;
type BOOL    = i32;

#[link(name = "kernel32")]
extern "system" {
    fn LoadLibraryW(name: *const u16) -> HMODULE;
    fn GetProcAddress(h: HMODULE, name: *const u8) -> FARPROC;
    fn FreeLibrary(h: HMODULE) -> BOOL;
    fn GetLastError() -> u32;
}

// ---------------------------------------------------------------------
//  Constants
// ---------------------------------------------------------------------

/// Windows error code: the image has the wrong format for the caller.
const ERROR_BAD_EXE_FORMAT: u32 = 193;

// PE machine values (COFF header, IMAGE_FILE_HEADER.Machine).
const IMAGE_FILE_MACHINE_I386:  u16 = 0x014C;
const IMAGE_FILE_MACHINE_AMD64: u16 = 0x8664;
const IMAGE_FILE_MACHINE_ARM64: u16 = 0xAA64;

// IMAGE_FILE_HEADER.Characteristics flag indicating a DLL.
const IMAGE_FILE_DLL: u16 = 0x2000;

// ---------------------------------------------------------------------
//  Architecture helpers
// ---------------------------------------------------------------------

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum Arch {
    X86,
    X64,
    Arm64,
    Unknown(u16),
}

impl Arch {
    const fn from_machine(machine: u16) -> Self {
        match machine {
            IMAGE_FILE_MACHINE_I386  => Arch::X86,
            IMAGE_FILE_MACHINE_AMD64 => Arch::X64,
            IMAGE_FILE_MACHINE_ARM64 => Arch::Arm64,
            other                    => Arch::Unknown(other),
        }
    }

    const fn name(self) -> &'static str {
        match self {
            Arch::X86        => "x86 (32-bit)",
            Arch::X64        => "x64 (64-bit)",
            Arch::Arm64      => "ARM64",
            Arch::Unknown(_) => "unknown",
        }
    }
}

#[cfg(target_arch = "x86_64")]
const HOST_ARCH: Arch = Arch::X64;
#[cfg(target_arch = "x86")]
const HOST_ARCH: Arch = Arch::X86;
#[cfg(target_arch = "aarch64")]
const HOST_ARCH: Arch = Arch::Arm64;

// ---------------------------------------------------------------------
//  Minimal PE header reader
// ---------------------------------------------------------------------

/// Returns `(machine, is_dll)` from the COFF file header.
///
/// Layout we care about:
///   offset 0x00  e_magic        "MZ"
///   offset 0x3C  e_lfanew       file offset to the PE signature
///   e_lfanew+0x00  signature    "PE\0\0"
///   e_lfanew+0x04  Machine      u16
///   e_lfanew+0x16  Characteristics u16 (bit 0x2000 = IMAGE_FILE_DLL)
fn read_pe_info(path: &Path) -> std::io::Result<(u16, bool)> {
    let data = fs::read(path)?;

    if data.len() < 0x40 {
        return Err(std::io::Error::new(
            std::io::ErrorKind::InvalidData,
            "file too small to be a PE image",
        ));
    }
    if &data[0..2] != b"MZ" {
        return Err(std::io::Error::new(
            std::io::ErrorKind::InvalidData,
            "missing DOS header (MZ)",
        ));
    }

    let e_lfanew = u32::from_le_bytes([data[0x3C], data[0x3D], data[0x3E], data[0x3F]]) as usize;
    let coff = e_lfanew + 4;
    if coff + 20 > data.len() {
        return Err(std::io::Error::new(
            std::io::ErrorKind::InvalidData,
            "PE header out of bounds",
        ));
    }
    if &data[e_lfanew..e_lfanew + 4] != b"PE\0\0" {
        return Err(std::io::Error::new(
            std::io::ErrorKind::InvalidData,
            "invalid PE signature",
        ));
    }

    let machine = u16::from_le_bytes([data[coff], data[coff + 1]]);
    let characteristics = u16::from_le_bytes([data[coff + 18], data[coff + 19]]);
    let is_dll = (characteristics & IMAGE_FILE_DLL) != 0;

    Ok((machine, is_dll))
}

// ---------------------------------------------------------------------
//  Utilities
// ---------------------------------------------------------------------

fn wide(s: &str) -> Vec<u16> {
    s.encode_utf16().chain(std::iter::once(0)).collect()
}

// ---------------------------------------------------------------------
//  Entry point
// ---------------------------------------------------------------------

fn main() {
    let args: Vec<String> = env::args().collect();
    if args.len() < 2 {
        eprintln!("Usage: {} <path_to_dll> [export_name]", args[0]);
        std::process::exit(2);
    }

    println!("[*] Host process architecture: {}", HOST_ARCH.name());

    // Canonicalise to an absolute path so Windows does not apply its
    // default search order when the filename collides with a system one.
    let path = match fs::canonicalize(&args[1]) {
        Ok(p) => p,
        Err(e) => {
            eprintln!("[!] Cannot resolve '{}': {}", args[1], e);
            std::process::exit(1);
        }
    };

    if !path.is_file() {
        eprintln!("[!] Not a regular file: {}", path.display());
        std::process::exit(1);
    }

    println!("[*] Target DLL: {}", path.display());

    // -----------------------------------------------------------------
    // Pre-flight: inspect the PE header before handing the file to the
    // loader. This lets us diagnose architecture mismatches cleanly
    // rather than relying on a bare error code from LoadLibraryW.
    // -----------------------------------------------------------------
    match read_pe_info(&path) {
        Ok((machine, is_dll)) => {
            let target = Arch::from_machine(machine);
            println!("[*] Target architecture: {}", target.name());

            if !is_dll {
                eprintln!("[!] Warning: the file does not carry the IMAGE_FILE_DLL flag");
            }

            if target != HOST_ARCH {
                eprintln!(
                    "[!] Architecture mismatch: host is {}, target is {}",
                    HOST_ARCH.name(),
                    target.name()
                );
                eprintln!(
                    "[!] Windows cannot load a {} module into a {} process \
                     (ERROR_BAD_EXE_FORMAT, {}).",
                    target.name(),
                    HOST_ARCH.name(),
                    ERROR_BAD_EXE_FORMAT
                );
                eprintln!(
                    "[!] Rebuild the loader for the target's architecture, e.g. \
                     `rustc -O --target i686-pc-windows-msvc dllloader.rs -o dllloader32.exe`"
                );
                std::process::exit(3);
            }
        }
        Err(e) => {
            eprintln!("[!] Could not parse PE header: {}", e);
            // Fall through: LoadLibraryW will produce the definitive error.
        }
    }

    // -----------------------------------------------------------------
    // Attempt the load.
    // -----------------------------------------------------------------
    let h = unsafe { LoadLibraryW(wide(&path.to_string_lossy()).as_ptr()) };

    if h.is_null() {
        let err = unsafe { GetLastError() };
        eprintln!("[!] LoadLibraryW failed. GetLastError = {} (0x{:X})", err, err);

        if err == ERROR_BAD_EXE_FORMAT {
            eprintln!(
                "[!] ERROR_BAD_EXE_FORMAT usually means the module's architecture \
                 does not match the loader's."
            );
            eprintln!(
                "[!] Host is {}. Rebuild the loader for the target architecture.",
                HOST_ARCH.name()
            );
        }
        std::process::exit(1);
    }

    println!("[+] Loaded. HMODULE = {:p}", h);

    // -----------------------------------------------------------------
    // Optional export resolution.
    // -----------------------------------------------------------------
    if args.len() >= 3 {
        let sym = &args[2];

        // Build a NUL-terminated byte string without copying through String.
        let mut name = Vec::with_capacity(sym.len() + 1);
        name.extend_from_slice(sym.as_bytes());
        name.push(0);

        let proc = unsafe { GetProcAddress(h, name.as_ptr()) };
        if proc.is_null() {
            let err = unsafe { GetLastError() };
            eprintln!("[!] GetProcAddress(\"{}\") failed. GetLastError = {}", sym, err);
        } else {
            println!("[+] {} -> {:p}", sym, proc);
        }
    }

    // Give DllMain and any threads it spawns a moment to run before we
    // unload. FreeLibrary will not actually unload the module while
    // payload threads are still executing.
    println!("[*] Waiting 3 s for DllMain and spawned threads...");
    std::thread::sleep(std::time::Duration::from_secs(3));

    unsafe { FreeLibrary(h); }
    println!("[+] Done.");
}