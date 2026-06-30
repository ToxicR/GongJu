# 工具软件（C# 版）

使用 C# + Windows Forms 实现与 Python 版相同的功能，无需安装 Python 或 scrcpy 即可使用日志与文件浏览；投屏支持 scrcpy 视频流或 ADB 截屏预览。

## 功能

- **1. 日志输出**：实时显示 `adb logcat -v time`，按包名筛选（pidof）、导出日志、保存包名列表。
- **2. ADB 文件浏览器**：浏览设备目录（`adb shell ls`）、路径栏跳转、导出文件到本机（`adb pull`）。
- **3. 投屏**：  
  - **视频流**：若已安装 scrcpy，可点击「启动视频流投屏」打开 scrcpy 窗口（流畅）。  
  - **截屏预览**：在窗口内以约 8 帧/秒显示设备画面，支持点击映射到设备。

## 环境要求

- Windows 10/11
- [.NET 8 SDK](https://dotnet.microsoft.com/download/dotnet/8.0) 或运行时
- ADB（Android SDK Platform-Tools），并加入 PATH 或使用默认安装路径  
- （可选）scrcpy：用于投屏视频流，如 `winget install scrcpy`

## 编译与运行

```bash
cd GongjuCSharp
dotnet build
dotnet run --project GongjuCSharp
```

或使用 Visual Studio 2022 打开 `GongjuCSharp.sln` 后生成并运行。

## 发布单文件 exe（可选）

```bash
dotnet publish -c Release -r win-x64 --self-contained true -p:PublishSingleFile=true
```

输出在 `GongjuCSharp\bin\Release\net8.0-windows\win-x64\publish\`。

## 项目结构

- `Program.cs`：入口
- `MainForm.cs`：主窗口，三个功能入口
- `AdbHelper.cs`：ADB 查找、设备检测、命令执行、目录列表解析
- `LogViewerForm.cs`：日志输出窗口
- `AdbFileBrowserForm.cs`：ADB 文件浏览窗口
- `ScreenMirrorForm.cs`：投屏（scrcpy 或截屏预览）

## 与 Python 版对应关系

| Python 版           | C# 版                |
|---------------------|----------------------|
| main.py             | MainForm.cs          |
| log_viewer.py       | LogViewerForm.cs     |
| adb_file_browser.py | AdbFileBrowserForm.cs|
| screen_mirror.py    | ScreenMirrorForm.cs  |
| log_viewer.find_adb / check_android_device | AdbHelper.FindAdb / CheckDevices |
| adb_file_browser.list_dir | AdbHelper.ListDir   |
