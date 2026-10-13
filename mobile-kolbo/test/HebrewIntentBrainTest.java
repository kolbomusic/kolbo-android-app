package com.kolbomusic.video;

public final class HebrewIntentBrainTest {
    private static int checks=0;
    private static void check(boolean yes,String why){checks++;if(!yes)throw new AssertionError(why);}
    private static HebrewIntentBrain.Cast find(HebrewIntentBrain.Scene s,String english){
        for(HebrewIntentBrain.Cast c:s.cast)if(c.english.equals(english))return c;
        return null;
    }
    public static void main(String[] args){
        String user="תנקה את התמונה מכל האפקטים והרעשים בשביל שתתקבל הדמות נקייה "
          +"ואז שייצור סרטון שהדמות נלחמת ב 2 אריות והיא מכניעה אותם";
        HebrewIntentBrain.Scene lion=HebrewIntentBrain.interpret(user);
        check(lion.photoCleanup,"detect cleanup");
        check(lion.actionText.contains("נלחמת"),"retain action after prep");
        check(!lion.actionText.contains("האפקטים"),"separate photo prep");
        check(find(lion,"lion")!=null,"identify lions");
        check(find(lion,"lion").count==2,"precise two lions");
        check(lion.verbsEnglish.contains("fight"),"detect fight");
        check(lion.verbsEnglish.contains("defeat"),"detect ending");
        check(lion.complex,"complex scene flagged");
        String prompt=lion.prompt("The person fights two lions and defeats them.");
        check(prompt.contains("exactly 2 lion"),"count cannot be lost in translation");
        check(prompt.indexOf("fight") < prompt.indexOf("defeat ->"),"action order");
        check(lion.summary.contains("2 × אריה"),"simple summary in Hebrew");
        check(!lion.soundtrack,"no invented audio request");

        HebrewIntentBrain.Scene dance=HebrewIntentBrain.interpret(
           "הבחורה רוקדת על החוף, הכלב קופץ ליד החתול");
        check(dance.verbsEnglish.contains("dance"),"dance");
        check(dance.verbsEnglish.contains("jump"),"jump");
        check(find(dance,"dog")!=null,"dog");
        check(find(dance,"cat")!=null,"cat");
        check(dance.actionText.contains("החוף"),"preserve other details without dictionary word");

        HebrewIntentBrain.Scene vehicles=HebrewIntentBrain.interpret(
           "שני סוסים רצים ואז קופצים מעל המכונית");
        check(find(vehicles,"horse")!=null,"horses recognized");
        check(find(vehicles,"horse").count==2,"two horses");
        check(find(vehicles,"car")!=null,"car");
        check(vehicles.verbsEnglish.contains("run"),"run");
        check(vehicles.verbsEnglish.contains("jump"),"jump");

        HebrewIntentBrain.Scene ball=HebrewIntentBrain.interpret("הכדור מתגלגל במורד המדרגות");
        check(find(ball,"ball")!=null,"ball noun");
        check(ball.verbsEnglish.contains("roll"),"roll verb");
        check(ball.actionText.contains("המדרגות"),"retains not-yet-covered nouns");

        HebrewIntentBrain.Scene music=HebrewIntentBrain.interpret("האישה מנגנת בגיטרה ומחייכת");
        check(find(music,"guitar")!=null,"guitar");
        check(music.verbsEnglish.contains("play instrument"),"play instrument");
        check(music.verbsEnglish.contains("smile"),"smile");
        check(!music.soundtrack,"do not invent user request for audible song just from playing guitar");

        HebrewIntentBrain.Scene sound=HebrewIntentBrain.interpret("היא שרה ומדברת בקול");
        check(sound.soundtrack,"requested singing/audio");
        check(sound.verbsEnglish.contains("sing"),"singing");
        check(sound.verbsEnglish.contains("speak"),"speaking");

        HebrewIntentBrain.Scene exclude=HebrewIntentBrain.interpret("אל תוסיף אריות לתמונה");
        check(find(exclude,"lion")==null,"respect explicit exclusion");
        check(find(HebrewIntentBrain.interpret("לא רוצה מכונית בסרטון"),"car")==null,
           "respect no-car preference");

        HebrewIntentBrain.Scene future=HebrewIntentBrain.interpret(
            "אני רוצה שהדמות תילחם בשני אריות ותכניע אותם");
        check(future.verbsEnglish.contains("fight"),"future verb fight");
        check(future.verbsEnglish.contains("defeat"),"future verb defeat");
        check(find(future,"lion").count==2,"quantifier in conversational future");
        check(future.prompt("Person fights lions").contains("2 lion"),"scene grounding");

        HebrewIntentBrain.Scene photo=HebrewIntentBrain.interpret(
          "תוריד את האפקטים מהתמונה ואחר כך האישה תרקוד");
        check(photo.photoCleanup,"photo prep variant");
        check(photo.actionText.contains("האישה תרקוד"),"temporal split");
        check(photo.verbsEnglish.contains("dance"),"dance future");
        check(HebrewIntentBrain.interpret("תעשה שהיא תצייר ציור").actionText
              .contains("תצייר"),"graceful unknown verb passthrough");
        check(HebrewIntentBrain.interpret("שלב את שתי התמונות").multiPhoto,
              "two photo demand caught");
        check(HebrewIntentBrain.interpret("רקדה").summary!=null,"short unsupported text handled");
        System.out.println("PASS: "+checks+" bilingual scene planning checks without network or GPU");
    }
}
