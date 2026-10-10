package com.kolbo.videostudio;

import java.util.Locale;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/**
 * Deterministic character-slot and action-role contract.
 * It cannot establish face identity from images, and does not invent attributes
 * or professions from a prompt. It preserves source image and direction bindings.
 */
public final class CharacterRoleContract {
    private static final Pattern SUBJECT_RELATION = Pattern.compile(
        "(?iu)(?:דמות|character|person|subject)\\s*([12])\\b"
        + ".{1,180}?"
        + "(?:דמות|character|person|subject)\\s*([12])\\b");
    private static final Pattern NUMBERS = Pattern.compile(
        "(?iu)(?:דמות|character|person|subject)\\s*([12])\\b");
    public final int agent;
    public final int patient;
    public final boolean explicitDirection;
    public final String sourceInstruction;

    private CharacterRoleContract(int a,int p,boolean directed,String instruction) {
        agent=a;patient=p;explicitDirection=directed;sourceInstruction=instruction;
    }
    public static CharacterRoleContract from(String instruction) {
        if(instruction==null)instruction="";
        Matcher m=SUBJECT_RELATION.matcher(instruction);
        while(m.find()) {
            int a=Integer.parseInt(m.group(1)),b=Integer.parseInt(m.group(2));
            if(a!=b)return new CharacterRoleContract(a,b,true,instruction);
        }
        return new CharacterRoleContract(0,0,false,instruction);
    }
    /** Separate immutable photographic slots; no guessed demographics/occupation. */
    public String immutableSubjects() {
        return "CHARACTER LOCK CONTRACT. "
            +"SUBJECT_1 is ONLY the specific person depicted in reference IMAGE_1. "
            +"SUBJECT_2 is ONLY the different specific person depicted in reference IMAGE_2. "
            +"Reference slots must never be swapped. In every frame keep each subject's own face, "
            +"hairstyle, physique, accessories and ORIGINAL CLOTHING from their OWN separate input photo. "
            +"A police/military/workplace setting does NOT authorize putting both in matching uniforms. "
            +"Never turn SUBJECT_2 into a duplicate of SUBJECT_1 or make both subjects employees "
            +"of the same organization merely because of the environment. "
            +"Costume changes are allowed only when EXPLICITLY commanded by the user. "
            +"Do not clone, merge, disappear, replace or add subjects. ";
    }
    public String actionDirection() {
        if(!explicitDirection)return
            "Apply each action to exactly the actor and recipient explicitly stated in the instruction. "
           +"Never infer a role from costume or background alone. If the actor is not specified, "
           +"do not substitute another person for a requested character. ";
        return "RELATION LOCK: SUBJECT_"+agent+" is the ACTOR performing the directed action; "
            +"SUBJECT_"+patient+" is the DISTINCT RECIPIENT of that action. "
            +"The recipient is never silently promoted into a second actor with matching clothes. "
            +"Do not reverse who acts on whom. Do not swap agent and patient during later shots. ";
    }
    public String prompt(String stageAction,int sceneIndex,int sceneCount) {
        if(stageAction==null||stageAction.trim().isEmpty())
            throw new IllegalArgumentException("empty stage");
        return immutableSubjects()+actionDirection()
            +"STORYBOARD SHOT "+sceneIndex+" OF "+sceneCount+". "
            +"Only one specific action is mandatory in this shot: "+stageAction.trim()+". "
            +"Show it visibly with correct physical cause and effect. Do not replace it with posing, "
            +"walking past the camera, waving or other generic activity. "
            +"Keep all subjects, objects, vehicles and props consistent with the described situation. "
            +"Do not invent English captions, subtitles or unrelated dialogue. ";
    }
    public String preview() {
        String association="תמונה 1 ↔ דמות 1; תמונה 2 ↔ דמות 2; אין החלפת זהות או לבוש.";
        if(explicitDirection)
            return association+" דמות "+agent+" מבצעת את הפעולה ביחס לדמות "+patient
                    +", בלי להחליף תפקידים.";
        return association+" כיוון הפעולה לא זוהה באופן מפורש; בודקים את תוכנית הסצנות.";
    }
}
