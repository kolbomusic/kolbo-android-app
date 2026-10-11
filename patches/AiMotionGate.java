package com.kolbo.videostudio;

import android.graphics.Bitmap;
import android.media.MediaMetadataRetriever;
import java.io.File;

/** Real AI video proof: reject static/collage MP4 regardless of metadata.
 * A scene with camera pan may still pass; semantic/identity adherence is NOT
 * automatically verified. Kept separate from the explicit photo editor.
 */
final class AiMotionGate {
    private AiMotionGate(){}
    private static Bitmap reduced(Bitmap frame){
        Bitmap result=Bitmap.createScaledBitmap(frame,48,48,true);
        if(result!=frame)frame.recycle();
        return result;
    }
    static void verify(File file) throws Exception{
        MediaMetadataRetriever tool=new MediaMetadataRetriever();
        Bitmap a=null,b=null,c=null;
        try{
            tool.setDataSource(file.getAbsolutePath());
            String value=tool.extractMetadata(
                MediaMetadataRetriever.METADATA_KEY_DURATION);
            long ms=Long.parseLong(value);
            if(ms<900)throw new Exception("הסרטון קצר מכדי לאמת תנועה");
            a=tool.getFrameAtTime(100000,
                MediaMetadataRetriever.OPTION_CLOSEST_SYNC);
            b=tool.getFrameAtTime((ms/2)*1000L,
                MediaMetadataRetriever.OPTION_CLOSEST);
            c=tool.getFrameAtTime((ms*85/100)*1000L,
                MediaMetadataRetriever.OPTION_CLOSEST);
            if(a==null||b==null||c==null)
                throw new Exception("לא ניתן לפענח פריימים לבדיקה");
            a=reduced(a);b=reduced(b);c=reduced(c);
            double ab=difference(a,b),bc=difference(b,c);
            if(Math.max(ab,bc)<2.2)
                throw new Exception("הסרטון מכיל פריימים כמעט קפואים; לא נוצרה תנועה מספקת");
        }finally{
            if(a!=null&&!a.isRecycled())a.recycle();
            if(b!=null&&!b.isRecycled())b.recycle();
            if(c!=null&&!c.isRecycled())c.recycle();
            tool.release();
        }
    }
    static double difference(Bitmap a,Bitmap b){
        long total=0;
        int count=48*48;
        for(int y=0;y<48;y+=2){
            for(int x=0;x<48;x+=2){
                int c=a.getPixel(x,y),d=b.getPixel(x,y);
                total+=Math.abs(((c>>16)&255)-((d>>16)&255));
                total+=Math.abs(((c>>8)&255)-((d>>8)&255));
                total+=Math.abs((c&255)-(d&255));
            }
        }
        return total/(3.0*(count/4));
    }
}
