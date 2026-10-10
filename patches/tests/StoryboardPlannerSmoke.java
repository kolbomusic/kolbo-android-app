package com.kolbo.videostudio;

public final class StoryboardPlannerSmoke {
    private static void check(boolean good,String label) {
        if(!good)throw new AssertionError(label);
        System.out.println("PASS "+label);
    }
    public static void main(String[] args) {
        StoryboardPlanner.Plan he=StoryboardPlanner.plan("החיילת עוצרת את האיש, מכניסה אותו לטנק, ואז נוסעת",8);
        check(he.scenes.size()==3,"Hebrew actions separated into chronological shots");
        check(he.scenes.get(0).action.contains("עוצרת"),"First action retained");
        check(he.scenes.get(1).action.contains("מכניסה"),"Second action retained");
        check(he.scenes.get(2).action.contains("נוסעת"),"Third action retained");
        int total=0;for(StoryboardPlanner.Scene s:he.scenes)total+=s.seconds;
        check(total==8,"Exact requested duration allocation");
        check(StoryboardPlanner.stagePrompt(he.scenes.get(0),3,true).contains("Image 1"),"Two independent identity constraints");
        StoryboardPlanner.Plan en=StoryboardPlanner.plan("The woman walks toward the car, opens the door, and drives away",8);
        check(en.scenes.size()==3,"English multiaction prompt");
        StoryboardPlanner.Plan shortPlan=StoryboardPlanner.plan("קודם רוקדת ואז שרה לאחר מכן יושבת ולבסוף מחייכת",3);
        check(shortPlan.reduced,"Short duration requires action consolidation");
        check(shortPlan.scenes.size()==1,"3 seconds has one compact stage");
        check(shortPlan.scenes.get(0).action.contains("שרה")&&shortPlan.scenes.get(0).action.contains("מחייכת"),"No actions discarded on consolidation");
        check(StoryboardPlanner.plan("A cat jumps",60).scenes.get(0).seconds==60,"Long prompts maintain duration");
        check(ProviderFailure.classify("ZeroGPU quota exhausted (429)") == ProviderFailure.Kind.QUOTA,"Quota recognized");
        check(ProviderFailure.classify("HTTP 503: GPU queue is busy") == ProviderFailure.Kind.BUSY,"Provider overload recognized");
        check(ProviderFailure.classify("The server returned 403 Forbidden") == ProviderFailure.Kind.AUTH,"Permissions respected");
        check(ProviderFailure.explain(new RuntimeException("HTTP 429")).contains("מכסה"),"User-friendly Hebrew quota error");
        System.out.println("ALL PLANNER SMOKE TESTS PASSED");
    }
}
