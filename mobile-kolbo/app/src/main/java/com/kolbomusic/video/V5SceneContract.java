package com.kolbomusic.video;

import java.util.ArrayList;
import java.util.Collections;
import java.util.List;

/**
 * V5 immutable execution contract. Human Hebrew story is treated as an
 * objective and decomposed into verifiable phases, not a prompt decoration.
 * Actual video models MAY ignore these constraints: only postflight evidence
 * decides whether output merits acceptance. ZeroGPU cannot guarantee action.
 */
public final class V5SceneContract {
    public enum Stage { PHOTO_REPAIR, STAGE_ACTION, SHOW_OUTCOME, VISUAL_AUDIT }
    public final String humanStory;
    public final String translatedAction;
    public final List<Stage> stages;
    public final String compiledPrompt;
    public final String negativePrompt;
    public final boolean highAction;
    public final boolean requiresNewBody;
    public final boolean needsSound;
    public final boolean multipleReferenceImages;
    public final int requestedSeconds;
    public final int requiredLions;
    public final boolean requiresFighting;
    public final boolean requiresVictory;
    public final String hebrewExplanation;
    private V5SceneContract(HebrewIntentBrain.Scene scene,String translated,int seconds,
                            List<Stage> stages,String positive,String negative,
                            boolean action,boolean newBody,int lions,boolean fight,boolean victory) {
        humanStory=scene.original;translatedAction=translated;
        this.stages=Collections.unmodifiableList(new ArrayList<>(stages));
        compiledPrompt=positive;negativePrompt=negative;
        highAction=action;requiresNewBody=newBody;
        needsSound=scene.soundtrack;multipleReferenceImages=scene.multiPhoto;
        requestedSeconds=seconds;requiredLions=lions;
        requiresFighting=fight;requiresVictory=victory;
        hebrewExplanation=scene.summary;
    }

    public static V5SceneContract compile(HebrewIntentBrain.Scene scene,String translated,int seconds){
        if(scene==null || translated==null || translated.trim().length()<2)
            throw new IllegalArgumentException("No interpreted story");
        if(seconds<2||seconds>5)throw new IllegalArgumentException("Experimental 2-5s limit");
        boolean fight=scene.verbsEnglish.contains("fight")||
                      scene.verbsEnglish.contains("fight back");
        boolean victory=scene.verbsEnglish.contains("defeat");
        int lions=0;
        for(HebrewIntentBrain.Cast c:scene.cast){
            if("lion".equals(c.english))lions=Math.max(lions,c.count);
        }
        boolean action=fight||victory||scene.verbsEnglish.contains("run")||
                       scene.verbsEnglish.contains("chase")||scene.verbsEnglish.contains("dance");
        boolean bodies=action && (fight||lions>0||scene.cast.size()>1);
        List<Stage> stages=new ArrayList<>();
        if(scene.photoCleanup)stages.add(Stage.PHOTO_REPAIR);
        stages.add(Stage.STAGE_ACTION);
        if(victory)stages.add(Stage.SHOW_OUTCOME);
        stages.add(Stage.VISUAL_AUDIT);

        StringBuilder positive=new StringBuilder(1400);
        positive.append("STORY AND EVIDENCE CONTRACT: actual visible physical events. ");
        positive.append("Accurately preserve the reference human identity and clothing. ");
        positive.append("User's translated scene: ").append(translated.trim()).append(". ");
        if(bodies)positive.append("Medium-wide full-body camera composition, hands and legs in frame. ");
        if(fight)positive.append("Action requires physical struggle with clear defensive movements, ")
                          .append("active limbs and changing body positions, no face-only animation. ");
        for(HebrewIntentBrain.Cast c:scene.cast){
            if(c.count>0)positive.append("Show EXACTLY ").append(c.count)
                       .append(" distinct ").append(c.english).append(" subjects. ");
            else positive.append("Preserve required ").append(c.english).append(" subject. ");
        }
        if(lions==2&&fight){
            positive.append("Both lions are separate animals visible together, ");
            positive.append("both confront the human, the human resists, pushes them away ");
            positive.append("and gains control during a staged cinematic non-graphic fight. ");
            positive.append("The human MUST NOT lick, kiss, nuzzle, hug, pet, cuddle, ")
                    .append("or press their mouth to either lion. ");
        }
        if(victory)positive.append("Final frames clearly show victory: defeated opponents ")
                            .append("step back or lie subdued, while the human stands in control. ");
        if(!scene.verbsEnglish.isEmpty()){
            positive.append("Required actions in order: ");
            for(String verb:scene.verbsEnglish)positive.append(verb).append(" -> ");
            positive.append("final result. ");
        }
        positive.append("Do not substitute unrelated facial expressions for the requested action.");

        StringBuilder negative=new StringBuilder();
        negative.append("static portrait, talking head, facial expression only, no action, ")
                .append("offscreen action, zoomed face, missing required actors, ")
                .append("duplicate animals, distorted face, extra limbs, subtitles, watermark");
        if(fight){
            negative.append(", licking, tongue protruding, kissing, nuzzling, cuddling, ")
                    .append("affectionate touching, petting, hugging, friendly behavior, ")
                    .append("mouth-to-mouth contact, face sniffing, nose-to-nose contact, ")
                    .append("calm lion posing next to human");
        }
        return new V5SceneContract(scene,translated,seconds,stages,
                positive.toString(),negative.toString(),action,bodies,lions,fight,victory);
    }

    public boolean requiresSemanticEvidence(){
        return requiresFighting||requiresVictory||requiredLions>0||highAction;
    }
    /** A rendered MP4 alone never verifies combat, animal count or victory. */
    public String reviewHint(){
        if(requiredLions>0 && requiresFighting){
            return "בדוק: שני אריות נפרדים, מאבק גופני, בלי ליקוק או חיבה"
                    +(requiresVictory?", וסיום שבו הדמות מכניעה אותם.":".");
        }
        return "בדוק שהפעולה המתוארת אכן קרתה ולא הוחלפה בהבעות פנים.";
    }
}
