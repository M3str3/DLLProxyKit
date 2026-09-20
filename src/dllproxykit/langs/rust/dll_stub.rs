#[export_name = "__EXPORT_NAME__"]
pub extern "system" fn __stub___IDX__(
    a1: usize, a2: usize, a3: usize, a4: usize, a5: usize,
    a6: usize, a7: usize, a8: usize, a9: usize, a10: usize,
) -> usize {
    unsafe {
        let f = resolve(b"__EXPORT_NAME__\0");
        if f.is_null() { return 0; }
        let f: extern "system" fn(
            usize, usize, usize, usize, usize,
            usize, usize, usize, usize, usize,
        ) -> usize = std::mem::transmute(f);
        f(a1, a2, a3, a4, a5, a6, a7, a8, a9, a10)
    }
}
