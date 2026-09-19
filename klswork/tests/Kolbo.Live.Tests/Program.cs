using Kolbo.Live.Core;
var tests = new List<(string,Action)> {
 ("master sums dry + actual wet + backing and shares overload clipping",()=> { float[] dry=[.2f,2f],wet=[.1f,.2f,.3f,.4f],back=[.4f,.6f,0,0],master=new float[4],send=new float[4]; Mixer.Process(dry,wet,back,master,send,new Gains(1,.5f,.25f,.8f)); Near(master[0],.35f);Near(master[1],.45f);Near(master[2],1f); Near(send[2],1f);Near(send[3],1f); }),
 ("routing rejects feedback outputs, duplicate inputs, unsupported rates and missing confirmation",()=> { var r=new Routing(0,1,2,0,1,2,3,48000); Check(r.Validate(3,4,[48000],true).Length==0,"valid mapping rejected"); Check((r with {MasterLeft=0}).Validate(3,4,[48000],true).Length>0,"output overlap accepted"); Check((r with {WetLeft=0}).Validate(3,4,[48000],true).Length>0,"dry duplicated in return"); Check(r.Validate(2,4,[48000],true).Length>0,"invalid input accepted"); Check(r.Validate(3,4,[96000],true).Length>0,"unsupported rate accepted"); Check(r.Validate(3,4,[48000],false).Length>0,"wet-only not confirmed"); })
};
tests.Add(("recorded master is bit-identical and stems have the same frame clock",()=> {
 var path=Temp(); using(var writer=new SessionWriter(path,48000,64,64)) {
  for(int block=0;block<20;block++) {float[] dry=Enumerable.Repeat(.2f,64).ToArray(),wet=Enumerable.Repeat(.3f,128).ToArray(),back=Enumerable.Repeat(.4f,128).ToArray(),master=new float[128],send=new float[128]; Mixer.Process(dry,wet,back,master,send,new Gains());Check(writer.TryWrite(dry,wet,back,master),"unexpected write refusal");}
  writer.Complete();Check(writer.Error is null,"writer error");Check(writer.FramesWritten==1280,"frame loss");
 }
 var m=SessionWriter.ReadManifest(path);Check(m.Status=="Completed"&&m.Frames==1280,"manifest incomplete");
 var wav=File.ReadAllBytes(Path.Combine(path,"master.wav"));Check(System.Text.Encoding.ASCII.GetString(wav,0,4)=="RIFF","missing header");Check(BitConverter.ToInt32(wav,52)==1280*8,"WAV data length");Near(BitConverter.ToSingle(wav,56),.545f);
 Check(File.ReadAllBytes(Path.Combine(path,"dry.wav")).Length==56+1280*4,"stem mismatch");
}));
tests.Add(("bounded queue rejects overflow visibly without blocking producer",()=> {
 using var gate=new ManualResetEventSlim(false);var streams=new List<Stream>();
 using var writer=new SessionWriter(Temp(),48000,16,2,p=> {var s=new GatedStream(gate);streams.Add(s);return s;});
 float[] d=new float[16],s=new float[32];var clock=System.Diagnostics.Stopwatch.StartNew();bool refused=false;
 for(int i=0;i<100;i++)if(!writer.TryWrite(d,s,s,s)){refused=true;break;}
 gate.Set();Check(refused,"overflow not rejected");Check(clock.ElapsedMilliseconds<500,"producer blocked");writer.Complete();Check(writer.Error?.Contains("overflow")==true,"overflow not visible");
}));
tests.Add(("disk failure preserves an error and incomplete session can be recovered into a new directory",()=> {
 var path=Temp();using(var writer=new SessionWriter(path,48000,16,8,p=>new FailureStream(new FileStream(p,FileMode.CreateNew,FileAccess.ReadWrite)))) {float[] d=new float[16],s=new float[32];writer.TryWrite(d,s,s,s);writer.Complete();Check(writer.Error!=null,"disk failure swallowed");}
 Check(SessionWriter.ReadManifest(path).Status=="Error","failed session presented as successful");
 var original=File.ReadAllBytes(Path.Combine(path,"master.wav"));var recovered=SessionWriter.Recover(path);Check(recovered!=path,"recovery overwrote original");Check(File.ReadAllBytes(Path.Combine(path,"master.wav")).SequenceEqual(original),"original modified");Check(SessionWriter.ReadManifest(recovered).Status=="Recovered","recovery manifest missing");
}));
tests.Add(("phone token is single-use, expires, authenticates and scopes uploads",()=> {
 var time=new FakeTime();var a=new PairingAuthority(time);Check(a.PairCode.Length>=32,"weak token");Check(a.Exchange("wrong")==null,"wrong token accepted");var bearer=a.Exchange(a.PairCode);Check(bearer!=null&&a.Authenticate(bearer),"pair failed");Check(a.Exchange(a.PairCode)==null,"pair token reusable");
 a.Begin("one");Check(!a.AllowUpload(bearer!,"one",10),"upload while audio recording");a.End();Check(a.AllowUpload(bearer!,"one",10),"current upload rejected");Check(!a.AllowUpload(bearer!,"../outside",10),"path injection allowed");Check(!a.AllowUpload(bearer!,"one",PairingAuthority.MaxUploadBytes+1),"oversize upload accepted");
 a.Begin("two");a.End();Check(!a.AllowUpload(bearer!,"one",10),"old recording accepted");a.Revoke();Check(!a.Authenticate(bearer),"revoked session accepted");
 var b=new PairingAuthority(time);time.Advance(TimeSpan.FromMinutes(6));Check(b.Exchange(b.PairCode)==null,"expired pair token accepted");
}));
tests.Add(("native PCM conversion preserves channels and saturates without wraparound",()=> {
 foreach(var encoding in Enum.GetValues<SampleEncoding>()) {float[] input=[-1f,.2f,-.25f,.3f,.5f,.4f,1f,.5f];byte[] data=new byte[4*PcmCodec.Bytes(encoding)];PcmCodec.Encode(input,2,0,data,encoding);float[] decoded=new float[8];PcmCodec.Decode(data,decoded,2,0,encoding);Check(Math.Abs(decoded[0]+1)<.00004,"negative full scale");Check(Math.Abs(decoded[2]+.25)<.00004,"negative sample");Check(Math.Abs(decoded[4]-.5)<.00004,"positive sample");Check(decoded[6]>.9999,"positive full scale");Near(decoded[1],0);}
}));
tests.Add(("nonfinite input cannot poison master or hardware send",()=> {float[] d=[float.NaN],w=[float.PositiveInfinity,0],b=[0,0],m=new float[2],send=new float[2];Mixer.Process(d,w,b,m,send,new Gains());Check(m.All(float.IsFinite)&&send.All(float.IsFinite),"nonfinite propagated");}));
var failed=0; foreach(var (name,test) in tests)try{test();Console.WriteLine("PASS "+name);}catch(Exception e){failed++;Console.WriteLine("FAIL "+name+": "+e.Message);} Console.WriteLine($"{tests.Count-failed}/{tests.Count} passed"); return failed==0?0:1;
static void Check(bool ok,string message) {if(!ok)throw new Exception(message);}
static void Near(float actual,float expected) => Check(Math.Abs(actual-expected)<.000001f,$"expected {expected}, got {actual}");
static string Temp() {var p=Path.Combine(Path.GetTempPath(),"kolbo-test-"+Guid.NewGuid().ToString("N"));Directory.CreateDirectory(p);return p;}
sealed class GatedStream(ManualResetEventSlim gate) : MemoryStream {
 public override void Write(ReadOnlySpan<byte> buffer) {if(Position>=56)gate.Wait();base.Write(buffer);}
}
sealed class FailureStream(Stream inner):Stream {
 public override bool CanRead=>inner.CanRead;public override bool CanSeek=>true;public override bool CanWrite=>true;public override long Length=>inner.Length;public override long Position{get=>inner.Position;set=>inner.Position=value;}
 public override void Flush()=>inner.Flush();public override int Read(byte[] b,int o,int n)=>inner.Read(b,o,n);public override long Seek(long o,SeekOrigin origin)=>inner.Seek(o,origin);public override void SetLength(long n)=>inner.SetLength(n);
 public override void Write(byte[] b,int o,int n) {if(Position>=56)throw new IOException("simulated disk full");inner.Write(b,o,n);}
 public override void Write(ReadOnlySpan<byte> b) {if(Position>=56)throw new IOException("simulated disk full");inner.Write(b);}
 protected override void Dispose(bool disposing){if(disposing)inner.Dispose();base.Dispose(disposing);}
}
sealed class FakeTime:TimeProvider {DateTimeOffset now=DateTimeOffset.UtcNow;public override DateTimeOffset GetUtcNow()=>now;public void Advance(TimeSpan time)=>now+=time;}
