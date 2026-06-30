using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Text.RegularExpressions;

namespace GongjuCSharp;

/// <summary>
/// ADB 与设备检测、命令执行、目录列表等。
/// </summary>
public static class AdbHelper
{
    public static string? FindAdb()
    {
        foreach (var name in new[] { "adb.exe", "adb" })
        {
            try
            {
                var psi = new ProcessStartInfo(name, "version") { CreateNoWindow = true, UseShellExecute = false };
                using var p = Process.Start(psi);
                if (p != null && p.WaitForExit(5000) && p.ExitCode == 0)
                    return name;
            }
            catch { /* ignore */ }
        }

        var paths = new[]
        {
            Environment.ExpandEnvironmentVariables(@"%LOCALAPPDATA%\Android\Sdk\platform-tools\adb.exe"),
            Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.UserProfile), "AppData", "Local", "Android", "Sdk", "platform-tools", "adb.exe"),
        };
        foreach (var path in paths)
        {
            if (!string.IsNullOrEmpty(path) && File.Exists(path))
                return path;
        }
        return null;
    }

    /// <summary>检查是否有已连接设备，返回 (是否成功, 设备列表或错误信息)。</summary>
    public static (bool ok, List<string>? devices) CheckDevices(string adbPath)
    {
        try
        {
            var (outStr, errStr, exitCode) = RunAdb(adbPath, "devices");
            if (exitCode != 0)
                return (false, null);
            var lines = (outStr ?? "").Trim().Split(new[] { '\r', '\n' }, StringSplitOptions.RemoveEmptyEntries);
            var list = new List<string>();
            foreach (var line in lines)
            {
                var t = line.Trim();
                if (t.StartsWith("*") || !t.Contains("\tdevice"))
                    continue;
                list.Add(t);
            }
            return (list.Count > 0, list.Count > 0 ? list : null);
        }
        catch
        {
            return (false, null);
        }
    }

    /// <summary>执行 adb [args]，返回 (stdout, stderr, exitCode)。</summary>
    public static (string? stdout, string? stderr, int exitCode) RunAdb(string adbPath, params string[] args)
    {
        var allArgs = string.Join(" ", args);
        var psi = new ProcessStartInfo(adbPath, allArgs)
        {
            CreateNoWindow = true,
            UseShellExecute = false,
            RedirectStandardOutput = true,
            RedirectStandardError = true,
        };
        using var p = Process.Start(psi);
        if (p == null)
            return (null, null, -1);
        var outTask = p.StandardOutput.ReadToEndAsync();
        var errTask = p.StandardError.ReadToEndAsync();
        p.WaitForExit(30000);
        return (outTask.Result, errTask.Result, p.ExitCode);
    }

    /// <summary>执行 adb exec-out [args]，返回二进制 stdout（用于 screencap -p）。</summary>
    public static byte[]? RunAdbExecOut(string adbPath, params string[] args)
    {
        var allArgs = "exec-out " + string.Join(" ", args);
        var psi = new ProcessStartInfo(adbPath, allArgs)
        {
            CreateNoWindow = true,
            UseShellExecute = false,
            RedirectStandardOutput = true,
            RedirectStandardError = true,
        };
        using var p = Process.Start(psi);
        if (p == null)
            return null;
        using var ms = new MemoryStream();
        p.StandardOutput.BaseStream.CopyTo(ms);
        p.WaitForExit(10000);
        return p.ExitCode == 0 ? ms.ToArray() : null;
    }

    public static string? GetPidByPackage(string adbPath, string package)
    {
        if (string.IsNullOrWhiteSpace(package))
            return null;
        var (outStr, _, exitCode) = RunAdb(adbPath, "shell", "pidof", "-s", package.Trim());
        if (exitCode != 0 || string.IsNullOrWhiteSpace(outStr))
            return null;
        var parts = outStr.Trim().Split((char[]?)null, StringSplitOptions.RemoveEmptyEntries);
        return parts.Length > 0 && int.TryParse(parts[0], out _) ? parts[0] : null;
    }

    public static (int w, int h)? GetDeviceSize(string adbPath)
    {
        var (outStr, errStr, _) = RunAdb(adbPath, "shell", "wm", "size");
        var text = (outStr ?? "") + (errStr ?? "");
        var m = Regex.Match(text, @"(\d+)\s*[x×]\s*(\d+)");
        if (m.Success && int.TryParse(m.Groups[1].Value, out var w) && int.TryParse(m.Groups[2].Value, out var h))
            return (w, h);
        return null;
    }

    public static string? FindScrcpy()
    {
        foreach (var name in new[] { "scrcpy.exe", "scrcpy" })
        {
            try
            {
                var psi = new ProcessStartInfo(name, "--version") { CreateNoWindow = true, UseShellExecute = false, RedirectStandardOutput = true, RedirectStandardError = true };
                using var p = Process.Start(psi);
                if (p != null && p.WaitForExit(5000))
                {
                    var outStr = p.StandardOutput.ReadToEnd() + p.StandardError.ReadToEnd();
                    if (outStr.IndexOf("scrcpy", StringComparison.OrdinalIgnoreCase) >= 0)
                        return name;
                }
            }
            catch { /* ignore */ }
        }

        var baseDirs = new[]
        {
            Environment.ExpandEnvironmentVariables("%LOCALAPPDATA%"),
            Environment.GetFolderPath(Environment.SpecialFolder.UserProfile),
        };
        foreach (var baseDir in baseDirs)
        {
            if (string.IsNullOrEmpty(baseDir)) continue;
            var candidates = new[]
            {
                Path.Combine(baseDir, "scoop", "apps", "scrcpy", "current", "scrcpy.exe"),
                Path.Combine(baseDir, "scrcpy", "scrcpy.exe"),
            };
            foreach (var path in candidates)
            {
                if (File.Exists(path))
                    return path;
            }
        }
        return null;
    }

    // ---------- 文件浏览：ls 解析 ----------
    private static readonly HashSet<string> SkipTokens = new(StringComparer.OrdinalIgnoreCase)
        { "no", "such", "or", "directory", "file", "and", "the", "a", "an", "in", "to", "for" };

    private static bool IsLsError(string? text)
    {
        if (string.IsNullOrWhiteSpace(text)) return true;
        var t = text.Trim().ToLowerInvariant();
        if (t.Contains("ls:") || t.Contains("unknown option") || t.Contains("aborting") || t.Contains("invalid")) return true;
        if (t.Contains("no devices") || t.Contains("not found") || t.Contains("no such") || t.Contains("or directory")) return true;
        return false;
    }

    private static (string output, int exitCode) RunAdbLs(string adbPath, string path)
    {
        path = path.TrimEnd('/');
        if (string.IsNullOrEmpty(path)) path = "/";
        var (outStr, errStr, code) = RunAdb(adbPath, "shell", "ls", path);
        var combined = ((outStr ?? "") + "\n" + (errStr ?? "")).Replace("\r", "\n").Trim();
        return (combined, code);
    }

    private static (string output, int exitCode) RunAdbCdLs(string adbPath, string path)
    {
        path = path.TrimEnd('/');
        if (string.IsNullOrEmpty(path)) path = "/";
        var cmd = "cd " + path.Replace("'", "'\\''") + " && ls";
        var (outStr, errStr, code) = RunAdb(adbPath, "shell", cmd);
        var combined = ((outStr ?? "") + "\n" + (errStr ?? "")).Replace("\r", "\n").Trim();
        return (combined, code);
    }

    private static List<(string name, bool isDir)> ParseLs(string combined, string pathFilter)
    {
        var items = new List<(string, bool)>();
        pathFilter = pathFilter?.TrimEnd('/') ?? "";
        foreach (var line in combined.Split(new[] { '\r', '\n' }, StringSplitOptions.RemoveEmptyEntries))
        {
            var lineTrim = line.Trim();
            if (string.IsNullOrEmpty(lineTrim) || IsLsError(lineTrim)) continue;
            if (!string.IsNullOrEmpty(pathFilter) && (lineTrim == pathFilter || lineTrim.TrimEnd('/') == pathFilter)) continue;
            foreach (var part in lineTrim.Split(new[] { ' ', '\t', ';' }, StringSplitOptions.RemoveEmptyEntries))
            {
                var p = part.Trim().TrimEnd(';');
                if (string.IsNullOrEmpty(p) || p == "." || p == "..") continue;
                if (SkipTokens.Contains(p)) continue;
                if (p.StartsWith("/") && p.Length > 2) continue;
                items.Add((p, true));
            }
        }
        return items;
    }

    /// <summary>列出设备目录，返回 (条目列表, 错误信息)。</summary>
    public static (List<(string name, bool isDir)>? items, string? error) ListDir(string adbPath, string path)
    {
        path = path?.TrimEnd('/') ?? "/";
        if (string.IsNullOrEmpty(path)) path = "/";

        if (path == "/sdcard")
        {
            var (combinedCd, codeCd) = RunAdbCdLs(adbPath, "/sdcard");
            if (!string.IsNullOrEmpty(combinedCd) && !IsLsError(combinedCd))
            {
                var items = ParseLs(combinedCd, "");
                if (items.Count > 0) return (items, null);
            }
            var (combinedAlt, _) = RunAdbLs(adbPath, "/storage/emulated/0");
            if (!string.IsNullOrEmpty(combinedAlt) && !IsLsError(combinedAlt))
            {
                var items = ParseLs(combinedAlt, "/storage/emulated/0");
                if (items.Count > 0) return (items, null);
            }
            var (combined, code) = RunAdbLs(adbPath, path);
            if (!string.IsNullOrEmpty(combined) && !IsLsError(combined))
            {
                var items = ParseLs(combined, path);
                if (items.Count > 0) return (items, null);
            }
            return (null, string.IsNullOrEmpty(combinedCd) ? "无法列出 /sdcard" : combinedCd.Trim());
        }

        if (path.StartsWith("/sdcard/", StringComparison.Ordinal))
        {
            var suffix = path.Substring(8).TrimStart('/');
            var alt = "/storage/emulated/0/" + suffix;
            var (combinedAlt, _) = RunAdbLs(adbPath, alt);
            if (!string.IsNullOrEmpty(combinedAlt) && !IsLsError(combinedAlt))
            {
                var items = ParseLs(combinedAlt, alt);
                if (items.Count > 0) return (items, null);
            }
        }

        var (outStr, code) = RunAdbLs(adbPath, path);
        if (!string.IsNullOrEmpty(outStr) && !IsLsError(outStr))
        {
            var items = ParseLs(outStr, path);
            if (items.Count > 0) return (items, null);
        }
        if (code != 0 && !string.IsNullOrEmpty(outStr))
            return (null, outStr.Trim());

        if (path.StartsWith("/sdcard/", StringComparison.Ordinal))
        {
            var suffix = path.Substring(8).TrimStart('/');
            var alt = "/storage/emulated/0/" + suffix;
            var (out2, code2) = RunAdbLs(adbPath, alt);
            if (!string.IsNullOrEmpty(out2) && !IsLsError(out2))
            {
                var items = ParseLs(out2, alt);
                if (items.Count > 0) return (items, null);
            }
            if (code2 != 0 && !string.IsNullOrEmpty(out2))
                return (null, out2.Trim());
        }

        return (null, "无法列出该目录（请检查路径或权限）");
    }
}
