using System.Security.Cryptography;
using System.Text;
namespace Kolbo.Live.Core;
public sealed class PairingAuthority {
 readonly TimeProvider clock;readonly object sync=new();readonly DateTimeOffset expires;string? bearer;bool exchanged;string? currentId;bool recording;
 public string PairCode {get;}=Convert.ToHexString(RandomNumberGenerator.GetBytes(32));
 public const long MaxUploadBytes=512L*1024*1024;
 public PairingAuthority(TimeProvider? clock=null){this.clock=clock??TimeProvider.System;expires=this.clock.GetUtcNow().AddMinutes(5);}
 static bool Equal(string? a,string? b)=>a!=null&&b!=null&&CryptographicOperations.FixedTimeEquals(Encoding.UTF8.GetBytes(a),Encoding.UTF8.GetBytes(b));
 public string? Exchange(string code){lock(sync){if(exchanged||clock.GetUtcNow()>expires||!Equal(code,PairCode))return null;exchanged=true;return bearer=Convert.ToHexString(RandomNumberGenerator.GetBytes(32));}}
 public bool Authenticate(string? token){lock(sync)return Equal(token,bearer)&&clock.GetUtcNow()<expires.AddHours(8);}
 public void Begin(string id){if(!Guid.TryParseExact(id,"N",out _)&&!System.Text.RegularExpressions.Regex.IsMatch(id,"^[a-zA-Z0-9_-]{1,80}$"))throw new ArgumentException("Invalid id");lock(sync){currentId=id;recording=true;}}
 public void End(){lock(sync)recording=false;}
 public bool AllowUpload(string token,string id,long bytes){lock(sync)return Authenticate(token)&&!recording&&id==currentId&&bytes>0&&bytes<=MaxUploadBytes;}
 public string? CurrentId {get{lock(sync)return currentId;}}
 public bool Recording {get{lock(sync)return recording;}}
 public void Revoke(){lock(sync){bearer=null;exchanged=true;recording=false;currentId=null;}}
}
