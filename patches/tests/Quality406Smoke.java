package com.kolbo.videostudio;
public final class Quality406Smoke {
    static void yes(boolean condition,String message) {
        if(!condition)throw new AssertionError(message);
        System.out.println("PASS "+message);
    }
    public static void main(String[] args) {
        yes(DurationPolicy.acceptable(10000,10),"Exact 10-second clip");
        yes(DurationPolicy.acceptable(9950,10),"10s with one frame trimming");
        yes(!DurationPolicy.acceptable(3041,10),"3.04-second clip rejected for 10s request");
        yes(!DurationPolicy.acceptable(8200,10),"8.2-second clip rejected for 10s request");
        yes(!DurationPolicy.acceptable(9050,10),"No lenient 1-second shortfall");
        yes(DurationPolicy.acceptable(3000,3),"Individual 3-second shot allowed only when requested");
        yes(!DurationPolicy.acceptable(0,10),"Empty duration fails");
        yes(!DurationPolicy.acceptable(10000,61),"Unsupported target fails");
        CharacterRoleContract duo=CharacterRoleContract.from("דמות 1 ודמות 2 מופיעים על במה בקיסריה שרים בוכרית ורוקדים יחד");
        yes(!duo.explicitDirection,"Concert duet is not a directed arrest-style action");
        CharacterRoleContract police=CharacterRoleContract.from("דמות 1 עוצרת את דמות 2 ואז נוסעת");
        yes(police.explicitDirection&&police.agent==1&&police.patient==2,"Arrest remains directed subject 1 to 2");
        SceneIntentContract audience=SceneIntentContract.from("שתי הדמויות שרות על במה בקיסריה מול 1000 איש בקהל");
        yes(audience.sceneSetting().contains("one thousand"),"Explicit 1000-person crowd retained");
        System.out.println("ALL 4.0.6 QUALITY REGRESSIONS PASSED");
    }
}
