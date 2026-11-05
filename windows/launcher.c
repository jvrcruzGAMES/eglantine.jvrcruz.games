#ifndef UNICODE
#define UNICODE
#endif
#ifndef _UNICODE
#define _UNICODE
#endif
#include <windows.h>
#include <wincrypt.h>
#include <wchar.h>
#include <stdlib.h>

int WINAPI wWinMain(HINSTANCE instance, HINSTANCE previous, PWSTR args, int show) {
    (void)instance; (void)previous; (void)show;
    WCHAR root[32768], system[32768];
    if (!GetModuleFileNameW(NULL, root, 32768) || !GetSystemDirectoryW(system, 32768)) return 1;
    WCHAR *slash = wcsrchr(root, L'\\');
    if (!slash) return 1;
    *slash = 0;
    const WCHAR *raw = *args ? args : L" ";
    DWORD count = 0;
    DWORD flags = CRYPT_STRING_BASE64 | CRYPT_STRING_NOCRLF;
    if (!CryptBinaryToStringW((const BYTE *)raw, (DWORD)(wcslen(raw) * sizeof(WCHAR)), flags, NULL, &count)) return 1;
    WCHAR *encoded = calloc(count, sizeof(WCHAR));
    if (!encoded) return 1;
    CryptBinaryToStringW((const BYTE *)raw, (DWORD)(wcslen(raw) * sizeof(WCHAR)), flags, encoded, &count);
    size_t capacity = wcslen(root) + wcslen(system) + count + 512;
    WCHAR *command = calloc(capacity, sizeof(WCHAR));
    WCHAR executable[32768];
    _snwprintf(executable, 32768, L"%ls\\WindowsPowerShell\\v1.0\\powershell.exe", system);
    _snwprintf(command, capacity, L"\"%ls\" -NoLogo -NoProfile -NonInteractive -WindowStyle Hidden -ExecutionPolicy RemoteSigned -File \"%ls\\updater.ps1\" -ArgsBase64 \"%ls\"", executable, root, encoded);
    STARTUPINFOW startup = {0}; startup.cb = sizeof(startup);
    PROCESS_INFORMATION process = {0};
    SetDllDirectoryW(L"");
    BOOL ok = CreateProcessW(executable, command, NULL, NULL, FALSE, CREATE_NO_WINDOW, NULL, root, &startup, &process);
    if (ok) { CloseHandle(process.hThread); CloseHandle(process.hProcess); }
    else MessageBoxW(NULL, L"The update launcher could not start Windows PowerShell. Repair the installation or check your Windows application policies.", L"Eglantine", MB_OK | MB_ICONERROR);
    free(command); free(encoded);
    return ok ? 0 : 1;
}
