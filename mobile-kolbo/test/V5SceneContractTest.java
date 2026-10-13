package com.kolbomusic.video;

public final class V5SceneContractTest {
    private static int n=0;
    private static void yes(boolean predicate,String why){
        n++;
        if(!predicate)throw new AssertionError(why);
    }
    public static void main(String[] args){
        String he="תנקה את התמונה מכל האפקטים והרעשים ואז שהדמות נלחמת ב 2 אריות "+
                  "ומנצחת ומכניעה אותם";
        HebrewIntentBrain.Scene scene=HebrewIntentBrain.interpret(he);
        V5SceneContract c=V5SceneContract.compile(scene,
            "The person fights two lions and defeats both.",5);
        yes(c.stages.size()==4,"separate source prep, motion, ending, audit");
        yes(c.stages.get(0)==V5SceneContract.Stage.PHOTO_REPAIR,"photo first");
        yes(c.stages.get(1)==V5SceneContract.Stage.STAGE_ACTION,"motion second");
        yes(c.stages.get(2)==V5SceneContract.Stage.SHOW_OUTCOME,"victory after fight");
        yes(c.stages.get(3)==V5SceneContract.Stage.VISUAL_AUDIT,"visual review last");
        yes(c.requiredLions==2,"precise 2 lions");
        yes(c.requiresFighting,"fight");
        yes(c.requiresVictory,"defeat");
        yes(c.requiresNewBody,"need full-body source");
        yes(c.highAction,"action scene");
        yes(c.compiledPrompt.contains("EXACTLY 2"),"literal animal count");
        yes(c.compiledPrompt.contains("physical struggle"),"physical battle not grimace");
        yes(c.compiledPrompt.contains("Final frames"),"end-state contract");
        yes(c.compiledPrompt.contains("MUST NOT lick"),"anti-lick directive");
        yes(c.negativePrompt.contains("licking"),"negative anti-lick");
        yes(c.negativePrompt.contains("mouth-to-mouth"),"prevent face-contact");
        yes(c.reviewHint().contains("שני אריות"),"actual QA objective");
        yes(c.requiresSemanticEvidence(),"no media-only passing");
        yes(c.compiledPrompt.contains("reference human identity"),"identity intent");

        HebrewIntentBrain.Scene simple=HebrewIntentBrain.interpret("הדמות מחייכת");
        V5SceneContract p=V5SceneContract.compile(simple,"The subject smiles.",2);
        yes(p.stages.size()==2,"simple action and audit");
        yes(!p.requiresNewBody,"do not demand body for smile");
        yes(p.requiredLions==0,"never hallucinate lions");
        yes(!p.negativePrompt.contains("licking"),"no unrelated overconstraints");
        yes(p.requestedSeconds==2,"requested duration retained");

        HebrewIntentBrain.Scene multi=HebrewIntentBrain.interpret("שלב שתי התמונות יחד");
        V5SceneContract mc=V5SceneContract.compile(multi,"Join two images",2);
        yes(mc.multipleReferenceImages,"multiple input unsupported downstream");
        HebrewIntentBrain.Scene singing=HebrewIntentBrain.interpret("הדמות שרה בעברית");
        V5SceneContract sc=V5SceneContract.compile(singing,"Person sings",2);
        yes(sc.needsSound,"sound must not be silently dropped");
        yes(!sc.requiresSemanticEvidence(),"don't fabricate complex visuals");
        try{V5SceneContract.compile(scene,"",5);throw new AssertionError("empty translated");}
        catch(IllegalArgumentException expected){n++;}
        try{V5SceneContract.compile(scene,"scene",15);throw new AssertionError("15s unverified");}
        catch(IllegalArgumentException expected){n++;}

        V5RetryPolicy.Decision quota=V5RetryPolicy.server("GPU_QUOTA");
        yes(quota.next==V5RetryPolicy.Next.WAIT_QUOTA,"quota -> wait");
        yes(!quota.mayPreferDifferentProvider,"quota cannot be bypassed");
        V5RetryPolicy.Decision busy=V5RetryPolicy.server("PROVIDER_BUSY");
        yes(busy.next==V5RetryPolicy.Next.EXPLICIT_OTHER_PROVIDER,"other engine explicit");
        yes(busy.mayPreferDifferentProvider,"recoverable provider error");
        yes(V5RetryPolicy.server("AUTH_REQUIRED").next==
            V5RetryPolicy.Next.CHECK_ACCESS,"honor login");
        yes(V5RetryPolicy.sourceUnsuitable().next==
            V5RetryPolicy.Next.CHANGE_REFERENCE,"source issue not just prompt");
        yes(V5RetryPolicy.semanticUnverified().next==
            V5RetryPolicy.Next.REVIEW_OUTPUT,"semantic mismatch requires review");
        yes(V5RetryPolicy.server("UNKNOWN").next==
            V5RetryPolicy.Next.CHECK_UNKNOWN_JOB,"no automatic retry on unknown submission");
        System.out.println("PASS: "+n+" v5 contract, stage ordering, anti-lick and retry assertions");
    }
}
