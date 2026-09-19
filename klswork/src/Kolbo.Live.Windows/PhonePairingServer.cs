using System.Net;
using System.Net.NetworkInformation;
using System.Text;
using System.IO;
using Microsoft.AspNetCore.Builder;
using Microsoft.AspNetCore.Hosting;
using Microsoft.AspNetCore.Http;
using Kolbo.Live.Core;

namespace Kolbo.Live.Windows;

/// <summary>
/// Local-network phone capture server.
/// Uses HTTP plus the phone's native camera capture control instead of getUserMedia.
/// This avoids self-signed TLS failures on mobile browsers while keeping the video on the local network.
/// Pairing uses a high-entropy, single-use token and uploads are accepted only for the current session.
/// </summary>
sealed class PhonePairingServer : IAsyncDisposable
{
    WebApplication? app;
    readonly PairingAuthority authority;
    readonly string code;
    readonly string sessionId;
    readonly string sessionDirectory;

    public Uri? Url { get; private set; }
    public string? LocalAddress { get; private set; }

    public PhonePairingServer(PairingAuthority authority, string sessionId, string sessionDirectory)
    {
        this.authority = authority;
        this.sessionId = sessionId;
        this.sessionDirectory = sessionDirectory;
        code = authority.PairCode;
    }

    public async Task StartAsync(CancellationToken cancellationToken = default)
    {
        if (app is not null) return;
        var localIp = LocalIp();
        if (IPAddress.IsLoopback(localIp))
            throw new InvalidOperationException("לא נמצאה כתובת רשת מקומית. חבר את המחשב והטלפון לאותה רשת Wi-Fi/‏LAN.");

        using var probe = new System.Net.Sockets.TcpListener(localIp, 0);
        probe.Start();
        var port = ((IPEndPoint)probe.LocalEndpoint).Port;
        probe.Stop();

        var builder = WebApplication.CreateBuilder();
        builder.WebHost.ConfigureKestrel(o => o.Listen(localIp, port));
        app = builder.Build();

        app.MapGet("/", () => Results.Content(Page(sessionId), "text/html", Encoding.UTF8));
        app.MapGet("/health", () => Results.Ok(new
        {
            service = "kolbo-live-studio-phone",
            transport = "local-http-native-camera",
            session = sessionId
        }));
        app.MapPost("/pair", (PairRequest body) =>
        {
            var bearer = authority.Exchange(body.Code);
            return bearer is null ? Results.Unauthorized() : Results.Ok(new { bearer });
        });
        app.MapPost("/upload/{id}", UploadAsync);

        await app.StartAsync(cancellationToken);
        LocalAddress = $"{localIp}:{port}";
        Url = new Uri($"http://{localIp}:{port}/?code={Uri.EscapeDataString(code)}");

        // Verify that Kestrel really answers on the LAN address before showing the QR.
        using var http = new HttpClient { Timeout = TimeSpan.FromSeconds(3) };
        using var response = await http.GetAsync(new Uri($"http://{localIp}:{port}/health"), cancellationToken);
        response.EnsureSuccessStatusCode();
    }

    async Task<IResult> UploadAsync(HttpRequest request, string id)
    {
        var bearer = Bearer(request);
        if (bearer is null || !authority.Authenticate(bearer))
            return Results.Unauthorized();

        if (id.Length is < 1 or > 80 || id != sessionId || authority.CurrentId != id)
            return Results.Unauthorized();

        if (authority.Recording)
            return Results.StatusCode(StatusCodes.Status409Conflict);

        if (request.ContentLength is > PairingAuthority.MaxUploadBytes)
            return Results.BadRequest("file too large");

        var safe = new string(id.Where(c => char.IsLetterOrDigit(c) || c is '-' or '_').ToArray());
        if (safe != id) return Results.BadRequest("invalid session id");

        var contentType = request.ContentType ?? string.Empty;
        var extension =
            contentType.Contains("mp4", StringComparison.OrdinalIgnoreCase) ? ".mp4" :
            contentType.Contains("quicktime", StringComparison.OrdinalIgnoreCase) ? ".mov" :
            contentType.Contains("webm", StringComparison.OrdinalIgnoreCase) ? ".webm" : ".mp4";

        Directory.CreateDirectory(sessionDirectory);
        var temp = Path.Combine(sessionDirectory, $"phone-video-{Guid.NewGuid():N}.part");
        var final = Path.Combine(sessionDirectory, "phone-video" + extension);
        long written = 0;

        try
        {
            await using (var output = new FileStream(temp, FileMode.CreateNew, FileAccess.Write, FileShare.None, 64 * 1024, useAsync: true))
            {
                var buffer = new byte[64 * 1024];
                while (true)
                {
                    var read = await request.Body.ReadAsync(buffer, request.HttpContext.RequestAborted);
                    if (read == 0) break;
                    written += read;
                    if (written > PairingAuthority.MaxUploadBytes)
                        return Results.BadRequest("file too large");
                    await output.WriteAsync(buffer.AsMemory(0, read), request.HttpContext.RequestAborted);
                }
                await output.FlushAsync(request.HttpContext.RequestAborted);
            }

            if (!authority.AllowUpload(bearer, id, written))
                return Results.Unauthorized();

            File.Move(temp, final, true);
            return Results.Ok(new { saved = true, bytes = written, file = Path.GetFileName(final) });
        }
        finally
        {
            if (File.Exists(temp))
                try { File.Delete(temp); } catch { }
        }
    }

    static string? Bearer(HttpRequest request)
    {
        if (!request.Headers.TryGetValue("Authorization", out var value)) return null;
        const string prefix = "Bearer ";
        var text = value.ToString();
        return text.StartsWith(prefix, StringComparison.Ordinal) ? text[prefix.Length..] : null;
    }

    static IPAddress LocalIp()
    {
        foreach (var nic in NetworkInterface.GetAllNetworkInterfaces()
                     .Where(n => n.OperationalStatus == OperationalStatus.Up &&
                                 n.NetworkInterfaceType != NetworkInterfaceType.Loopback &&
                                 n.NetworkInterfaceType != NetworkInterfaceType.Tunnel))
        {
            var props = nic.GetIPProperties();
            if (!props.GatewayAddresses.Any(g => g.Address.AddressFamily == System.Net.Sockets.AddressFamily.InterNetwork))
                continue;

            var ip = props.UnicastAddresses.Select(u => u.Address).FirstOrDefault(a =>
                a.AddressFamily == System.Net.Sockets.AddressFamily.InterNetwork &&
                !IPAddress.IsLoopback(a) &&
                !a.ToString().StartsWith("169.254.", StringComparison.Ordinal));

            if (ip is not null) return ip;
        }

        return Dns.GetHostEntry(Dns.GetHostName()).AddressList.FirstOrDefault(a =>
            a.AddressFamily == System.Net.Sockets.AddressFamily.InterNetwork &&
            !IPAddress.IsLoopback(a)) ?? IPAddress.Loopback;
    }

    static string Page(string id)
    {
        const string sessionMarker = "__KOLBO_SESSION_ID__";
        var escapedId = Uri.EscapeDataString(id);
        return """
<!doctype html>
<html lang='he' dir='rtl'>
<head>
<meta charset='utf-8'>
<meta name='viewport' content='width=device-width,initial-scale=1'>
<title>Kolbo Live Studio</title>
<style>
body{margin:0;background:#08111f;color:#fff;font:18px system-ui,sans-serif}
main{max-width:720px;margin:auto;padding:24px}
.card{background:#111d31;border:1px solid #486080;border-radius:18px;padding:20px;margin-top:16px}
h1{font-size:28px;margin:0 0 10px}p{line-height:1.55;color:#d8e2f2}
input[type=file]{display:block;width:100%;box-sizing:border-box;background:#fff;color:#111827;padding:14px;border-radius:10px;margin:16px 0}
button{width:100%;font-size:18px;font-weight:700;padding:14px;border:0;border-radius:10px;background:#8f6cff;color:#fff}
button:disabled{opacity:.45}#s{font-weight:600;color:#35d7c5}.warn{color:#ffd56a}
</style>
</head>
<body>
<main>
  <h1>Kolbo Live Studio</h1>
  <div class='card'>
    <p>החיבור למחשב נוצר. לחץ על שדה הווידאו כדי לפתוח את מצלמת הטלפון המקורית, צלם את הביצוע ושמור.</p>
    <input id='pick' type='file' accept='video/*' capture='environment'>
    <button id='upload' disabled>שלח את הווידאו למחשב</button>
    <p id='s'>מתחבר למחשב...</p>
    <p class='warn'>את ההעלאה בצע לאחר שלחצת במחשב על “עצור ושמור”.</p>
  </div>
</main>
<script>
const q=new URLSearchParams(location.search);
const code=q.get('code');
const s=document.getElementById('s');
const pick=document.getElementById('pick');
const upload=document.getElementById('upload');
let bearer=null,file=null;
(async()=>{
  try{
    const r=await fetch('/pair',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({code})});
    if(!r.ok){s.textContent='קוד הצימוד פג או כבר נוצל';return}
    bearer=(await r.json()).bearer;
    s.textContent='מחובר למחשב — אפשר לצלם';
  }catch(e){s.textContent='החיבור למחשב נכשל: '+e.message}
})();
pick.onchange=()=>{
  file=pick.files&&pick.files[0];
  upload.disabled=!file;
  if(file)s.textContent='הווידאו מוכן לשליחה: '+Math.round(file.size/1024/1024)+' MB';
};
upload.onclick=async()=>{
  if(!file||!bearer)return;
  upload.disabled=true;
  s.textContent='שולח למחשב...';
  try{
    const r=await fetch('/upload/__KOLBO_SESSION_ID__',{
      method:'POST',
      headers:{Authorization:'Bearer '+bearer,'Content-Type':file.type||'video/mp4'},
      body:file
    });
    if(r.status===409){
      s.textContent='ההקלטה במחשב עדיין פעילה. לחץ במחשב “עצור ושמור” ואז לחץ כאן שוב.';
      upload.disabled=false;
      return;
    }
    if(!r.ok){
      s.textContent='שליחת הווידאו נכשלה. קוד: '+r.status;
      upload.disabled=false;
      return;
    }
    s.textContent='הווידאו נשמר בהצלחה במחשב';
    upload.textContent='נשלח בהצלחה';
  }catch(e){
    s.textContent='שליחת הווידאו נכשלה: '+e.message;
    upload.disabled=false;
  }
};
</script>
</body>
</html>
""".Replace(sessionMarker, escapedId, StringComparison.Ordinal);
    }

    sealed record PairRequest(string Code);

    public async ValueTask DisposeAsync()
    {
        if (app is not null)
        {
            await app.StopAsync();
            await app.DisposeAsync();
            app = null;
        }
    }
}
