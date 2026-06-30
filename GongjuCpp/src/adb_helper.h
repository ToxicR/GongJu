#pragma once

#include <string>
#include <vector>
#include <cstdint>

namespace adb {

struct DirEntry { std::string name; bool isDir; };

std::string find_adb();
bool check_devices(const std::string& adb_path, std::vector<std::string>* out_devices = nullptr);
int run_adb(const std::string& adb_path, const std::string& args, std::string* out_stdout = nullptr, std::string* out_stderr = nullptr);
bool run_adb_exec_out(const std::string& adb_path, const std::string& args, std::vector<uint8_t>* out);
std::string get_pid_by_package(const std::string& adb_path, const std::string& package);
bool get_device_size(const std::string& adb_path, int* out_w, int* out_h);
bool list_dir(const std::string& adb_path, const std::string& path, std::vector<DirEntry>* out_items, std::string* out_error = nullptr);
std::string find_scrcpy();

}
