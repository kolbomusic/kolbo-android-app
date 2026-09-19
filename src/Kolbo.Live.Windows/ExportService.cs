using System.Diagnostics;
using System.Globalization;
using System.IO;

namespace Kolbo.Live.Windows;

static class ExportService
{
    public static async Task<string> ExportPhoneMasterAsync(string sessionDirectory, double videoOffsetSeconds, CancellationToken cancellationToken = default)
    {
        var ffmpeg = Path.Combine(AppContext.BaseDirectory, "tools", "ffmpeg.exe");
        if (!File.Exists(ffmpeg)) throw new FileNotFoundException("ffmpeg.exe לא נמצא בחבילת התוכנה", ffmpeg);
        var master = Path.Combine(sessionDirectory, "master.wav");
        if (!File.Exists(master)) throw new FileNotFoundException("master.wav לא נמצא בסשן", master);
        var video = Directory.EnumerateFiles(sessionDirectory, "phone-video.*")
            .FirstOrDefault(p => p.EndsWith(".webm", StringComparison.OrdinalIgnoreCase) || p.EndsWith(".mp4", StringComparison.OrdinalIgnoreCase));
        if (video is null) throw new FileNotFoundException("וידאו מהטלפון עדיין לא נמצא בסשן");

        var output = Path.Combine(sessionDirectory, "final.mp4");
        var temp = Path.Combine(sessionDirectory, "final." + Guid.NewGuid().ToString("N") + ".tmp.mp4");
        var psi = new ProcessStartInfo(ffmpeg)
        {
            UseShellExecute = false,
            CreateNoWindow = true,
            RedirectStandardError = true,
            RedirectStandardOutput = true
        };
        psi.ArgumentList.Add("-hide_banner");
        psi.ArgumentList.Add("-y");
        psi.ArgumentList.Add("-itsoffset");
        psi.ArgumentList.Add(videoOffsetSeconds.ToString("0.###", CultureInfo.InvariantCulture));
        psi.ArgumentList.Add("-i"); psi.ArgumentList.Add(video);
        psi.ArgumentList.Add("-i"); psi.ArgumentList.Add(master);
        psi.ArgumentList.Add("-map"); psi.ArgumentList.Add("0:v:0");
        psi.ArgumentList.Add("-map"); psi.ArgumentList.Add("1:a:0");
        psi.ArgumentList.Add("-c:v"); psi.ArgumentList.Add("libx264");
        psi.ArgumentList.Add("-preset"); psi.ArgumentList.Add("medium");
        psi.ArgumentList.Add("-crf"); psi.ArgumentList.Add("18");
        psi.ArgumentList.Add("-pix_fmt"); psi.ArgumentList.Add("yuv420p");
        psi.ArgumentList.Add("-c:a"); psi.ArgumentList.Add("aac");
        psi.ArgumentList.Add("-b:a"); psi.ArgumentList.Add("256k");
        psi.ArgumentList.Add("-shortest");
        psi.ArgumentList.Add("-movflags"); psi.ArgumentList.Add("+faststart");
        psi.ArgumentList.Add(temp);

        using var process = new Process { StartInfo = psi };
        process.Start();
        var stderrTask = process.StandardError.ReadToEndAsync(cancellationToken);
        var stdoutTask = process.StandardOutput.ReadToEndAsync(cancellationToken);
        await process.WaitForExitAsync(cancellationToken);
        var stderr = await stderrTask;
        _ = await stdoutTask;
        if (process.ExitCode != 0)
        {
            try { if (File.Exists(temp)) File.Delete(temp); } catch { }
            var tail = stderr.Length <= 3000 ? stderr : stderr[^3000..];
            throw new InvalidOperationException("FFmpeg export failed: " + tail);
        }
        File.Move(temp, output, true);
        return output;
    }
}
