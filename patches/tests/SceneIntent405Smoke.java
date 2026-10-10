package com.kolbo.videostudio;

public final class SceneIntent405Smoke {
    private static void ok(boolean value,String description) {
        if(!value)throw new AssertionError(description);
        System.out.println("PASS "+description);
    }
    public static void main(String[] args) {
        final String concert="שתי הדמויות שרות בקצב מזרחי שיר על הבמה הופעה בקיסריה";
        SceneIntentContract music=SceneIntentContract.from(concert);
        ok(music.category==SceneIntentContract.Category.MUSIC_PERFORMANCE,"Concert category recognized");
        ok(music.caesarea&&music.mizrahi&&music.singing&&music.jointSubjects,"Explicit concert intent details preserved");
        String prompt=CharacterRoleContract.from(concert).prompt(concert,1,1)+" "+music.sceneSetting();
        String lower=prompt.toLowerCase(java.util.Locale.ROOT);
        ok(prompt.contains("STAGE")&&prompt.contains("Mizrahi")&&prompt.contains("amphitheater"),"Specific performance setting, venue and genre");
        for(String forbidden:new String[]{"police","uniform","arrest","soldier","military","workshop","detention","tank"}){
            ok(!lower.contains(forbidden),"Unrequested "+forbidden+" excluded from performance prompt");
        }
        SceneIntentContract request2=SceneIntentContract.from("דמות 1 עוצרת את דמות 2 מכניסה אותו לניידת המשטרה ונוסעת");
        ok(request2.category==SceneIntentContract.Category.VEHICLE_ACTION,"Vehicle action is separate from music");
        ok(!request2.sceneSetting().contains("Mizrahi")&&!request2.sceneSetting().contains("STAGE"),"Music setting cannot leak into vehicle action");
        SceneIntentContract everyday=SceneIntentContract.from("חתול נרדם על שטיח בבית");
        ok(everyday.category==SceneIntentContract.Category.GENERAL,"Arbitrary daily task is not forced into predefined scene");
        ok(!everyday.sceneSetting().contains("Mizrahi"),"No concert details in generic scene");
        SceneIntentContract dance=SceneIntentContract.from("שני חברים רוקדים ביחד");
        ok(dance.category==SceneIntentContract.Category.DANCE,"Dance context");
        ok(dance.sceneSetting().contains("full-body"),"Dance-specific foreground action");
        String role=CharacterRoleContract.from(concert).immutableSubjects().toLowerCase(java.util.Locale.ROOT);
        ok(!role.contains("police")&&!role.contains("military")&&!role.contains("uniform"),
            "Identity contract no longer injects visual police/uniform cues");
        ok(music.audioNote().contains("may not"),"Audio capability is labeled uncertain");
        System.out.println("ALL 4.0.5 SCENE INTENT TESTS PASSED");
    }
}
