namespace Kolbo.Live.Core;
public sealed record Routing(int Dry, int WetLeft, int WetRight, int SendLeft, int SendRight, int MasterLeft, int MasterRight, int SampleRate) {
 public string[] Validate(int inputs,int outputs,IReadOnlyCollection<int> rates,bool wetOnlyConfirmed) {
  List<string> errors=[];
  int[] ins=[Dry,WetLeft,WetRight],outs=[SendLeft,SendRight,MasterLeft,MasterRight];
  if(ins.Any(c=>c<0||c>=inputs))errors.Add("ערוץ כניסה מחוץ לטווח");
  if(outs.Any(c=>c<0||c>=outputs))errors.Add("ערוץ יציאה מחוץ לטווח");
  if(ins.Distinct().Count()!=3)errors.Add("הכניסה היבשה והחזרת האפקט חייבות להיות ערוצים נפרדים");
  if(outs.Distinct().Count()!=4)errors.Add("שליחת האפקט ויציאת המאסטר חייבות להיות נפרדות");
  if(!rates.Contains(SampleRate))errors.Add("קצב הדגימה לא אושר על ידי הדרייבר");
  if(!wetOnlyConfirmed)errors.Add("נדרש אישור שההחזרה היא אפקט בלבד ושאין ניטור כפול");
  return errors.ToArray();
 }
}
public sealed record Gains(float Dry = 1, float Wet = .35f, float Backing = .6f, float Send = .5f);
public static class Mixer {
 public static int Process(ReadOnlySpan<float> dry,ReadOnlySpan<float> wet,ReadOnlySpan<float> backing,Span<float> master,Span<float> send,Gains gains) {
  int frames=dry.Length;
  if(wet.Length!=frames*2||backing.Length!=frames*2||master.Length!=frames*2||send.Length!=frames*2)throw new ArgumentException("Audio block sizes differ");
  int overloads=0;
  for(int i=0;i<frames;i++) {
   float d=Finite(dry[i])*gains.Dry,s=Finite(dry[i])*gains.Send;
   master[i*2]=d+Finite(wet[i*2])*gains.Wet+Finite(backing[i*2])*gains.Backing;
   master[i*2+1]=d+Finite(wet[i*2+1])*gains.Wet+Finite(backing[i*2+1])*gains.Backing;
   if(!float.IsFinite(dry[i])||!float.IsFinite(wet[i*2])||!float.IsFinite(wet[i*2+1])||Math.Abs(master[i*2])>1||Math.Abs(master[i*2+1])>1||Math.Abs(s)>1)overloads++;
   master[i*2]=Math.Clamp(Finite(master[i*2]),-1,1);master[i*2+1]=Math.Clamp(Finite(master[i*2+1]),-1,1);
   send[i*2]=send[i*2+1]=Math.Clamp(Finite(s),-1,1);
  }
  return overloads;
 }
 static float Finite(float value)=>float.IsFinite(value)?value:0;
}
