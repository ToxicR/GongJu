#include "main_window.h"
#include "adb_helper.h"
#include "log_viewer.h"
#include "adb_browser.h"
#include "screen_mirror.h"
#include <string>
#include <commctrl.h>

#pragma comment(lib, "comctl32.lib")

static std::string g_adb_path;
static HWND g_hMain = nullptr;

static std::wstring utf8_to_wide(const std::string& utf8) {
    if (utf8.empty()) return L"";
    int n = MultiByteToWideChar(CP_UTF8, 0, utf8.c_str(), (int)utf8.size(), nullptr, 0);
    if (n <= 0) return L"";
    std::wstring w(n, 0);
    MultiByteToWideChar(CP_UTF8, 0, utf8.c_str(), (int)utf8.size(), &w[0], n);
    return w;
}

static void on_btn_log(HWND) {
    if (g_adb_path.empty()) return;
    log_viewer_show(g_hMain, g_adb_path);
}

static void on_btn_browser(HWND) {
    if (g_adb_path.empty()) return;
    adb_browser_show(g_hMain, g_adb_path);
}

static void on_btn_mirror(HWND) {
    if (g_adb_path.empty()) return;
    screen_mirror_show(g_hMain, g_adb_path);
}

static LRESULT CALLBACK main_wnd_proc(HWND hwnd, UINT msg, WPARAM wp, LPARAM lp) {
    switch (msg) {
    case WM_CREATE: {
        int y = 50;
        CreateWindowW(L"BUTTON", L"1. \u65e5\u5fd7\u8f93\u51fa\u529f\u80fd", WS_CHILD | WS_VISIBLE | BS_PUSHBUTTON,
            80, y, 320, 48, hwnd, (HMENU)101, nullptr, nullptr);
        y += 56;
        CreateWindowW(L"BUTTON", L"2. ADB \u6587\u4ef6\u6d4f\u89c8\u5668", WS_CHILD | WS_VISIBLE | BS_PUSHBUTTON,
            80, y, 320, 48, hwnd, (HMENU)102, nullptr, nullptr);
        y += 56;
        CreateWindowW(L"BUTTON", L"3. \u6295\u5c4f", WS_CHILD | WS_VISIBLE | BS_PUSHBUTTON,
            80, y, 320, 48, hwnd, (HMENU)103, nullptr, nullptr);
        return 0;
    }
    case WM_COMMAND:
        switch (LOWORD(wp)) {
        case 101: on_btn_log(hwnd); break;
        case 102: on_btn_browser(hwnd); break;
        case 103: on_btn_mirror(hwnd); break;
        }
        return 0;
    case WM_DESTROY:
        PostQuitMessage(0);
        return 0;
    case WM_PAINT: {
        PAINTSTRUCT ps;
        HDC hdc = BeginPaint(hwnd, &ps);
        SetBkMode(hdc, TRANSPARENT);
        TextOutW(hdc, 40, 12, L"\u8bf7\u9009\u62e9\u8981\u4f7f\u7528\u7684\u529f\u80fd", 10);
        EndPaint(hwnd, &ps);
        return 0;
    }
    }
    return DefWindowProcW(hwnd, msg, wp, lp);
}

void register_main_window_class() {
    WNDCLASSEXW wc = {};
    wc.cbSize = sizeof(wc);
    wc.style = CS_HREDRAW | CS_VREDRAW;
    wc.lpfnWndProc = main_wnd_proc;
    wc.hInstance = GetModuleHandle(nullptr);
    wc.hCursor = LoadCursor(nullptr, IDC_ARROW);
    wc.hbrBackground = (HBRUSH)(COLOR_WINDOW + 1);
    wc.lpszClassName = L"GongjuMainWnd";
    RegisterClassExW(&wc);
}

HWND create_main_window() {
    g_adb_path = adb_helper::find_adb();
    if (g_adb_path.empty()) {
        MessageBoxW(nullptr, L"\u672a\u627e\u5230 ADB\uff0c\u8bf7\u5b89\u88c5 Android SDK Platform-Tools \u6216\u5c06 adb \u52a0\u5165 PATH\u3002",
            L"\u9519\u8bef", MB_OK | MB_ICONWARNING);
        return nullptr;
    }
    std::vector<std::string> devs;
    if (!adb_helper::check_devices(g_adb_path, &devs) || devs.empty()) {
        MessageBoxW(nullptr, L"\u8bf7\u8fde\u63a5 Android \u8bbe\u5907\u5e76\u5f00\u5427 USB \u8c03\u8bd5\u3002",
            L"\u672a\u68c0\u6d4b\u5230\u8bbe\u5907", MB_OK | MB_ICONWARNING);
    }

    g_hMain = CreateWindowExW(0, L"GongjuMainWnd", L"\u5de5\u5177\u8f6f\u4ef6",
        WS_OVERLAPPEDWINDOW, CW_USEDEFAULT, CW_USEDEFAULT, 480, 320, nullptr, nullptr, GetModuleHandle(nullptr), nullptr);
    return g_hMain;
}
