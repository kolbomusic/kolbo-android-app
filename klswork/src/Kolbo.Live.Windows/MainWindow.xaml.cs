using System.Collections.ObjectModel;
using System.Diagnostics;
using System.Globalization;
using System.IO;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Input;
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
    PairingAuthority? pairing;
    bool recording;
    bool probed;
    bool mr816ExternalFxReady;
    int dryActiveTicks;
    bool wetSeen;
    int[] supportedRates = [];
    string? backingPath;
    string? sessionId;
    string? sessionDirectory;
    PreparedPlayback? preparedPlayback;
    readonly MediaSourceService mediaSources = new();
    CancellationTokenSource? mediaLoadCts;
    readonly DispatcherTimer uiTimer;
    readonly Stopwatch elapsed = new();

    public MainWindow()
    {
        InitializeComponent();
        DeviceBox.ItemsSource = Devices;
        LoadDevices();
        uiTimer = new DispatcherTimer(TimeSpan.FromMilliseconds(80), DispatcherPriority.Background, (_, _) => UpdateMeters(), Dispatcher);
        uiTimer.Start();
    }

    static bool IsMr816Driver(string driver) =>
        driver.Contains("Yamaha Steinberg FW ASIO", StringComparison.OrdinalIgnoreCase);

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

    async Task PreparePlaybackAsync(
        Func<CancellationToken, Task<PreparedPlayback>> loader,
        string initialStatus)
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
            ? "האודיו מוכן ל־ASIO."
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
                // MR816X External FX mode exposes 10 DAW inputs and 10 DAW outputs.
                // Channels 9/10 are the documented REV-X send/return pair.
                if (probe.Inputs.Count == 10 && probe.Outputs.Count == 10)
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
                        "MR816X External FX זוהה (10×10). REV-X Send = DAW 9/10, Return = ASIO 9/10, Monitor = 1/2. " +
                        "Dry נשמע דרך Direct Monitor של הכרטיס ואינו נשלח שוב למוניטור מהתוכנה.";
                    HardwareProfileText.Foreground = Brushes.LightGreen;
                    EffectStatusText.Text = "נתיב REV-X מוכן. בזמן ההקלטה אשווה בין מד Dry למד Wet ואאמת שמגיע אפקט אמיתי.";
                    EffectStatusDot.Fill = Brushes.Goldenrod;
                    InfoText.Text = $"MR816X External FX מוכן. Sample Rate: {probe.CurrentRate} Hz. אשר Direct Monitor ולחץ התחל הקלטה.";
                }
                else
                {
                    SelectIndex(DryBox, 0);
                    SelectIndex(MasterLBox, 0);
                    SelectIndex(MasterRBox, 1);
                    HardwareProfileText.Text =
                        $"Yamaha Steinberg FW ASIO זוהה עם {probe.Inputs.Count} כניסות / {probe.Outputs.Count} יציאות, " +
                        "אבל MR816X אינו במצב External FX של REV-X. פתח לוח בקרה ASIO והגדר Digital I/O, External FX = External FX, ואז בדוק שוב.";
                    HardwareProfileText.Foreground = Brushes.OrangeRed;
                    EffectStatusText.Text = "REV-X לא יאושר להקלטה עד שהכרטיס יופיע כ־10×10 External FX.";
                    EffectStatusDot.Fill = Brushes.OrangeRed;
                    InfoText.Text = "נדרש MR816X External FX. לחץ “פתח לוח בקרה ASIO”, בחר External FX וחזור לבדיקה.";
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
                HardwareProfileText.Text =
                    "כרטיס כללי: נדרש מיפוי ידני של Dry / Wet Return / FX Send / Monitor לפי יכולות החומרה.";
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

    async void Record_Click(object sender, RoutedEventArgs e)
    {
        if (recording) return;
        if (DeviceBox.SelectedItem is not string driver) { InfoText.Text = "בחר דרייבר ASIO תחילה."; return; }
        if (backingPath is null) { InfoText.Text = "בחר פלייבק לפני ההקלטה."; return; }
        if (!probed) { InfoText.Text = "בצע קודם בדיקת ASIO ומיפוי."; return; }

        if (IsMr816Driver(driver) && !mr816ExternalFxReady)
        {
            InfoText.Text = "ההקלטה נעצרה לפני התחלה: MR816X חייב להיות במצב External FX כדי להקליט את REV-X דרך 9/10.";
            EffectStatusText.Text = "אין נתיב REV-X מאומת.";
            EffectStatusDot.Fill = Brushes.OrangeRed;
            return;
        }

        if (WetOnlyConfirm.IsChecked != true)
        {
            InfoText.Text = "אשר ש־Direct Monitor פעיל בכרטיס ושאין ניטור Dry כפול.";
            return;
        }

        if (!TryRouting(out var route, out var message)) { InfoText.Text = message; return; }

        if (phone is not null)
        {
            await phone.DisposeAsync();
            phone = null;
        }
        pairing?.Revoke();
        pairing = null;

        var id = DateTime.UtcNow.ToString("yyyyMMdd-HHmmss");
        var dir = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.MyMusic), "Kolbo Live Studio", "Sessions", id);

        try
        {
            SetState("מכין פלייבק", "#F4B942");
            engine = new AsioCaptureEngine();
            var gains = new Gains(
                (float)(DryGain.Value / 100.0),
                (float)(WetGain.Value / 100.0),
                (float)(BackingGain.Value / 100.0),
                (float)(SendGain.Value / 100.0));

            var useHardwareDirectDry = IsMr816Driver(driver) && mr816ExternalFxReady;
            engine.Start(driver, route.SampleRate, dir, backingPath, route, gains, useHardwareDirectDry);

            sessionId = id;
            sessionDirectory = dir;
            recording = true;
            dryActiveTicks = 0;
            wetSeen = false;
            DeviceBox.IsEnabled = false;
            elapsed.Restart();
            StartKaraokeVideo();
            SetState("מקליט", "#FF5263");
            EffectStatusText.Text = "שיר למיקרופון. מחפש REV-X Return אמיתי בערוצים 9/10...";
            EffectStatusDot.Fill = Brushes.Goldenrod;
            InfoText.Text = useHardwareDirectDry
                ? "מקליט MR816X: Dry מהכניסה נשמר ל־Master אך לא מוכפל במוניטור; Wet REV-X + Playback נשלחים למוניטור ונשמרים."
                : "מקליט. ה־Master נשמר יחד עם ה־stems.";
        }
        catch (Exception ex)
        {
            engine?.Dispose();
            engine = null;
            SetState("מוכן", "#35D7C5");
            InfoText.Text = "ההקלטה לא התחילה: " + ex.Message;
        }
    }

    void Stop_Click(object sender, RoutedEventArgs e)
    {
        if (!recording) return;
        SetState("מסיים ושומר", "#F4B942");
        pairing?.End();
        engine?.Stop();
        var error = engine?.Error;
        var clips = engine?.Overloads ?? 0;
        var hadMr816 = engine?.HardwareDirectDry == true;
        engine = null;
        recording = false;
        DeviceBox.IsEnabled = true;
        elapsed.Stop();
        StopKaraokeVideo();

        if (error is not null)
        {
            SetState("הושלם עם שגיאה", "#E45757");
            InfoText.Text = "הסשן הסתיים עם שגיאה: " + error;
            return;
        }

        if (hadMr816 && !wetSeen)
        {
            SetState("נשמר — REV-X לא אומת", "#E45757");
            EffectStatusText.Text = "הקובץ נשמר, אבל לא זוהה Wet Return משמעותי. אל תתייחס ל־Master כגרסת אפקט מאומתת.";
            EffectStatusDot.Fill = Brushes.OrangeRed;
            InfoText.Text = $"הסשן נשמר, אך REV-X לא אומת. אירועי clipping: {clips}. בדוק External FX ו־REV-X Send/Return.";
        }
        else
        {
            SetState("הושלם", "#35D7C5");
            InfoText.Text = $"הסשן נשמר: dry, wet, backing ו־master. אירועי clipping: {clips}.";
        }
    }

    async void PairPhone_Click(object sender, RoutedEventArgs e)
    {
        if (!recording || sessionId is null || sessionDirectory is null)
        {
            MessageBox.Show("התחל הקלטה לפני חיבור הטלפון.", "חיבור טלפון", MessageBoxButton.OK, MessageBoxImage.Information);
            return;
        }

        try
        {
            if (phone is not null)
            {
                await phone.DisposeAsync();
                phone = null;
            }

            pairing?.Revoke();
            pairing = new PairingAuthority();
            pairing.Begin(sessionId);
            phone = new PhonePairingServer(pairing, sessionId, sessionDirectory);
            await phone.StartAsync();
            ShowPairingWindow(phone.Url!, phone.LocalAddress ?? string.Empty);
        }
        catch (Exception ex)
        {
            InfoText.Text = "חיבור הטלפון נכשל: " + ex.Message;
        }
    }

    async void Export_Click(object sender, RoutedEventArgs e)
    {
        if (recording)
        {
            InfoText.Text = "עצור ושמור את האודיו לפני הייצוא.";
            return;
        }

        if (sessionDirectory is null)
        {
            InfoText.Text = "אין סשן נוכחי לייצוא.";
            return;
        }

        if (!double.TryParse(VideoOffsetBox.Text, NumberStyles.Float, CultureInfo.InvariantCulture, out var offset) &&
            !double.TryParse(VideoOffsetBox.Text, NumberStyles.Float, CultureInfo.CurrentCulture, out offset))
        {
            InfoText.Text = "Video Offset אינו מספר תקין.";
            return;
        }

        if (offset is < -10 or > 10)
        {
            InfoText.Text = "Video Offset חייב להיות בין ‎-10 ל־10 שניות.";
            return;
        }

        try
        {
            SetState("מייצא", "#F4B942");
            InfoText.Text = "מכין את התוצאה הסופית...";
            var output = await ExportService.ExportResultAsync(
                sessionDirectory,
                preparedPlayback?.VideoPath,
                offset);
            SetState("הייצוא הושלם", "#35D7C5");
            InfoText.Text = "הקובץ נשמר: " + output;
        }
        catch (Exception ex)
        {
            SetState("שגיאת ייצוא", "#E45757");
            InfoText.Text = "הייצוא נכשל: " + ex.Message;
        }
    }

    void ShowPairingWindow(Uri url, string localAddress)
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
            Text = "סרוק בטלפון",
            Foreground = Brushes.Black,
            FontSize = 25,
            FontWeight = FontWeights.SemiBold,
            HorizontalAlignment = HorizontalAlignment.Center
        });
        panel.Children.Add(new TextBlock
        {
            Text = "המחשב והטלפון חייבים להיות באותה רשת. הדף פותח את מצלמת הטלפון המקורית — ללא תעודת HTTPS עצמית.",
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
            FlowDirection = FlowDirection.LeftToRight,
            Margin = new Thickness(0, 0, 0, 8)
        });
        panel.Children.Add(new TextBlock
        {
            Text = "Local: " + localAddress + " • אם Windows Firewall שואל — אפשר גישה ברשת פרטית.",
            Foreground = Brushes.DarkSlateGray,
            FontSize = 14,
            TextWrapping = TextWrapping.Wrap,
            TextAlignment = TextAlignment.Center
        });

        phoneDialog = new Window
        {
            Owner = this,
            Title = "מצלמת טלפון — Kolbo Live Studio",
            Width = 500,
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
                EffectStatusText.Text = "REV-X Wet Return זוהה בפועל. האפקט נכנס ל־Master המוקלט.";
            }
            else if (!wetSeen && dryActiveTicks >= 18)
            {
                EffectStatusDot.Fill = Brushes.OrangeRed;
                EffectStatusText.Text =
                    "יש Dry מהמיקרופון אבל עדיין אין Wet Return. אם אתה שומע Reverb באוזניות, עצור ובדוק שה־MR816X במצב External FX וש־REV-X פעיל על DAW 9/10.";
            }
            else if (!wetSeen && dryActiveTicks > 0)
            {
                EffectStatusDot.Fill = Brushes.Goldenrod;
                EffectStatusText.Text = "Dry זוהה. ממתין ל־REV-X Return...";
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

    void TitleBar_MouseLeftButtonDown(object sender, MouseButtonEventArgs e)
    {
        if (e.ClickCount == 2)
        {
            ToggleMaximize();
            return;
        }

        if (e.LeftButton == MouseButtonState.Pressed)
        {
            try
            {
                if (WindowState == WindowState.Maximized)
                    WindowState = WindowState.Normal;
                DragMove();
            }
            catch { }
        }
    }

    void Minimize_Click(object sender, RoutedEventArgs e) => WindowState = WindowState.Minimized;
    void Maximize_Click(object sender, RoutedEventArgs e) => ToggleMaximize();
    void Close_Click(object sender, RoutedEventArgs e) => Close();

    void ToggleMaximize() =>
        WindowState = WindowState == WindowState.Maximized ? WindowState.Normal : WindowState.Maximized;

    void Window_StateChanged(object? sender, EventArgs e)
    {
        if (MaximizeButton is not null)
            MaximizeButton.Content = WindowState == WindowState.Maximized ? "❐" : "□";
    }

    protected override async void OnClosed(EventArgs e)
    {
        uiTimer.Stop();
        mediaLoadCts?.Cancel();
        mediaLoadCts?.Dispose();
        StopKaraokeVideo();
        if (recording) Stop_Click(this, new RoutedEventArgs());
        phoneDialog?.Close();
        pairing?.Revoke();
        if (phone is not null) await phone.DisposeAsync();
        base.OnClosed(e);
    }
}
