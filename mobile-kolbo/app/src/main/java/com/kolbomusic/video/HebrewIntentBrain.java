package com.kolbomusic.video;

import java.text.Normalizer;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;

/**
 * Original hand-authored Hebrew action/scene lexicon, not a third-party scraped
 * dictionary. No licence-restricted Hebrew corpus, no private text upload,
 * no paid API and no large model loaded into Android memory.
 *
 * Purpose: augment the existing on-device ML Kit Hebrew->English translation
 * with explicit subjects, quantities, action ordering and scene constraints.
 * This is an explainable finite lexicon, NOT a universal Hebrew LLM.
 */
public final class HebrewIntentBrain {
    private HebrewIntentBrain(){}

    private static final class Term {
        final String en,he;
        final String[] forms;
        Term(String english,String hebrew,String... forms) {
            en=english;he=hebrew;this.forms=forms;
        }
    }
    private static final class Hit {
        final Term term;final int index;
        Hit(Term t,int i){term=t;index=i;}
    }
    private static final List<Term> ENTITIES=new ArrayList<>();
    private static final List<Term> ACTIONS=new ArrayList<>();

    static {
        entity("lion","אריה","אריה","אריות","ארי","ארייות");
        entity("dog","כלב","כלב","כלבים","כלבה","כלבות");
        entity("cat","חתול","חתול","חתולים","חתולה","חתולות");
        entity("horse","סוס","סוס","סוסים","סוסה","סוסות");
        entity("tiger","טיגריס","טיגריס","טיגריסים","נמר","נמרים");
        entity("elephant","פיל","פיל","פילים");
        entity("bird","ציפור","ציפור","ציפורים");
        entity("eagle","נשר","נשר","נשרים");
        entity("bear","דוב","דוב","דובים");
        entity("wolf","זאב","זאב","זאבים");
        entity("snake","נחש","נחש","נחשים");
        entity("dolphin","דולפין","דולפין","דולפינים");
        entity("fish","דג","דג","דגים");
        entity("human","אדם","אדם","אנשים","איש","אישה","אשה","אישיות");
        entity("boy","ילד","ילד","ילדים");
        entity("girl","ילדה","ילדה","ילדות");
        entity("baby","תינוק","תינוק","תינוקת","תינוקות");
        entity("robot","רובוט","רובוט","רובוטים");
        entity("soldier","חייל","חייל","חיילים","חיילת");
        entity("person","דמות","דמות","דמויות");
        entity("car","מכונית","מכונית","מכוניות","אוטו","רכב","רכבים");
        entity("truck","משאית","משאית","משאיות");
        entity("motorcycle","אופנוע","אופנוע","אופנועים");
        entity("bicycle","אופניים","אופניים","אופני");
        entity("boat","סירה","סירה","סירות","ספינה","ספינות");
        entity("airplane","מטוס","מטוס","מטוסים");
        entity("train","רכבת","רכבת","רכבות");
        entity("ball","כדור","כדור","כדורים");
        entity("guitar","גיטרה","גיטרה","גיטרות");
        entity("piano","פסנתר","פסנתר","פסנתרים");
        entity("drum","תוף","תוף","תופים");
        entity("microphone","מיקרופון","מיקרופון","מיקרופונים");
        entity("chair","כיסא","כיסא","כיסאות","כסא","כסאות");
        entity("table","שולחן","שולחן","שולחנות");
        entity("tree","עץ","עץ","עצים");
        entity("house","בית","בית","בתים");
        entity("door","דלת","דלת","דלתות");
        entity("water","מים","מים","אגם","ים","בריכה");
        entity("fire","אש","אש","להבות","להבה");
        entity("mountain","הר","הר","הרים","הררית");
        entity("sword","חרב","חרב","חרבות");
        entity("cake","עוגה","עוגה","עוגות");
        entity("food","אוכל","אוכל","מאכל","ארוחה");
        action("fight","קרב","נלחם","נלחמת","נלחמים","להילחם","לחימה","קרב","מלחמה","נאבק","נאבקת","להיאבק","מתאבק","מתאבקת","תילחם","יילחם","להלחם","להיאבק");
        action("defeat","ניצחון","מכניע","מכניעה","מכניעים","מנצח","מנצחת","מנצחים","מנצחות","לנצח","הכניע","הכניעה","גובר","גוברת","מביס","מביסה","תכניע","יכניע","תנצח","ינצח");
        action("run","ריצה","רץ","רצה","רצים","לרוץ","ריצה","רצות","ורץ","ורצה","ירוץ","תרוץ");
        action("walk","הליכה","הולך","הולכת","הולכים","צועד","צועדת","צועדים","ללכת","הליכה");
        action("dance","ריקוד","רוקד","רוקדת","רוקדים","רוקדות","לרקוד","ריקוד","תרקוד");
        action("jump","קפיצה","קופץ","קופצת","קופצים","לקפוץ","קפיצה","קפצו","יקפוץ","תקפוץ");
        action("fly","תעופה","עף","עפה","עפים","לעוף","מתעופף","ממריא","ממריאה","ממריאים");
        action("swim","שחייה","שוחה","שוחים","שוחות","לשחות","שחיה","צולל","צוללת");
        action("fall","נפילה","נופל","נופלת","נופלים","נפילה","נפל","נפלה","תיפול","ייפול");
        action("climb","טיפוס","מטפס","מטפסת","מטפסים","לטפס","טיפוס","מטפסות");
        action("chase","מרדף","רודף","רודפת","רודפים","רודפות","רודף אחרי","רודפת אחרי","מרדף","לרדוף");
        action("ride","רכיבה","רוכב","רוכבת","רוכבים","רוכבות","רכיבה","לרכוב");
        action("drive","נהיגה","נוהג","נוהגת","נוהגים","לנהוג","נוסע","נוסעת","נוסעים");
        action("hug","חיבוק","מחבק","מחבקת","מחבקים","חיבוק","מתחבק","מתחבקים");
        action("wave","נפנוף","מנופף","מנופפת","מנופפים","מנופפות","מניף יד","מניפה יד");
        action("smile","חיוך","מחייך","מחייכת","מחייכים","מחייכות","לחייך","חיוך");
        action("laugh","צחוק","צוחק","צוחקת","צוחקים","צוחקות","צחוק");
        action("cry","בכי","בוכה","בוכים","בוכות","לבכות","בכי");
        action("play instrument","נגינה","מנגן","מנגנת","מנגנים","מנגנות","לנגן","נגינה");
        action("sing","שירה","שר","שרה","שרים","שרות","לשיר","שירה");
        action("speak","דיבור","מדבר","מדברת","מדברים","אומר","אומרת","להגיד","משוחח","משוחחת");
        action("sit down","ישיבה","יושב","יושבת","יושבים","יושבות","מתיישב","מתיישבת","לשבת");
        action("stand up","עמידה","עומד","עומדת","עומדים","עומדות","קם","קמה","לקום");
        action("eat","אכילה","אוכל","אוכלת","אוכלים","אוכלות","לאכול","נוגס");
        action("drink","שתייה","שותה","שותים","שותות","לשתות","שתיה","לוגם");
        action("cook","בישול","מבשל","מבשלת","מבשלים","לבשל","בישול","אופה","אופה");
        action("open","פתיחה","פותח","פותחת","פותחים","לפתוח","פתיחה");
        action("close","סגירה","סוגר","סוגרת","סוגרים","לסגור","סגירה");
        action("throw","זריקה","זורק","זורקת","זורקים","לזרוק","משליך","משליכה");
        action("catch","תפיסה","תופס","תופסת","תופסים","לתפוס","לוכד","לוכדת");
        action("roll","גלגול","מתגלגל","מתגלגלת","מתגלגלים","גלגול","לגלגל");
        action("transform","שינוי צורה","הופך","הופכת","להפוך","משתנה","משתנים","הופכים","משנה צורה");
        action("approach","התקרבות","מתקרב","מתקרבת","מתקרבים","להתקרב");
        action("retreat","נסיגה","נסוג","נסוגה","נסוגים","בורח","בורחת","בורחים","נמלט");
        action("fight back","התגוננות","מתגונן","מתגוננת","מתחמק","מתחמקת","חוסם");
        action("clean photo","ניקוי תמונה","לנקות תמונה","ניקוי תמונה","לנקות את התמונה");
    }

    private static void entity(String en,String he,String... forms){
        ENTITIES.add(new Term(en,he,forms));
    }
    private static void action(String en,String he,String... forms){
        ACTIONS.add(new Term(en,he,forms));
    }

    public static final class Cast {
        public final String english;
        public final String hebrew;
        public final int count;
        Cast(String en,String he,int count){this.english=en;this.hebrew=he;this.count=count;}
    }
    public static final class Scene {
        public final String original;
        public final String actionText;
        public final String summary;
        public final boolean photoCleanup;
        public final boolean soundtrack;
        public final boolean multiPhoto;
        public final boolean complex;
        public final List<Cast> cast;
        public final List<String> verbsEnglish;
        public final List<String> verbsHebrew;
        public final int understoodSignals;
        Scene(String o,String a,String sum,boolean clean,boolean sound,boolean multi,
              boolean complex,List<Cast> cast,List<String> actions,List<String> labels){
            original=o;actionText=a;summary=sum;photoCleanup=clean;
            soundtrack=sound;multiPhoto=multi;this.complex=complex;
            this.cast=Collections.unmodifiableList(cast);
            verbsEnglish=Collections.unmodifiableList(actions);
            verbsHebrew=Collections.unmodifiableList(labels);
            understoodSignals=cast.size()+actions.size()+(clean?1:0);
        }
        public String prompt(String englishTranslation){
            if(englishTranslation==null||englishTranslation.trim().isEmpty())
                throw new IllegalArgumentException("Missing translated action");
            StringBuilder p=new StringBuilder(1100);
            p.append("Animate the specific events, not merely the subject's facial expression. ");
            p.append("Follow this translated user request faithfully: ")
             .append(englishTranslation.trim()).append(". ");
            if(!cast.isEmpty()){
                p.append("Required visible objects: ");
                for(Cast c:cast){
                    if(c.count>=0)p.append("exactly ").append(c.count).append(' ');
                    p.append(c.english).append("; ");
                }
                p.append("Do not omit required subjects. ");
            }
            if(!verbsEnglish.isEmpty()){
                p.append("Visible event order: ");
                for(String verb:verbsEnglish)p.append(verb).append(" -> ");
                p.append("final state. ");
            }
            p.append("Frame the subjects to show the requested interactions; ");
            p.append("keep reference person identity visually consistent. ");
            p.append("No text overlays, no extra characters, no facial-expression-only shortcut. ");
            return p.toString();
        }
    }
    private static String normalize(String text){
        return Normalizer.normalize(text,Normalizer.Form.NFD)
            .replaceAll("[\\u0591-\\u05C7]","")
            .replace('־',' ')
            .toLowerCase(Locale.ROOT)
            .replaceAll("[^\\p{L}\\p{N}]+"," ")
            .trim();
    }
    private static boolean equivalent(String token,String form){
        if(token.equals(form))return true;
        String[] prefixes={"ו","ה","ב","ל","כ","מ","ש","וה","בה","לה","כה","מה","שה"};
        for(String prefix:prefixes)
            if(token.startsWith(prefix) && token.length()-prefix.length()>=2 &&
               token.substring(prefix.length()).equals(form))return true;
        return false;
    }
    private static int findTerm(String[] words,Term t){
        int best=-1;
        for(String form:t.forms){
            String[] phrase=normalize(form).split(" ");
            for(int i=0;i<=words.length-phrase.length;i++){
                boolean match=true;
                for(int k=0;k<phrase.length;k++){
                    if(!equivalent(words[i+k],phrase[k])){match=false;break;}
                }
                if(match && !negated(words,i) && (best<0||i<best))best=i;
            }
        }
        return best;
    }
    private static boolean negated(String[] words,int at){
        if(at>0 && (words[at-1].equals("לא")||words[at-1].equals("בלי")||
                    words[at-1].equals("ללא")||words[at-1].equals("אל")))return true;
        if(at>1 && (words[at-2].equals("אל")||words[at-2].equals("לא")) &&
           (words[at-1].equals("תוסיף")||words[at-1].equals("להוסיף")||
            words[at-1].equals("להראות")||words[at-1].equals("רוצה")||
            words[at-1].equals("תראה")))return true;
        return false;
    }
    private static int count(String[] words,int index){
        for(int n=Math.max(0,index-3);n<index;n++){
            String w=words[n];
            if(w.equals("2")||equivalent(w,"שני")||equivalent(w,"שתי")||
               equivalent(w,"שניים")||equivalent(w,"שתיים")||equivalent(w,"זוג"))return 2;
            if(w.equals("3")||equivalent(w,"שלושה")||equivalent(w,"שלוש"))return 3;
            if(w.equals("4")||equivalent(w,"ארבע")||equivalent(w,"ארבעה"))return 4;
            if(w.equals("1")||equivalent(w,"אחד")||equivalent(w,"אחת"))return 1;
        }
        // Never infer a count merely from grammatical plural.
        return -1;
    }
    private static boolean contains(String normalized,String... options){
        for(String o:options)if(normalized.contains(o))return true;
        return false;
    }
    private static String removePreparation(String original){
        String n=normalize(original);
        String[] markers={"ואז","אחר כך","לאחר מכן","ואחרי זה","רק אז"};
        for(String marker:markers){
            int i=original.indexOf(marker);
            if(i>=0 && i+marker.length()<original.length()){
                String later=original.substring(i+marker.length()).trim();
                if(later.length()>=3)return later;
            }
        }
        return original;
    }

    public static Scene interpret(String freeText){
        if(freeText==null || freeText.trim().isEmpty())
            throw new IllegalArgumentException("Empty story");
        String original=freeText.trim();
        String normalized=normalize(original);
        String[] words=normalized.split(" ");
        boolean cleanup=contains(normalized,"נקה את התמונה","לנקות את התמונה",
            "ניקוי של התמונה","נקה תמונה","תנקה את התמונה","תנקה תמונה",
            "תוריד את האפקט","תסיר את האפקט","להסיר רעשים מהתמונה",
            "שפר את איכות התמונה","תוריד רעשים","נקי את התמונה",
            "להסיר את הפילטר","בלי פילטר","נקה את הצילום","תנקה את הצילום","תנקה את התמונה",
            "תסיר את הרעשים","תנקה רעשים","תנקה אפקטים");
        String actionText=cleanup?removePreparation(original):original;
        String[] actionWords=normalize(actionText).split(" ");
        Map<String,Hit> actors=new LinkedHashMap<>();
        for(Term t:ENTITIES){
            int i=findTerm(actionWords,t);
            if(i>=0)actors.putIfAbsent(t.en,new Hit(t,i));
        }
        // Strip entities from the photo-edit preamble when it precedes a scene.
        List<Hit> hits=new ArrayList<>();
        for(Term term:ACTIONS){
            if(term.en.equals("clean photo"))continue;
            int pos=findTerm(actionWords,term);
            if(pos>=0)hits.add(new Hit(term,pos));
        }
        hits.sort(Comparator.comparingInt(h->h.index));
        List<Cast> cast=new ArrayList<>();
        for(Hit hit:actors.values())
            cast.add(new Cast(hit.term.en,hit.term.he,count(actionWords,hit.index)));
        List<String> verbs=new ArrayList<>(),labels=new ArrayList<>();
        for(Hit hit:hits){
            if(verbs.contains(hit.term.en))continue;
            verbs.add(hit.term.en);labels.add(hit.term.he);
        }
        boolean audio=verbs.contains("sing")||verbs.contains("speak")||
             contains(normalized,"קולות","שומעים","סאונד","קריינות",
                "פסקול","מוזיקה","בקול","תדבר","דיבור","תשיר","שיר בפועל");
        boolean multi=contains(normalized,"שתי תמונות","שתי התמונות",
            "2 תמונות","שני צילומים","שני קבצי","משתי תמונות");
        boolean complex=cast.size()>=2&&verbs.size()>=2 ||
                        verbs.size()>=3 || contains(normalized,"בסוף","לבסוף","ולבסוף");
        List<String> summary=new ArrayList<>();
        if(cleanup)summary.add("ניקוי בסיסי של התמונה");
        if(!cast.isEmpty()){
            StringBuilder c=new StringBuilder("דמויות וחפצים: ");
            for(int i=0;i<cast.size();i++){
                Cast item=cast.get(i);
                if(i>0)c.append(", ");
                if(item.count>0)c.append(item.count).append(" × ");
                c.append(item.hebrew);
            }
            summary.add(c.toString());
        }
        if(!labels.isEmpty())summary.add("פעולות: "+String.join(" ← ",labels));
        if(summary.isEmpty())summary.add("הבקשה המקורית שלך — ללא זיהוי פרטים נוסף");
        return new Scene(original,actionText,String.join(" · ",summary),cleanup,audio,multi,
            complex,cast,verbs,labels);
    }
}
