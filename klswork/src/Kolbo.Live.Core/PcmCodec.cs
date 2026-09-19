using System.Buffers.Binary;
namespace Kolbo.Live.Core;
public enum SampleEncoding {Int16,Int24,Int32,Float32}
/// <summary>Little-endian native ASIO formats. Integer conversion necessarily quantizes by one LSB.</summary>
public static class PcmCodec {
 public static int Bytes(SampleEncoding format)=>format==SampleEncoding.Int16?2:format==SampleEncoding.Int24?3:4;
 public static void Encode(ReadOnlySpan<float> source,int stride,int channel,Span<byte> target,SampleEncoding format) {
  int size=Bytes(format),frames=target.Length/size;
  for(int i=0;i<frames;i++) {
   float x=source[i*stride+channel];x=float.IsFinite(x)?Math.Clamp(x,-1,1):0;var b=target.Slice(i*size,size);
   switch(format){case SampleEncoding.Float32:BinaryPrimitives.WriteSingleLittleEndian(b,x);break;case SampleEncoding.Int16:BinaryPrimitives.WriteInt16LittleEndian(b,(short)Math.Clamp((long)Math.Round(x*32768d),short.MinValue,short.MaxValue));break;case SampleEncoding.Int24:int v=(int)Math.Clamp((long)Math.Round(x*8388608d),-8388608,8388607);b[0]=(byte)v;b[1]=(byte)(v>>8);b[2]=(byte)(v>>16);break;case SampleEncoding.Int32:BinaryPrimitives.WriteInt32LittleEndian(b,(int)Math.Clamp((long)Math.Round(x*2147483648d),int.MinValue,int.MaxValue));break;}
  }
 }
 public static void Decode(ReadOnlySpan<byte> source,Span<float> target,int stride,int channel,SampleEncoding format) {
  int size=Bytes(format);for(int i=0;i<source.Length/size;i++){var b=source.Slice(i*size,size);target[i*stride+channel]=format switch{SampleEncoding.Float32=>BinaryPrimitives.ReadSingleLittleEndian(b),SampleEncoding.Int16=>BinaryPrimitives.ReadInt16LittleEndian(b)/32768f,SampleEncoding.Int24=>(b[0]|b[1]<<8|(sbyte)b[2]<<16)/8388608f,SampleEncoding.Int32=>(float)(BinaryPrimitives.ReadInt32LittleEndian(b)/2147483648d),_=>throw new NotSupportedException()};}
 }
}
