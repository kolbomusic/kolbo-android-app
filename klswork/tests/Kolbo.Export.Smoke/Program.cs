using System.Diagnostics;
using NAudio.Wave;
using Kolbo.Live.Windows;

var session = Path.Combine(Path.GetTempPath(), "kolbo-export-smoke-" + Guid.NewGuid().ToString("N"));
Directory.CreateDirectory(session);
var master = Path.Combine(session, "master.wav");

using (var writer = new WaveFileWriter(master, WaveFormat.CreateIeeeFloatWaveFormat(48000, 2)))
{
    for (var i = 0; i < 48000 * 2; i++)
    {
        var sample = (float)(Math.Sin(2 * Math.PI * 440 * i / 48000.0) * 0.15);
        writer.WriteSample(sample);
        writer.WriteSample(sample);
    }
}

var tools = Path.Combine(AppContext.BaseDirectory, "tools");
var ffmpeg = Path.Combine(tools, "ffmpeg.exe");
if (!File.Exists(ffmpeg)) throw new Exception("ffmpeg missing from export smoke test");

var video = Path.Combine(session, "source.mp4");
var psi = new ProcessStartInfo(ffmpeg)
{
    UseShellExecute = false,
    CreateNoWindow = true,
    RedirectStandardError = true
};
foreach (var a in new[] { "-hide_banner","-loglevel","error","-y","-f","lavfi","-i","color=c=black:s=640x360:r=25","-t","2","-c:v","libx264","-pix_fmt","yuv420p",video })
    psi.ArgumentList.Add(a);
using (var p = Process.Start(psi)!)
{
    var err = await p.StandardError.ReadToEndAsync();
    await p.WaitForExitAsync();
    if (p.ExitCode != 0) throw new Exception("synthetic video failed: " + err);
}

double audioProgress = 0, videoProgress = 0;
var audio = await ExportService.ExportAudioAsync(session, new Progress<ExportProgressInfo>(p => audioProgress = Math.Max(audioProgress, p.Percent)));
if (!File.Exists(audio.WavPath) || new FileInfo(audio.WavPath).Length <= 100) throw new Exception("WAV export missing");
if (!File.Exists(audio.Mp3Path) || new FileInfo(audio.Mp3Path).Length <= 100) throw new Exception("MP3 export missing");

var mp4 = await ExportService.ExportVideoAsync(session, video, 0, new Progress<ExportProgressInfo>(p => videoProgress = Math.Max(videoProgress, p.Percent)));
if (!File.Exists(mp4) || new FileInfo(mp4).Length <= 1000) throw new Exception("MP4 export missing");

await Task.Delay(100);
if (audioProgress < 99) throw new Exception("audio progress did not reach completion");
if (videoProgress < 99) throw new Exception("video progress did not reach completion");

Console.WriteLine("PASS actual WAV+MP3 export");
Console.WriteLine("PASS actual MP4 export");
Console.WriteLine("PASS progress reaches 100%");
