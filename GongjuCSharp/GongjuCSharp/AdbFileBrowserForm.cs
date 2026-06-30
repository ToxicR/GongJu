using System;
using System.Drawing;
using System.IO;
using System.Threading.Tasks;
using System.Windows.Forms;

namespace GongjuCSharp;

public class AdbFileBrowserForm : Form
{
    private string? _adbPath;
    private string _currentPath = "/";
    private bool _loading;
    private TextBox _pathBox = null!;
    private FlowLayoutPanel _listPanel = null!;
    private Label _statusLabel = null!;

    public AdbFileBrowserForm()
    {
        Text = "ADB 文件浏览器";
        Size = new Size(720, 520);
        StartPosition = FormStartPosition.CenterScreen;
        FormBorderStyle = FormBorderStyle.Sizable;

        var top = new FlowLayoutPanel { FlowDirection = FlowDirection.LeftToRight, Dock = DockStyle.Top, Height = 44, Padding = new Padding(8) };
        top.Controls.Add(new Label { Text = "路径：", AutoSize = true });
        _pathBox = new TextBox { Width = 320, Height = 24 };
        _pathBox.Text = "/";
        _pathBox.KeyDown += (_, e) => { if (e.KeyCode == Keys.Enter) GoToPath(); };
        top.Controls.Add(_pathBox);

        var btnGo = new Button { Text = "转到", Width = 50 };
        btnGo.Click += (_, _) => GoToPath();
        top.Controls.Add(btnGo);

        var btnParent = new Button { Text = "上级", Width = 50 };
        btnParent.Click += (_, _) => GoParent();
        top.Controls.Add(btnParent);

        var btnRefresh = new Button { Text = "刷新", Width = 50 };
        btnRefresh.Click += (_, _) => LoadDir(_currentPath);
        top.Controls.Add(btnRefresh);

        _statusLabel = new Label { Text = "状态：就绪", AutoSize = true, Dock = DockStyle.Top, Height = 24 };
        _listPanel = new FlowLayoutPanel { Dock = DockStyle.Fill, FlowDirection = FlowDirection.TopDown, AutoScroll = true, WrapContents = false };

        Controls.Add(_listPanel);
        Controls.Add(_statusLabel);
        Controls.Add(top);

        Load += (_, _) => InitConnection();
    }

    private void SetStatus(string msg)
    {
        if (InvokeRequired) { BeginInvoke(() => _statusLabel.Text = "状态：" + msg); return; }
        _statusLabel.Text = "状态：" + msg;
    }

    private void InitConnection()
    {
        _adbPath = AdbHelper.FindAdb();
        if (string.IsNullOrEmpty(_adbPath))
        {
            SetStatus("未找到 ADB");
            MessageBox.Show("未找到 ADB，请安装 Android SDK Platform-Tools。", "错误", MessageBoxButtons.OK, MessageBoxIcon.Warning);
            return;
        }
        var (ok, _) = AdbHelper.CheckDevices(_adbPath);
        if (!ok)
        {
            SetStatus("未检测到设备");
            MessageBox.Show("请连接 Android 设备并开启 USB 调试。", "未检测到设备", MessageBoxButtons.OK, MessageBoxIcon.Warning);
            return;
        }
        SetStatus("已连接，正在加载…");
        LoadDir("/");
    }

    private void GoToPath()
    {
        var path = (_pathBox.Text ?? "").Trim().TrimEnd('/');
        if (string.IsNullOrEmpty(path)) path = "/";
        if (!path.StartsWith("/")) path = "/" + path;
        LoadDir(path);
    }

    private void GoParent()
    {
        var path = _currentPath.TrimEnd('/');
        if (path == "" || path == "/") return;
        var idx = path.LastIndexOf('/');
        var parent = idx <= 0 ? "/" : path.Substring(0, idx);
        if (string.IsNullOrEmpty(parent)) parent = "/";
        LoadDir(parent);
    }

    private void LoadDir(string path)
    {
        if (_loading || string.IsNullOrEmpty(_adbPath)) return;
        _loading = true;
        SetStatus("加载中…");
        _listPanel.Controls.Clear();

        Task.Run(() =>
        {
            var (items, err) = AdbHelper.ListDir(_adbPath, path);
            BeginInvoke(() =>
            {
                _loading = false;
                if (err != null || items == null)
                {
                    SetStatus(err ?? "错误");
                    if (err != null)
                        MessageBox.Show(err, "列出目录失败", MessageBoxButtons.OK, MessageBoxIcon.Error);
                    return;
                }
                _currentPath = path.TrimEnd('/');
                if (string.IsNullOrEmpty(_currentPath)) _currentPath = "/";
                _pathBox.Text = _currentPath;
                SetStatus($"共 {items.Count} 项");

                items.Sort((a, b) =>
                {
                    var ad = a.isDir ? 0 : 1;
                    var bd = b.isDir ? 0 : 1;
                    if (ad != bd) return ad.CompareTo(bd);
                    return string.Compare(a.name, b.name, StringComparison.OrdinalIgnoreCase);
                });

                foreach (var (name, isDir) in items)
                {
                    var row = new FlowLayoutPanel { FlowDirection = FlowDirection.LeftToRight, Width = _listPanel.ClientSize.Width - 30, Height = 32, Margin = new Padding(2) };
                    var prefix = isDir ? "[目录] " : "[文件] ";
                    var btn = new Button
                    {
                        Text = prefix + name,
                        TextAlign = ContentAlignment.MiddleLeft,
                        AutoSize = true,
                        FlatStyle = FlatStyle.Flat,
                        BackColor = isDir ? SystemColors.Control : Color.LightGray,
                    };
                    var fullPath = _currentPath == "/" ? "/" + name : _currentPath + "/" + name;
                    if (isDir)
                        btn.Click += (_, _) => LoadDir(fullPath);
                    else
                    {
                        btn.Click += (_, _) => PullFile(fullPath);
                    }
                    row.Controls.Add(btn);
                    _listPanel.Controls.Add(row);
                }
            });
        });
    }

    private void PullFile(string devicePath)
    {
        if (string.IsNullOrEmpty(_adbPath)) return;
        using var dlg = new FolderBrowserDialog { Description = "选择保存目录" };
        if (dlg.ShowDialog() != DialogResult.OK) return;
        var destDir = dlg.SelectedPath;
        SetStatus("导出中…");
        Task.Run(() =>
        {
            var (_, stderr, exitCode) = AdbHelper.RunAdb(_adbPath, "pull", devicePath, destDir);
            BeginInvoke(() =>
            {
                SetStatus(exitCode == 0 ? "导出完成" : (stderr ?? "导出失败"));
                if (exitCode != 0 && !string.IsNullOrEmpty(stderr))
                    MessageBox.Show(stderr, "导出", MessageBoxButtons.OK, MessageBoxIcon.Warning);
            });
        });
    }
}
