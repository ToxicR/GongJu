#include "adb_browser.h"
#include "adb_helper.h"
#include <windows.h>
#include <commctrl.h>
#include <string>
#include <vector>
#include <algorithm>
#include <shlobj.h>

static std::string g_adb_path;
static std::string g_current_path = "/";

static std::wstring utf8_to_wide(const std::string& s) {
    if (s.empty()) return L"";
    int n = MultiByteToWideChar(CP_UTF8, 0, s.c_str(), (int)s.size(), nullptr, 0);
    if (n <= 0) return L"";
    std::wstring w(n, 0);
    MultiByteToWideChar(CP_UTF8, 0, s.c_str(), (int)s.size(), &w[0], n);
    return w;
}

struct BrowserState {
    HWND hPathEdit;
    HWND hList;
    std::string current_path;
};

static void refresh_list(BrowserState* state) {
    ListBox_ResetContent(state->hList);
    std::vector<adb::DirEntry> items;
    std::string err;
    if (!adb::list_dir(g_adb_path, state->current_path, &items, &err)) {
        ListBox_AddString(state->hList, utf8_to_wide(err).c_str());
        return;
    }
    std::sort(items.begin(), items.end(), [](const adb::DirEntry& a, const adb::DirEntry& b) {
        if (a.isDir != b.isDir) return a.isDir;
        return a.name < b.name;
    });
    for (const auto& e : items) {
        std::wstring line = utf8_to_wide(e.isDir ? "[\u76ee\u5f55] " : "[\u6587\u4ef6] ");
        line += utf8_to_wide(e.name);
        ListBox_AddString(state->hList, line.c_str());
    }
}

static void on_sel(BrowserState* state, int idx) {
    std::vector<adb::DirEntry> items;
    std::string err;
    if (!adb::list_dir(g_adb_path, state->current_path, &items, &err)) return;
    std::sort(items.begin(), items.end(), [](const adb::DirEntry& a, const adb::DirEntry& b) {
        if (a.isDir != b.isDir) return a.isDir;
        return a.name < b.name;
    });
    if (idx < 0 || idx >= (int)items.size()) return;
    const auto& e = items[idx];
    std::string full = state->current_path;
    if (full != "/") full += "/";
    full += e.name;
    if (e.isDir) {
        state->current_path = full;
        SetWindowTextA(state->hPathEdit, state->current_path.c_str());
        refresh_list(state);
    } else {
        BROWSEINFOW bi = {};
        wchar_t path[MAX_PATH] = {};
        bi.hwndOwner = GetParent(state->hList);
        bi.lpszTitle = L"\u9009\u62e9\u4fdd\u5b58\u76ee\u5f55";
        LPITEMIDLIST pidl = SHBrowseForFolderW(&bi);
        if (pidl) {
            if (SHGetPathFromIDListW(pidl, path)) {
                std::string dest;
                int n = WideCharToMultiByte(CP_UTF8, 0, path, -1, nullptr, 0, nullptr, nullptr);
                dest.resize(n);
                WideCharToMultiByte(CP_UTF8, 0, path, -1, &dest[0], n, nullptr, nullptr);
                dest.pop_back();
                adb::run_adb(g_adb_path, "pull \"" + full + "\" \"" + dest + "\"", nullptr, nullptr);
                MessageBoxW(GetParent(state->hList), L"\u5bfc\u51fa\u5b8c\u6210", L"\u5bfc\u51fa", MB_OK);
            }
            CoTaskMemFree(pidl);
        }
    }
}

static LRESULT CALLBACK browser_wnd_proc(HWND hwnd, UINT msg, WPARAM wp, LPARAM lp) {
    BrowserState* state = (BrowserState*)GetWindowLongPtrW(hwnd, GWLP_USERDATA);
    switch (msg) {
    case WM_CREATE: {
        state = new BrowserState();
        state->current_path = "/";
        SetWindowLongPtrW(hwnd, GWLP_USERDATA, (LONG_PTR)state);
        CreateWindowW(L"STATIC", L"\u8def\u5f84\uff1a", WS_CHILD | WS_VISIBLE, 12, 12, 40, 24, hwnd, nullptr, nullptr, nullptr);
        state->hPathEdit = CreateWindowW(L"EDIT", L"/", WS_CHILD | WS_VISIBLE | WS_BORDER, 56, 10, 320, 24, hwnd, nullptr, nullptr, nullptr);
        CreateWindowW(L"BUTTON", L"\u8f6c\u5230", WS_CHILD | WS_VISIBLE, 384, 10, 50, 24, hwnd, (HMENU)301, nullptr, nullptr);
        CreateWindowW(L"BUTTON", L"\u4e0a\u7ea7", WS_CHILD | WS_VISIBLE, 440, 10, 50, 24, hwnd, (HMENU)302, nullptr, nullptr);
        CreateWindowW(L"BUTTON", L"\u5237\u65b0", WS_CHILD | WS_VISIBLE, 496, 10, 50, 24, hwnd, (HMENU)303, nullptr, nullptr);
        state->hList = CreateWindowW(L"LISTBOX", nullptr, WS_CHILD | WS_VISIBLE | WS_VSCROLL | LBS_NOTIFY, 12, 44, 756, 420, hwnd, (HMENU)304, nullptr, nullptr);
        refresh_list(state);
        return 0;
    }
    case WM_COMMAND:
        if (!state) return 0;
        if (LOWORD(wp) == 304 && HIWORD(wp) == LBN_DBLCLK) {
            on_sel(state, (int)SendMessage(state->hList, LB_GETCURSEL, 0, 0));
            return 0;
        }
        switch (LOWORD(wp)) {
        case 301: {
            char buf[512] = {};
            GetWindowTextA(state->hPathEdit, buf, sizeof(buf));
            state->current_path = buf;
            if (!state->current_path.empty() && state->current_path[0] != '/') state->current_path = "/" + state->current_path;
            if (state->current_path.empty()) state->current_path = "/";
            refresh_list(state);
            break;
        }
        case 302: {
            std::string p = state->current_path;
            while (!p.empty() && p.back() == '/') p.pop_back();
            if (p.empty() || p == "/") break;
            size_t pos = p.rfind('/');
            state->current_path = (pos == 0 || pos == std::string::npos) ? "/" : p.substr(0, pos);
            SetWindowTextA(state->hPathEdit, state->current_path.c_str());
            refresh_list(state);
            break;
        }
        case 303:
            refresh_list(state);
            break;
        }
        return 0;
    case WM_CLOSE:
        DestroyWindow(hwnd);
        return 0;
    case WM_DESTROY:
        if (state) delete state;
        return 0;
    }
    return DefWindowProcW(hwnd, msg, wp, lp);
}

void adb_browser_show(HWND parent, const std::string& adb_path) {
    g_adb_path = adb_path;
    static bool reg = false;
    if (!reg) {
        WNDCLASSEXW wc = {};
        wc.cbSize = sizeof(wc);
        wc.lpfnWndProc = browser_wnd_proc;
        wc.hInstance = GetModuleHandle(nullptr);
        wc.lpszClassName = L"AdbBrowserWnd";
        wc.hbrBackground = (HBRUSH)(COLOR_WINDOW + 1);
        RegisterClassExW(&wc);
        reg = true;
    }
    HWND hwnd = CreateWindowExW(0, L"AdbBrowserWnd", L"ADB \u6587\u4ef6\u6d4f\u89c8\u5668",
        WS_OVERLAPPEDWINDOW, CW_USEDEFAULT, CW_USEDEFAULT, 800, 520, parent, nullptr, GetModuleHandle(nullptr), nullptr);
    if (hwnd) ShowWindow(hwnd, SW_SHOW);
}
