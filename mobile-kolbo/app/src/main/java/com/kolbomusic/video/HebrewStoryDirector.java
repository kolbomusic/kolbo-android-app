package com.kolbomusic.video;

import java.text.Normalizer;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import java.util.regex.Pattern;

/**
 * Lightweight, deterministic Hebrew scene planner.
 *
 * Users speak normally: no commands, prompt templates, special punctuation
 * or manual English translation. The engine translates the inferred action
 * separately from photo-editing instructions and anchors essential objects.
 * This planner does not claim to be a large language model or visual verifier.
 */
public final class HebrewStoryDirector {
    private HebrewStoryDirector() {}

    public static final class Plan {
        public final String original;
        public final String actionToTranslate;
        public final String visibleSummary;
        public final String englishConstraints;
        public final boolean cleanPhoto;
        public final int lionCount;
        public final boolean fight;
        public final boolean wins;
        public final boolean complexScene;
        public final boolean wantsSound;
        public final boolean wantsMultiplePhotos;

        Plan(String original,String actionToTranslate,String visibleSummary,
             String englishConstraints,boolean cleanPhoto,int lionCount,boolean fight,
             boolean wins,boolean complexScene,boolean wantsSound,
             boolean wantsMultiplePhotos) {
            this.original=original;
            this.actionToTranslate=actionToTranslate;
            this.visibleSummary=visibleSummary;
            this.englishConstraints=englishConstraints;
            this.cleanPhoto=cleanPhoto;
            this.lionCount=lionCount;
            this.fight=fight;
            this.wins=wins;
            this.complexScene=complexScene;
            this.wantsSound=wantsSound;
            this.wantsMultiplePhotos=wantsMultiplePhotos;
        }

        public String directedPrompt(String englishTranslation) {
            if (englishTranslation==null || englishTranslation.trim().isEmpty())
                throw new IllegalArgumentException("Missing translation");
            StringBuilder p=new StringBuilder(900);
            p.append("Generate real changing video frames; do not just animate facial expressions. ");
            p.append("Reference image: preserve the identity, hair and clothing of the visible person. ");
            p.append("VISUAL ACTION FROM THE USER: ").append(englishTranslation.trim()).append(". ");
            if(lionCount>0) {
                p.append("Required cast: exactly ").append(lionCount)
                 .append(lionCount==1?" distinct lion":" distinct lions")
                 .append(" and the reference human. Show all specified animals visibly in the scene. ");
                p.append("The lions must NOT be merely imagined, mentioned or off camera. ");
            }
            if(fight){
                p.append("The primary event is a physical staged cinematic struggle, not a face close-up. ");
                p.append("Show bodily movement and interaction between the person and the opponents. ");
            }
            if(wins)
                p.append("Resolve the action on screen: the human overpowers the opponents, ")
                 .append("and the opponents yield or retreat. No graphic injury. ");
            if(complexScene)
                p.append("Frame the key physical event; do not substitute talking, grimacing or static posing. ");
            p.append("Keep a stable visual identity and coherent composition. ");
            return p.toString();
        }

        public String supportedLimit() {
            if(wantsSound)return "הסיפור כולל שמע או דיבור. מנוע הווידאו הנוכחי אילם.";
            if(wantsMultiplePhotos)return "הסיפור דורש שילוב תמונות נפרדות. מנוע זה מקבל תמונה אחת.";
            return null;
        }
    }

    private static String canonical(String raw) {
        String n=Normalizer.normalize(raw,Normalizer.Form.NFD)
            .replaceAll("[\\u0591-\\u05C7]","");
        return n.replace('־',' ').replaceAll("\\s+"," ").trim();
    }
    private static boolean any(String normalized,String... variants) {
        for(String term:variants)if(normalized.contains(term))return true;
        return false;
    }
    private static boolean twoLions(String s) {
        if(s.matches(".*(?:\\b2\\b|שני|שתי|זוג|שניים|שתיים)\\s*(?:ה)?(?:אריות|אריה|ארי|ליאונים).*"))
            return true;
        return s.matches(".*(?:אריות|אריה)\\s*(?:2|שני|שתי).*");
    }
    public static Plan understand(String plainHebrew) {
        if(plainHebrew==null||plainHebrew.trim().isEmpty())
            throw new IllegalArgumentException("Empty natural language request");
        String original=plainHebrew.trim();
        String s=canonical(original).toLowerCase(Locale.ROOT);
        boolean cleaning=any(s,"נקה","לנקות","ניקוי","לנקות","תנקה",
            "להסיר רעש","הסר רעשים","להוריד אפקט","בלי אפקט",
            "שחזר את התמונה","להחזיר איכות","לשפר איכות","תיקון התמונה");
        boolean lions=any(s,"אריות","אריה","ארי ");
        int lionsCount=lions?(twoLions(s)?2:1):0;
        boolean combat=any(s,"נלחמ","נלחמת","נלחם","קרב","להילחם","תלחם",
            "מתאבק","נאבק","מתעמת","מרביץ","מכות","היאבקות");
        boolean overcome=any(s,"מכניע","מכניעה","הכניע","הכניעה",
            "מנצח","מנצחת","לנצח","גובר","גוברת","מנצח אותם","גבר עליהם");
        boolean sound=any(s,"שר ","שרה","לשיר","שירה","דיבור",
            "מדבר","מדברת","בקול","קולות","מוזיקה","שומעים","פסקול",
            "צועק","צעקות","משמיע");
        boolean multiple=any(s,"שתי תמונות","שני צילומים","שתי דמויות מהתמונות",
            "2 תמונות","שתי תמונות נפרדות");
        boolean complex=(lionsCount>=2 && combat)|| (combat && overcome);
        String action=original;
        if(cleaning){
            // Separate the initial image-cleaning instruction from the scene.
            // Do not assume an image-to-video model can restore damaged pixels.
            int boundary=-1;int boundaryLength=0;
            String[] temporal={"ואז","אחר כך","לאחר מכן","אחרי זה","בסיום הניקוי",
                               "לאחר הניקוי","ורק אז","ואחרי זה"};
            for(String token:temporal){
                int index=s.indexOf(token);
                if(index>=0 && (boundary<0||index<boundary)) {
                    boundary=index;boundaryLength=token.length();
                }
            }
            if(boundary>=0 && boundary+boundaryLength<original.length()){
                String remaining=original.substring(boundary+boundaryLength).trim();
                if(remaining.length()>=8)action=remaining;
            }
        }
        List<String> beats=new ArrayList<>();
        if(cleaning)beats.add("ניקוי בסיסי של תמונת המקור לפני הפקה");
        if(combat&&lionsCount>0)
            beats.add("סצנת קרב עם "+(lionsCount==2?"שני אריות":"אריה"));
        else if(combat)beats.add("פעולת קרב");
        else if(lionsCount>0)beats.add("הופעת "+(lionsCount==2?"שני אריות":"אריה"));
        if(overcome)beats.add("הדמות גוברת על היריבים בסוף");
        if(beats.isEmpty())beats.add("הפעולה שתיארת בעברית");
        String summary=String.join(" ← ",beats);
        // Hebrew is RTL: arrow points visually through the sequence.
        String anchors="Do not reinterpret the requested action as facial grimacing. ";
        if(lionsCount==2)anchors+="Two separate lions are mandatory visual subjects. ";
        return new Plan(original,action,summary,anchors,cleaning,lionsCount,
                        combat,overcome,complex,sound,multiple);
    }
}
