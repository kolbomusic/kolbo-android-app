package com.kolbomusic.video;

import android.media.MediaMetadataRetriever;
import java.io.File;
import java.util.Locale;

/** Ultra-light MP4 metadata validation; no frame decoding or vision model. */
public final class V5OutputAudit {
    private V5OutputAudit(){}
    public static final class Report {
        public final boolean playable,shorterThanRequested,complexStory,semanticVerified;
        public final double actualSeconds;
        public final String message;
        Report(boolean p,boolean cut,boolean complex,double seconds,String text){
            playable=p;shorterThanRequested=cut;complexStory=complex;
            semanticVerified=false;actualSeconds=seconds;message=text;
        }
        public boolean hasHardFailure(){return !playable||shorterThanRequested;}
    }
    public static Report check(File file,int secondsRequested,boolean complex) {
        if(file==null||!file.isFile()||file.length()<4000)
            return new Report(false,false,complex,0,"לא התקבל קובץ MP4 תקין.");
        MediaMetadataRetriever retriever=new MediaMetadataRetriever();
        try {
            retriever.setDataSource(file.getAbsolutePath());
            String duration=retriever.extractMetadata(MediaMetadataRetriever.METADATA_KEY_DURATION);
            String hasVideo=retriever.extractMetadata(MediaMetadataRetriever.METADATA_KEY_HAS_VIDEO);
            double actual=duration==null?0:Long.parseLong(duration)/1000.0;
            if(actual<0.6||actual>30||!"yes".equalsIgnoreCase(hasVideo))
                return new Report(false,false,complex,actual,
                    "לא הצלחתי לאמת ערוץ וידאו ומשך תקין.");
            boolean shortfall=actual+0.35<secondsRequested;
            String status=String.format(Locale.ROOT,"ביקשת %d שניות, התקבלו %.2f שניות. ",
                secondsRequested,actual);
            if(shortfall)status+="משך התוצאה קצר מהמבוקש. ";
            status+="בדיקת פעולות, אריות, ניצחון ותנועה דורשת מנוע ראייה בצד השרת. "+
                "התוצאה אינה מסומנת כהצלחה סמנטית.";
            return new Report(true,shortfall,complex,actual,status);
        }catch(Exception e){
            return new Report(false,false,complex,0,
                "פענוח מאפייני הסרטון נכשל. הקובץ לא סומן כהצלחה.");
        }finally{try{retriever.release();}catch(Exception ignored){}}
    }
}
