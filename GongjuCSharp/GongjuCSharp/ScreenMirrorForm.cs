using System;
using System.Drawing;
using System.Drawing.Drawing2D;
using System.IO;
using System.Threading;
using System.Windows.Forms;

namespace GongjuCSharp;

public class ScreenMirrorForm : Form
{
    private const int PreviewFps = 8;
    private string? _adbPath;
    private string? _scrcpyPath;
    private Thread? _captureThread;
    private volatile bool _running;
    private (int w, int h)? _deviceSize;
    private double _scale = 1;
    private int _shownW, _shownH, _origW, _origH;
    private PictureBox _pictureBox = null!;
    private Button _btnStream = null!;
    private Button _btnScreencap = null!;
    private Label _statusLabel = null!;

    public ScreenMirrorForm()
    {
        Text = "Android 投屏";
        Size = new Size(900, 680);
        StartPosition = FormStartPosition.CenterScreen;
        FormBorderStyle = FormBorderStyle.Sizable;
        _adbPath = AdbHelper.FindAdb();
        _scrcpyPath = AdbHelper.FindScrcpy();

        var top = new FlowLayoutPanel { FlowDirection = FlowDirection.LeftToRight, Dock = DockStyle.Top, Height = 44, Padding = new Padding(8) };
        _statusLabel = new Label { Text = "正在检测…", AutoSize = true };
        top.Controls.Add(_statusLabel);

        _btnStream = new Button { Text = "启动视频流投屏（scrcpy）", Width = 180 };
        _btnStream.Click += (_, _) => StartScrcpyStream();
        top.Controls.Add(_btnStream);

        _btnScreencap = new Button { Text = "开始预览（截屏）", Width = 140 };
        _btnScreencap.Click += (_, _) => ToggleScreencap();
        top.Controls.Add(_btnScreencap);

        _pictureBox = new PictureBox
        {
            Dock = DockStyle.Fill,
            BackColor = Color.FromArgb(0x1a, 0x1a, 0x1a),
            SizeMode = PictureBoxSizeMode.CenterImage,
        };
        _pictureBox.Click += PictureBox_Click;

        Controls.Add(_pictureBox);
        Controls.Add(top);

        Load += (_, _) => InitConnection();
        FormClosing += (_, e) =>
        {
            _running = false;
            _captureThread?.Join(2000);
        };
    }

    private void SetStatus(string msg)
    {
        if (InvokeRequired) { BeginInvoke(() => _statusLabel.Text = msg); return; }
        _statusLabel.Text = msg;
    }

    private void InitConnection()
    {
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
        _deviceSize = AdbHelper.GetDeviceSize(_adbPath);
        SetStatus("设备已连接");
        _btnScreencap.Enabled = true;
        if (!string.IsNullOrEmpty(_scrcpyPath))
            _btnStream.Enabled = true;
        else
            SetStatus("设备已连接（安装 scrcpy 可使用视频流，如 winget install scrcpy）");
    }

    private void StartScrcpyStream()
    {
        if (string.IsNullOrEmpty(_adbPath) || string.IsNullOrEmpty(_scrcpyPath))
        {
            MessageBox.Show("请先安装 scrcpy（如 winget install scrcpy）。", "视频流", MessageBoxButtons.OK, MessageBoxIcon.Information);
            return;
        }
        try
        {
            var psi = new System.Diagnostics.ProcessStartInfo(_scrcpyPath, "--no-audio")
            {
                UseShellExecute = true,
            };
            System.Diagnostics.Process.Start(psi);
            SetStatus("已启动 scrcpy，请到 scrcpy 窗口操作");
        }
        catch (Exception ex)
        {
            MessageBox.Show(ex.Message, "启动失败", MessageBoxButtons.OK, MessageBoxIcon.Error);
        }
    }

    private void ToggleScreencap()
    {
        if (_running)
        {
            _running = false;
            _pollTimer?.Stop();
            _captureThread?.Join(2500);
            _btnScreencap.Text = "开始预览（截屏）";
            SetStatus("已停止");
            return;
        }
        if (string.IsNullOrEmpty(_adbPath)) return;
        _running = true;
        _btnScreencap.Text = "停止预览（截屏）";
        SetStatus($"预览中（约 {PreviewFps} 帧/秒），在画面中点击可操作设备");
        _captureThread = new Thread(CaptureLoop) { IsBackground = true };
        _captureThread.Start();
    }

    private byte[]? CapturePng()
    {
        if (string.IsNullOrEmpty(_adbPath)) return null;
        return AdbHelper.RunAdbExecOut(_adbPath, "screencap", "-p");
    }

    private void CaptureLoop()
    {
        var intervalMs = 1000 / PreviewFps;
        while (_running && !string.IsNullOrEmpty(_adbPath))
        {
            var t0 = Environment.TickCount;
            var png = CapturePng();
            if (png != null && png.Length > 0)
            {
                Bitmap? bmp = null;
                try
                {
                    using var ms = new MemoryStream(png);
                    bmp = new Bitmap(ms);
                }
                catch { /* ignore */ }
                if (bmp != null)
                {
                    var w = bmp.Width;
                    var h = bmp.Height;
                    var cw = _pictureBox.ClientSize.Width;
                    var ch = _pictureBox.ClientSize.Height;
                    if (cw > 0 && ch > 0 && w > 0 && h > 0)
                    {
                        var scale = Math.Min((double)cw / w, (double)ch / h);
                        var nw = (int)(w * scale);
                        var nh = (int)(h * scale);
                        Bitmap? scaled = null;
                        try
                        {
                            scaled = new Bitmap(nw, nh);
                            using (var g = Graphics.FromImage(scaled))
                            {
                                g.InterpolationMode = InterpolationMode.Low;
                                g.DrawImage(bmp, 0, 0, nw, nh);
                            }
                            var ox = (cw - nw) / 2;
                            var oy = (ch - nh) / 2;
                            var origW = w;
                            var origH = h;
                            if (InvokeRequired)
                                BeginInvoke(() => ShowFrame(scaled, ox, oy, nw, nh, origW, origH));
                            else
                                ShowFrame(scaled, ox, oy, nw, nh, origW, origH);
                        }
                        finally
                        {
                            scaled?.Dispose();
                        }
                    }
                    bmp.Dispose();
                }
            }
            var elapsed = Environment.TickCount - t0;
            if (elapsed < intervalMs)
                Thread.Sleep(intervalMs - elapsed);
        }
    }

    private void ShowFrame(Bitmap? bmp, int ox, int oy, int nw, int nh, int origW, int origH)
    {
        if (!_running || bmp == null) return;
        _shownW = nw;
        _shownH = nh;
        _origW = origW;
        _origH = origH;
        _scale = _shownW > 0 ? (double)_origW / _shownW : 1;
        if (_deviceSize == null)
            _deviceSize = (_origW, _origH);
        var old = _pictureBox.Image;
        _pictureBox.Image = (Image)bmp.Clone();
        old?.Dispose();
        bmp.Dispose();
    }

    private void PictureBox_Click(object? sender, EventArgs e)
    {
        if (!_running || string.IsNullOrEmpty(_adbPath) || _shownW <= 0 || _shownH <= 0) return;
        if (e is not MouseEventArgs me) return;
        var ox = (_pictureBox.ClientSize.Width - _shownW) / 2;
        var oy = (_pictureBox.ClientSize.Height - _shownH) / 2;
        var dx = (int)((me.X - ox) * _scale);
        var dy = (int)((me.Y - oy) * _scale);
        if (_deviceSize is { } ds)
        {
            dx = Math.Clamp(dx, 0, ds.w - 1);
            dy = Math.Clamp(dy, 0, ds.h - 1);
        }
        AdbHelper.RunAdb(_adbPath, "shell", "input", "tap", dx.ToString(), dy.ToString());
    }
}
