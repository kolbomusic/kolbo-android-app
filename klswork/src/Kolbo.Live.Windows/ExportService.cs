using System.Diagnostics;
using System.Globalization;
using System.IO;
using NAudio.Wave;

namespace Kolbo.Live.Windows;

sealed record ExportedAudio(string WavPath, string Mp3Path);
sealed record ExportProgressInfo(double Percent, string Message);

static class ExportService
{
    public static async Task<ExportedAudio> ExportAudioAsync(
        string sessionDirectory,
        IProgress<ExportProgressInfo>? progress = null,
        CancellationToken cancellationToken = default)
    {
        var ffmpeg = Ffmpeg();
        var master = Master(sessionDirectory);
        var duration = DurationSeconds(master);

        progress?.Report(new ExportProgressInfo(5, "מכין WAV ללא אובדן איכות..."));
        var wav = Path.Combine(sessionDirectory, "final-audio.wav");
        File.Copy(master, wav, true);

        cancellationToken.ThrowIfCancellationRequested();
        progress?.Report(new ExportProgressInfo(12, "מקודד MP3 באיכות 320kbps..."));

        var mp3 = Path.Combine(sessionDirectory, "final-audio.mp3");
        var temp = Path.Combine(sessionDirectory, "final-audio." + Guid.NewGuid().ToString("N") + ".tmp.mp3");
        var args = new[]
        {
            "-hide_banner", "-y",
            "-i", master,
            "-map", "0:a:0",
            "-c:a", "libmp3lame",
            "-b:a", "320k",
            "-id3v2_version", "3",
            "-progress", "pipe:1",
            "-nostats",
            temp
        };

        await RunWithProgressAsync(
            ffmpeg, args, temp, duration,
            p => progress?.Report(new ExportProgressInfo(12 + p * 0.88, $"מייצא MP3... {Math.Round(p)}%")),
            cancellationToken);

        File.Move(temp, mp3, true);
        progress?.Report(new ExportProgressInfo(100, "ייצוא האודיו הושלם."));
        return new ExportedAudio(wav, mp3);
    }

    public static async Task<string> ExportVideoAsync(
        string sessionDirectory,
        string? fallbackVideoPath,
        double videoOffsetSeconds,
        IProgress<ExportProgressInfo>? progress = null,
        CancellationToken cancellationToken = default)
    {
        var ffmpeg = Ffmpeg();
        var master = Master(sessionDirectory);
        var duration = DurationSeconds(master);

        var phoneVideo = Directory.EnumerateFiles(sessionDirectory, "phone-video.*")
            .FirstOrDefault(IsVideo);
        var video = phoneVideo ??
                    (fallbackVideoPath is not null && File.Exists(fallbackVideoPath)
                        ? fallbackVideoPath
                        : null);

        if (video is null)
            throw new InvalidOperationException("אין וידאו לסשן הזה. ייצוא אודיו אינו דורש וידאו; ל־MP4 חבר מצלמת טלפון או בחר סרטון קריוקי.");

        progress?.Report(new ExportProgressInfo(2, "מכין ייצוא MP4..."));
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
            "-progress", "pipe:1",
            "-nostats",
            temp
        };

        await RunWithProgressAsync(
            ffmpeg, args, temp, duration,
            p => progress?.Report(new ExportProgressInfo(Math.Max(2, p), $"מייצא MP4... {Math.Round(p)}%")),
            cancellationToken);

        File.Move(temp, output, true);
        progress?.Report(new ExportProgressInfo(100, "ייצוא הווידאו הושלם."));
        return output;
    }

    static double DurationSeconds(string master)
    {
        using var reader = new WaveFileReader(master);
        return Math.Max(0.1, reader.TotalTime.TotalSeconds);
    }

    static string Ffmpeg()
    {
        var ffmpeg = Path.Combine(AppContext.BaseDirectory, "tools", "ffmpeg.exe");
        if (!File.Exists(ffmpeg))
            throw new FileNotFoundException("ffmpeg.exe לא נמצא בחבילת התוכנה", ffmpeg);
        return ffmpeg;
    }

    static string Master(string sessionDirectory)
    {
        var master = Path.Combine(sessionDirectory, "master.wav");
        if (!File.Exists(master))
            throw new FileNotFoundException("master.wav לא נמצא בסשן", master);
        return master;
    }

    static async Task RunWithProgressAsync(
        string executable,
        IEnumerable<string> args,
        string tempOutput,
        double durationSeconds,
        Action<double> progress,
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
        try
        {
            while (true)
            {
                var line = await process.StandardOutput.ReadLineAsync(cancellationToken);
                if (line is null) break;

                if (line.StartsWith("out_time_ms=", StringComparison.Ordinal) &&
                    long.TryParse(line.AsSpan("out_time_ms=".Length), NumberStyles.Integer, CultureInfo.InvariantCulture, out var micros))
                {
                    var seconds = micros / 1_000_000d;
                    progress(Math.Clamp(seconds / durationSeconds * 100d, 0d, 99d));
                }
                else if (line.StartsWith("out_time=", StringComparison.Ordinal) &&
                         TimeSpan.TryParse(line["out_time=".Length..], CultureInfo.InvariantCulture, out var time))
                {
                    progress(Math.Clamp(time.TotalSeconds / durationSeconds * 100d, 0d, 99d));
                }
            }

            await process.WaitForExitAsync(cancellationToken);
            var stderr = await stderrTask;

            if (process.ExitCode == 0)
            {
                progress(100);
                return;
            }

            var tail = stderr.Length <= 3000 ? stderr : stderr[^3000..];
            throw new InvalidOperationException("FFmpeg export failed: " + tail);
        }
        catch (OperationCanceledException)
        {
            try
            {
                if (!process.HasExited) process.Kill(entireProcessTree: true);
            }
            catch { }
            throw;
        }
        finally
        {
            try
            {
                if (File.Exists(tempOutput))
                    File.Delete(tempOutput);
            }
            catch { }
        }
    }

    static bool IsVideo(string path) =>
        path.EndsWith(".webm", StringComparison.OrdinalIgnoreCase) ||
        path.EndsWith(".mp4", StringComparison.OrdinalIgnoreCase) ||
        path.EndsWith(".mov", StringComparison.OrdinalIgnoreCase) ||
        path.EndsWith(".mkv", StringComparison.OrdinalIgnoreCase);
}
