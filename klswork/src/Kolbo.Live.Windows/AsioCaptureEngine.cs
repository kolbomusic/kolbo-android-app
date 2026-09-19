using System.Buffers;
using System.IO;
using NAudio.Wave;
using NAudio.Wave.SampleProviders;
using Kolbo.Live.Core;

namespace Kolbo.Live.Windows;

/// <summary>
/// Low-latency ASIO duplex engine. The exact same master sample block is sent to the
/// selected monitor outputs and queued for lossless recording. Only the dry mic is
/// sent to the hardware-FX send outputs, so wet/master audio cannot feed back into FX.
/// </summary>
sealed class AsioCaptureEngine : IDisposable
{
    AsioDevice? asio;
    SessionWriter? writer;
    Routing? routing;
    Gains gains = new();
    float[] backingSamples = [];
    int backingPosition;
    float[] dryBlock = [];
    float[] wetBlock = [];
    float[] backingBlock = [];
    float[] masterBlock = [];
    float[] sendBlock = [];
    string? error;
    long frames;
    long overloads;
    float dryPeak;
    float wetPeak;

    public bool Running { get; private set; }
    public long Frames => Interlocked.Read(ref frames);
    public long Overloads => Interlocked.Read(ref overloads);
    public string? Error => Volatile.Read(ref error) ?? writer?.Error;
    public float DryPeak => Volatile.Read(ref dryPeak);
    public float WetPeak => Volatile.Read(ref wetPeak);

    public static IReadOnlyList<string> Drivers() => AsioDevice.GetDriverNames();

    public static DeviceProbe Probe(string driver, IEnumerable<int> candidateRates)
    {
        using var device = AsioDevice.Open(driver);
        var rates = candidateRates.Distinct().Where(device.IsSampleRateSupported).ToArray();
        var inputs = device.Capabilities.InputChannelInfos
            .Select((c, i) => new AudioChannel(i, string.IsNullOrWhiteSpace(c.name) ? $"Input {i + 1}" : c.name))
            .ToArray();
        var outputs = device.Capabilities.OutputChannelInfos
            .Select((c, i) => new AudioChannel(i, string.IsNullOrWhiteSpace(c.name) ? $"Output {i + 1}" : c.name))
            .ToArray();
        return new DeviceProbe(inputs, outputs, rates, device.CurrentSampleRate);
    }

    public void Start(string driver, int rate, string folder, string backingPath, Routing route, Gains mix)
    {
        if (Running) throw new InvalidOperationException("כבר מתבצעת הקלטה");
        if (!AsioDevice.GetDriverNames().Contains(driver, StringComparer.Ordinal))
            throw new InvalidOperationException("דרייבר ASIO לא נמצא");

        var device = AsioDevice.Open(driver);
        try
        {
            if (!device.IsSampleRateSupported(rate))
                throw new InvalidOperationException($"הכרטיס אינו תומך ב־{rate}Hz");
            if (device.CurrentSampleRate != rate)
                throw new InvalidOperationException($"הכרטיס מוגדר כרגע ל־{device.CurrentSampleRate}Hz. שנה את Sample Rate בלוח הבקרה של הכרטיס ל־{rate}Hz ואז נסה שוב; התוכנה לא משנה Clock/Sample Rate אוטומטית.");

            var validation = route.Validate(
                device.Capabilities.NbInputChannels,
                device.Capabilities.NbOutputChannels,
                [rate],
                wetOnlyConfirmed: true);
            if (validation.Length != 0)
                throw new InvalidOperationException(string.Join("; ", validation));

            backingSamples = LoadBacking(backingPath, rate);
            backingPosition = 0;
            routing = route;
            gains = mix;

            device.InitDuplex(new AsioDuplexOptions
            {
                InputChannels = [route.Dry, route.WetLeft, route.WetRight],
                OutputChannels = [route.SendLeft, route.SendRight, route.MasterLeft, route.MasterRight],
                SampleRate = rate,
                Processor = ProcessAudio
            });

            var blockFrames = device.FramesPerBuffer;
            dryBlock = new float[blockFrames];
            wetBlock = new float[blockFrames * 2];
            backingBlock = new float[blockFrames * 2];
            masterBlock = new float[blockFrames * 2];
            sendBlock = new float[blockFrames * 2];

            var sessionId = Path.GetFileName(folder.TrimEnd(Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar));
            writer = new SessionWriter(
                folder,
                rate,
                blockFrames,
                128,
                metadata: new SessionManifest(sessionId, rate, "Recording", 0, Routing: route, Gains: mix, Device: driver));

            device.Stopped += (_, e) =>
            {
                if (e.Exception is not null)
                    Volatile.Write(ref error, "ASIO stopped: " + e.Exception.Message);
            };
            device.DriverResetRequest += (_, _) =>
                Volatile.Write(ref error, "ASIO driver settings changed during the session. Stop and start a new recording.");

            asio = device;
            device.Start();
            Running = true;
        }
        catch
        {
            device.Dispose();
            writer?.Dispose();
            writer = null;
            backingSamples = [];
            throw;
        }
    }

    void ProcessAudio(in AsioProcessBuffers b)
    {
        try
        {
            var n = b.Frames;
            var dryIn = b.GetInput(0);
            var wetL = b.GetInput(1);
            var wetR = b.GetInput(2);
            var sendL = b.GetOutput(0);
            var sendR = b.GetOutput(1);
            var masterL = b.GetOutput(2);
            var masterR = b.GetOutput(3);

            float dp = 0, wp = 0;
            var bp = backingPosition;
            for (var i = 0; i < n; i++)
            {
                var d = Finite(dryIn[i]);
                var wl = Finite(wetL[i]);
                var wr = Finite(wetR[i]);
                dryBlock[i] = d;
                wetBlock[i * 2] = wl;
                wetBlock[i * 2 + 1] = wr;

                if (bp + 1 < backingSamples.Length)
                {
                    backingBlock[i * 2] = backingSamples[bp++];
                    backingBlock[i * 2 + 1] = backingSamples[bp++];
                }
                else
                {
                    backingBlock[i * 2] = 0;
                    backingBlock[i * 2 + 1] = 0;
                }
                dp = Math.Max(dp, Math.Abs(d));
                wp = Math.Max(wp, Math.Max(Math.Abs(wl), Math.Abs(wr)));
            }
            backingPosition = bp;

            var clipped = Mixer.Process(dryBlock.AsSpan(0, n), wetBlock.AsSpan(0, n * 2), backingBlock.AsSpan(0, n * 2), masterBlock.AsSpan(0, n * 2), sendBlock.AsSpan(0, n * 2), gains);
            if (clipped > 0) Interlocked.Add(ref overloads, clipped);

            for (var i = 0; i < n; i++)
            {
                sendL[i] = sendBlock[i * 2];
                sendR[i] = sendBlock[i * 2 + 1];
                masterL[i] = masterBlock[i * 2];
                masterR[i] = masterBlock[i * 2 + 1];
            }

            if (writer is null || !writer.TryWrite(dryBlock.AsSpan(0, n), wetBlock.AsSpan(0, n * 2), backingBlock.AsSpan(0, n * 2), masterBlock.AsSpan(0, n * 2)))
                Volatile.Write(ref error, writer?.Error ?? "לא ניתן לשמור את האודיו");

            Volatile.Write(ref dryPeak, Math.Clamp(dp, 0, 1));
            Volatile.Write(ref wetPeak, Math.Clamp(wp, 0, 1));
            Interlocked.Add(ref frames, n);
        }
        catch (Exception ex)
        {
            Volatile.Write(ref error, ex.Message);
            writer?.Fail(ex.Message);
            throw;
        }
    }

    static float Finite(float value) => float.IsFinite(value) ? value : 0;

    static float[] LoadBacking(string path, int rate)
    {
        using var reader = new AudioFileReader(path);
        ISampleProvider source = reader;
        if (source.WaveFormat.Channels == 1)
            source = new MonoToStereoSampleProvider(source);
        else if (source.WaveFormat.Channels != 2)
            throw new InvalidOperationException("הפלייבק חייב להיות מונו או סטריאו");
        if (source.WaveFormat.SampleRate != rate)
            source = new WdlResamplingSampleProvider(source, rate);

        var estimated = Math.Max(65536L, (long)(reader.TotalTime.TotalSeconds + 1) * rate * 2);
        if (estimated > 600_000_000)
            throw new InvalidOperationException("קובץ הפלייבק גדול מדי לטעינה בטוחה לזיכרון");
        var capacity = (int)Math.Min(8_000_000L, estimated);
        var buffer = new ArrayBufferWriter<float>(capacity);
        while (true)
        {
            var span = buffer.GetSpan(32768);
            var read = source.Read(span[..32768]);
            if (read <= 0) break;
            buffer.Advance(read);
            if (buffer.WrittenCount > 600_000_000)
                throw new InvalidOperationException("קובץ הפלייבק גדול מדי לטעינה בטוחה לזיכרון");
        }
        return buffer.WrittenSpan.ToArray();
    }

    public void Stop()
    {
        if (!Running && asio is null && writer is null) return;
        try { asio?.Stop(); }
        catch (Exception ex) { Volatile.Write(ref error, ex.Message); }
        finally
        {
            asio?.Dispose();
            asio = null;
            writer?.Complete();
            writer = null;
            backingSamples = [];
            dryBlock = wetBlock = backingBlock = masterBlock = sendBlock = [];
            Running = false;
        }
    }

    public void Dispose() => Stop();
}

sealed record AudioChannel(int Index, string Name)
{
    public override string ToString() => $"{Index + 1}: {Name}";
}

sealed record DeviceProbe(IReadOnlyList<AudioChannel> Inputs, IReadOnlyList<AudioChannel> Outputs, IReadOnlyList<int> Rates, int CurrentRate);
