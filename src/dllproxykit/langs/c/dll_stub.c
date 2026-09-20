uintptr_t WINAPI stub___IDX__(
    uintptr_t a1, uintptr_t a2, uintptr_t a3, uintptr_t a4, uintptr_t a5,
    uintptr_t a6, uintptr_t a7, uintptr_t a8, uintptr_t a9, uintptr_t a10)
{
    fn10 f = (fn10)resolve("__EXPORT_NAME__");
    if (!f) {
        return 0;
    }
    return f(a1, a2, a3, a4, a5, a6, a7, a8, a9, a10);
}
