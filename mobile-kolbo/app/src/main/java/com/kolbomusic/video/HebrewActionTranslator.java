package com.kolbomusic.video;

import android.content.Context;

import com.google.android.gms.tasks.Tasks;
import com.google.mlkit.common.model.DownloadConditions;
import com.google.mlkit.nl.translate.TranslateLanguage;
import com.google.mlkit.nl.translate.Translation;
import com.google.mlkit.nl.translate.Translator;
import com.google.mlkit.nl.translate.TranslatorOptions;

import java.io.IOException;
import java.util.concurrent.TimeUnit;

/** Offline-on-device Hebrew-to-English prompt translation for the video model.
 * Only the ML model is downloaded; user text is translated on device.
 */
public final class HebrewActionTranslator {
    private HebrewActionTranslator() {}

    public static boolean containsHebrew(String value){
        if(value==null)return false;
        for(int i=0;i<value.length();i++){
            char c=value.charAt(i);
            if(c>=0x0590 && c<=0x05ff)return true;
        }
        return false;
    }

    public static String translate(String original, WanNativeClient.Progress progress)
        throws Exception {
        if(original==null || original.trim().length()<2)
            throw new IOException("ההנחיה קצרה מדי");
        if(!containsHebrew(original))return original;
        TranslatorOptions options = new TranslatorOptions.Builder()
            .setSourceLanguage(TranslateLanguage.HEBREW)
            .setTargetLanguage(TranslateLanguage.ENGLISH)
            .build();
        Translator translator=Translation.getClient(options);
        try {
            progress.status("מכין תרגום עברית־אנגלית מקומי. בפעם הראשונה ייתכן שתידרש הורדת מודל של כ־30MB…");
            Tasks.await(translator.downloadModelIfNeeded(
                new DownloadConditions.Builder().build()),150,TimeUnit.SECONDS);
            progress.status("מתרגם את הפעולות שתיארת, ללא שליחת הטקסט לשרת תרגום…");
            String translated=Tasks.await(translator.translate(original),40,TimeUnit.SECONDS);
            if(translated==null || translated.trim().length()<9)
                throw new IOException("לא ניתן היה לתרגם את ההוראות במידה מספקת");
            return translated.trim();
        }catch(Exception e){
            throw new IOException("לא ניתן לתרגם את ההנחיה כעת. "+
                "לא נשלחה תמונה ולא הוזמנה הפקה; בדוק חיבור לרשת ונסה שוב.",e);
        }finally{translator.close();}
    }
}
