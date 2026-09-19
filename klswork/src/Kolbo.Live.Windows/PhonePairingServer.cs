using System.Diagnostics;
using System.IO;
using System.Net;
using System.Net.WebSockets;
using System.Text;
using System.Text.Json;
using System.Text.RegularExpressions;
using Microsoft.AspNetCore.Builder;
using Microsoft.AspNetCore.Hosting;
using Microsoft.AspNetCore.Http;
using Kolbo.Live.Core;

namespace Kolbo.Live.Windows;

/// <summary>
/// Secure browser-camera bridge. Kestrel listens only on loopback; cloudflared provides
/// a trusted HTTPS/WSS endpoint so mobile getUserMedia works without installing certificates.
/// Live JPEG preview frames are sent over WebSocket before and during audio recording.
/// The browser records camera-only video and uploads it automatically after Stop.
/// </summary>
sealed class PhonePairingServer : IAsyncDisposable
{
    readonly PairingAuthority authority = new();
    readonly SemaphoreSlim sendLock = new(1, 1);
    readonly object stateLock = new();

    WebApplication? app;
    Process? tunnel;
    WebSocket? socket;
    string? sessionDirectory;

    public Uri? Url { get; private set; }
    public bool Connected => socket?.State == WebSocketState.Open;

    public event Action<byte[]>? PreviewFrameReceived;
    public event Action<string>? StatusChanged;
    public event Action<string>? VideoSaved;

    public async Task StartAsync(CancellationToken cancellationToken = default)
    {
        if (app is not null) return;

        var listener = new System.Net.Sockets.TcpListener(IPAddress.Loopback, 0);
        listener.Start();
        var port = ((IPEndPoint)listener.LocalEndpoint).Port;
        listener.Stop();

        var builder = WebApplication.CreateBuilder();
        builder.WebHost.ConfigureKestrel(o => o.Listen(IPAddress.Loopback, port));
        app = builder.Build();
        app.UseWebSockets();

        app.MapGet("/", () => Results.Content(Page(), "text/html", Encoding.UTF8));
        app.MapGet("/health", () => Results.Ok(new { service = "kolbo-phone-camera", secure_browser_camera = true }));
        app.MapPost("/pair", (PairRequest body) =>
        {
            var bearer = authority.Exchange(body.Code);
            return bearer is null ? Results.Unauthorized() : Results.Ok(new { bearer });
        });
        app.Map("/ws", HandleWebSocketAsync);
        app.MapPost("/upload", UploadAsync);

        await app.StartAsync(cancellationToken);

        var cloudflared = Path.Combine(AppContext.BaseDirectory, "tools", "cloudflared.exe");
        if (!File.Exists(cloudflared))
            throw new FileNotFoundException("cloudflared.exe לא נמצא בחבילת התוכנה", cloudflared);

        var psi = new ProcessStartInfo(cloudflared)
        {
            UseShellExecute = false,
            CreateNoWindow = true,
            RedirectStandardOutput = true,
            RedirectStandardError = true
        };
        psi.ArgumentList.Add("tunnel");
        psi.ArgumentList.Add("--no-autoupdate");
        psi.ArgumentList.Add("--url");
        psi.ArgumentList.Add($"http://127.0.0.1:{port}");

        tunnel = new Process { StartInfo = psi, EnableRaisingEvents = true };
        if (!tunnel.Start())
            throw new InvalidOperationException("לא ניתן להפעיל את מנהרת המצלמה המאובטחת.");

        var urlTcs = new TaskCompletionSource<Uri>(TaskCreationOptions.RunContinuationsAsynchronously);
        _ = PumpTunnelAsync(tunnel.StandardOutput, urlTcs, cancellationToken);
        _ = PumpTunnelAsync(tunnel.StandardError, urlTcs, cancellationToken);

        using var timeout = CancellationTokenSource.CreateLinkedTokenSource(cancellationToken);
        timeout.CancelAfter(TimeSpan.FromSeconds(25));
        using var registration = timeout.Token.Register(() => urlTcs.TrySetCanceled(timeout.Token));
        var baseUrl = await urlTcs.Task;

        Url = new Uri(baseUrl, "/?code=" + Uri.EscapeDataString(authority.PairCode));
        StatusChanged?.Invoke("קישור מצלמה מאובטח מוכן. סרוק את ה-QR ואשר מצלמה בדפדפן.");
    }

    async Task PumpTunnelAsync(StreamReader reader, TaskCompletionSource<Uri> urlTcs, CancellationToken ct)
    {
        var regex = new Regex(@"https://[a-z0-9-]+\.trycloudflare\.com", RegexOptions.IgnoreCase | RegexOptions.Compiled);
        while (!ct.IsCancellationRequested)
        {
            var line = await reader.ReadLineAsync(ct);
            if (line is null) break;
            var match = regex.Match(line);
            if (match.Success && Uri.TryCreate(match.Value, UriKind.Absolute, out var uri))
                urlTcs.TrySetResult(uri);
        }
    }

    async Task HandleWebSocketAsync(HttpContext context)
    {
        if (!context.WebSockets.IsWebSocketRequest)
        {
            context.Response.StatusCode = StatusCodes.Status400BadRequest;
            return;
        }

        var bearer = context.Request.Query["bearer"].ToString();
        if (!authority.Authenticate(bearer))
        {
            context.Response.StatusCode = StatusCodes.Status401Unauthorized;
            return;
        }

        using var ws = await context.WebSockets.AcceptWebSocketAsync();
        lock (stateLock)
        {
            socket?.Abort();
            socket = ws;
        }
        StatusChanged?.Invoke("מצלמת הטלפון מחוברת — תצוגה חיה פעילה.");

        var buffer = new byte[128 * 1024];
        try
        {
            while (ws.State == WebSocketState.Open)
            {
                using var message = new MemoryStream();
                WebSocketReceiveResult result;
                do
                {
                    result = await ws.ReceiveAsync(buffer, context.RequestAborted);
                    if (result.MessageType == WebSocketMessageType.Close)
                    {
                        await ws.CloseAsync(WebSocketCloseStatus.NormalClosure, "bye", CancellationToken.None);
                        return;
                    }
                    message.Write(buffer, 0, result.Count);
                    if (message.Length > 2 * 1024 * 1024)
                        throw new InvalidDataException("Phone preview frame too large.");
                }
                while (!result.EndOfMessage);

                var payload = message.ToArray();
                if (result.MessageType == WebSocketMessageType.Binary)
                {
                    PreviewFrameReceived?.Invoke(payload);
                }
                else if (result.MessageType == WebSocketMessageType.Text)
                {
                    var text = Encoding.UTF8.GetString(payload);
                    StatusChanged?.Invoke(ParseBrowserStatus(text));
                }
            }
        }
        catch (OperationCanceledException) { }
        catch (WebSocketException) { }
        finally
        {
            lock (stateLock)
            {
                if (ReferenceEquals(socket, ws)) socket = null;
            }
            StatusChanged?.Invoke("מצלמת הטלפון נותקה.");
        }
    }

    static string ParseBrowserStatus(string json)
    {
        try
        {
            using var doc = JsonDocument.Parse(json);
            if (doc.RootElement.TryGetProperty("status", out var value))
                return value.GetString() ?? "מצלמה מחוברת";
        }
        catch { }
        return "מצלמה מחוברת";
    }

    public void SetSessionDirectory(string? directory)
    {
        lock (stateLock) sessionDirectory = directory;
    }

    public Task<bool> StartRemoteRecordingAsync(CancellationToken ct = default) =>
        SendCommandAsync("start-recording", ct);

    public Task<bool> StopRemoteRecordingAsync(CancellationToken ct = default) =>
        SendCommandAsync("stop-recording", ct);

    async Task<bool> SendCommandAsync(string command, CancellationToken ct)
    {
        WebSocket? ws;
        lock (stateLock) ws = socket;
        if (ws?.State != WebSocketState.Open) return false;

        var bytes = Encoding.UTF8.GetBytes(JsonSerializer.Serialize(new { command }));
        await sendLock.WaitAsync(ct);
        try
        {
            await ws.SendAsync(bytes, WebSocketMessageType.Text, true, ct);
            return true;
        }
        finally
        {
            sendLock.Release();
        }
    }

    async Task<IResult> UploadAsync(HttpRequest request)
    {
        var bearer = Bearer(request);
        if (bearer is null || !authority.Authenticate(bearer))
            return Results.Unauthorized();

        string? directory;
        lock (stateLock) directory = sessionDirectory;
        if (string.IsNullOrWhiteSpace(directory))
            return Results.StatusCode(StatusCodes.Status409Conflict);

        if (request.ContentLength is > PairingAuthority.MaxUploadBytes)
            return Results.BadRequest("file too large");

        Directory.CreateDirectory(directory);
        var contentType = request.ContentType ?? "";
        var ext = contentType.Contains("mp4", StringComparison.OrdinalIgnoreCase) ? ".mp4" :
                  contentType.Contains("quicktime", StringComparison.OrdinalIgnoreCase) ? ".mov" : ".webm";
        var temp = Path.Combine(directory, "phone-video-" + Guid.NewGuid().ToString("N") + ".part");
        var final = Path.Combine(directory, "phone-video" + ext);
        long total = 0;

        try
        {
            await using var output = new FileStream(temp, FileMode.CreateNew, FileAccess.Write, FileShare.None, 65536, useAsync: true);
            var buffer = new byte[65536];
            while (true)
            {
                var read = await request.Body.ReadAsync(buffer, request.HttpContext.RequestAborted);
                if (read == 0) break;
                total += read;
                if (total > PairingAuthority.MaxUploadBytes)
                    return Results.BadRequest("file too large");
                await output.WriteAsync(buffer.AsMemory(0, read), request.HttpContext.RequestAborted);
            }
            await output.FlushAsync(request.HttpContext.RequestAborted);
            File.Move(temp, final, true);
            VideoSaved?.Invoke(final);
            StatusChanged?.Invoke("סרטון הטלפון נשמר ומוכן לייצוא.");
            return Results.Ok(new { saved = true, bytes = total });
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
        var text = value.ToString();
        return text.StartsWith("Bearer ", StringComparison.Ordinal) ? text[7..] : null;
    }

    static string Page() => """
<!doctype html>
<html lang="he" dir="rtl">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<title>Kolbo Live Studio Camera</title>
<style>
body{margin:0;background:#07111f;color:#fff;font-family:system-ui,sans-serif}main{max-width:720px;margin:auto;padding:16px}
.card{background:#111d31;border:1px solid #486080;border-radius:18px;padding:16px}
video{display:block;width:100%;max-height:70vh;background:#000;border-radius:14px;object-fit:contain}
button{width:100%;padding:14px;margin-top:10px;border:0;border-radius:12px;font-size:18px;font-weight:700;background:#8f6cff;color:#fff}
button.secondary{background:#23334f}.status{color:#35d7c5;line-height:1.5}.bad{color:#ff8a9b}
</style>
</head>
<body><main>
<div class="card">
<h2>מצלמת Kolbo Live Studio</h2>
<p id="status" class="status">מתחבר למחשב...</p>
<video id="preview" autoplay muted playsinline></video>
<button id="enable">אפשר מצלמה והתחל תצוגה חיה</button>
<button id="flip" class="secondary" disabled>החלף מצלמה</button>
</div>
<canvas id="canvas" hidden></canvas>
<script>
const q=new URLSearchParams(location.search),code=q.get('code');
const statusEl=document.getElementById('status'),video=document.getElementById('preview');
const enable=document.getElementById('enable'),flip=document.getElementById('flip'),canvas=document.getElementById('canvas');
let bearer=null,ws=null,stream=null,recorder=null,chunks=[],facing='user',previewTimer=null;

function status(t,bad=false){statusEl.textContent=t;statusEl.className=bad?'bad':'status';if(ws&&ws.readyState===1)try{ws.send(JSON.stringify({status:t}))}catch{}}
async function pair(){
 const r=await fetch('/pair',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({code})});
 if(!r.ok)throw new Error('קוד הצימוד פג או כבר נוצל');
 bearer=(await r.json()).bearer;
 const proto=location.protocol==='https:'?'wss:':'ws:';
 ws=new WebSocket(proto+'//'+location.host+'/ws?bearer='+encodeURIComponent(bearer));
 ws.binaryType='arraybuffer';
 ws.onmessage=e=>{try{const m=JSON.parse(e.data);if(m.command==='start-recording')startRecording();if(m.command==='stop-recording')stopRecording();}catch{}};
 ws.onopen=()=>status('מחובר למחשב. אשר הרשאת מצלמה כדי להתחיל תצוגה חיה.');
 ws.onclose=()=>status('החיבור למחשב נותק.',true);
}
async function openCamera(){
 if(stream)stream.getTracks().forEach(t=>t.stop());
 stream=await navigator.mediaDevices.getUserMedia({video:{facingMode:{ideal:facing},width:{ideal:1280},height:{ideal:720}},audio:false});
 video.srcObject=stream;await video.play();flip.disabled=false;enable.textContent='המצלמה פעילה';
 status('מצלמה פעילה — התצוגה החיה משודרת לתוכנה עוד לפני ההקלטה.');
 if(previewTimer)clearInterval(previewTimer);
 previewTimer=setInterval(sendPreview,180);
}
async function sendPreview(){
 if(!stream||!ws||ws.readyState!==1||ws.bufferedAmount>500000||video.videoWidth===0)return;
 const w=640,h=Math.max(1,Math.round(video.videoHeight*(640/video.videoWidth)));
 canvas.width=w;canvas.height=h;canvas.getContext('2d').drawImage(video,0,0,w,h);
 const blob=await new Promise(r=>canvas.toBlob(r,'image/jpeg',0.68));
 if(blob&&ws.readyState===1&&ws.bufferedAmount<500000)ws.send(await blob.arrayBuffer());
}
function bestMime(){
 const types=['video/mp4;codecs=h264','video/mp4','video/webm;codecs=vp9','video/webm;codecs=vp8','video/webm'];
 return types.find(t=>window.MediaRecorder&&MediaRecorder.isTypeSupported(t))||'';
}
function startRecording(){
 if(!stream){status('המחשב ביקש להתחיל, אבל המצלמה עדיין לא אושרה.',true);return}
 if(recorder&&recorder.state!=='inactive')return;
 chunks=[];const mime=bestMime();
 recorder=mime?new MediaRecorder(stream,{mimeType:mime}):new MediaRecorder(stream);
 recorder.ondataavailable=e=>{if(e.data&&e.data.size)chunks.push(e.data)};
 recorder.onstart=()=>status('מקליט וידאו יחד עם הטייק במחשב.');
 recorder.start(1000);
}
function stopRecording(){
 if(!recorder||recorder.state==='inactive'){status('האודיו נעצר. לא היה וידאו פעיל להעלאה.');return}
 recorder.onstop=uploadVideo;recorder.stop();status('מסיים וידאו ומעלה למחשב...');
}
async function uploadVideo(){
 const type=recorder.mimeType||bestMime()||'video/webm';
 const blob=new Blob(chunks,{type});
 try{
   const r=await fetch('/upload',{method:'POST',headers:{Authorization:'Bearer '+bearer,'Content-Type':type},body:blob});
   if(!r.ok)throw new Error('HTTP '+r.status);
   status('הווידאו נשמר במחשב ומוכן לייצוא.');
 }catch(e){status('העלאת הווידאו נכשלה: '+e.message,true)}
}
enable.onclick=()=>openCamera().catch(e=>status('לא ניתן לקבל הרשאת מצלמה: '+e.message,true));
flip.onclick=async()=>{facing=facing==='user'?'environment':'user';try{await openCamera()}catch(e){status('החלפת מצלמה נכשלה: '+e.message,true)}};
(async()=>{try{await pair();try{await openCamera()}catch{status('החיבור מוכן. לחץ “אפשר מצלמה” ואשר את ההרשאה בדפדפן.')}}catch(e){status('החיבור נכשל: '+e.message,true)}})();
</script>
</main></body></html>
""";

    public async ValueTask DisposeAsync()
    {
        authority.Revoke();
        WebSocket? ws;
        lock (stateLock) { ws = socket; socket = null; }
        if (ws is not null)
        {
            try { ws.Abort(); ws.Dispose(); } catch { }
        }

        if (app is not null)
        {
            await app.StopAsync();
            await app.DisposeAsync();
            app = null;
        }

        if (tunnel is not null)
        {
            try
            {
                if (!tunnel.HasExited) tunnel.Kill(entireProcessTree: true);
                tunnel.Dispose();
            }
            catch { }
            tunnel = null;
        }
        sendLock.Dispose();
    }

    sealed record PairRequest(string Code);
}
