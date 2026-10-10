package com.kolbo.videostudio;

import java.util.Locale;

/** Explicit provider status without quota evasion or silent fallback. */
public final class ProviderFailure {
    private ProviderFailure() {}
    public enum Kind { QUOTA, BUSY, AUTH, NETWORK, OTHER }
    public static Kind classify(String detail) {
        String t=detail==null?"":detail.toLowerCase(Locale.ROOT);
        if(t.contains("429")||t.contains("quota")||t.contains("exhaust")||
           t.contains("rate limit")||t.contains("rate_limit")||
           t.contains("zero gpu quota")||t.contains("zerogpu quota")||
           t.contains("credit")||t.contains("usage limit")||
           t.contains("gpu limit")||t.contains("gpu quota")||
           t.contains("max duration")||t.contains("limit reached"))
            return Kind.QUOTA;
        if(t.contains("503")||t.contains("502")||t.contains("504")||
           t.contains("queue")||t.contains("overload")||
           t.contains("capacity")||t.contains("temporarily unavailable")||
           t.contains("busy")||t.contains("space is sleeping"))
            return Kind.BUSY;
        if(t.contains("401")||t.contains("403")||t.contains("unauthoriz")||
           t.contains("forbidden")||t.contains("permission"))
            return Kind.AUTH;
        if(t.contains("timeout")||t.contains("timed out")||t.contains("reset")||
           t.contains("unknownhost")||t.contains("unreachable")||
           t.contains("connection")||t.contains("network"))
            return Kind.NETWORK;
        return Kind.OTHER;
    }
    public static String explain(Exception failure) {
        String error=failure==null?"":String.valueOf(failure.getMessage());
        Kind kind=classify(error);
        switch(kind){
            case QUOTA:
                return "שירות היצירה הגיע למכסה או למגבלת שימוש. אין דרך חוקית להבטיח ממנו יצירה בלתי מוגבלת. "
                    +"לא נעשה ניסיון לעקוף את המכסה או לעבור למנוע שאינו שומר שתי דמויות. "
                    +"הפרויקט נשאר במכשיר וניתן לנסות שוב כאשר הספק מתפנה.";
            case BUSY:
                return "שרת הווידאו הציבורי עמוס או זמנית לא זמין. לא נשלחה בקשת יצירה נוספת אוטומטית. "
                    +"נסה שוב מאוחר יותר, או השתמש בספק עצמאי התומך בשתי תמונות.";
            case AUTH:
                return "השירות דורש הרשאה שאינה זמינה באפליקציה החינמית. לא נעקוף הרשאות.";
            case NETWORK:
                return "לא ניתן להשלים את החיבור לשירות הווידאו. בדוק חיבור ונסה שנית.";
            default:
                return "שירות הווידאו החזיר שגיאה: "+error;
        }
    }
}
