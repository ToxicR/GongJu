#include "screen_mirror.h"
#include "adb_helper.h"
#include <windows.h>
#include <string>
#include <vector>
#include <thread>
#include <atomic>
#include <cstdio>
#include <gdiplus.h>

#pragma comment(lib, "gdiplus.lib")

static std::string g_adb_path;
static std::atomic<bool> g_preview_running{ false };
static int g_scale_num = 1, g_scale_den = 1;
static int g_offset_x = 0, g_offset_y = 0;
static int g_shown_w = 0, g_shown_h = 0;
static int g_orig_w = 0, g_orig_h = 0;
static HBITMAP g_hPreviewBmp = nullptr;
static HWND g_hPreviewStatic = nullptr;
static ULONG_PTR g_gdiplusToken = 0;

static void preview_thread(HWND hwnd) {
    const int interval_ms = 1000 / 8;
    while (g_preview_running) {
        auto t0 = GetTickCount();
        std::vector<uint8_t> png;
        if (!adb::run_adb_exec_out(g_adb_path, "screencap -p", &png) || png.empty()) {
            Sleep(interval_ms);
            continue;
        }
        wchar_t tmpPath[MAX_PATH];
        GetTempPathW(MAX_PATH, tmpPath);
        wchar_t tmpFile[MAX_PATH];
        GetTempFileNameW(tmpPath, L"sc", 0, tmpFile);
        FILE* f = _wfopen(tmpFile, L"wb");
        if (f) {
            fwrite(png.data(), 1, png.size(), f);
            fclose(f);
            Gdiplus::Bitmap* bmp = Gdiplus::Bitmap::FromFile(tmpFile);
            DeleteFileW(tmpFile);
            if (bmp && bmp->GetLastStatus() == Gdiplus::Ok) {
                int w = bmp->GetWidth();
                int h = bmp->GetHeight();
                RECT rc;
                GetClientRect(GetDlgItem(hwnd, 402), &rc);
                int cw = rc.right - rc.left;
                int ch = rc.bottom - rc.top;
                if (cw > 0 && ch > 0 && w > 0 && h > 0) {
                    double scale = (double)cw / w;
                    if ((double)ch / h < scale) scale = (double)ch / h;
                    int nw = (int)(w * scale);
                    int nh = (int)(h * scale);
                    g_orig_w = w;
                    g_orig_h = h;
                    g_shown_w = nw;
                    g_shown_h = nh;
                    g_offset_x = (cw - nw) / 2;
                    g_offset_y = (ch - nh) / 2;
                    g_scale_num = w;
                    g_scale_den = (nw > 0) ? nw : 1;
                    HBITMAP hOld = g_hPreviewBmp;
                    HDC hdcScreen = GetDC(nullptr);
                    g_hPreviewBmp = CreateCompatibleBitmap(hdcScreen, nw, nh);
                    ReleaseDC(nullptr, hdcScreen);
                    if (g_hPreviewBmp) {
                        HDC hdcMem = CreateCompatibleDC(nullptr);
                        SelectObject(hdcMem, g_hPreviewBmp);
                        Gdiplus::Graphics gr(hdcMem);
                        gr.DrawImage(bmp, 0, 0, nw, nh);
                        DeleteDC(hdcMem);
                        if (g_hPreviewStatic)
                            SendMessageW(g_hPreviewStatic, STM_SETIMAGE, IMAGE_BITMAP, (LPARAM)g_hPreviewBmp);
                        if (hwnd) InvalidateRect(GetDlgItem(hwnd, 402), nullptr, TRUE);
                        if (hOld) DeleteObject(hOld);
                    }
                }
                delete bmp;
            }
        }
        DWORD elapsed = GetTickCount() - t0;
        if (elapsed < (DWORD)interval_ms) Sleep(interval_ms - elapsed);
    }
}

static void on_preview_click(int x, int y) {
    if (!g_preview_running || g_scale_den <= 0) return;
    int dx = (x - g_offset_x) * g_scale_num / g_scale_den;
    int dy = (y - g_offset_y) * g_scale_num / g_scale_den;
    if (dx < 0) dx = 0;
    if (dy < 0) dy = 0;
    char cmd[128];
    snprintf(cmd, sizeof(cmd), "shell input tap %d %d", dx, dy);
    adb::run_adb(g_adb_path, cmd, nullptr, nullptr);
}

static WNDPROC g_origStaticProc = nullptr;
static LRESULT CALLBACK preview_static_proc(HWND hwnd, UINT msg, WPARAM wp, LPARAM lp) {
    if (msg == WM_LBUTTONDOWN) {
        int x = GET_X_LPARAM(lp);
        int y = GET_Y_LPARAM(lp);
        on_preview_click(x, y);
    }
    return CallWindowProcW(g_origStaticProc, hwnd, msg, wp, lp);
}

static LRESULT CALLBACK mirror_wnd_proc(HWND hwnd, UINT msg, WPARAM wp, LPARAM lp) {
    switch (msg) {
    case WM_CREATE: {
        CreateWindowW(L"BUTTON", L"\u542f\u52a8\u89c6\u9891\u6d41\u6295\u5c4f\uff08scrcpy\uff09", WS_CHILD | WS_VISIBLE, 12, 12, 180, 28, hwnd, (HMENU)401, nullptr, nullptr);
        CreateWindowW(L"BUTTON", L"\u5f00\u59cb\u9884\u89c8\uff08\u622a\u5c4f\uff09", WS_CHILD | WS_VISIBLE, 200, 12, 120, 28, hwnd, (HMENU)403, nullptr, nullptr);
        g_hPreviewStatic = CreateWindowW(L"STATIC", nullptr, WS_CHILD | WS_VISIBLE | SS_BITMAP, 12, 48, 760, 520, hwnd, (HMENU)402, nullptr, nullptr);
        if (g_hPreviewStatic)
            g_origStaticProc = (WNDPROC)SetWindowLongPtrW(g_hPreviewStatic, GWLP_WNDPROC, (LONG_PTR)preview_static_proc);
        return 0;
    }
    case WM_COMMAND:
        switch (LOWORD(wp)) {
        case 401: {
            std::string scrcpy = adb::find_scrcpy();
            if (scrcpy.empty()) {
                MessageBoxW(hwnd, L"\u8bf7\u5148\u5b89\u88c5 scrcpy\uff08\u5982 winget install scrcpy\uff09\u3002", L"\u89c6\u9891\u6d41", MB_OK);
                break;
            }
            STARTUPINFOA si = {};
            si.cb = sizeof(si);
            PROCESS_INFORMATION pi = {};
            std::string cmd = "\"" + scrcpy + "\" --no-audio\0";
            std::vector<char> buf(cmd.begin(), cmd.end());
            buf.push_back('\0');
            if (CreateProcessA(nullptr, buf.data(), nullptr, nullptr, FALSE, 0, nullptr, nullptr, &si, &pi)) {
                CloseHandle(pi.hProcess);
                CloseHandle(pi.hThread);
            }
            break;
        }
        case 403:
            if (g_preview_running) {
                g_preview_running = false;
                SetWindowTextW(GetDlgItem(hwnd, 403), L"\u5f00\u59cb\u9884\u89c8");
            } else {
                g_preview_running = true;
                SetWindowTextW(GetDlgItem(hwnd, 403), L"\u505c\u6b62\u9884\u89c8");
                std::thread t(preview_thread, hwnd);
                t.detach();
            }
            break;
        }
        return 0;
    case WM_CLOSE:
        g_preview_running = false;
        if (g_hPreviewBmp) { DeleteObject(g_hPreviewBmp); g_hPreviewBmp = nullptr; }
        DestroyWindow(hwnd);
        return 0;
    }
    return DefWindowProcW(hwnd, msg, wp, lp);
}

void screen_mirror_show(HWND parent, const std::string& adb_path) {
    g_adb_path = adb_path;
    Gdiplus::GdiplusStartupInput input;
    if (g_gdiplusToken == 0)
        Gdiplus::GdiplusStartup(&g_gdiplusToken, &input, nullptr);
    static bool reg = false;
    if (!reg) {
        WNDCLASSEXW wc = {};
        wc.cbSize = sizeof(wc);
        wc.lpfnWndProc = mirror_wnd_proc;
        wc.hInstance = GetModuleHandle(nullptr);
        wc.lpszClassName = L"ScreenMirrorWnd";
        wc.hbrBackground = (HBRUSH)(COLOR_WINDOW + 1);
        RegisterClassExW(&wc);
        reg = true;
    }
    HWND hwnd = CreateWindowExW(0, L"ScreenMirrorWnd", L"Android \u6295\u5c4f",
        WS_OVERLAPPEDWINDOW, CW_USEDEFAULT, CW_USEDEFAULT, 800, 600, parent, nullptr, GetModuleHandle(nullptr), nullptr);
    if (hwnd) ShowWindow(hwnd, SW_SHOW);
}
