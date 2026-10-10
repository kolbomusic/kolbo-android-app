package com.kolbo.videostudio;

public final class RoleAndActions404Smoke {
    static void ok(boolean v,String message) {
        if(!v)throw new AssertionError(message);
        System.out.println("PASS "+message);
    }
    static String concat(StoryboardPlanner.Plan p) {
        StringBuilder x=new StringBuilder();
        for(StoryboardPlanner.Scene s:p.scenes)x.append(s.action).append(" ");
        return x.toString();
    }
    public static void main(String[] args) {
        String request="דמות 1 עוצרת את דמות 2 מכניסה אותו לניידת המשטרה ונוסעת";
        CharacterRoleContract a=CharacterRoleContract.from(request);
        ok(a.explicitDirection&&a.agent==1&&a.patient==2,"Hebrew actor 1 -> target 2");
        ok(a.prompt("places man in vehicle",2,3).contains("SUBJECT_1 is the ACTOR"),"Actor contract persists across shots");
        ok(a.prompt("drives away",3,3).contains("SUBJECT_2 is the DISTINCT RECIPIENT"),"Recipient remains separately bound");
        ok(a.prompt("drives away",3,3).contains("ORIGINAL CLOTHING"),"No changing recipient into officer");
        StoryboardPlanner.Plan p=StoryboardPlanner.plan(request,8);
        System.out.println("PLAN "+p.preview());
        ok(p.scenes.size()>=3,"Three distinct actions extracted from unpunctuated Hebrew");
        ok(p.scenes.get(0).action.contains("עוצרת"),"First scene includes arresting action");
        ok(!p.scenes.get(0).action.equals("דמות 1"),"Initial bare actor label is NOT a shot");
        ok(concat(p).contains("מכניסה")&&concat(p).contains("ונוסעת"),"All requested Hebrew verbs preserved");
        int sum=0;for(StoryboardPlanner.Scene scene:p.scenes)sum+=scene.seconds;
        ok(sum==8,"Duration preserved after action extraction");
        CharacterRoleContract reverse=CharacterRoleContract.from("דמות 2 מחבקת את דמות 1 ואז דמות 1 מחייכת");
        ok(reverse.explicitDirection&&reverse.agent==2&&reverse.patient==1,"Reverse action direction retained");
        CharacterRoleContract free=CharacterRoleContract.from("כלב משחק עם כדור ועץ ברקע");
        ok(!free.explicitDirection,"No hallucinated subject role if absent");
        StoryboardPlanner.Plan en=StoryboardPlanner.plan("Character 1 stops character 2 and opens the door and drives away",9);
        ok(en.scenes.size()>=2,"English conjunctive action planning");
        ok(concat(en).contains("door")&&concat(en).contains("drives"),"English actions preserved");
        System.out.println("ALL 4.0.4 ROLE + ACTION SMOKE TESTS PASSED");
    }
}
