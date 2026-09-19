using System.Diagnostics;
using System.IO;
using System.Security.Cryptography;
using System.Text;

namespace Kolbo.Live.Windows;

enum PlaybackSourceKind
{
    AudioFile,
    KaraokeVideo,
    YouTube
}

sealed record PreparedPlayback(
    PlaybackSourceKind Kind,
    string AudioPath,
    string? VideoPath,
    string DisplayName,
    string? SourceUrl = null);

sealed class MediaSourceService
{
    readonly string ffmpeg = Path.Combine(AppContext.BaseDirectory, "tools", "ffmpeg.exe");
    readonly string ytdlp = Path.Combine(AppContext.BaseDirectory, "tools", "yt-dlp.exe");
    readonly string cacheRoot = Path.Combine(
        Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
        "KolboLiveStudio",
        "MediaCache");

    static readonly HashSet<string> AudioExtensions = new(StringComparer.OrdinalIgnoreCase)
    {
        ".wav", ".mp3", ".m4a", ".aac", ".flac", ".aiff", ".aif", ".ogg", ".wma"
    };

    static readonly HashSet<string> VideoExtensions = new(StringComparer.OrdinalIgnoreCase)
    {
        ".mp4", ".m4v", ".mov", ".mkv", ".webm", ".avi", ".wmv", ".mpeg", ".mpg"
    };

    public static string FileDialogFilter =>
        "Audio / Karaoke Video|*.wav;*.mp3;*.m4a;*.aac;*.flac;*.aiff;*.aif;*.ogg;*.wma;*.mp4;*.m4v;*.mov;*.mkv;*.webm;*.avi;*.wmv;*.mpeg;*.mpg|" +
        "Audio|*.wav;*.mp3;*.m4a;*.aac;*.flac;*.aiff;*.aif;*.ogg;*.wma|" +
        "Karaoke Video|*.mp4;*.m4v;*.mov;*.mkv;*.webm;*.avi;*.wmv;*.mpeg;*.mpg|All files|*.*";

    public async Task<PreparedPlayback> PrepareLocalAsync(
        string path,
        IProgress<string>? progress = null,
        CancellationToken cancellationToken = default)
    {
        if (!File.Exists(path))
            throw new FileNotFoundException("קובץ הפלייבק לא נמצא", path);

        var ext = Path.GetExtension(path);
        if (AudioExtensions.Contains(ext))
            return new PreparedPlayback(PlaybackSourceKind.AudioFile, path, null, Path.GetFileName(path));

        if (!VideoExtensions.Contains(ext))
            throw new InvalidOperationException("סוג הקובץ אינו נתמך כפלייבק או כסרטון קריוקי.");

        EnsureFfmpeg();
        progress?.Report("מכין סרטון קריוקי ואודיו ל־ASIO...");
        return await NormalizeVideoAsync(path, PlaybackSourceKind.KaraokeVideo, Path.GetFileName(path), null, progress, cancellationToken);
    }

    public async Task<PreparedPlayback> PrepareYouTubeAsync(
        string url,
        IProgress<string>? progress = null,
        CancellationToken cancellationToken = default)
    {
        if (!Uri.TryCreate(url.Trim(), UriKind.Absolute, out var uri) ||
            (uri.Scheme != Uri.UriSchemeHttps && uri.Scheme != Uri.UriSchemeHttp))
            throw new InvalidOperationException("קישור YouTube אינו תקין.");

        if (!IsYouTubeHost(uri.Host))
            throw new InvalidOperationException("הכנס קישור YouTube או youtu.be.");

        EnsureFfmpeg();
        if (!File.Exists(ytdlp))
            throw new FileNotFoundException("yt-dlp.exe לא נמצא בחבילת התוכנה", ytdlp);

        Directory.CreateDirectory(cacheRoot);
        var job = Path.Combine(cacheRoot, "youtube-" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(job);
        var template = Path.Combine(job, "source.%(ext)s");

        progress?.Report("מוריד את סרטון הקריוקי מ־YouTube...");
        var args = new List<string>
        {
            "--no-playlist",
            "--no-progress",
            "--newline",
            "--windows-filenames",
            "--merge-output-format", "mp4",
            "--ffmpeg-location", Path.GetDirectoryName(ffmpeg)!,
            "-f", "bv*+ba/b",
            "-o", template,
            "--print", "after_move:filepath",
            uri.ToString()
        };

        var (exit, stdout, stderr) = await RunAsync(ytdlp, args, cancellationToken);
        if (exit != 0)
            throw new InvalidOperationException("טעינת YouTube נכשלה: " + Tail(stderr, 2500));

        var downloaded = stdout
            .Split(new[] { '\r', '\n' }, StringSplitOptions.RemoveEmptyEntries)
            .Select(x => x.Trim())
            .LastOrDefault(File.Exists);

        downloaded ??= Directory.EnumerateFiles(job)
            .Where(p => VideoExtensions.Contains(Path.GetExtension(p)) || AudioExtensions.Contains(Path.GetExtension(p)))
            .OrderByDescending(File.GetLastWriteTimeUtc)
            .FirstOrDefault();

        if (downloaded is null)
            throw new InvalidOperationException("YouTube הסתיים ללא קובץ מדיה.");

        var display = "YouTube: " + Path.GetFileNameWithoutExtension(downloaded);
        return await NormalizeVideoAsync(downloaded, PlaybackSourceKind.YouTube, display, uri.ToString(), progress, cancellationToken);
    }

    async Task<PreparedPlayback> NormalizeVideoAsync(
        string input,
        PlaybackSourceKind kind,
        string displayName,
        string? sourceUrl,
        IProgress<string>? progress,
        CancellationToken cancellationToken)
    {
        var key = Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(
            Path.GetFullPath(input) + "|" + new FileInfo(input).Length + "|" + File.GetLastWriteTimeUtc(input).Ticks)));
        var folder = Path.Combine(cacheRoot, key[..20]);
        Directory.CreateDirectory(folder);

        var audio = Path.Combine(folder, "playback.wav");
        var video = Path.Combine(folder, "karaoke.mp4");

        if (!File.Exists(audio))
        {
            progress?.Report("מחלץ את האודיו למסלול ASIO...");
            var audioArgs = new[]
            {
                "-hide_banner", "-loglevel", "error", "-y",
                "-i", input,
                "-map", "0:a:0",
                "-vn",
                "-ac", "2",
                "-ar", "48000",
                "-c:a", "pcm_s16le",
                audio
            };
            var (exit, _, stderr) = await RunAsync(ffmpeg, audioArgs, cancellationToken);
            if (exit != 0 || !File.Exists(audio))
                throw new InvalidOperationException("לא נמצא מסלול אודיו תקין בסרטון: " + Tail(stderr, 2000));
        }

        if (!File.Exists(video))
        {
            progress?.Report("מכין תצוגת וידאו אחידה לקריוקי...");
            var videoArgs = new[]
            {
                "-hide_banner", "-loglevel", "error", "-y",
                "-i", input,
                "-map", "0:v:0",
                "-an",
                "-c:v", "libx264",
                "-preset", "veryfast",
                "-crf", "20",
                "-pix_fmt", "yuv420p",
                "-movflags", "+faststart",
                video
            };
            var (exit, _, stderr) = await RunAsync(ffmpeg, videoArgs, cancellationToken);
            if (exit != 0 || !File.Exists(video))
                throw new InvalidOperationException("לא ניתן להכין את תצוגת סרטון הקריוקי: " + Tail(stderr, 2000));
        }

        progress?.Report("מקור הפלייבק מוכן.");
        return new PreparedPlayback(kind, audio, video, displayName, sourceUrl);
    }

    static bool IsYouTubeHost(string host)
    {
        host = host.TrimEnd('.').ToLowerInvariant();
        return host == "youtu.be" ||
               host == "youtube.com" ||
               host.EndsWith(".youtube.com", StringComparison.Ordinal);
    }

    void EnsureFfmpeg()
    {
        if (!File.Exists(ffmpeg))
            throw new FileNotFoundException("ffmpeg.exe לא נמצא בחבילת התוכנה", ffmpeg);
    }

    static async Task<(int ExitCode, string Stdout, string Stderr)> RunAsync(
        string executable,
        IEnumerable<string> arguments,
        CancellationToken cancellationToken)
    {
        var psi = new ProcessStartInfo(executable)
        {
            UseShellExecute = false,
            CreateNoWindow = true,
            RedirectStandardOutput = true,
            RedirectStandardError = true
        };
        foreach (var arg in arguments)
            psi.ArgumentList.Add(arg);

        using var process = new Process { StartInfo = psi };
        process.Start();
        var stdoutTask = process.StandardOutput.ReadToEndAsync(cancellationToken);
        var stderrTask = process.StandardError.ReadToEndAsync(cancellationToken);
        await process.WaitForExitAsync(cancellationToken);
        return (process.ExitCode, await stdoutTask, await stderrTask);
    }

    static string Tail(string text, int max) =>
        text.Length <= max ? text : text[^max..];
}
