package com.kolbomusic.video;

import android.content.Context;
import android.graphics.BitmapFactory;
import android.net.Uri;
import java.io.IOException;
import java.io.InputStream;

/** Size/header validation only. No face/pose AI inference on the phone. */
public final class V5SourceAudit {
    private V5SourceAudit(){}
    public static final class Result {
        public final String level,explanation;
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
        BitmapFactory.Options options=new BitmapFactory.Options();
        options.inJustDecodeBounds=true;
        try(InputStream in=ctx.getContentResolver().openInputStream(image)){
            if(in==null)throw new IOException("קובץ התמונה אינו נגיש");
            BitmapFactory.decodeStream(in,null,options);
        }
        if(options.outWidth<128||options.outHeight<128||
            options.outWidth>12000||options.outHeight>12000)
            throw new IOException("התמונה פגומה או אינה במידות נתמכות");
        if(fullBodyAction)
            return new Result("WARNING","נבדק קובץ התמונה. התאמת הפריים לסצנת הפעולה "+
                "תיבדק בעתיד על השרת; לא מורץ זיהוי פנים בטלפון.",
                0,options.outWidth,options.outHeight);
        return new Result("OK","הקובץ תקין, לא הופעל מנוע AI מקומי.",
            0,options.outWidth,options.outHeight);
    }
}
