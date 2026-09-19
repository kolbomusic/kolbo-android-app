using System.Runtime.InteropServices;
using System.Text;
using System.Text.Json;
namespace Kolbo.Live.Core;
public sealed record SessionManifest(string Id,int SampleRate,string Status,long Frames,string? Error=null,Routing? Routing=null,Gains? Gains=null,string? Device=null);
/// <summary>One audio producer; one disk consumer. All slots are allocated before recording.</summary>
public sealed class SessionWriter : IDisposable {
 sealed class Block(int maxFrames) {public readonly float[] Dry=new float[maxFrames],Wet=new float[maxFrames*2],Backing=new float[maxFrames*2],Master=new float[maxFrames*2];public int Frames;}
 readonly Block[] blocks;readonly WaveFile[] files;readonly Thread worker;readonly SessionManifest metadata;
 long writeIndex,readIndex,framesWritten;int complete;string? error;
 public string DirectoryPath {get;}
 public string? Error => Volatile.Read(ref error);
 public long FramesWritten => Interlocked.Read(ref framesWritten);
 public SessionWriter(string directory,int rate,int maxFrames=1024,int capacity=64,Func<string,Stream>? open=null,SessionManifest? metadata=null) {
  if(rate<=0||maxFrames<=0||capacity<2)throw new ArgumentOutOfRangeException();
  DirectoryPath=directory;Directory.CreateDirectory(directory);
  if(File.Exists(Path.Combine(directory,"session.json")))throw new IOException("Session already exists");
  this.metadata=metadata??new SessionManifest(Guid.NewGuid().ToString("N"),rate,"Recording",0);
  blocks=Enumerable.Range(0,capacity).Select(_=>new Block(maxFrames)).ToArray();
  open??=p=>new FileStream(p,FileMode.CreateNew,FileAccess.ReadWrite,FileShare.Read,65536,FileOptions.SequentialScan);
  List<WaveFile> opened=[];
  try {foreach(var (name,ch) in Tracks)opened.Add(new WaveFile(open(Path.Combine(directory,name+".wav")),rate,ch));files=opened.ToArray();SaveManifest(directory,this.metadata with {Status="Recording",Frames=0});}
  catch {foreach(var file in opened)file.Dispose();throw;}
  worker=new Thread(Consume){IsBackground=true,Name="Kolbo lossless writer"};worker.Start();
 }
 static readonly (string Name,int Channels)[] Tracks=[("dry",1),("wet",2),("backing",2),("master",2)];
 public bool TryWrite(ReadOnlySpan<float> dry,ReadOnlySpan<float> wet,ReadOnlySpan<float> backing,ReadOnlySpan<float> master) {
  if(Volatile.Read(ref complete)!=0||Error!=null)return false;
  long w=writeIndex;
  if(w-Volatile.Read(ref readIndex)>=blocks.Length){Fail("Recording queue overflow: recording stopped; monitor remains active");return false;}
  var b=blocks[(int)(w%blocks.Length)];int n=dry.Length;
  if(n>b.Dry.Length||wet.Length!=n*2||backing.Length!=n*2||master.Length!=n*2){Fail("Invalid audio block size");return false;}
  dry.CopyTo(b.Dry);wet.CopyTo(b.Wet);backing.CopyTo(b.Backing);master.CopyTo(b.Master);b.Frames=n;
  Volatile.Write(ref writeIndex,w+1);return true;
 }
 public void Fail(string message)=>Interlocked.CompareExchange(ref error,message,null);
 void Consume() {
  try {
   while(Volatile.Read(ref complete)==0||readIndex<Volatile.Read(ref writeIndex)) {
    long r=readIndex;
    if(r==Volatile.Read(ref writeIndex)){Thread.Sleep(2);continue;}
    var b=blocks[(int)(r%blocks.Length)];
    files[0].Write(b.Dry.AsSpan(0,b.Frames));files[1].Write(b.Wet.AsSpan(0,b.Frames*2));files[2].Write(b.Backing.AsSpan(0,b.Frames*2));files[3].Write(b.Master.AsSpan(0,b.Frames*2));
    Interlocked.Add(ref framesWritten,b.Frames);Volatile.Write(ref readIndex,r+1);
   }
  }catch(Exception e){Fail("Disk writer failed: "+e.Message);}
  finally {
   foreach(var file in files)try{file.Dispose();}catch(Exception e){Fail("WAV finalization failed: "+e.Message);}
   try{SaveManifest(DirectoryPath,metadata with {Status=Error==null?"Completed":"Error",Frames=FramesWritten,Error=Error});}catch(Exception e){Fail("Manifest save failed: "+e.Message);}
  }
 }
 /// <summary>Call only after audio producer is quiescent.</summary>
 public void Complete(){Interlocked.Exchange(ref complete,1);worker.Join();}
 public void Dispose()=>Complete();
 public static SessionManifest ReadManifest(string directory)=>JsonSerializer.Deserialize<SessionManifest>(File.ReadAllText(Path.Combine(directory,"session.json")))??throw new InvalidDataException("Invalid manifest");
 public static void SaveManifest(string directory,SessionManifest manifest) {
  var path=Path.Combine(directory,"session.json");var temp=path+"."+Guid.NewGuid().ToString("N")+".tmp";
  using(var f=new FileStream(temp,FileMode.CreateNew,FileAccess.Write,FileShare.None)){JsonSerializer.Serialize(f,manifest,new JsonSerializerOptions{WriteIndented=true});f.Flush(true);}
  File.Move(temp,path,true);
 }
 public static string Recover(string directory) {
  var m=ReadManifest(directory);if(m.SampleRate<=0)throw new InvalidDataException("Invalid sample rate");
  long frames=Tracks.Min(t=>Math.Max(0,new FileInfo(Path.Combine(directory,t.Name+".wav")).Length-56)/(t.Channels*4));
  string target=Path.Combine(Path.GetDirectoryName(Path.GetFullPath(directory))!,Path.GetFileName(directory)+"-recovered-"+Guid.NewGuid().ToString("N")[..8]);Directory.CreateDirectory(target);
  foreach(var (name,channels) in Tracks) {
   using var source=File.OpenRead(Path.Combine(directory,name+".wav"));source.Position=56;
   using var wave=new WaveFile(new FileStream(Path.Combine(target,name+".wav"),FileMode.CreateNew,FileAccess.ReadWrite),m.SampleRate,channels);
   byte[] bytes=new byte[65536];long left=frames*channels*4;
   while(left>0){int got=source.Read(bytes,0,(int)Math.Min(left,bytes.Length));if(got==0)throw new EndOfStreamException();wave.WriteBytes(bytes.AsSpan(0,got));left-=got;}
  }
  SaveManifest(target,m with {Id=Guid.NewGuid().ToString("N"),Status="Recovered",Frames=frames,Error="Recovered aligned frames; originals preserved. "+m.Error});return target;
 }
}
internal sealed class WaveFile : IDisposable {
 readonly Stream stream;readonly int rate,channels;long bytes;bool disposed;
 public WaveFile(Stream stream,int rate,int channels){this.stream=stream;this.rate=rate;this.channels=channels;Header();}
 void Header(){stream.Position=0;using var w=new BinaryWriter(stream,Encoding.ASCII,true);w.Write(Encoding.ASCII.GetBytes("RIFF"));w.Write((uint)(48+bytes));w.Write(Encoding.ASCII.GetBytes("WAVEfmt "));w.Write(16);w.Write((ushort)3);w.Write((ushort)channels);w.Write(rate);w.Write(rate*channels*4);w.Write((ushort)(channels*4));w.Write((ushort)32);w.Write(Encoding.ASCII.GetBytes("fact"));w.Write(4);w.Write((uint)(bytes/(channels*4)));w.Write(Encoding.ASCII.GetBytes("data"));w.Write((uint)bytes);}
 public void Write(ReadOnlySpan<float> samples)=>WriteBytes(MemoryMarshal.AsBytes(samples));
 public void WriteBytes(ReadOnlySpan<byte> value){if(bytes+value.Length>uint.MaxValue-48)throw new IOException("WAV size limit reached; start a new session");stream.Write(value);bytes+=value.Length;}
 public void Dispose(){if(disposed)return;disposed=true;try{Header();stream.Flush();if(stream is FileStream f)f.Flush(true);}finally{stream.Dispose();}}
}
