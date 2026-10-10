package com.kolbo.videostudio;

import java.util.Locale;
import java.util.regex.Pattern;

/**
 * Request-scoped scene intent from explicit Hebrew / English cues.
 * Never adds an unrelated scene category or a global list of forbidden words.
 * Not a general natural-language or visual understanding model.
 */
public final class SceneIntentContract {
    public enum Category { MUSIC_PERFORMANCE, DANCE, VEHICLE_ACTION, GENERAL }
    public final Category category;
    public final boolean caesarea;
    public final boolean mizrahi;
    public final boolean singing;
    public final boolean jointSubjects;
    public final String original;
    private SceneIntentContract(Category category,boolean caesarea,boolean mizrahi,
            boolean singing,boolean joint,String original) {
        this.category=category;this.caesarea=caesarea;this.mizrahi=mizrahi;
        this.singing=singing;this.jointSubjects=joint;this.original=original;
    }
    private static boolean containsAny(String s,String... terms){
        for(String t:terms)if(s.contains(t))return true;
        return false;
    }
    public static SceneIntentContract from(String original) {
        if(original==null) original="";
        String s=original.toLowerCase(Locale.ROOT);
        boolean song=containsAny(s,"שרות","שרים","שר ","שרה","שירה","לשיר",
            "מזמר","דואט","sing","song","vocal","duet");
        boolean concert=containsAny(s,"הופעה","הופעת","הופיע","קונצרט","במה",
            "בימת","קיסריה","אצטדיון","concert","stage","live show","amphitheater");
        boolean dancing=containsAny(s,"ריקוד","רוקד","רוקדת","רוקדים","dance","dancing");
        boolean vehicles=containsAny(s,"ניידת","טנק","רכב","מכונית","משאית",
            "נסיעה","נוסע","נוסעת","police car","tank","truck","vehicle","drives");
        Category cat=(song||concert)&&concert?Category.MUSIC_PERFORMANCE:
            dancing?Category.DANCE:vehicles?Category.VEHICLE_ACTION:Category.GENERAL;
        boolean caesarea=s.contains("קיסריה")||s.contains("caesarea")||s.contains("caesaria");
        boolean mizrahi=containsAny(s,"מזרחי","מזרחית","מזרחיים","mizrah","middle eastern","oriental music");
        boolean joint=containsAny(s,"שתי הדמויות","שניהם","שתיהן","ביחד","יחד",
            "both people","both characters","together","duet");
        return new SceneIntentContract(cat,caesarea,mizrahi,song,joint,original);
    }
    public String sceneSetting() {
        switch(category){
            case MUSIC_PERFORMANCE:
                String stage="SCENE TYPE: live music performance, not a portrait montage. "
                    +"LOCATION AND PROPS: performers on a concert STAGE, stage lighting, microphones, "
                    +"musical instruments and a live audience in the distant background. "
                    +"BACKGROUND audience must not replace the TWO reference performers. ";
                if(caesarea) stage+="VENUE: open-air Caesarea Roman amphitheater concert venue, "
                    +"recognizable historic stone seating. ";
                if(mizrahi) stage+="MUSIC STYLE: Mizrahi / Middle Eastern popular music rhythm and instrumentation. ";
                if(singing) stage+="VISIBLE MAIN ACTION: both requested singers performing with expressive "
                    +"mouth and body movements, rather than merely standing still. ";
                return stage;
            case DANCE:
                return "SCENE TYPE: visible physically performed dance, with full-body movement, "
                    +"natural steps and leg/arm choreography. ";
            case VEHICLE_ACTION:
                return "SCENE TYPE: realistic human interaction with a vehicle if requested. "
                    +"Preserve cause-and-effect order for entering, closing doors and departing. ";
            default:
                return "SCENE TYPE: follow the current user instruction literally. "
                    +"Do not introduce settings, costumes, professions or props not present in THIS request. ";
        }
    }
    public String audioNote() {
        if(category==Category.MUSIC_PERFORMANCE)
            return "Audio note: the AI video service may not provide the requested "
                +"live song, singing voice, lyrics or lip-sync; audio must be audited separately.";
        return "Check any required dialog and sound effects separately from visual frames.";
    }
    public String reviewHebrew(){
        String scene=category==Category.MUSIC_PERFORMANCE?"הופעה מוזיקלית על במה":
            category==Category.DANCE?"ריקוד":
            category==Category.VEHICLE_ACTION?"פעולות סביב רכב":"סצנה לפי ההנחיה";
        return "סוג סצנה: "+scene
            +(caesarea?" | מקום: הופעה בקיסריה":"")
            +(mizrahi?" | סגנון מוזיקה: מזרחי":"")
            +(singing?" | שירה: מבוקשת, אך אינה מובטחת":"")
            +" | התפקידים והתמונות נשמרים במפרט ההנחיה בלבד.";
    }
    public String sourceIntent(String originalPrompt){
        // We do not reconstruct unrelated negative instructions from prior requests.
        return sceneSetting()+"CURRENT REQUEST ONLY: "+originalPrompt+". ";
    }
}
