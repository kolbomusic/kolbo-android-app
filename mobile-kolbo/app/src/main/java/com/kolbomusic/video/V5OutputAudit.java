package com.kolbomusic.video;

import android.graphics.Bitmap;
import android.media.MediaMetadataRetriever;
import com.google.android.gms.tasks.Tasks;
import com.google.mlkit.vision.common.InputImage;
import com.google.mlkit.vision.label.ImageLabel;
import com.google.mlkit.vision.label.ImageLabeling;
import com.google.mlkit.vision.label.ImageLabeler;
import com.google.mlkit.vision.label.defaults.ImageLabelerOptions;

import java.io.File;
import java.util.HashSet;
import java.util.List;
import java.util.Locale;
import java.util.Set;
import java.util.concurrent.TimeUnit;

/**
 * V5 after-render evidence. Duration and frame changes are objective local QA.
 * General image labels are WEAK presence clues; they never verify the number
 * of lions, physical combat, victory, identity or correct causal sequence.
 * Requires no remote calls. Truthful status is UNVERIFIED, not SUCCESS.
 */
public final class V5OutputAudit {
    private V5OutputAudit(){}
    public static final class Report {
        public final boolean playable,shorterThanRequested,visibleMotion,lionLabelSeen;
        public final double actualSeconds;
        public final boolean complexStory,semanticVerified;
        public final int sampledFrames;
        public final String message;
        Report(boolean p,boolean shortVideo,boolean motion,boolean lion,
               double sec,boolean complex,int samples,String text){
            playable=p;shorterThanRequested=shortVideo;visibleMotion=motion;
            lionLabelSeen=lion;actualSeconds=sec;
            complexStory=complex;semanticVerified=false;
            sampledFrames=samples;message=text;
        }
        public boolean hasHardFailure(){return !playable||!visibleMotion||shorterThanRequested;}
    }

    private static double change(Bitmap a,Bitmap b){
        Bitmap first=Bitmap.createScaledBitmap(a,48,48,true);
        Bitmap second=Bitmap.createScaledBitmap(b,48,48,true);
        int[] x=new int[48*48],y=new int[48*48];
        first.getPixels(x,0,48,0,0,48,48);
        second.getPixels(y,0,48,0,0,48,48);
        double sum=0;
        for(int i=0;i<x.length;i++){
            int v1=((x[i]>>16)&255)*54+((x[i]>>8)&255)*183+(x[i]&255)*19;
            int v2=((y[i]>>16)&255)*54+((y[i]>>8)&255)*183+(y[i]&255)*19;
            sum+=Math.abs(v1-v2)/256.0;
        }
        first.recycle();second.recycle();
        return sum/x.length;
    }

    public static Report check(File file,int requestedSeconds,boolean complex) {
        if(file==null||!file.isFile()||file.length()<4000)
            return new Report(false,true,false,false,0,complex,0,"קובץ הווידאו חסר או פגום.");
        MediaMetadataRetriever r=new MediaMetadataRetriever();
        double seconds=0;
        boolean moving=false, lionEvidence=false;
        int samples=0;
        try{
            r.setDataSource(file.getAbsolutePath());
            String d=r.extractMetadata(MediaMetadataRetriever.METADATA_KEY_DURATION);
            seconds=d==null?0:Long.parseLong(d)/1000.0;
            if(!Double.isFinite(seconds)||seconds<0.6||seconds>20)
                return new Report(false,true,false,false,seconds,complex,0,"משך הווידאו אינו תקין.");
            Bitmap previous=null;
            ImageLabeler labeler=ImageLabeling.getClient(
                new ImageLabelerOptions.Builder().setConfidenceThreshold(0.65f).build());
            try{
                // Respect battery/memory: only four reduced temporal samples.
                for(double fraction:new double[]{0.08,0.34,0.63,0.9}){
                    Bitmap raw=r.getFrameAtTime((long)(seconds*fraction*1_000_000.0),
                                               MediaMetadataRetriever.OPTION_CLOSEST_SYNC);
                    if(raw==null)continue;
                    Bitmap bitmap=Bitmap.createScaledBitmap(raw,224,224,true);
                    raw.recycle();
                    samples++;
                    if(previous!=null && change(previous,bitmap)>=3.2)moving=true;
                    try{
                        List<ImageLabel> labels=Tasks.await(
                            labeler.process(InputImage.fromBitmap(bitmap,0)),
                            12,TimeUnit.SECONDS);
                        for(ImageLabel label:labels){
                            String name=label.getText().toLowerCase(Locale.ROOT);
                            if(name.contains("lion"))lionEvidence=true;
                        }
                    }catch(Exception ignored){
                        // Weak optional label evidence unavailable, not failure.
                    }
                    if(previous!=null)previous.recycle();
                    previous=bitmap;
                }
                if(previous!=null)previous.recycle();
            }finally{labeler.close();}
            boolean cut=seconds+0.35<requestedSeconds;
            StringBuilder text=new StringBuilder();
            text.append(String.format(Locale.ROOT,"ביקשת %d שניות, התקבלו %.2f שניות. ",
                      requestedSeconds,seconds));
            if(cut)text.append("משך קצר מהמבוקש — התוצאה חלקית. ");
            if(!moving)text.append("לא אומתה תנועה בין פריימים; תוצאת הווידאו חשודה. ");
            if(complex){
                text.append(lionEvidence?"זוהה רמז חזותי חלש לאריה. ":"לא אומתה נוכחות אריות. ");
                text.append("אי אפשר לאמת מקומית שמופיעים שני אריות, קרב, ניצחון או היעדר ליקוק. ");
                text.append("לכן הסיפור לא סומן כבוצע; נדרשת בחינה חזותית של המשתמש.");
            } else {
                text.append("התנועה והמשך נבדקו; משמעות הפעולה לא אומתה.");
            }
            return new Report(true,cut,moving,lionEvidence,seconds,complex,samples,text.toString());
        }catch(Exception ex){
            return new Report(false,true,false,false,seconds,complex,samples,
                "לא ניתן לבדוק את פריימי הווידאו. לא סומן כהפקה מוצלחת.");
        }finally{
            try{r.release();}catch(Exception ignored){}
        }
    }
}
