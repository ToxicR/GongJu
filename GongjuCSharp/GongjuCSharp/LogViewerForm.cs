using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.Text;
using System.Text.Json;
using System.Text.RegularExpressions;
using System.Threading;
using System.Windows.Forms;

namespace GongjuCSharp;

public class LogViewerForm : Form
{
    private string? _adbPath;
    private Process? _logcatProcess;
    private Thread? _readThread;
    private volatile bool _running;
    private string? _filterPid;
    private List<string> _savedPackages = new();
    private const string PackagesFile = "log_viewer_packages.json";
    private const string DefaultPackage = "com.jpgk.autobooth";

    private TextBox _logBox = null!;
    private ComboBox _packageCombo = null!;
    private Button _btnStartStop = null!;
    private Button _btnExport = null!;
    private Label _statusLabel = null!;

    public LogViewerForm()
    {
        Text = "Android 日志实时输出";
        Size = new Size(900, 600);
        StartPosition = FormStartPosition.CenterScreen;
        FormBorderStyle = FormBorderStyle.Sizable;

        LoadPackages();

        var top = new FlowLayoutPanel { FlowDirection = FlowDirection.LeftToRight, Dock = DockStyle.Top, Height = 44, Padding = new Padding(8) };
        var lblPkg = new Label { Text = "包名筛选：", AutoSize = true, Anchor = AnchorStyles.Left };
        _packageCombo = new ComboBox { Width = 220, DropDownStyle = ComboBoxStyle.DropDown };
        foreach (var p in _savedPackages)
            _packageCombo.Items.Add(p);
        if (_savedPackages.Count > 0)
            _packageCombo.Text = _savedPackages[0];
        else
            _packageCombo.Text = DefaultPackage;

        var btnDel = new Button { Text = "删除当前", Width = 70 };
        btnDel.Click += (_, _) =>
        {
            var t = _packageCombo.Text?.Trim();
            if (string.IsNullOrEmpty(t)) return;
            _savedPackages.RemoveAll(x => string.Equals(x, t, StringComparison.OrdinalIgnoreCase));
            _packageCombo.Items.Clear();
            foreach (var p in _savedPackages) _packageCombo.Items.Add(p);
            _packageCombo.Text = _savedPackages.Count > 0 ? _savedPackages[0] : "";
            SavePackages();
        };

        _btnStartStop = new Button { Text = "开始", Width = 70 };
        _btnStartStop.Click += (_, _) => ToggleLogcat();

        _btnExport = new Button { Text = "导出", Width = 60 };
        _btnExport.Click += (_, _) => ExportLog();

        _statusLabel = new Label { AutoSize = true, Text = "状态：就绪" };

        top.Controls.Add(lblPkg);
        top.Controls.Add(_packageCombo);
        top.Controls.Add(btnDel);
        top.Controls.Add(_btnStartStop);
        top.Controls.Add(_btnExport);
        top.Controls.Add(_statusLabel);

        _logBox = new TextBox
        {
            Multiline = true,
            ScrollBars = ScrollBars.Both,
            WordWrap = false,
            Dock = DockStyle.Fill,
            Font = new Font("Consolas", 9f),
            ReadOnly = true,
        };

        Controls.Add(_logBox);
        Controls.Add(top);

        Load += (_, _) => InitConnection();
    }

    private void LoadPackages()
    {
        try
        {
            var path = Path.Combine(AppContext.BaseDirectory, PackagesFile);
            if (!File.Exists(path)) return;
            var json = File.ReadAllText(path);
            var list = JsonSerializer.Deserialize<List<string>>(json);
            if (list != null)
                _savedPackages = list;
        }
        catch { /* ignore */ }
    }

    private void SavePackages()
    {
        try
        {
            var path = Path.Combine(AppContext.BaseDirectory, PackagesFile);
            File.WriteAllText(path, JsonSerializer.Serialize(_savedPackages, new JsonSerializerOptions { WriteIndented = true }));
        }
        catch { /* ignore */ }
    }

    private void SetStatus(string text)
    {
        if (IsDisposed || !IsHandleCreated) return;
        try
        {
            if (InvokeRequired)
                BeginInvoke(() => _statusLabel.Text = "状态：" + text);
            else
                _statusLabel.Text = "状态：" + text;
        }
        catch { /* ignore */ }
    }

    private void AppendLog(string text)
    {
        if (IsDisposed || !IsHandleCreated || string.IsNullOrEmpty(text)) return;
        try
        {
            if (InvokeRequired)
            {
                BeginInvoke(() => DoAppend(text));
                return;
            }
            DoAppend(text);
        }
        catch { /* ignore */ }
    }

    private void DoAppend(string text)
    {
        if (_logBox.TextLength > 2_000_000)
            _logBox.Text = _logBox.Text.Substring(_logBox.Text.Length / 2);
        _logBox.AppendText(text);
        _logBox.ScrollToCaret();
    }

    private void InitConnection()
    {
        _adbPath = AdbHelper.FindAdb();
        if (string.IsNullOrEmpty(_adbPath))
        {
            SetStatus("未找到 ADB");
            MessageBox.Show("未找到 ADB，请安装 Android SDK Platform-Tools 或将 adb 加入 PATH。", "错误", MessageBoxButtons.OK, MessageBoxIcon.Warning);
            return;
        }
        var (ok, _) = AdbHelper.CheckDevices(_adbPath);
        if (!ok)
        {
            SetStatus("未检测到设备");
            MessageBox.Show("请连接 Android 设备并开启 USB 调试。", "未检测到设备", MessageBoxButtons.OK, MessageBoxIcon.Warning);
            return;
        }
        SetStatus("已连接，可点击「开始」");
    }

    private void ToggleLogcat()
    {
        if (_running)
        {
            StopLogcat();
            return;
        }
        if (string.IsNullOrEmpty(_adbPath)) return;
        var (ok, _) = AdbHelper.CheckDevices(_adbPath);
        if (!ok)
        {
            MessageBox.Show("设备未连接。", "提示", MessageBoxButtons.OK, MessageBoxIcon.Warning);
            return;
        }

        var pkg = _packageCombo.Text?.Trim();
        if (!string.IsNullOrEmpty(pkg) && !_savedPackages.Contains(pkg, StringComparer.OrdinalIgnoreCase))
        {
            _savedPackages.Add(pkg);
            _packageCombo.Items.Clear();
            foreach (var x in _savedPackages) _packageCombo.Items.Add(x);
            SavePackages();
        }

        _filterPid = null;
        if (!string.IsNullOrEmpty(pkg))
            _filterPid = AdbHelper.GetPidByPackage(_adbPath, pkg);

        // 清空 logcat 缓存
        AdbHelper.RunAdb(_adbPath, "logcat", "-c");

        var psi = new ProcessStartInfo(_adbPath, "logcat -v time")
        {
            CreateNoWindow = true,
            UseShellExecute = false,
            RedirectStandardOutput = true,
            RedirectStandardError = true,
            StandardOutputEncoding = Encoding.UTF8,
            StandardErrorEncoding = Encoding.UTF8,
        };
        try
        {
            _logcatProcess = Process.Start(psi);
            if (_logcatProcess == null)
            {
                SetStatus("启动失败");
                return;
            }
            _running = true;
            _btnStartStop.Text = "停止";
            SetStatus("输出中…");
            _readThread = new Thread(ReadLogcatOutput) { IsBackground = true };
            _readThread.Start();
        }
        catch (Exception ex)
        {
            _running = false;
            _btnStartStop.Text = "开始";
            SetStatus("启动失败");
            MessageBox.Show(ex.Message, "错误", MessageBoxButtons.OK, MessageBoxIcon.Error);
        }
    }

    private void ReadLogcatOutput()
    {
        if (_logcatProcess?.StandardOutput == null) return;
        var sb = new StringBuilder();
        var pid = _filterPid;
        var pidWord = string.IsNullOrEmpty(pid) ? null : pid;
        try
        {
            while (_running && _logcatProcess.StandardOutput.ReadLine() is { } line)
            {
                if (!string.IsNullOrEmpty(pidWord))
                {
                    if (!ContainsPid(line, pidWord))
                        continue;
                }
                sb.AppendLine(line);
                if (sb.Length >= 4096)
                {
                    var chunk = sb.ToString();
                    sb.Clear();
                    AppendLog(chunk);
                }
            }
            if (sb.Length > 0)
                AppendLog(sb.ToString());
        }
        catch { /* ignore */ }
    }

    private static bool ContainsPid(string line, string pid)
    {
        if (string.IsNullOrEmpty(line) || string.IsNullOrEmpty(pid)) return true;
        var idx = line.IndexOf(pid, StringComparison.Ordinal);
        if (idx < 0) return false;
        var before = idx == 0 || !char.IsLetterOrDigit(line[idx - 1]);
        var after = idx + pid.Length >= line.Length || !char.IsLetterOrDigit(line[idx + pid.Length]);
        return before && after;
    }

    private void StopLogcat()
    {
        _running = false;
        try
        {
            _logcatProcess?.Kill(entireProcessTree: true);
        }
        catch { /* ignore */ }
        _logcatProcess = null;
        _readThread = null;
        _btnStartStop.Text = "开始";
        SetStatus("已停止");
    }

    private void ExportLog()
    {
        var text = _logBox.Text;
        if (string.IsNullOrWhiteSpace(text))
        {
            MessageBox.Show("当前无内容可导出。", "导出", MessageBoxButtons.OK, MessageBoxIcon.Information);
            return;
        }
        using var dlg = new SaveFileDialog
        {
            Filter = "文本文件 (*.txt)|*.txt|所有文件 (*.*)|*.*",
            DefaultExt = "txt",
            FileName = "logcat_" + DateTime.Now.ToString("yyyyMMdd_HHmmss") + ".txt",
        };
        if (dlg.ShowDialog() != DialogResult.OK) return;
        var toSave = Regex.Replace(text, @"(\r?\n){3,}", "\r\n");
        File.WriteAllText(dlg.FileName, toSave, System.Text.Encoding.UTF8);
        MessageBox.Show("已导出。", "导出", MessageBoxButtons.OK, MessageBoxIcon.Information);
    }

    protected override void OnFormClosing(FormClosingEventArgs e)
    {
        if (_running)
            StopLogcat();
        base.OnFormClosing(e);
    }
}
