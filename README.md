# 工具软件

在 Windows 上运行的桌面工具，支持从主菜单选择功能使用。

## 功能

1. **日志输出功能**：自动连接已连接的 Android 设备，在界面中实时显示设备 logcat 日志。

## 环境要求

- Windows 10/11
- Python 3.8 或以上
- **Android 日志功能**：本机已安装 [Android SDK Platform-Tools](https://developer.android.com/studio/releases/platform-tools)（含 `adb`），并将 `adb` 所在目录加入系统 PATH；或使用默认路径：`%LOCALAPPDATA%\Android\Sdk\platform-tools\`

使用前请用 USB 连接 Android 设备并开启 **USB 调试**。

## 安装与运行

```bash
# 进入项目目录
cd i:\MyObject\gongju

# 创建虚拟环境（可选）
python -m venv venv
venv\Scripts\activate

# 安装依赖
pip install -r requirements.txt

# 启动程序
python main.py
```

## 分发给他人使用（无需安装 Python）

若要把软件发给别人使用，可打包成**独立 exe**，对方**不需要安装 Python**：

1. 在本机已安装 Python 的前提下，双击运行 **`build.bat`**。
2. 等待打包完成，在 **`dist\工具软件.exe`** 得到可执行文件。
3. 将 **`工具软件.exe`** 发给对方；对方在 Windows 上双击即可运行。

说明：exe 体积较大（约几十 MB），因内含 Python 运行环境。若杀毒软件误报，可添加信任或暂时关闭后运行。

## 使用说明

1. 运行 `python main.py` 或双击 `工具软件.exe` 打开主界面。
2. 点击 **「1. 日志输出功能」** 进入日志窗口。
3. 在日志窗口中点击 **「开始抓取日志」**，程序会通过 ADB 连接当前设备并实时显示 logcat；点击 **「停止」** 停止抓取，**「清空」** 清空当前显示内容。
