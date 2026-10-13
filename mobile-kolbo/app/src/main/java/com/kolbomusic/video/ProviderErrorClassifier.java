package com.kolbomusic.video;

import java.util.Locale;

/**
 * Safe Hebrew explanations for Gradio/ZeroGPU error event data.
 * Never display raw server HTML, traceback, email, tokens or user input.
 * Parsing an error event never triggers a retry or changes supplier quota.
 */
public final class ProviderErrorClassifier {
    private ProviderErrorClassifier() {}

    public static final class Result {
        public final String code;
        public final String hebrew;
        public final boolean finalForJob;
        Result(String code, String hebrew) {
            this.code = code;
            this.hebrew = hebrew;
            this.finalForJob = true;
        }
    }

    public static Result classify(String data) {
        String lower = data == null ? "" : data.toLowerCase(Locale.ROOT);
        if (has(lower, "quota","exceeded","out of gpu time","remaining gpu",
                     "time limit","usage limit","daily limit","zerogpu quota")) {
            return new Result("GPU_QUOTA", "מכסת ה-GPU החינמית של הספק נגמרה או אינה מספיקה לבקשה. "
              + "אפשר לנסות ביום אחר לאחר חידוש המכסה, אך אין הפקה מובטחת.");
        }
        if (has(lower,"too busy","queue is full","queue full","queue limit",
                     "overloaded","high demand","capacity","resource unavailable",
                     "no gpu available","gpu unavailable")) {
            return new Result("PROVIDER_BUSY", "שרת הווידאו החיצוני עמוס או שאין כעת GPU פנוי. "
              + "אפשר לנסות מאוחר יותר בבקשה חדשה שתבחר בעצמך.");
        }
        if (has(lower,"login","unauthorized","not authenticated","authentication",
                     "access denied","permission","requires authorization","not allowed")) {
            return new Result("AUTH_REQUIRED", "הספק דורש התחברות או הרשאת גישה. "
              + "לא נעקוף דרישת הרשאה או מכסת שימוש.");
        }
        if (has(lower,"out of memory","cuda error","memory allocation",
                     "gpu memory","oom")) {
            return new Result("GPU_MEMORY", "ההפקה נכשלה עקב מגבלת זיכרון GPU בצד הספק.");
        }
        if (has(lower,"invalid","validation error","invalid duration",
                     "unsupported","not supported","valueerror")) {
            return new Result("PARAMETER_REJECTED", "הספק דחה את פרמטרי היצירה או את התמונה. "
              + "המנוע הציבורי עשוי לשנות דרישות ללא התראה.");
        }
        return new Result("PROVIDER_REJECTED", "שרת ה-AI עצר את המשימה. הספק לא סיפק אבחנה "
          + "שאפשר להציג בבטחה; לא נוצר סרטון, ולא בוצע ניסיון נוסף.");
    }

    private static boolean has(String text,String... needles){
        for(String n:needles) if(text.contains(n)) return true;
        return false;
    }
}
