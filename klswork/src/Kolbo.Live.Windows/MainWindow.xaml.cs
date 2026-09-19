using System.Collections.ObjectModel;
using System.Diagnostics;
using System.Globalization;
using System.IO;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Media;
using System.Windows.Media.Imaging;
using System.Windows.Threading;
using Microsoft.Win32;
using Kolbo.Live.Core;
using QRCoder;

namespace Kolbo.Live.Windows;

public partial class MainWindow : Window
{
    static readonly int[] CandidateRates = [44100, 48000, 88200, 96000, 192000];
    public ObservableCollection<string> Devices { get; } = [];

    AsioCaptureEngine? engine;
    PhonePairingServer? phone;
    Window? phoneDialog;
    bool recording;
    bool probed;
    bool mr816ExternalFxReady;
    int dryActiveTicks;
    bool wetSeen;
    bool effectGateFailed;
    bool requireWetReturn;
    int[] supportedRates = [];
    string? backingPath;
    string? sessionId;
    string? sessionDirectory;
    string? lastOutputPath;
    PreparedPlayback? preparedPlayback;
    readonly MediaSourceService mediaSources = new();
    CancellationTokenSource? mediaLoadCts;
    CancellationTokenSource? exportCts;
    readonly DispatcherTimer uiTimer;
    readonly Stopwatch elapsed = new();

    public MainWindow()
    {
        InitializeComponent();

        var work = SystemParameters.WorkArea;
        Width = Math.Min(1180, Math.Max(860, work.Width - 24));
        Height = Math.Min(700, Math.Max(560, work.Height - 24));
        Left = work.Left + Math.Max(0, (work.Width - Width) / 2);
        Top = work.Top + Math.Max(0, (work.Height - Height) / 2);

        DeviceBox.ItemsSource = Devices;
        LoadDevices();
        UpdateMixLabels();

        uiTimer = new DispatcherTimer(TimeSpan.FromMilliseconds(80), DispatcherPriority.Background, (_, _) => UpdateMeters(), Dispatcher);
        uiTimer.Start();
    }

    static bool IsMr816Driver(string driver) =>
        driver.Contains("Yamaha Steinberg FW ASIO", StringComparison.OrdinalIgnoreCase);

    Gains CurrentGains() => new(
        (float)(DryGain.Value / 100.0),
        (float)(WetGain.Value / 100.0),
        (float)(BackingGain.Value / 100.0),
        (float)(SendGain.Value / 100.0));

    void MixGain_ValueChanged(object sender, RoutedPropertyChangedEventArgs<double> e)
    {
        if (MicLevelText is null || PlaybackLevelText is null || WetLevelText is null || SendLevelText is null) return;
        UpdateMixLabels();
        engine?.UpdateGains(CurrentGains());
    }

    void UpdateMixLabels()
    {
        MicLevelText.Text = $"{Math.Round(DryGain.Value)}%";
        PlaybackLevelText.Text = $"{Math.Round(BackingGain.Value)}%";
        WetLevelText.Text = $"{Math.Round(WetGain.Value)}%";
        SendLevelText.Text = $"{Math.Round(SendGain.Value)}%";
    }

    void LoadDevices()
    {
        try { foreach (var n in AsioCaptureEngine.Drivers()) Devices.Add(n); }
        catch (Exception ex) { InfoText.Text = "קריאת ASIO נכשלה: " + ex.Message; }
        if (Devices.Count > 0) DeviceBox.SelectedIndex = 0;
    }

    void DeviceBox_SelectionChanged(object sender, SelectionChangedEventArgs e)
    {
        if (!IsLoaded || recording) return;
        InvalidateProbe("כרטיס ה-ASIO השתנה. בצע שוב בדיקת ASIO ומיפוי.");
    }

    void AsioControlPanel_Click(object sender, RoutedEventArgs e)
    {
        if (recording)
        {
            InfoText.Text = "לא ניתן לפתוח את לוח הבקרה של ASIO בזמן הקלטה.";
            return;
        }
        if (DeviceBox.SelectedItem is not string driver)
        {
            InfoText.Text = "בחר דרייבר ASIO תחילה.";
            return;
        }

        try
        {
            using var device = NAudio.Wave.AsioDevice.Open(driver);
            device.ShowControlPanel();
            InvalidateProbe(IsMr816Driver(driver)
                ? "לוח הבקרה נסגר. אם בחרת Digital I/O / External FX = External FX, לחץ עכשיו על בדיקת ASIO ומיפוי."
                : "לוח הבקרה נסגר. בצע שוב בדיקת ASIO ומיפוי.");
        }
        catch (Exception ex)
        {
            InfoText.Text = "פתיחת לוח הבקרה של ASIO נכשלה: " + ex.Message;
        }
    }

    void InvalidateProbe(string message)
    {
        probed = false;
        mr816ExternalFxReady = false;
        supportedRates = [];
        foreach (var box in new[] { DryBox, WetLBox, WetRBox, SendLBox, SendRBox, MasterLBox, MasterRBox })
        {
            box.ItemsSource = null;
            box.SelectedItem = null;
        }
        HardwareProfileText.Text = "נדרשת בדיקת ASIO מחדש";
        HardwareProfileText.Foreground = Brushes.Gold;
        EffectStatusText.Text = "לא נבדק.";
        EffectStatusDot.Fill = Brushes.Goldenrod;
        InfoText.Text = message;
        SetState("נדרשת בדיקת ASIO", "#F4B942");
    }

    async void ChooseBacking_Click(object sender, RoutedEventArgs e)
    {
        if (recording)
        {
            InfoText.Text = "עצור את ההקלטה לפני החלפת מקור הפלייבק.";
            return;
        }

        var d = new OpenFileDialog { Filter = MediaSourceService.FileDialogFilter };
        if (d.ShowDialog() != true) return;

        try
        {
            await PreparePlaybackAsync(
                ct => mediaSources.PrepareLocalAsync(
                    d.FileName,
                    new Progress<string>(s => MediaStatusText.Text = s),
                    ct),
                "מכין את מקור הפלייבק...");
        }
        catch (OperationCanceledException)
        {
            MediaStatusText.Text = "טעינת המדיה בוטלה.";
        }
        catch (Exception ex)
        {
            SetState("שגיאת מדיה", "#E45757");
            MediaStatusText.Text = "טעינת הקובץ נכשלה: " + ex.Message;
            InfoText.Text = MediaStatusText.Text;
        }
    }

    async void LoadYouTube_Click(object sender, RoutedEventArgs e)
    {
        if (recording)
        {
            InfoText.Text = "עצור את ההקלטה לפני החלפת מקור הפלייבק.";
            return;
        }

        var url = YouTubeUrlBox.Text.Trim();
        if (string.IsNullOrWhiteSpace(url))
        {
            MediaStatusText.Text = "הדבק קישור YouTube תחילה.";
            return;
        }

        try
        {
            await PreparePlaybackAsync(
                ct => mediaSources.PrepareYouTubeAsync(
                    url,
                    new Progress<string>(s => MediaStatusText.Text = s),
                    ct),
                "טוען YouTube...");
        }
        catch (OperationCanceledException)
        {
            MediaStatusText.Text = "טעינת YouTube בוטלה.";
        }
        catch (Exception ex)
        {
            SetState("שגיאת YouTube", "#E45757");
            MediaStatusText.Text = "טעינת YouTube נכשלה: " + ex.Message;
            InfoText.Text = MediaStatusText.Text;
        }
    }

    async Task PreparePlaybackAsync(Func<CancellationToken, Task<PreparedPlayback>> loader, string initialStatus)
    {
        mediaLoadCts?.Cancel();
        mediaLoadCts?.Dispose();
        mediaLoadCts = new CancellationTokenSource();
        SetState("מכין מדיה", "#F4B942");
        MediaStatusText.Text = initialStatus;
        var prepared = await loader(mediaLoadCts.Token);
        ApplyPreparedPlayback(prepared);
        SetState("מקור מוכן", "#35D7C5");
    }

    void ApplyPreparedPlayback(PreparedPlayback prepared)
    {
        preparedPlayback = prepared;
        backingPath = prepared.AudioPath;

        var kind = prepared.Kind switch
        {
            PlaybackSourceKind.AudioFile => "אודיו",
            PlaybackSourceKind.KaraokeVideo => "סרטון קריוקי",
            PlaybackSourceKind.YouTube => "YouTube",
            _ => "מדיה"
        };

        BackingText.Text = $"{kind}: {prepared.DisplayName}";
        MediaStatusText.Text = prepared.VideoPath is null
            ? "האודיו מוכן ל-ASIO."
            : "הווידאו מוכן לתצוגה. האודיו שלו ייכנס דרך ASIO כדי שלא יהיה אודיו כפול.";

        KaraokeVideoPlayer.Stop();
        if (prepared.VideoPath is not null)
        {
            KaraokeVideoPlayer.Source = new Uri(prepared.VideoPath, UriKind.Absolute);
            KaraokeVideoPlayer.Position = TimeSpan.Zero;
            KaraokeVideoFrame.Visibility = Visibility.Visible;
        }
        else
        {
            KaraokeVideoPlayer.Source = null;
            KaraokeVideoFrame.Visibility = Visibility.Collapsed;
        }

        InfoText.Text = "מקור הפלייבק מוכן. בצע בדיקת ASIO ומיפוי לפני ההקלטה.";
    }

    void StartKaraokeVideo()
    {
        if (preparedPlayback?.VideoPath is null) return;
        try
        {
            KaraokeVideoPlayer.Stop();
            KaraokeVideoPlayer.Position = TimeSpan.Zero;
            KaraokeVideoPlayer.Play();
        }
        catch (Exception ex)
        {
            MediaStatusText.Text = "האודיו ממשיך דרך ASIO, אך תצוגת הווידאו לא התחילה: " + ex.Message;
        }
    }

    void StopKaraokeVideo()
    {
        try { KaraokeVideoPlayer.Stop(); } catch { }
    }

    void Probe_Click(object sender, RoutedEventArgs e)
    {
        if (recording) return;
        if (DeviceBox.SelectedItem is not string driver)
        {
            InfoText.Text = "בחר דרייבר ASIO תחילה.";
            return;
        }

        try
        {
            SetState("בודק ASIO", "#F4B942");
            var probe = AsioCaptureEngine.Probe(driver, CandidateRates);
            DryBox.ItemsSource = probe.Inputs;
            WetLBox.ItemsSource = probe.Inputs;
            WetRBox.ItemsSource = probe.Inputs;
            SendLBox.ItemsSource = probe.Outputs;
            SendRBox.ItemsSource = probe.Outputs;
            MasterLBox.ItemsSource = probe.Outputs;
            MasterRBox.ItemsSource = probe.Outputs;

            supportedRates = probe.Rates.ToArray();
            SelectRate(probe.CurrentRate);
            probed = true;
            mr816ExternalFxReady = false;

            if (IsMr816Driver(driver))
            {
                if (probe.Inputs.Count >= 10 && probe.Outputs.Count >= 10)
                {
                    SelectIndex(DryBox, 0);
                    SelectIndex(WetLBox, 8);
                    SelectIndex(WetRBox, 9);
                    SelectIndex(SendLBox, 8);
                    SelectIndex(SendRBox, 9);
                    SelectIndex(MasterLBox, 0);
                    SelectIndex(MasterRBox, 1);
                    mr816ExternalFxReady = true;

                    HardwareProfileText.Text =
                        $"MR816X זוהה עם {probe.Inputs.Count} כניסות / {probe.Outputs.Count} יציאות. " +
                        "נבחר מסלול REV-X דרך DAW/ASIO 9/10 ו-Monitor 1/2. " +
                        "המסלול יאושר רק לאחר זיהוי Wet Return אמיתי.";
                    HardwareProfileText.Foreground = Brushes.LightGreen;
                    EffectStatusText.Text = "מסלול REV-X מועמד מוכן. אם לא יגיע Wet אמיתי בזמן הטייק — ההקלטה תיעצר.";
                    EffectStatusDot.Fill = Brushes.Goldenrod;
                    InfoText.Text = $"MR816X מוכן לבדיקה. Sample Rate: {probe.CurrentRate} Hz.";
                }
                else
                {
                    SelectIndex(DryBox, 0);
                    SelectIndex(MasterLBox, 0);
                    SelectIndex(MasterRBox, 1);
                    HardwareProfileText.Text =
                        $"Yamaha Steinberg FW ASIO זוהה עם {probe.Inputs.Count} כניסות / {probe.Outputs.Count} יציאות, " +
                        "אך אין מספיק ערוצים למסלול REV-X 9/10.";
                    HardwareProfileText.Foreground = Brushes.OrangeRed;
                    EffectStatusText.Text = "פתח לוח בקרה ASIO ובדוק Digital I/O / External FX.";
                    EffectStatusDot.Fill = Brushes.OrangeRed;
                }
            }
            else
            {
                SelectIndex(DryBox, 0);
                SelectIndex(WetLBox, 1);
                SelectIndex(WetRBox, 2);
                SelectIndex(SendLBox, 2);
                SelectIndex(SendRBox, 3);
                SelectIndex(MasterLBox, 0);
                SelectIndex(MasterRBox, 1);
                HardwareProfileText.Text = "כרטיס כללי: מפה ידנית את Dry / Wet Return / FX Send / Monitor.";
                HardwareProfileText.Foreground = Brushes.LightBlue;
                InfoText.Text = $"ASIO זוהה: {probe.Inputs.Count} כניסות, {probe.Outputs.Count} יציאות. Sample Rate: {probe.CurrentRate} Hz.";
            }

            SetState(mr816ExternalFxReady || !IsMr816Driver(driver) ? "ASIO מוכן" : "נדרש External FX",
                mr816ExternalFxReady || !IsMr816Driver(driver) ? "#35D7C5" : "#E45757");
        }
        catch (Exception ex)
        {
            probed = false;
            mr816ExternalFxReady = false;
            SetState("שגיאת ASIO", "#E45757");
            InfoText.Text = "בדיקת ASIO נכשלה: " + ex.Message;
        }
    }

    async void PairPhone_Click(object sender, RoutedEventArgs e)
    {
        try
        {
            if (phone is not null)
            {
                await phone.DisposeAsync();
                phone = null;
            }

            PhonePreviewImage.Source = null;
            PhoneStatusText.Text = "מכין קישור HTTPS מאובטח...";
            phone = new PhonePairingServer();
            phone.StatusChanged += status => Dispatcher.BeginInvoke(() => PhoneStatusText.Text = status);
            phone.PreviewFrameReceived += bytes => Dispatcher.BeginInvoke(() => ShowPhonePreview(bytes));
            phone.VideoSaved += path => Dispatcher.BeginInvoke(() =>
            {
                lastOutputPath = path;
                PhoneStatusText.Text = "סרטון הטלפון נשמר ומוכן לייצוא.";
                ExportStatusText.Text = "וידאו מהטלפון התקבל. אפשר לייצא MP4.";
            });

            await phone.StartAsync();
            ShowPairingWindow(phone.Url!);
            PhoneStatusText.Text = "QR מוכן — אשר מצלמה בדפדפן. אפשר לעשות זאת לפני ההקלטה.";
        }
        catch (Exception ex)
        {
            if (phone is not null)
            {
                await phone.DisposeAsync();
                phone = null;
            }
            PhoneStatusText.Text = "חיבור מצלמה נכשל.";
            InfoText.Text = "חיבור מצלמת הטלפון נכשל: " + ex.Message;
        }
    }

    void ShowPhonePreview(byte[] jpeg)
    {
        try
        {
            var bitmap = new BitmapImage();
            using var ms = new MemoryStream(jpeg);
            bitmap.BeginInit();
            bitmap.CacheOption = BitmapCacheOption.OnLoad;
            bitmap.StreamSource = ms;
            bitmap.EndInit();
            bitmap.Freeze();
            PhonePreviewImage.Source = bitmap;
        }
        catch { }
    }

    async void Record_Click(object sender, RoutedEventArgs e)
    {
        if (recording) return;
        if (DeviceBox.SelectedItem is not string driver) { InfoText.Text = "בחר דרייבר ASIO תחילה."; return; }
        if (backingPath is null) { InfoText.Text = "בחר מקור פלייבק לפני ההקלטה."; return; }
        if (!probed) { InfoText.Text = "בצע קודם בדיקת ASIO ומיפוי."; return; }

        if (IsMr816Driver(driver) && !mr816ExternalFxReady)
        {
            InfoText.Text = "MR816X חייב להיות במצב External FX לפני תחילת הטייק.";
            return;
        }

        if (WetOnlyConfirm.IsChecked != true)
        {
            InfoText.Text = "אשר את מצב הניטור לפני ההקלטה.";
            return;
        }

        if (!TryRouting(out var route, out var message)) { InfoText.Text = message; return; }

        var id = DateTime.UtcNow.ToString("yyyyMMdd-HHmmss");
        var dir = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.MyMusic), "Kolbo Live Studio", "Sessions", id);

        try
        {
            SetState("מכין פלייבק", "#F4B942");
            engine = new AsioCaptureEngine();
            requireWetReturn = IsMr816Driver(driver) && mr816ExternalFxReady;
            engine.Start(driver, route.SampleRate, dir, backingPath, route, CurrentGains(), hardwareDirectDry: false);

            sessionId = id;
            sessionDirectory = dir;
            lastOutputPath = null;
            phone?.SetSessionDirectory(dir);

            recording = true;
            dryActiveTicks = 0;
            wetSeen = false;
            effectGateFailed = false;
            DeviceBox.IsEnabled = false;
            elapsed.Restart();
            StartKaraokeVideo();

            if (phone?.Connected == true)
            {
                var started = await phone.StartRemoteRecordingAsync();
                PhoneStatusText.Text = started
                    ? "מצלמת הטלפון מקליטה יחד עם הטייק."
                    : "המצלמה מחוברת אך לא קיבלה פקודת הקלטה.";
            }

            SetState("מקליט", "#FF5263");
            EffectStatusText.Text = requireWetReturn
                ? "שיר למיקרופון. מחפש REV-X Wet Return אמיתי..."
                : "הקלטה פעילה.";
            EffectStatusDot.Fill = Brushes.Goldenrod;
            ExportStatusText.Text = "";
            InfoText.Text = "מקליט. יחס מיקרופון/פלייבק ניתן לשינוי בזמן אמת.";
        }
        catch (Exception ex)
        {
            engine?.Dispose();
            engine = null;
            SetState("מוכן", "#35D7C5");
            InfoText.Text = "ההקלטה לא התחילה: " + ex.Message;
        }
    }

    async void Stop_Click(object sender, RoutedEventArgs e)
    {
        if (!recording) return;

        SetState("מסיים ושומר", "#F4B942");
        engine?.Stop();
        var error = engine?.Error;
        var clips = engine?.Overloads ?? 0;
        var neededWet = requireWetReturn;

        requireWetReturn = false;
        engine = null;
        recording = false;
        DeviceBox.IsEnabled = true;
        elapsed.Stop();
        StopKaraokeVideo();

        if (phone?.Connected == true)
        {
            var stopSent = await phone.StopRemoteRecordingAsync();
            PhoneStatusText.Text = stopSent
                ? "האודיו נשמר. הטלפון מסיים ומעלה את הווידאו..."
                : "האודיו נשמר; מצלמת הטלפון אינה מחוברת כרגע.";
        }

        if (error is not null)
        {
            SetState("הושלם עם שגיאה", "#E45757");
            InfoText.Text = "הסשן הסתיים עם שגיאה: " + error;
            return;
        }

        if (neededWet && !wetSeen)
        {
            SetState("נעצר — REV-X לא אומת", "#E45757");
            EffectStatusText.Text = "לא זוהה Wet Return. אל תשתמש בטייק הזה כגרסת אפקט.";
            EffectStatusDot.Fill = Brushes.OrangeRed;
        }
        else
        {
            SetState("נשמר — מוכן לייצוא", "#35D7C5");
        }

        ExportStatusText.Text = "השמירה הסתיימה. אפשר לייצא אודיו מיד; MP4 יהיה זמין כאשר וידאו מהטלפון/קריוקי קיים.";
        InfoText.Text = $"הסשן נשמר. אירועי clipping: {clips}.";
    }

    async void ExportAudio_Click(object sender, RoutedEventArgs e)
    {
        if (!CanExport()) return;
        exportCts = new CancellationTokenSource();
        BeginExport("מתחיל ייצוא WAV + MP3...");

        try
        {
            var progress = new Progress<ExportProgressInfo>(UpdateExportProgress);
            var result = await ExportService.ExportAudioAsync(sessionDirectory!, progress, exportCts.Token);
            lastOutputPath = result.Mp3Path;
            FinishExport("ייצוא האודיו הושלם: WAV + MP3 320kbps.", result.Mp3Path);
        }
        catch (OperationCanceledException)
        {
            FinishExport("הייצוא בוטל.", null, success: false);
        }
        catch (Exception ex)
        {
            FinishExport("ייצוא האודיו נכשל: " + ex.Message, null, success: false);
        }
        finally
        {
            exportCts.Dispose();
            exportCts = null;
            EndExportBusy();
        }
    }

    async void ExportVideo_Click(object sender, RoutedEventArgs e)
    {
        if (!CanExport()) return;

        if (!double.TryParse(VideoOffsetBox.Text, NumberStyles.Float, CultureInfo.InvariantCulture, out var offset) &&
            !double.TryParse(VideoOffsetBox.Text, NumberStyles.Float, CultureInfo.CurrentCulture, out offset))
        {
            ExportStatusText.Text = "Video Offset אינו מספר תקין.";
            return;
        }

        exportCts = new CancellationTokenSource();
        BeginExport("מתחיל ייצוא MP4...");

        try
        {
            var progress = new Progress<ExportProgressInfo>(UpdateExportProgress);
            var output = await ExportService.ExportVideoAsync(
                sessionDirectory!,
                preparedPlayback?.VideoPath,
                offset,
                progress,
                exportCts.Token);

            lastOutputPath = output;
            FinishExport("ייצוא הווידאו הושלם.", output);
        }
        catch (OperationCanceledException)
        {
            FinishExport("הייצוא בוטל.", null, success: false);
        }
        catch (Exception ex)
        {
            FinishExport("ייצוא הווידאו נכשל: " + ex.Message, null, success: false);
        }
        finally
        {
            exportCts.Dispose();
            exportCts = null;
            EndExportBusy();
        }
    }

    bool CanExport()
    {
        if (recording)
        {
            ExportStatusText.Text = "עצור ושמור לפני הייצוא.";
            return false;
        }
        if (sessionDirectory is null || !File.Exists(Path.Combine(sessionDirectory, "master.wav")))
        {
            ExportStatusText.Text = "אין עדיין הקלטה שמורה לייצוא.";
            return false;
        }
        if (exportCts is not null)
        {
            ExportStatusText.Text = "כבר מתבצע ייצוא.";
            return false;
        }
        return true;
    }

    void BeginExport(string message)
    {
        ExportAudioButton.IsEnabled = false;
        ExportVideoButton.IsEnabled = false;
        CancelExportButton.Visibility = Visibility.Visible;
        OpenOutputButton.Visibility = Visibility.Collapsed;
        ExportProgressBar.Visibility = Visibility.Visible;
        ExportProgressBar.IsIndeterminate = false;
        ExportProgressBar.Value = 0;
        ExportStatusText.Text = message;
        SetState("מייצא", "#F4B942");
    }

    void UpdateExportProgress(ExportProgressInfo info)
    {
        ExportProgressBar.Value = Math.Clamp(info.Percent, 0, 100);
        ExportStatusText.Text = info.Message;
    }

    void FinishExport(string message, string? output, bool success = true)
    {
        ExportProgressBar.Visibility = Visibility.Visible;
        ExportProgressBar.Value = success ? 100 : ExportProgressBar.Value;
        ExportStatusText.Text = message;
        OpenOutputButton.Visibility = output is null ? Visibility.Collapsed : Visibility.Visible;
        SetState(success ? "ייצוא הושלם" : "ייצוא לא הושלם", success ? "#35D7C5" : "#E45757");

        if (success && output is not null)
            MessageBox.Show(message + Environment.NewLine + output, "Kolbo Live Studio", MessageBoxButton.OK, MessageBoxImage.Information);
    }

    void EndExportBusy()
    {
        ExportAudioButton.IsEnabled = true;
        ExportVideoButton.IsEnabled = true;
        CancelExportButton.Visibility = Visibility.Collapsed;
    }

    void CancelExport_Click(object sender, RoutedEventArgs e) => exportCts?.Cancel();

    void OpenOutput_Click(object sender, RoutedEventArgs e)
    {
        var path = lastOutputPath ?? sessionDirectory;
        if (path is null) return;
        var directory = File.Exists(path) ? Path.GetDirectoryName(path) : path;
        if (directory is null || !Directory.Exists(directory)) return;

        Process.Start(new ProcessStartInfo
        {
            FileName = "explorer.exe",
            Arguments = """ + directory + """,
            UseShellExecute = true
        });
    }

    void ShowPairingWindow(Uri url)
    {
        phoneDialog?.Close();

        using var generator = new QRCodeGenerator();
        using var data = generator.CreateQrCode(url.ToString(), QRCodeGenerator.ECCLevel.Q);
        using var png = new PngByteQRCode(data);
        var bytes = png.GetGraphic(12);
        var bitmap = new BitmapImage();
        using (var ms = new MemoryStream(bytes))
        {
            bitmap.BeginInit();
            bitmap.CacheOption = BitmapCacheOption.OnLoad;
            bitmap.StreamSource = ms;
            bitmap.EndInit();
            bitmap.Freeze();
        }

        var panel = new StackPanel { Margin = new Thickness(22), FlowDirection = FlowDirection.RightToLeft };
        panel.Children.Add(new TextBlock
        {
            Text = "סרוק בטלפון ואשר מצלמה",
            Foreground = Brushes.Black,
            FontSize = 25,
            FontWeight = FontWeights.SemiBold,
            HorizontalAlignment = HorizontalAlignment.Center
        });
        panel.Children.Add(new TextBlock
        {
            Text = "הקישור נפתח ב-HTTPS מאובטח בדפדפן. אשר הרשאת מצלמה; התצוגה החיה תופיע מיד בתוכנה, גם לפני תחילת ההקלטה.",
            Foreground = Brushes.DarkSlateGray,
            FontSize = 15,
            TextWrapping = TextWrapping.Wrap,
            TextAlignment = TextAlignment.Center,
            Margin = new Thickness(0, 8, 0, 0)
        });
        panel.Children.Add(new Image
        {
            Source = bitmap,
            Width = 300,
            Height = 300,
            Margin = new Thickness(0, 14, 0, 12)
        });
        panel.Children.Add(new TextBox
        {
            Text = url.ToString(),
            IsReadOnly = true,
            Foreground = Brushes.Black,
            Background = Brushes.White,
            TextWrapping = TextWrapping.Wrap,
            FlowDirection = FlowDirection.LeftToRight
        });

        phoneDialog = new Window
        {
            Owner = this,
            Title = "מצלמת טלפון — Kolbo Live Studio",
            Width = 520,
            Height = 590,
            MinWidth = 430,
            MinHeight = 520,
            ResizeMode = ResizeMode.CanResize,
            WindowStartupLocation = WindowStartupLocation.CenterOwner,
            Background = Brushes.White,
            Foreground = Brushes.Black,
            Content = panel
        };
        phoneDialog.Closed += (_, _) => phoneDialog = null;
        phoneDialog.Show();
    }

    bool TryRouting(out Routing route, out string error)
    {
        route = default!;
        error = string.Empty;

        if (DryBox.SelectedItem is not AudioChannel dry ||
            WetLBox.SelectedItem is not AudioChannel wetL ||
            WetRBox.SelectedItem is not AudioChannel wetR ||
            SendLBox.SelectedItem is not AudioChannel sendL ||
            SendRBox.SelectedItem is not AudioChannel sendR ||
            MasterLBox.SelectedItem is not AudioChannel masterL ||
            MasterRBox.SelectedItem is not AudioChannel masterR)
        {
            error = "מיפוי הערוצים אינו מלא. בצע בדיקת ASIO ובחר את כל הערוצים.";
            return false;
        }

        if (RateBox.SelectedItem is not ComboBoxItem item ||
            !int.TryParse(item.Content?.ToString()?.Split(' ')[0], out var rate))
        {
            error = "קצב הדגימה אינו תקין.";
            return false;
        }

        route = new Routing(dry.Index, wetL.Index, wetR.Index, sendL.Index, sendR.Index, masterL.Index, masterR.Index, rate);
        var errors = route.Validate(DryBox.Items.Count, SendLBox.Items.Count, supportedRates, WetOnlyConfirm.IsChecked == true);
        if (errors.Length > 0)
        {
            error = string.Join("; ", errors);
            return false;
        }

        return true;
    }

    void SelectRate(int rate)
    {
        foreach (var entry in RateBox.Items.OfType<ComboBoxItem>())
        {
            if (entry.Content?.ToString()?.StartsWith(rate.ToString(), StringComparison.Ordinal) == true)
            {
                RateBox.SelectedItem = entry;
                return;
            }
        }
    }

    static void SelectIndex(ComboBox box, int physicalIndex)
    {
        if (physicalIndex >= 0 && physicalIndex < box.Items.Count)
            box.SelectedIndex = physicalIndex;
        else if (box.Items.Count > 0)
            box.SelectedIndex = 0;
    }

    void UpdateMeters()
    {
        if (recording && engine is not null)
        {
            var dry = engine.DryPeak;
            var wet = engine.WetPeak;
            DryMeter.Value = dry;
            WetMeter.Value = wet;
            ElapsedText.Text = elapsed.Elapsed.ToString(@"hh\:mm\:ss");

            if (dry > 0.025f) dryActiveTicks++;
            if (wet > 0.004f)
            {
                wetSeen = true;
                EffectStatusDot.Fill = Brushes.LimeGreen;
                EffectStatusText.Text = "REV-X Wet Return זוהה בפועל. האפקט נכנס ל-Master המוקלט.";
            }
            else if (!wetSeen && dryActiveTicks >= 24 && requireWetReturn && !effectGateFailed)
            {
                effectGateFailed = true;
                EffectStatusDot.Fill = Brushes.OrangeRed;
                EffectStatusText.Text = "יש Dry אך אין REV-X Wet Return. הטייק נעצר כדי לא לשמור קול יבש בטעות.";
                InfoText.Text = "REV-X לא הגיע חזרה מה-MR816X. בדוק External FX ונסה שוב.";
                Dispatcher.BeginInvoke(() => Stop_Click(this, new RoutedEventArgs()));
            }
            else if (!wetSeen && dryActiveTicks > 0)
            {
                EffectStatusDot.Fill = Brushes.Goldenrod;
                EffectStatusText.Text = "Dry זוהה. ממתין ל-REV-X Wet Return...";
            }

            if (engine.Error is { } engineError)
            {
                SetState("שגיאת הקלטה", "#E45757");
                InfoText.Text = engineError;
            }
        }
        else
        {
            DryMeter.Value *= .75;
            WetMeter.Value *= .75;
        }
    }

    void SetState(string text, string color)
    {
        StateTextBlock.Text = text;
        StateDot.Fill = (Brush)new BrushConverter().ConvertFromString(color)!;
    }

    protected override async void OnClosed(EventArgs e)
    {
        uiTimer.Stop();
        mediaLoadCts?.Cancel();
        mediaLoadCts?.Dispose();
        exportCts?.Cancel();
        exportCts?.Dispose();
        StopKaraokeVideo();

        if (recording)
        {
            try
            {
                engine?.Stop();
                recording = false;
            }
            catch { }
        }

        phoneDialog?.Close();
        if (phone is not null) await phone.DisposeAsync();
        base.OnClosed(e);
    }
}
