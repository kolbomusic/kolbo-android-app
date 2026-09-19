using System.Net;
using System.Net.NetworkInformation;
using System.Security.Cryptography;
using System.Security.Cryptography.X509Certificates;
using System.Text;
using System.IO;
using Microsoft.AspNetCore.Builder;
using Microsoft.AspNetCore.Hosting;
using Microsoft.AspNetCore.Http;
using Kolbo.Live.Core;

namespace Kolbo.Live.Windows;

sealed class PhonePairingServer : IAsyncDisposable
{
    WebApplication? app;
    X509Certificate2? certificate;
    RSA? certificateKey;
    readonly PairingAuthority authority;
    readonly string code;
    readonly string sessionId;
    readonly string sessionDirectory;

    public Uri? Url { get; private set; }
    public string? Fingerprint { get; private set; }

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
        using var probe = new System.Net.Sockets.TcpListener(localIp, 0);
        probe.Start();
        var port = ((IPEndPoint)probe.LocalEndpoint).Port;
        probe.Stop();

        certificateKey = RSA.Create(2048);
        var request = new CertificateRequest("CN=Kolbo Live Studio Local", certificateKey, HashAlgorithmName.SHA256, RSASignaturePadding.Pkcs1);
        request.CertificateExtensions.Add(new X509BasicConstraintsExtension(false, false, 0, false));
        request.CertificateExtensions.Add(new X509KeyUsageExtension(X509KeyUsageFlags.DigitalSignature, false));
        var san = new SubjectAlternativeNameBuilder();
        san.AddDnsName("localhost");
        san.AddIpAddress(IPAddress.Loopback);
        san.AddIpAddress(localIp);
        request.CertificateExtensions.Add(san.Build());
        certificate = request.CreateSelfSigned(DateTimeOffset.UtcNow.AddMinutes(-2), DateTimeOffset.UtcNow.AddHours(8));
        Fingerprint = certificate.Thumbprint;

        var builder = WebApplication.CreateBuilder();
        builder.WebHost.ConfigureKestrel(o => o.Listen(localIp, port, l => l.UseHttps(certificate)));
        app = builder.Build();
        app.MapGet("/", () => Results.Content(Page(sessionId), "text/html", Encoding.UTF8));
        app.MapGet("/health", () => Results.Ok(new { service = "kolbo-live-studio-phone", authenticated = false }));
        app.MapPost("/pair", (PairRequest body) =>
        {
            var bearer = authority.Exchange(body.Code);
            return bearer is null ? Results.Unauthorized() : Results.Ok(new { bearer });
        });
        app.MapPost("/upload/{id}", UploadAsync);
        await app.StartAsync(cancellationToken);
        Url = new Uri($"https://{localIp}:{port}/?code={Uri.EscapeDataString(code)}");
    }

    async Task<IResult> UploadAsync(HttpRequest request, string id)
    {
        var bearer = Bearer(request);
        if (bearer is null || !authority.Authenticate(bearer)) return Results.Unauthorized();
        if (id.Length is < 1 or > 80 || id != sessionId || authority.CurrentId != id || authority.Recording)
            return Results.Unauthorized();
        if (request.ContentLength is > PairingAuthority.MaxUploadBytes)
            return Results.BadRequest("file too large");
        var safe = new string(id.Where(c => char.IsLetterOrDigit(c) || c is '-' or '_').ToArray());
        if (safe != id) return Results.BadRequest("invalid session id");

        var contentType = request.ContentType ?? string.Empty;
        var extension = contentType.Contains("mp4", StringComparison.OrdinalIgnoreCase) ? ".mp4" : ".webm";
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
            if (!authority.AllowUpload(bearer, id, written)) return Results.Unauthorized();
            File.Move(temp, final, true);
            return Results.Ok(new { saved = true, bytes = written, file = Path.GetFileName(final) });
        }
        finally
        {
            if (File.Exists(temp)) try { File.Delete(temp); } catch { }
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
                     .Where(n => n.OperationalStatus == OperationalStatus.Up && n.NetworkInterfaceType != NetworkInterfaceType.Loopback && n.NetworkInterfaceType != NetworkInterfaceType.Tunnel))
        {
            var props = nic.GetIPProperties();
            if (!props.GatewayAddresses.Any(g => g.Address.AddressFamily == System.Net.Sockets.AddressFamily.InterNetwork)) continue;
            var ip = props.UnicastAddresses.Select(u => u.Address).FirstOrDefault(a =>
                a.AddressFamily == System.Net.Sockets.AddressFamily.InterNetwork &&
                !IPAddress.IsLoopback(a) &&
                !a.ToString().StartsWith("169.254.", StringComparison.Ordinal));
            if (ip is not null) return ip;
        }
        return Dns.GetHostEntry(Dns.GetHostName()).AddressList.FirstOrDefault(a =>
            a.AddressFamily == System.Net.Sockets.AddressFamily.InterNetwork && !IPAddress.IsLoopback(a)) ?? IPAddress.Loopback;
    }

    static string Page(string id)
    {
        const string sessionMarker = "__KOLBO_SESSION_ID__";
        var escapedId = Uri.EscapeDataString(id);
        return """
<!doctype html>
<html lang='he' dir='rtl'><head><meta charset='utf-8'><meta name=viewport content='width=device-width,initial-scale=1'>
<title>Kolbo Live Studio</title><style>body{background:#0b1220;color:#f4f7ff;font:18px system-ui,sans-serif;text-align:center;padding:20px}video{width:100%;max-width:700px;background:#000;border-radius:14px}button{font-size:18px;padding:12px 20px;margin:8px;border-radius:10px}#s{color:#9fb1ca}</style></head>
<body><h1>Kolbo Live Studio</h1><video id=v autoplay playsinline muted></video><p id=s>מתחבר...</p><button id=start disabled>התחל מצלמה</button><button id=stop disabled>עצור ושלח</button>
<script>
const q=new URLSearchParams(location.search),code=q.get('code'),s=document.getElementById('s'),v=document.getElementById('v'),start=document.getElementById('start'),stop=document.getElementById('stop');
let bearer,stream,rec,chunks=[],mime='',pendingBlob=null,pendingType='';
(async()=>{try{const r=await fetch('/pair',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({code})});if(!r.ok){s.textContent='קוד הצימוד פג או כבר נוצל';return}bearer=(await r.json()).bearer;start.disabled=false;s.textContent='מוכן — אשר הרשאת מצלמה'}catch(e){s.textContent='החיבור למחשב נכשל'}})();
async function uploadPending(){if(!pendingBlob)return;stop.disabled=true;s.textContent='שולח למחשב...';try{const r=await fetch('/upload/__KOLBO_SESSION_ID__',{method:'POST',headers:{Authorization:'Bearer '+bearer,'Content-Type':pendingType},body:pendingBlob});if(!r.ok){s.textContent='ההעלאה עדיין לא אושרה. עצור את ההקלטה במחשב ואז לחץ שוב על שלח.';stop.textContent='שלח שוב';stop.disabled=false;return}pendingBlob=null;s.textContent='הסרטון נשמר בסשן במחשב';stop.textContent='עצור ושלח'}catch(e){s.textContent='שליחת הסרטון נכשלה: '+e.message;stop.textContent='שלח שוב';stop.disabled=false}}
start.onclick=async()=>{try{stream=await navigator.mediaDevices.getUserMedia({video:{facingMode:'user'},audio:false});v.srcObject=stream;chunks=[];pendingBlob=null;mime=['video/mp4','video/webm;codecs=vp9','video/webm;codecs=vp8','video/webm'].find(x=>MediaRecorder.isTypeSupported(x))||'';rec=mime?new MediaRecorder(stream,{mimeType:mime}):new MediaRecorder(stream);rec.ondataavailable=e=>e.data.size&&chunks.push(e.data);rec.start(1000);start.disabled=true;stop.disabled=false;stop.textContent='עצור ושלח';s.textContent='מצלם'}catch(e){s.textContent='לא התקבלה הרשאת מצלמה: '+e.message}};
stop.onclick=async()=>{if(pendingBlob){await uploadPending();return}stop.disabled=true;s.textContent='מסיים צילום...';rec.onstop=async()=>{pendingType=rec.mimeType||mime||'video/webm';pendingBlob=new Blob(chunks,{type:pendingType});await uploadPending()};rec.stop();stream.getTracks().forEach(x=>x.stop())};
</script></body></html>
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
        certificate?.Dispose();
        certificate = null;
        certificateKey?.Dispose();
        certificateKey = null;
    }
}
