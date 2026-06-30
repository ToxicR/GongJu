# 工具软件（C++ 版）

使用 **C++ + Win32 API** 实现，编译为**单个 exe**，**无需用户安装任何运行时**（不依赖 .NET、Python、VC 运行库可选静态链接）。

## 功能

- **1. 日志输出**：实时 `adb logcat -v time`，包名筛选、导出、包名列表保存到 `log_viewer_packages.txt`
- **2. ADB 文件浏览器**：`adb shell ls` 浏览目录、路径栏、导出到本机（`adb pull`）
- **3. 投屏**：启动 scrcpy 视频流 或 截屏预览（约 8 帧/秒）+ 点击映射

## 环境要求

- **用户**：仅需 Windows 10/11，无需安装任何环境
- **开发/编译**：Visual Studio 2019/2022（或 VS Build Tools）或 CMake + MSVC；需安装 C++ 桌面开发

## 编译

### 使用 CMake（推荐）

```batch
cd GongjuCpp
mkdir build
cd build
cmake .. -G "Visual Studio 17 2022" -A x64
cmake --build . --config Release
```

生成的 exe 在 `build\Release\GongjuCpp.exe`。可单独拷贝到任意 Windows 机器运行。

### 使用 Visual Studio

1. 用 Visual Studio 打开 `GongjuCpp` 文件夹（“打开本地文件夹”）
2. 或先用 CMake 生成 `.sln` 后双击打开
3. 选择 Release、x64，生成解决方案

## 运行

直接双击 `GongjuCpp.exe`。请确保本机已安装 ADB（Android SDK Platform-Tools）并加入 PATH，且设备已连接并开启 USB 调试。

## 项目结构

- `CMakeLists.txt`：CMake 配置，静态链接 CRT（/MT）
- `src/main.cpp`：入口、消息循环
- `src/main_window.cpp`：主窗口、三个按钮
- `src/adb_helper.cpp`：查找 adb、设备检测、命令执行、目录列表
- `src/log_viewer.cpp`：日志窗口
- `src/adb_browser.cpp`：文件浏览窗口
- `src/screen_mirror.cpp`：投屏（scrcpy + 截屏预览，GDI+ 解码 PNG）
