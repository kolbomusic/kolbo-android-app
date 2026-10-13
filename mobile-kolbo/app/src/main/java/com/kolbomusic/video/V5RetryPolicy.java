package com.kolbomusic.video;

/**
 * Pure failure decision logic. Never initiates compute or auto re-submits.
 * Different failure modes have different next actions; the user must choose
 * when to start another (quota-consuming) generation.
 */
public final class V5RetryPolicy {
    private V5RetryPolicy(){}
    public enum Next { WAIT_QUOTA, CHECK_ACCESS, EXPLICIT_OTHER_PROVIDER,
                       CHANGE_REFERENCE, REVISE_STORY, REVIEW_OUTPUT, CHECK_UNKNOWN_JOB }
    public static final class Decision {
        public final Next next;
        public final String guidance;
        public final boolean mayPreferDifferentProvider;
        Decision(Next n,String text,boolean alternate){
            next=n;guidance=text;mayPreferDifferentProvider=alternate;
        }
    }
    public static Decision server(String code){
        if("GPU_QUOTA".equals(code))
            return new Decision(Next.WAIT_QUOTA,
                "מכסת ה־GPU כנראה אינה מספיקה. המתן להתחדשות המכסה; אין טעם לשלוח מיד שוב.",
                false);
        if("AUTH_REQUIRED".equals(code))
            return new Decision(Next.CHECK_ACCESS,
                "הספק דורש הרשאה או התחברות. האפליקציה לא תעקוף אותה.",false);
        if("GPU_MEMORY".equals(code)||"PROVIDER_BUSY".equals(code)||
           "PROVIDER_REJECTED".equals(code))
            return new Decision(Next.EXPLICIT_OTHER_PROVIDER,
                "המנוע נכשל. אפשר לבחור ניסיון חדש במנוע אחר, רק בלחיצה מפורשת שלך.",
                true);
        if("PARAMETER_REJECTED".equals(code))
            return new Decision(Next.REVISE_STORY,
                "המנוע דחה פרמטרים; לא נכון לבצע שוב בלי לאמת את דרישות השירות.",false);
        return new Decision(Next.CHECK_UNKNOWN_JOB,
            "לא ברור אם התקבלה משימה. בדוק אותה לפני שליחת בקשה אחרת.",false);
    }
    public static Decision sourceUnsuitable(){
        return new Decision(Next.CHANGE_REFERENCE,
          "התמונה צפופה מדי לפעולה רחבה. אין מנוע מאומת להשלמת גוף חסר.",false);
    }
    public static Decision semanticUnverified(){
        return new Decision(Next.REVIEW_OUTPUT,
          "תקינות קובץ אינה מוכיחה שהסיפור בוצע. בדוק את הדמויות, הפעולות והסיום.",false);
    }
}
