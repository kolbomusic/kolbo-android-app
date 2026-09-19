using System.Diagnostics;
using System.Globalization;
using System.IO;

namespace Kolbo.Live.Windows;

static class ExportService
{
    public static async Task<string> ExportResultAsync(
        string sessionDirectory,
        string? fallbackVideoPath,
        double videoOffsetSeconds,
        CancellationToken cancellationToken = default)
    {
        var ffmpeg = Path.Combine(AppContext.BaseDirectory, "tools", "ffmpeg.exe");
        if (!File.Exists(ffmpeg))
            throw new FileNotFoundException("ffmpeg.exe לא נמצא בחבילת התוכנה", ffmpeg);

        var master = Path.Combine(sessionDirectory, "master.wav");
        if (!File.Exists(master))
            throw new FileNotFoundException("master.wav לא נמצא בסשן", master);

        var phoneVideo = Directory.EnumerateFiles(sessionDirectory, "phone-video.*")
            .FirstOrDefault(IsVideo);

        var video = phoneVideo ?? (fallbackVideoPath is not null && File.Exists(fallbackVideoPath) ? fallbackVideoPath : null);

        return video is null
            ? await ExportAudioOnlyAsync(ffmpeg, master, sessionDirectory, cancellationToken)
            : await ExportVideoAsync(ffmpeg, video, master, sessionDirectory, videoOffsetSeconds, cancellationToken);
    }

    static async Task<string> ExportAudioOnlyAsync(
        string ffmpeg,
        string master,
        string sessionDirectory,
        CancellationToken cancellationToken)
    {
        var output = Path.Combine(sessionDirectory, "final-audio.mp3");
        var temp = Path.Combine(sessionDirectory, "final-audio." + Guid.NewGuid().ToString("N") + ".tmp.mp3");

        var args = new[]
        {
            "-hide_banner", "-y",
            "-i", master,
            "-map", "0:a:0",
            "-c:a", "libmp3lame",
            "-b:a", "320k",
            "-id3v2_version", "3",
            temp
        };

        await RunAsync(ffmpeg, args, temp, cancellationToken);
        File.Move(temp, output, true);
        return output;
    }

    static async Task<string> ExportVideoAsync(
        string ffmpeg,
        string video,
        string master,
        string sessionDirectory,
        double videoOffsetSeconds,
        CancellationToken cancellationToken)
    {
        var output = Path.Combine(sessionDirectory, "final-video.mp4");
        var temp = Path.Combine(sessionDirectory, "final-video." + Guid.NewGuid().ToString("N") + ".tmp.mp4");

        var args = new List<string>
        {
            "-hide_banner", "-y",
            "-itsoffset", videoOffsetSeconds.ToString("0.###", CultureInfo.InvariantCulture),
            "-i", video,
            "-i", master,
            "-map", "0:v:0",
            "-map", "1:a:0",
            "-c:v", "libx264",
            "-preset", "medium",
            "-crf", "18",
            "-pix_fmt", "yuv420p",
            "-c:a", "aac",
            "-b:a", "256k",
            "-shortest",
            "-movflags", "+faststart",
            temp
        };

        await RunAsync(ffmpeg, args, temp, cancellationToken);
        File.Move(temp, output, true);
        return output;
    }

    static async Task RunAsync(
        string executable,
        IEnumerable<string> args,
        string tempOutput,
        CancellationToken cancellationToken)
    {
        var psi = new ProcessStartInfo(executable)
        {
            UseShellExecute = false,
            CreateNoWindow = true,
            RedirectStandardError = true,
            RedirectStandardOutput = true
        };

        foreach (var arg in args)
            psi.ArgumentList.Add(arg);

        using var process = new Process { StartInfo = psi };
        process.Start();

        var stderrTask = process.StandardError.ReadToEndAsync(cancellationToken);
        var stdoutTask = process.StandardOutput.ReadToEndAsync(cancellationToken);
        await process.WaitForExitAsync(cancellationToken);
        var stderr = await stderrTask;
        _ = await stdoutTask;

        if (process.ExitCode == 0) return;

        try
        {
            if (File.Exists(tempOutput))
                File.Delete(tempOutput);
        }
        catch { }

        var tail = stderr.Length <= 3000 ? stderr : stderr[^3000..];
        throw new InvalidOperationException("FFmpeg export failed: " + tail);
    }

    static bool IsVideo(string path) =>
        path.EndsWith(".webm", StringComparison.OrdinalIgnoreCase) ||
        path.EndsWith(".mp4", StringComparison.OrdinalIgnoreCase) ||
        path.EndsWith(".mov", StringComparison.OrdinalIgnoreCase) ||
        path.EndsWith(".mkv", StringComparison.OrdinalIgnoreCase);
}
