using System;
using System.Drawing;
using System.Windows.Forms;

namespace GongjuCSharp;

public class MainForm : Form
{
    public MainForm()
    {
        Text = "工具软件";
        Size = new Size(480, 320);
        StartPosition = FormStartPosition.CenterScreen;
        FormBorderStyle = FormBorderStyle.Sizable;
        MinimizeBox = true;
        MaximizeBox = true;

        var title = new Label
        {
            Text = "请选择要使用的功能",
            Font = new Font("Microsoft YaHei UI", 14f, FontStyle.Bold),
            AutoSize = true,
        };
        title.Location = new Point(40, 32);

        var btnLog = new Button
        {
            Text = "1. 日志输出功能",
            Size = new Size(320, 48),
            Location = new Point(80, 80),
            Font = new Font("Microsoft YaHei UI", 11f),
        };
        btnLog.Click += (_, _) =>
        {
            using var f = new LogViewerForm();
            f.ShowDialog();
        };

        var btnFiles = new Button
        {
            Text = "2. ADB 文件浏览器",
            Size = new Size(320, 48),
            Location = new Point(80, 136),
            Font = new Font("Microsoft YaHei UI", 11f),
        };
        btnFiles.Click += (_, _) =>
        {
            using var f = new AdbFileBrowserForm();
            f.ShowDialog();
        };

        var btnMirror = new Button
        {
            Text = "3. 投屏",
            Size = new Size(320, 48),
            Location = new Point(80, 192),
            Font = new Font("Microsoft YaHei UI", 11f),
        };
        btnMirror.Click += (_, _) =>
        {
            using var f = new ScreenMirrorForm();
            f.ShowDialog();
        };

        var hint = new Label
        {
            Text = "更多功能敬请期待",
            ForeColor = Color.Gray,
            AutoSize = true,
            Location = new Point(80, 256),
        };

        Controls.Add(title);
        Controls.Add(btnLog);
        Controls.Add(btnFiles);
        Controls.Add(btnMirror);
        Controls.Add(hint);
    }
}
