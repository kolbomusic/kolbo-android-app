package com.kolbo.videostudio;

import android.media.MediaMetadataRetriever;
import java.io.File;

/** Fail-closed on missing or truncated output, including audio-finished MP4. */
final class OutputLengthGate {
    private OutputLengthGate(){}
    static long duration(File f) throws Exception {
        if(f==null||!f.isFile()||f.length()<12000)
            throw new Exception("קובץ הווידאו אינו תקין");
        MediaMetadataRetriever m=new MediaMetadataRetriever();
        try {
            m.setDataSource(f.getAbsolutePath());
            String raw=m.extractMetadata(MediaMetadataRetriever.METADATA_KEY_DURATION);
            if(raw==null)throw new Exception("לא ניתן לאמת את משך הסרטון");
            long duration=Long.parseLong(raw);
            if(duration<=0)throw new Exception("משך הסרטון אינו תקין");
            return duration;
        }finally{m.release();}
    }
    static void verify(File f,int requestedSeconds) throws Exception {
        if(requestedSeconds<1||requestedSeconds>60)
            throw new Exception("משך הסרטון המבוקש אינו תקין");
        long actual=duration(f), expected=requestedSeconds*1000L;
        // A 500ms tolerance covers a small final-frame offset, not missing seconds.
        if(Math.abs(actual-expected)>500L)
            throw new Exception("הספק החזיר "+(actual/1000.0)+
                " שניות במקום "+requestedSeconds+
                ". התוצאה לא אושרה. לא נציג קובץ חלקי כאילו הושלם.");
    }
}
