package com.kolbo.videostudio;

import android.graphics.Bitmap;
import android.media.MediaExtractor;
import android.media.MediaFormat;
import android.media.MediaMetadataRetriever;
import android.graphics.Rect;
import android.net.Uri;
import com.google.android.gms.tasks.Tasks;
import com.google.mlkit.vision.common.InputImage;
import com.google.mlkit.vision.face.Face;
import com.google.mlkit.vision.face.FaceDetection;
import com.google.mlkit.vision.face.FaceDetector;
import com.google.mlkit.vision.face.FaceDetectorOptions;
import java.io.File;
import java.util.List;
import java.util.concurrent.TimeUnit;

/**
 * On-device evidence review. Never labels appearance as a verified identity,
 * voice as singing or location as recognized without suitable models.
 * No network, screenshots, or image uploads.
 */
final class VideoEvidenceAudit {
    static final class Result {
        final int requestedSeconds;
        final long actualMs;
        final boolean audioTrack;
        final int sampledFrames;
        final int framesWithTwoMainFaces;
        final boolean faceReviewAvailable;
        final boolean singingRequested;
        Result(int request,long actual,boolean audio,int frames,int two,boolean checked,boolean singing){
            requestedSeconds=request;actualMs=actual;audioTrack=audio;
            sampledFrames=frames;framesWithTwoMainFaces=two;
            faceReviewAvailable=checked;singingRequested=singing;
        }
        String status() {
            if(singingRequested&&!audioTrack)return "נוצר וידאו, אך חסר ערוץ שמע לשירה";
            if(faceReviewAvailable&&framesWithTwoMainFaces==0)return "נוצר וידאו, אבל שתי הדמויות לא אומתו יחד";
            return "הסרטון מוכן לבדיקה";
        }
        String details() {
            StringBuilder b=new StringBuilder();
            b.append("משך: ").append(String.format(java.util.Locale.ROOT,"%.2f",actualMs/1000.0))
             .append(" מתוך ").append(requestedSeconds).append(" שניות.\n");
            b.append(audioTrack?"זוהה ערוץ שמע בקובץ.\n":"לא זוהה ערוץ שמע בקובץ.\n");
            if(faceReviewAvailable){
                b.append("נבדקו ").append(sampledFrames).append(" פריימים; זוהו שתי פנים מרכזיות יחד ב־")
                 .append(framesWithTwoMainFaces).append(" פריימים.\n");
            }else b.append("בדיקת נוכחות הפנים לא הושלמה.\n");
            b.append("לא אומתה זהות הפנים מול תמונות המקור. ");
            b.append("לא אומתו התאמה לסיפור, לבמה, למקום, למילים או לפעולות.\n");
            if(singingRequested)b.append("קיום ערוץ שמע אינו מוכיח שיש שירה, סנכרון שפתיים או שפה נכונה.\n");
            b.append("לא בוצע אימות זהות ביומטרי; זהו דוח ראיות חלקי בלבד.");
            return b.toString();
        }
    }
    private VideoEvidenceAudit() {}

    private static boolean hasAudio(File video) {
        MediaExtractor extractor=new MediaExtractor();
        try {
            extractor.setDataSource(video.getAbsolutePath());
            for(int i=0;i<extractor.getTrackCount();i++){
                MediaFormat fmt=extractor.getTrackFormat(i);
                String mime=fmt.getString(MediaFormat.KEY_MIME);
                if(mime!=null&&mime.startsWith("audio/"))return true;
            }
        }catch(Exception ignored){}finally{try{extractor.release();}catch(Exception ignored){}}
        return false;
    }
    private static int largeFaces(Bitmap bitmap,FaceDetector detector) throws Exception {
        List<Face> faces=Tasks.await(detector.process(InputImage.fromBitmap(bitmap,0)),15,TimeUnit.SECONDS);
        double screen=(double)bitmap.getWidth()*bitmap.getHeight();
        int n=0;
        for(Face face:faces){
            Rect r=face.getBoundingBox();
            if((double)Math.max(0,r.width())*Math.max(0,r.height())>=screen*0.004) n++;
        }
        return n;
    }
    static Result inspect(File video,int requestedSeconds,boolean twoSubjects,boolean singing)
            throws Exception {
        long actual=OutputLengthGate.duration(video);
        boolean audio=hasAudio(video);
        if(!twoSubjects)return new Result(requestedSeconds,actual,audio,0,0,false,singing);
        MediaMetadataRetriever retriever=new MediaMetadataRetriever();
        FaceDetector detector=FaceDetection.getClient(new FaceDetectorOptions.Builder()
            .setPerformanceMode(FaceDetectorOptions.PERFORMANCE_MODE_FAST)
            .setMinFaceSize(0.035f).build());
        int tested=0,two=0;
        try {
            retriever.setDataSource(video.getAbsolutePath());
            long[] times={150,actual/4,actual/2,3*actual/4,Math.max(100,actual-250)};
            for(long ms:times){
                Bitmap frame=null;
                try {
                    frame=retriever.getFrameAtTime(Math.max(0,ms)*1000L,
                        MediaMetadataRetriever.OPTION_CLOSEST);
                    if(frame==null)continue;
                    int count=largeFaces(frame,detector);
                    tested++;
                    if(count>=2)two++;
                }catch(Exception sampleError){
                    // One unreadable frame must not fabricate a negative identity verdict.
                }finally{if(frame!=null)frame.recycle();}
            }
        }finally{detector.close();retriever.release();}
        return new Result(requestedSeconds,actual,audio,tested,two,tested>0,singing);
    }
}
