package com.kolbomusic.video;

import android.content.Context;
import android.graphics.Bitmap;
import android.graphics.BitmapFactory;
import android.net.Uri;

import com.google.android.gms.tasks.Tasks;
import com.google.mlkit.vision.common.InputImage;
import com.google.mlkit.vision.face.Face;
import com.google.mlkit.vision.face.FaceDetection;
import com.google.mlkit.vision.face.FaceDetector;
import com.google.mlkit.vision.face.FaceDetectorOptions;

import java.io.IOException;
import java.io.InputStream;
import java.util.List;
import java.util.concurrent.TimeUnit;

/**
 * Local source suitability check before any public-GPU upload. Never uploads
 * images. Face ratio estimates whether image is a close-up, not full-body
 * pose validation. Abstain on uncertainty, do not reconstruct missing limbs.
 */
public final class V5SourceAudit {
    private V5SourceAudit(){}
    public static final class Result {
        public final String level;
        public final String explanation;
        public final float largestFaceRatio;
        public final int width,height;
        Result(String l,String why,float f,int w,int h){
            level=l;explanation=why;largestFaceRatio=f;width=w;height=h;
        }
        public boolean safeToAttempt(){return !"BLOCK".equals(level);}
    }

    public static Result examine(Context ctx,Uri image,boolean fullBodyAction) throws Exception {
        if(image==null||!"content".equalsIgnoreCase(image.getScheme()))
            throw new IOException("יש לבחור תמונת מקור מהטלפון");
        BitmapFactory.Options opt=new BitmapFactory.Options();
        opt.inJustDecodeBounds=true;
        try(InputStream in=ctx.getContentResolver().openInputStream(image)){
            if(in==null)throw new IOException("התמונה אינה זמינה");
            BitmapFactory.decodeStream(in,null,opt);
        }
        if(opt.outWidth<128||opt.outHeight<128||
           opt.outWidth>12000||opt.outHeight>12000)
            throw new IOException("תמונת המקור קטנה מדי או אינה תקינה");
        opt.inJustDecodeBounds=false;
        int sample=1;
        while(Math.max(opt.outWidth,opt.outHeight)/sample>1000)sample*=2;
        opt.inSampleSize=sample;
        Bitmap img;
        try(InputStream in=ctx.getContentResolver().openInputStream(image)){
            img=BitmapFactory.decodeStream(in,null,opt);
        }
        if(img==null)throw new IOException("פענוח התמונה נכשל");
        float maxFraction=0f;
        boolean detected=false;
        FaceDetector detector=FaceDetection.getClient(
            new FaceDetectorOptions.Builder()
                .setPerformanceMode(FaceDetectorOptions.PERFORMANCE_MODE_FAST)
                .build());
        try{
            List<Face> faces=Tasks.await(
                detector.process(InputImage.fromBitmap(img,0)),15,TimeUnit.SECONDS);
            for(Face face:faces){
                detected=true;
                float a=(float)face.getBoundingBox().width()*face.getBoundingBox().height();
                maxFraction=Math.max(maxFraction,a/(img.getWidth()*img.getHeight()));
            }
        }catch(Exception e){
            // No unsupported claim about body framing after ML inference failure.
            return new Result("UNKNOWN","לא ניתן להעריך באופן אוטומטי את התאמת התמונה לסצנת פעולה.",0,
                              opt.outWidth,opt.outHeight);
        }finally{detector.close();img.recycle();}
        if(fullBodyAction && maxFraction>0.20f)
            return new Result("WARNING","זוהה תקריב פנים: המנוע עלול להתקשות "+
                "ליצור תנועת גוף מלא. תבוצע הפקה רק לאחר אישור העלאת התמונה, "+
                "והתוצאה תישאר לא מאומתת עד בדיקה.",maxFraction,opt.outWidth,opt.outHeight);
        if(fullBodyAction && (maxFraction>0.065f || !detected))
            return new Result("WARNING","לסצנת קרב נדרש גוף וסביבה. התמונה אינה מוכיחה שהם "+
                "גלויים; הספק עלול ליצור תקריבי פנים במקום לחימה.",maxFraction,opt.outWidth,opt.outHeight);
        return new Result("OK","התמונה תקינה לעיבוד ראשוני. התאמתה המלאה לסיפור אינה מובטחת.",
            maxFraction,opt.outWidth,opt.outHeight);
    }
}
