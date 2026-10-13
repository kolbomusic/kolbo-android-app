package com.kolbomusic.video;

public final class HebrewStoryDirectorTest {
    private static void must(boolean condition,String what){
        if(!condition)throw new AssertionError(what);
    }
    public static void main(String[] args){
        String natural="תנקה את התמונה מכל האפקטים והרעשים בשביל שתתקבל הדמות נקייה "+
            "ואז שייצור סרטון שהדמות נלחמת ב 2 אריות והיא מכניעה אותם";
        HebrewStoryDirector.Plan p=HebrewStoryDirector.understand(natural);
        must(p.cleanPhoto,"local image cleaning detected");
        must(p.lionCount==2,"precise two-lion count");
        must(p.fight,"physical fight detected");
        must(p.wins,"subduing/ending detected");
        must(p.complexScene,"multi-character staged action");
        must(!p.actionToTranslate.contains("האפקטים"),"pre-cleaning request separated");
        must(p.actionToTranslate.contains("נלחמת"),"fighting action preserved");
        String english=p.directedPrompt("The character fights with two lions and overpowers them.");
        must(english.contains("exactly 2 distinct lions"),"hard cast anchoring");
        must(english.contains("overpowers"),"final outcome");
        must(!english.contains("User instruction (Hebrew)"),"not raw Hebrew prompt");
        must(p.visibleSummary.contains("ניקוי"),"automatic Hebrew stage summary");
        must(p.visibleSummary.contains("שני אריות"),"automatic cast summary");
        must(p.supportedLimit()==null,"visual scene not categorically refused");
        must(HebrewStoryDirector.understand("הוא נלחם בשני אריות ולבסוף מנצח").lionCount==2,
             "Hebrew numeric variant");
        must(HebrewStoryDirector.understand("היא נלחמת בשתי אריות ומכניעה אותם").lionCount==2,
             "colloquial gender variant");
        must(HebrewStoryDirector.understand("הדמות הולכת ברחוב").lionCount==0,
             "no hallucinated lions");
        must(HebrewStoryDirector.understand("האיש רוקד ושר בקול").wantsSound,
             "audio unsupported accurately recognized");
        must(HebrewStoryDirector.understand("שלב את שתי התמונות בוידאו").wantsMultiplePhotos,
             "two independent photos recognized");
        must(HebrewStoryDirector.understand("בתמונה מופיע אריה, צור תנועה").lionCount==1,
             "single animal supported by plan");
        must(HebrewStoryDirector.understand("צור סרטון שהדמות מחייכת").actionToTranslate
             .contains("מחייכת"),"simple original language not distorted");
        System.out.println("PASS: 19 natural Hebrew story-planning assertions");
    }
}
