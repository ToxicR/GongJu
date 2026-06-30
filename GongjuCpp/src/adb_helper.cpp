#include "adb_helper.h"
#include <windows.h>
#include <shlobj.h>
#include <cstdlib>
#include <sstream>
#include <regex>
#include <algorithm>
#include <fstream>

namespace adb {

static std::string get_env(const char* name) {
    char buf[32768];
    if (GetEnvironmentVariableA(name, buf, sizeof(buf)) > 0)
        return buf;
    return "";
}

static bool run_process(const std::string& exe, const std::string& args,
    std::string* out_stdout, std::string* out_stderr, std::vector<uint8_t>* out_binary,
    DWORD timeout_ms) {
    SECURITY_ATTRIBUTES sa = { sizeof(sa), nullptr, TRUE };
    HANDLE hOutR = nullptr, hOutW = nullptr, hErrR = nullptr, hErrW = nullptr;
    if (out_stdout || out_binary) {
        if (!CreatePipe(&hOutR, &hOutW, &sa, 0) || !SetHandleInformation(hOutR, HANDLE_FLAG_INHERIT, 0))
            return false;
    }
    if (out_stderr && !out_binary) {
        if (!CreatePipe(&hErrR, &hErrW, &sa, 0) || !SetHandleInformation(hErrR, HANDLE_FLAG_INHERIT, 0))
            return false;
    }

    STARTUPINFOA si = {};
    si.cb = sizeof(si);
    si.dwFlags = STARTF_USESTDHANDLES | STARTF_USESHOWWINDOW;
    si.wShowWindow = SW_HIDE;
    si.hStdInput = GetStdHandle(STD_INPUT_HANDLE);
    si.hStdOutput = (hOutW != nullptr) ? hOutW : GetStdHandle(STD_OUTPUT_HANDLE);
    si.hStdError = (hErrW != nullptr) ? hErrW : GetStdHandle(STD_ERROR_HANDLE);

    std::string cmd = "\"" + exe + "\" " + args + "\0";
    std::vector<char> cmd_buf(cmd.begin(), cmd.end());
    cmd_buf.push_back('\0');
    PROCESS_INFORMATION pi = {};
    if (!CreateProcessA(nullptr, cmd_buf.data(), nullptr, nullptr, TRUE, CREATE_NO_WINDOW, nullptr, nullptr, &si, &pi)) {
        if (hOutR) CloseHandle(hOutR);
        if (hOutW) CloseHandle(hOutW);
        if (hErrR) CloseHandle(hErrR);
        if (hErrW) CloseHandle(hErrW);
        return false;
    }
    CloseHandle(hOutW);
    if (hErrW) CloseHandle(hErrW);

    if (hOutR) {
        if (out_binary) {
            std::vector<uint8_t> data;
            char buf[8192];
            DWORD n;
            while (ReadFile(hOutR, buf, sizeof(buf), &n, nullptr) && n > 0)
                data.insert(data.end(), buf, buf + n);
            *out_binary = std::move(data);
        } else if (out_stdout) {
            char buf[8192];
            DWORD n;
            while (ReadFile(hOutR, buf, sizeof(buf), &n, nullptr) && n > 0)
                out_stdout->append(buf, n);
        }
        CloseHandle(hOutR);
    }
    if (hErrR && out_stderr) {
        char buf[8192];
        DWORD n;
        while (ReadFile(hErrR, buf, sizeof(buf), &n, nullptr) && n > 0)
            out_stderr->append(buf, n);
        CloseHandle(hErrR);
    }

    WaitForSingleObject(pi.hProcess, timeout_ms);
    DWORD exit_code = 0;
    GetExitCodeProcess(pi.hProcess, &exit_code);
    CloseHandle(pi.hProcess);
    CloseHandle(pi.hThread);
    return (exit_code == 0);
}

std::string find_adb() {
    const char* names[] = { "adb.exe", "adb" };
    for (const char* name : names) {
        std::string out, err;
        if (run_process(name, "version", &out, &err, nullptr, 5000) && !out.empty())
            return name;
    }
    std::string local = get_env("LOCALAPPDATA");
    if (!local.empty()) {
        std::string p = local + "\\Android\\Sdk\\platform-tools\\adb.exe";
        if (GetFileAttributesA(p.c_str()) != INVALID_FILE_ATTRIBUTES)
            return p;
    }
    std::string user = get_env("USERPROFILE");
    if (!user.empty()) {
        std::string p = user + "\\AppData\\Local\\Android\\Sdk\\platform-tools\\adb.exe";
        if (GetFileAttributesA(p.c_str()) != INVALID_FILE_ATTRIBUTES)
            return p;
    }
    return "";
}

bool check_devices(const std::string& adb_path, std::vector<std::string>* out_devices) {
    std::string out, err;
    if (!run_process(adb_path, "devices", &out, &err, nullptr, 10000))
        return false;
    std::istringstream is(out);
    std::string line;
    if (out_devices) out_devices->clear();
    while (std::getline(is, line)) {
        if (line.find('\t') != std::string::npos && line.find("device") != std::string::npos && line[0] != '*') {
            if (out_devices)
                out_devices->push_back(line);
        }
    }
    return out_devices ? !out_devices->empty() : true;
}

int run_adb(const std::string& adb_path, const std::string& args, std::string* out_stdout, std::string* out_stderr) {
    std::string out, err;
    bool ok = run_process(adb_path, args, out_stdout ? out_stdout : &out, out_stderr ? out_stderr : &err, nullptr, 30000);
    return ok ? 0 : -1;
}

bool run_adb_exec_out(const std::string& adb_path, const std::string& args, std::vector<uint8_t>* out) {
    return run_process(adb_path, "exec-out " + args, nullptr, nullptr, out, 10000);
}

std::string get_pid_by_package(const std::string& adb_path, const std::string& package) {
    if (package.empty()) return "";
    std::string pkg = package;
    while (!pkg.empty() && (pkg.back() == ' ' || pkg.back() == '\t')) pkg.pop_back();
    if (pkg.empty()) return "";
    std::string out;
    run_adb(adb_path, "shell pidof -s " + pkg, &out, nullptr);
    std::istringstream is(out);
    std::string pid;
    if (is >> pid && !pid.empty() && std::all_of(pid.begin(), pid.end(), ::isdigit))
        return pid;
    return "";
}

bool get_device_size(const std::string& adb_path, int* out_w, int* out_h) {
    std::string out;
    run_adb(adb_path, "shell wm size", &out, nullptr);
    std::regex re(R"((\d+)\s*[x×]\s*(\d+))");
    std::smatch m;
    if (std::regex_search(out, m, re)) {
        *out_w = std::stoi(m[1].str());
        *out_h = std::stoi(m[2].str());
        return true;
    }
    return false;
}

static bool is_ls_error(const std::string& s) {
    std::string t = s;
    std::transform(t.begin(), t.end(), t.begin(), ::tolower);
    if (t.find("ls:") != std::string::npos || t.find("no such") != std::string::npos ||
        t.find("or directory") != std::string::npos || t.find("not found") != std::string::npos)
        return true;
    return false;
}

static void parse_ls(const std::string& combined, const std::string& path_filter, std::vector<DirEntry>* items) {
    static const char* skip[] = { "no","such","or","directory","file","and","the","a","an","in","to","for", nullptr };
    std::istringstream is(combined);
    std::string line;
    while (std::getline(is, line)) {
        if (line.empty() || is_ls_error(line)) continue;
        std::istringstream ls(line);
        std::string part;
        while (ls >> part) {
            if (part == "." || part == "..") continue;
            if (part.size() > 2 && part[0] == '/') continue;
            bool skip_it = false;
            for (int i = 0; skip[i]; i++)
                if (part == skip[i]) { skip_it = true; break; }
            if (!skip_it)
                items->push_back({ part, true });
        }
    }
}

bool list_dir(const std::string& adb_path, const std::string& path, std::vector<DirEntry>* out_items, std::string* out_error) {
    std::string p = path;
    while (!p.empty() && p.back() == '/') p.pop_back();
    if (p.empty()) p = "/";

    auto run_ls = [&](const std::string& path_arg) {
        std::string out;
        run_adb(adb_path, "shell ls " + path_arg, &out, nullptr);
        return out;
    };
    auto run_cd_ls = [&](const std::string& path_arg) {
        std::string out;
        std::string cmd = "shell \"cd " + path_arg + " && ls\"";
        run_adb(adb_path, cmd, &out, nullptr);
        return out;
    };

    out_items->clear();
    if (p == "/sdcard") {
        std::string combined = run_cd_ls("/sdcard");
        if (!combined.empty() && !is_ls_error(combined)) {
            parse_ls(combined, "", out_items);
            if (!out_items->empty()) return true;
        }
        combined = run_ls("/storage/emulated/0");
        if (!combined.empty() && !is_ls_error(combined)) {
            parse_ls(combined, "/storage/emulated/0", out_items);
            if (!out_items->empty()) return true;
        }
        combined = run_ls(p);
        if (!combined.empty() && !is_ls_error(combined)) {
            parse_ls(combined, p, out_items);
            if (!out_items->empty()) return true;
        }
        if (out_error) *out_error = "无法列出 /sdcard";
        return false;
    }

    if (p.compare(0, 8, "/sdcard/") == 0) {
        std::string suffix = p.substr(8);
        std::string alt = "/storage/emulated/0/" + suffix;
        std::string combined = run_ls(alt);
        if (!combined.empty() && !is_ls_error(combined)) {
            parse_ls(combined, alt, out_items);
            if (!out_items->empty()) return true;
        }
    }

    std::string combined = run_ls(p);
    if (!combined.empty() && !is_ls_error(combined)) {
        parse_ls(combined, p, out_items);
        if (!out_items->empty()) return true;
    }
    if (out_error) *out_error = "无法列出该目录";
    return false;
}

std::string find_scrcpy() {
    const char* names[] = { "scrcpy.exe", "scrcpy" };
    for (const char* name : names) {
        std::string out, err;
        if (run_process(name, "--version", &out, &err, nullptr, 5000)) {
            if (out.find("scrcpy") != std::string::npos || err.find("scrcpy") != std::string::npos)
                return name;
        }
    }
    std::string local = get_env("LOCALAPPDATA");
    if (!local.empty()) {
        std::string p = local + "\\scoop\\apps\\scrcpy\\current\\scrcpy.exe";
        if (GetFileAttributesA(p.c_str()) != INVALID_FILE_ATTRIBUTES) return p;
    }
    return "";
}

} // namespace adb
