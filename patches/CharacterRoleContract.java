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
    /** Slots stay tied to their photos, but no globally irrelevant scene words. */
    public String immutableSubjects() {
        return "CHARACTER REFERENCE CONTRACT (CURRENT REQUEST ONLY). "
            +"SUBJECT_1 corresponds to the specific individual in reference IMAGE_1. "
            +"SUBJECT_2 corresponds to the different individual in reference IMAGE_2. "
            +"Preserve each reference person's face, hair, physique, accessories and ORIGINAL CLOTHING. "
            +"The two reference slots are distinct: never swap, merge, duplicate or replace them. "
            +"Never infer professions, occupations, events, locations or props from "
            +"any prior request or from anything not expressly required in this current instruction. "
            +"Only TWO principal reference subjects; unrelated background extras are allowed "
            +"when physically necessary (for example an audience), not as substitutes. ";
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
