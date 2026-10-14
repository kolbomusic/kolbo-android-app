package com.kolbomusic.video;

import java.io.IOException;

/**
 * Zero-neural fallback only. No ML Kit, tokenizer or model on Android.
 *
 * This DOES NOT replace a server-side LLM for arbitrary Hebrew instructions.
 * It preserves recognized entities/actions for a basic fallback when the
 * remote AI model is not yet deployed, and retains original text as context.
 */
public final class HebrewActionTranslator {
    private HebrewActionTranslator(){}
    public static boolean containsHebrew(String input){
        if(input==null)return false;
        for(int i=0;i<input.length();i++)
            if(input.charAt(i)>=0x0590&&input.charAt(i)<=0x05FF)return true;
        return false;
    }
    public static String translate(String original,WanNativeClient.Progress progress)
        throws IOException {
        if(original==null||original.trim().length()<2)
            throw new IOException("יש לכתוב מה תרצה שיקרה בסרטון");
        if(!containsHebrew(original))return original.trim();
        HebrewIntentBrain.Scene scene=HebrewIntentBrain.interpret(original.trim());
        StringBuilder output=new StringBuilder(1100);
        output.append("Video scene featuring the reference person. ");
        if(!scene.cast.isEmpty()){
            output.append("Visible subjects: ");
            for(HebrewIntentBrain.Cast cast:scene.cast) {
                if(cast.count>0)output.append("exactly ").append(cast.count).append(' ');
                output.append(cast.english).append("; ");
            }
        }
        if(!scene.verbsEnglish.isEmpty()){
            output.append("Physical events in story order: ");
            for(String verb:scene.verbsEnglish)output.append(verb).append("; ");
        }else{
            output.append("Do not invent an action when the scene is unclear. ");
        }
        output.append("Original user story in Hebrew for detail retention: ");
        output.append(original.trim());
        progress.status("הוכן תיאור בסיסי, ללא הרצת מודל בטלפון. "+
            "תכנון חופשי מתקדם יתאפשר אחרי חיבור שרת AI.");
        return output.toString();
    }
}
