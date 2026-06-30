#include "log_viewer.h"
#include "adb_helper.h"
#include <windows.h>
#include <commctrl.h>
#include <string>
#include <vector>
#include <thread>
#include <atomic>
#include <fstream>

static std::string g_adb_path;
static std::string g_filter_pid;
static std::atomic<bool> g_logcat_running{ false };
static const char* PACKAGES_FILE = "log_viewer_packages.txt";
static const char* DEFAULT_PACKAGE = "com.jpgk.autobooth";

static std::wstring utf8_to_wide(const std::string& s) {
    if (s.empty()) return L"";
    int n = MultiByteToWideChar(CP_UTF8, 0, s.c_str(), (int)s.size(), nullptr, 0);
    if (n <= 0) return L"";
    std::wstring w(n, 0);
    MultiByteToWideChar(CP_UTF8, 0, s.c_str(), (int)s.size(), &w[0], n);
    return w;
}

static bool line_contains_pid(const std::string& line, const std::string& pid) {
    if (pid.empty()) return true;
    size_t pos = 0;
    for (;;) {
        pos = line.find(pid, pos);
        if (pos == std::string::npos) return false;
        bool before = (pos == 0 || !isalnum((unsigned char)line[pos - 1]));
        bool after = (pos + pid.size() >= line.size() || !isalnum((unsigned char)line[pos + pid.size()]));
        if (before && after) return true;
        pos++;
    }
}

static void load_packages(std::vector<std::string>* out) {
    std::ifstream f(PACKAGES_FILE);
    std::string line;
    while (std::getline(f, line)) {
        while (!line.empty() && (line.back() == '\r' || line.back() == '\n')) line.pop_back();
        if (!line.empty()) out->push_back(line);
    }
}

static void save_packages(const std::vector<std::string>& pkgs) {
    std::ofstream f(PACKAGES_FILE);
    for (const auto& p : pkgs) f << p << "\n";
}

struct LogViewerState {
    HWND hWnd;
    HWND hEdit;
    HWND hCombo;
    HANDLE hProcess = nullptr;
    HANDLE hPipeOut = nullptr;
    std::thread reader_thread;
    std::vector<std::string> packages;
};

static void reader_thread_func(LogViewerState* state) {
    char buf[4096];
    DWORD n;
    std::string line_buf;
    while (g_logcat_running && state->hPipeOut) {
        if (ReadFile(state->hPipeOut, buf, sizeof(buf) - 1, &n, nullptr) && n > 0) {
            buf[n] = '\0';
            line_buf += buf;
            size_t pos;
            while ((pos = line_buf.find('\n')) != std::string::npos) {
                std::string line = line_buf.substr(0, pos);
                line_buf = line_buf.substr(pos + 1);
                if (!g_filter_pid.empty() && !line_contains_pid(line, g_filter_pid)) continue;
                line += "\r\n";
                std::wstring wline = utf8_to_wide(line);
                if (state->hEdit && IsWindow(state->hEdit)) {
                    int len = GetWindowTextLengthW(state->hEdit);
                    SendMessageW(state->hEdit, EM_SETSEL, len, len);
                    SendMessageW(state->hEdit, EM_REPLACESEL, FALSE, (LPARAM)wline.c_str());
                }
            }
        } else
            break;
    }
}

static LogViewerState* g_log_state = nullptr;

static LRESULT CALLBACK log_wnd_proc(HWND hwnd, UINT msg, WPARAM wp, LPARAM lp) {
    LogViewerState* state = (LogViewerState*)GetWindowLongPtrW(hwnd, GWLP_USERDATA);
    switch (msg) {
    case WM_CREATE: {
        state = (LogViewerState*)((CREATESTRUCT*)lp)->lpCreateParams;
        SetWindowLongPtrW(hwnd, GWLP_USERDATA, (LONG_PTR)state);
        state->hWnd = hwnd;
        CreateWindowW(L"STATIC", L"\u5305\u540d\u7b5b\u9009\uff1a", WS_CHILD | WS_VISIBLE, 12, 12, 70, 24, hwnd, nullptr, nullptr, nullptr);
        state->hCombo = CreateWindowW(L"COMBOBOX", nullptr, WS_CHILD | WS_VISIBLE | CBS_DROPDOWN, 88, 10, 220, 200, hwnd, (HMENU)202, nullptr, nullptr);
        state->hEdit = CreateWindowW(L"EDIT", nullptr, WS_CHILD | WS_VISIBLE | WS_VSCROLL | ES_MULTILINE | ES_READONLY | ES_AUTOVSCROLL, 12, 44, 756, 480, hwnd, (HMENU)201, nullptr, nullptr);
        SendMessageW(state->hEdit, EM_SETLIMITTEXT, (WPARAM)(2 * 1024 * 1024), 0);
        CreateWindowW(L"BUTTON", L"\u5f00\u59cb", WS_CHILD | WS_VISIBLE, 320, 10, 60, 24, hwnd, (HMENU)203, nullptr, nullptr);
        CreateWindowW(L"BUTTON", L"\u5bfc\u51fa", WS_CHILD | WS_VISIBLE, 390, 10, 60, 24, hwnd, (HMENU)204, nullptr, nullptr);
        for (const auto& p : state->packages)
            SendMessageA(state->hCombo, CB_ADDSTRING, 0, (LPARAM)p.c_str());
        if (!state->packages.empty())
            SendMessage(state->hCombo, CB_SETCURSEL, 0, 0);
        else
            SetWindowTextA(state->hCombo, DEFAULT_PACKAGE);
        return 0;
    }
    case WM_COMMAND:
        if (!state) return 0;
        switch (LOWORD(wp)) {
        case 203:
            if (g_logcat_running) {
                g_logcat_running = false;
                if (state->reader_thread.joinable()) state->reader_thread.join();
                if (state->hProcess) { TerminateProcess(state->hProcess, 0); CloseHandle(state->hProcess); state->hProcess = nullptr; }
                if (state->hPipeOut) { CloseHandle(state->hPipeOut); state->hPipeOut = nullptr; }
                SetWindowTextW(GetDlgItem(hwnd, 203), L"\u5f00\u59cb");
            } else {
                char pkg[256] = {};
                GetWindowTextA(state->hCombo, pkg, sizeof(pkg));
                g_filter_pid = adb_helper::get_pid_by_package(g_adb_path, pkg);
                adb_helper::run_adb(g_adb_path, "logcat -c", nullptr, nullptr);
                SECURITY_ATTRIBUTES sa = { sizeof(sa), nullptr, TRUE };
                HANDLE hOutR = nullptr, hOutW = nullptr;
                CreatePipe(&hOutR, &hOutW, &sa, 0);
                SetHandleInformation(hOutR, HANDLE_FLAG_INHERIT, 0);
                STARTUPINFOA si = {};
                si.cb = sizeof(si);
                si.dwFlags = STARTF_USESTDHANDLES | STARTF_USESHOWWINDOW;
                si.wShowWindow = SW_HIDE;
                si.hStdOutput = hOutW;
                si.hStdError = hOutW;
                PROCESS_INFORMATION pi = {};
                std::string cmd = "\"" + g_adb_path + "\" logcat -v time\0";
                std::vector<char> cmd_buf(cmd.begin(), cmd.end());
                cmd_buf.push_back('\0');
                if (CreateProcessA(nullptr, cmd_buf.data(), nullptr, nullptr, TRUE, CREATE_NO_WINDOW, nullptr, nullptr, &si, &pi)) {
                    CloseHandle(hOutW);
                    state->hProcess = pi.hProcess;
                    state->hPipeOut = hOutR;
                    CloseHandle(pi.hThread);
                    g_logcat_running = true;
                    state->reader_thread = std::thread(reader_thread_func, state);
                    SetWindowTextW(GetDlgItem(hwnd, 203), L"\u505c\u6b62");
                } else { CloseHandle(hOutR); CloseHandle(hOutW); }
            }
            break;
        case 204: {
            int len = GetWindowTextLengthW(state->hEdit);
            if (len <= 0) { MessageBoxW(hwnd, L"\u65e0\u5185\u5bb9\u53ef\u5bfc\u51fa", L"\u5bfc\u51fa", MB_OK); break; }
            std::wstring buf(len + 1, 0);
            GetWindowTextW(state->hEdit, &buf[0], len + 1);
            buf.resize(len);
            OPENFILENAMEW ofn = {};
            wchar_t path[MAX_PATH] = L"logcat.txt";
            ofn.lStructSize = sizeof(ofn);
            ofn.hwndOwner = hwnd;
            ofn.lpstrFile = path;
            ofn.nMaxFile = MAX_PATH;
            ofn.Flags = OFN_OVERWRITEPROMPT;
            if (GetSaveFileNameW(&ofn)) {
                int n = WideCharToMultiByte(CP_UTF8, 0, buf.c_str(), (int)buf.size(), nullptr, 0, nullptr, nullptr);
                std::string utf8(n, 0);
                WideCharToMultiByte(CP_UTF8, 0, buf.c_str(), (int)buf.size(), &utf8[0], n, nullptr, nullptr);
                std::ofstream f(path);
                f << utf8;
                MessageBoxW(hwnd, L"\u5df2\u5bfc\u51fa", L"\u5bfc\u51fa", MB_OK);
            }
            break;
        }
        }
        return 0;
    case WM_CLOSE:
        if (g_logcat_running && state) {
            g_logcat_running = false;
            if (state->reader_thread.joinable()) state->reader_thread.join();
            if (state->hProcess) { TerminateProcess(state->hProcess, 0); CloseHandle(state->hProcess); }
            if (state->hPipeOut) CloseHandle(state->hPipeOut);
        }
        DestroyWindow(hwnd);
        return 0;
    case WM_DESTROY:
        if (state) {
            if (state->reader_thread.joinable()) state->reader_thread.join();
            delete state;
        }
        return 0;
    }
    return DefWindowProcW(hwnd, msg, wp, lp);
}

void log_viewer_show(HWND parent, const std::string& adb_path) {
    g_adb_path = adb_path;
    static bool reg = false;
    if (!reg) {
        WNDCLASSEXW wc = {};
        wc.cbSize = sizeof(wc);
        wc.lpfnWndProc = log_wnd_proc;
        wc.hInstance = GetModuleHandle(nullptr);
        wc.lpszClassName = L"LogViewerWnd";
        wc.hbrBackground = (HBRUSH)(COLOR_WINDOW + 1);
        RegisterClassExW(&wc);
        reg = true;
    }
    LogViewerState* state = new LogViewerState();
    load_packages(&state->packages);
    HWND hwnd = CreateWindowExW(0, L"LogViewerWnd", L"Android \u65e5\u5fd7\u5b9e\u65f6\u8f93\u51fa",
        WS_OVERLAPPEDWINDOW, CW_USEDEFAULT, CW_USEDEFAULT, 800, 580, parent, nullptr, GetModuleHandle(nullptr), state);
    if (hwnd) ShowWindow(hwnd, SW_SHOW);
    else delete state;
}
