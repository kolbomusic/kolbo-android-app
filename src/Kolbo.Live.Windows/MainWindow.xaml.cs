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
    PairingAuthority? pairing;
    bool recording;
    bool probed;
    int[] supportedRates = [];
    string? backingPath;
    string? sessionId;
    string? sessionDirectory;
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

    void LoadDevices()
    {
        try { foreach (var n in AsioCaptureEngine.Drivers()) Devices.Add(n); }
        catch (Exception ex) { InfoText.Text = "קריאת ASIO נכשלה: " + ex.Message; }
        if (Devices.Count > 0) DeviceBox.SelectedIndex = 0;
    }

    void DeviceBox_SelectionChanged(object sender, SelectionChangedEventArgs e)
    {
        if (!IsLoaded || recording) return;
        InvalidateProbe("כרטיס ה-ASIO השתנה. בצע שוב בדיקת ASIO ומיפוי לפני ההקלטה.");
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
            InvalidateProbe("לוח הבקרה של ASIO נסגר. בצע שוב בדיקת ASIO ומיפוי כדי לקרוא מחדש Sample Rate וערוצים.");
        }
        catch (Exception ex)
        {
            InfoText.Text = "פתיחת לוח הבקרה של ASIO נכשלה: " + ex.Message;
        }
    }

    void InvalidateProbe(string message)
    {
        probed = false;
        supportedRates = [];
        foreach (var box in new[] { DryBox, WetLBox, WetRBox, SendLBox, SendRBox, MasterLBox, MasterRBox })
        {
            box.ItemsSource = null;
            box.SelectedItem = null;
        }
        InfoText.Text = message;
        SetState("נדרשת בדיקת ASIO", "#F4B942");
    }

    void ChooseBacking_Click(object sender, RoutedEventArgs e)
    {
        var d = new OpenFileDialog { Filter = "Audio|*.wav;*.mp3;*.m4a;*.aiff|All files|*.*" };
        if (d.ShowDialog() == true)
        {
            backingPath = d.FileName;
            BackingText.Text = Path.GetFileName(d.FileName);
            InfoText.Text = "הפלייבק ייטען לזיכרון לפני תחילת ASIO כדי שלא תהיה קריאת דיסק ב־callback.";
        }
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
            DryBox.ItemsSource = probe.Inputs; WetLBox.ItemsSource = probe.Inputs; WetRBox.ItemsSource = probe.Inputs;
            SendLBox.ItemsSource = probe.Outputs; SendRBox.ItemsSource = probe.Outputs; MasterLBox.ItemsSource = probe.Outputs; MasterRBox.ItemsSource = probe.Outputs;
            SelectIndex(DryBox, 0); SelectIndex(WetLBox, 8); SelectIndex(WetRBox, 9);
            SelectIndex(MasterLBox, 0); SelectIndex(MasterRBox, 1); SelectIndex(SendLBox, 2); SelectIndex(SendRBox, 3);
            supportedRates = probe.Rates.ToArray();
            SelectRate(probe.CurrentRate);
            probed = true;
            var rates = supportedRates.Length == 0 ? "ללא קצב מהמועמדים" : string.Join(", ", supportedRates.Select(r => r + " Hz"));
            InfoText.Text = $"ASIO זוהה: {probe.Inputs.Count} כניסות, {probe.Outputs.Count} יציאות. הכרטיס מוגדר כעת ל־{probe.CurrentRate} Hz. קצבים נתמכים: {rates}. התוכנה לא תשנה את ה־Clock/Sample Rate אוטומטית.";
            SetState("ASIO מוכן", "#35D7C5");
        }
        catch (Exception ex)
        {
            probed = false;
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
        if (WetOnlyConfirm.IsChecked != true) { InfoText.Text = "נדרש לאשר שה־Wet Return הוא אפקט בלבד ושאין Direct Monitor כפול."; return; }
        if (!TryRouting(out var route, out var message)) { InfoText.Text = message; return; }

        if (phone is not null)
        {
            await phone.DisposeAsync();
            phone = null;
        }
        pairing?.Revoke(); pairing = null;

        var id = DateTime.UtcNow.ToString("yyyyMMdd-HHmmss");
        var dir = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.MyMusic), "Kolbo Live Studio", "Sessions", id);
        try
        {
            SetState("מכין פלייבק", "#F4B942");
            engine = new AsioCaptureEngine();
            var gains = new Gains((float)(DryGain.Value / 100.0), (float)(WetGain.Value / 100.0), (float)(BackingGain.Value / 100.0), (float)(SendGain.Value / 100.0));
            engine.Start(driver, route.SampleRate, dir, backingPath, route, gains);
            sessionId = id; sessionDirectory = dir; recording = true;
            DeviceBox.IsEnabled = false;
            elapsed.Restart();
            SetState("מקליט", "#FF5263");
            InfoText.Text = "מקליט. אותו Master נשלח ליציאות שנבחרו ונכתב ל־master.wav. ניתן לחבר טלפון כעת.";
        }
        catch (Exception ex)
        {
            engine?.Dispose(); engine = null;
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
        engine = null;
        recording = false;
        DeviceBox.IsEnabled = true;
        elapsed.Stop();
        SetState(error is null ? "הושלם" : "הושלם עם שגיאה", error is null ? "#35D7C5" : "#E45757");
        InfoText.Text = error is null
            ? $"הסשן נשמר: dry, wet, backing ו־master. אירועי clipping: {clips}. אם צולם וידאו, עצור ושלח אותו כעת מהטלפון."
            : "הסשן הסתיים עם שגיאה: " + error;
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
            if (phone is not null) { await phone.DisposeAsync(); phone = null; }
            pairing?.Revoke();
            pairing = new PairingAuthority();
            pairing.Begin(sessionId);
            phone = new PhonePairingServer(pairing, sessionId, sessionDirectory);
            await phone.StartAsync();
            ShowPairingWindow(phone.Url!, phone.Fingerprint ?? string.Empty);
        }
        catch (Exception ex)
        {
            InfoText.Text = "חיבור הטלפון נכשל: " + ex.Message;
        }
    }

    async void Export_Click(object sender, RoutedEventArgs e)
    {
        if (recording) { InfoText.Text = "עצור ושמור את האודיו לפני ייצוא MP4."; return; }
        if (sessionDirectory is null) { InfoText.Text = "אין סשן נוכחי לייצוא."; return; }
        if (!double.TryParse(VideoOffsetBox.Text, NumberStyles.Float, CultureInfo.InvariantCulture, out var offset) &&
            !double.TryParse(VideoOffsetBox.Text, NumberStyles.Float, CultureInfo.CurrentCulture, out offset))
        { InfoText.Text = "Video Offset אינו מספר תקין."; return; }
        if (offset is < -10 or > 10) { InfoText.Text = "Video Offset חייב להיות בין ‎-10 ל־10 שניות."; return; }
        try
        {
            SetState("מייצא MP4", "#F4B942");
            InfoText.Text = "מייצא וידאו עם master.wav. אין שינוי בקבצי המקור.";
            var output = await ExportService.ExportPhoneMasterAsync(sessionDirectory, offset);
            SetState("הייצוא הושלם", "#35D7C5");
            InfoText.Text = "הקובץ נשמר: " + output;
        }
        catch (Exception ex)
        {
            SetState("שגיאת ייצוא", "#E45757");
            InfoText.Text = "ייצוא MP4 נכשל: " + ex.Message;
        }
    }

    void ShowPairingWindow(Uri url, string fingerprint)
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

        var panel = new StackPanel { Margin = new Thickness(22) };
        panel.Children.Add(new TextBlock { Text = "סרוק בטלפון", FontSize = 24, FontWeight = FontWeights.SemiBold, HorizontalAlignment = HorizontalAlignment.Center });
        panel.Children.Add(new Image { Source = bitmap, Width = 300, Height = 300, Margin = new Thickness(0, 16, 0, 12) });
        panel.Children.Add(new TextBox { Text = url.ToString(), IsReadOnly = true, TextWrapping = TextWrapping.Wrap, FlowDirection = FlowDirection.LeftToRight, Margin = new Thickness(0, 0, 0, 10) });
        panel.Children.Add(new TextBlock { Text = "חיבור HTTPS מקומי בלבד. ייתכן שהדפדפן יבקש אישור לתעודה המקומית לפני הרשאת מצלמה.", Foreground = Brushes.Gray, TextWrapping = TextWrapping.Wrap });
        panel.Children.Add(new TextBlock { Text = "Fingerprint: " + fingerprint, Foreground = Brushes.Gray, TextWrapping = TextWrapping.Wrap, FlowDirection = FlowDirection.LeftToRight, Margin = new Thickness(0, 8, 0, 0) });
        phoneDialog = new Window
        {
            Owner = this,
            Title = "חיבור מצלמת טלפון — Kolbo Live Studio",
            Width = 430, Height = 560,
            ResizeMode = ResizeMode.NoResize,
            WindowStartupLocation = WindowStartupLocation.CenterOwner,
            Background = Brushes.White,
            Content = panel
        };
        phoneDialog.Closed += (_, _) => phoneDialog = null;
        phoneDialog.Show();
    }

    bool TryRouting(out Routing route, out string error)
    {
        route = default!; error = string.Empty;
        if (DryBox.SelectedItem is not AudioChannel dry || WetLBox.SelectedItem is not AudioChannel wetL || WetRBox.SelectedItem is not AudioChannel wetR ||
            SendLBox.SelectedItem is not AudioChannel sendL || SendRBox.SelectedItem is not AudioChannel sendR || MasterLBox.SelectedItem is not AudioChannel masterL || MasterRBox.SelectedItem is not AudioChannel masterR)
        { error = "מיפוי הערוצים אינו מלא. בצע בדיקת ASIO ובחר את כל הערוצים."; return false; }
        if (RateBox.SelectedItem is not ComboBoxItem item || !int.TryParse(item.Content?.ToString()?.Split(' ')[0], out var rate))
        { error = "קצב הדגימה אינו תקין."; return false; }
        route = new Routing(dry.Index, wetL.Index, wetR.Index, sendL.Index, sendR.Index, masterL.Index, masterR.Index, rate);
        var errors = route.Validate(DryBox.Items.Count, SendLBox.Items.Count, supportedRates, WetOnlyConfirm.IsChecked == true);
        if (errors.Length > 0) { error = string.Join("; ", errors); return false; }
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
        if (physicalIndex >= 0 && physicalIndex < box.Items.Count) box.SelectedIndex = physicalIndex;
        else if (box.Items.Count > 0) box.SelectedIndex = 0;
    }

    void UpdateMeters()
    {
        if (recording && engine is not null)
        {
            DryMeter.Value = engine.DryPeak;
            WetMeter.Value = engine.WetPeak;
            ElapsedText.Text = elapsed.Elapsed.ToString(@"hh\:mm\:ss");
            if (engine.Error is { } error)
            {
                SetState("שגיאת הקלטה", "#E45757");
                InfoText.Text = error;
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
        if (recording) Stop_Click(this, new RoutedEventArgs());
        phoneDialog?.Close();
        pairing?.Revoke();
        if (phone is not null) await phone.DisposeAsync();
        base.OnClosed(e);
    }
}
