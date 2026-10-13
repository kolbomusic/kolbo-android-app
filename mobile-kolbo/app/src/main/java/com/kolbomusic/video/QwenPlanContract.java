package com.kolbomusic.video;

import org.json.JSONArray;
import org.json.JSONObject;

/**
 * Treat LLM text as UNTRUSTED advice. Do not let the model remove hard
 * identity, scene, duration or negation constraints from V5SceneContract.
 * Empty/malformed LLM output is safely ignored, without an extra GPU request.
 */
public final class QwenPlanContract {
    private QwenPlanContract(){}
    public static final class Result {
        public final String prompt;
        public final String negatives;
        public final boolean cleanupRequested;
        public final boolean requiresAudio;
        public final boolean usedLocalModel;
        public final String summary;
        Result(String p,String n,boolean clean,boolean sound,boolean model,String sum){
            prompt=p;negatives=n;cleanupRequested=clean;
            requiresAudio=sound;usedLocalModel=model;summary=sum;
        }
    }
    private static String limit(String text,int max){
        String safe=text==null?"":text.replaceAll("[\\x00-\\x1F]"," ").trim();
        if(safe.length()>max)safe=safe.substring(0,max);
        return safe;
    }
    public static Result compile(V5SceneContract hard,String raw) {
        if(hard==null)throw new IllegalArgumentException("Missing execution contract");
        Result fallback=new Result(hard.compiledPrompt,hard.negativePrompt,
            hard.stages.contains(V5SceneContract.Stage.PHOTO_REPAIR),
            hard.needsSound,false,"מוח גיבוי: כללי כוונה ותרגום");
        if(raw==null||raw.length()>16_000)return fallback;
        int start=raw.indexOf('{'),end=raw.lastIndexOf('}');
        if(start<0||end<=start)return fallback;
        try {
            JSONObject plan=new JSONObject(raw.substring(start,end+1));
            String action=limit(plan.optString("action",""),440);
            String framing=limit(plan.optString("camera",""),140);
            String avoid=limit(plan.optString("avoid",""),280);
            JSONArray steps=plan.optJSONArray("steps");
            if(action.length()<12||framing.length()<3||steps==null||
                steps.length()<1||steps.length()>3)return fallback;
            StringBuilder p=new StringBuilder(hard.compiledPrompt);
            p.append("\nDirector interpretation (optional supporting guidance, user goal above wins): ");
            p.append(action);
            p.append("\nCamera: ").append(framing).append(". Physical event order: ");
            for(int i=0;i<steps.length();i++){
                String stage=limit(steps.optString(i,""),130);
                if(stage.length()<3)return fallback;
                p.append((i+1)).append(": ").append(stage).append("; ");
            }
            // Semantic anchor cannot be overruled by a small language model.
            if(hard.requiredLions==2 && hard.requiresFighting){
                p.append(" EXACTLY TWO LIONS in physical combat with the human, ");
                p.append("NOT licking, NOT nuzzling; the requested victory is visible. ");
            }
            String negatives=hard.negativePrompt;
            if(!avoid.isEmpty())negatives+=", "+avoid;
            return new Result(p.toString(),negatives,
                fallback.cleanupRequested||plan.optBoolean("cleanup",false),
                hard.needsSound||plan.optBoolean("requires_audio",false),
                true,"תוכנית דינמית ממודל Qwen3 מקומי; אינה מבטיחה ציות של מנוע הווידאו.");
        }catch(Exception ignored){
            return fallback;
        }
    }
}
