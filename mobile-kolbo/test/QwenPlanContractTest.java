package com.kolbomusic.video;

public final class QwenPlanContractTest {
    private static int checks=0;
    private static void ok(boolean c,String why){
        checks++;if(!c)throw new AssertionError(why);
    }
    public static void main(String[] args){
        HebrewIntentBrain.Scene story=HebrewIntentBrain.interpret(
            "תנקה את התמונה ותיצור שהדמות נלחמת בשני אריות ומכניעה אותם");
        V5SceneContract hard=V5SceneContract.compile(story,
            "The person fights two lions and defeats them",5);
        String response="{\"action\":\"The person physically confronts the two lions and pushes them away\","+
            "\"camera\":\"Wide action framing shows all figures\","+
            "\"avoid\":\"licking lions or nuzzling faces\","+
            "\"steps\":[\"two lions attack\", \"person defends with hands\", \"both lions retreat\"],"+
            "\"cleanup\":true,\"requires_audio\":false}";
        QwenPlanContract.Result result=QwenPlanContract.compile(hard,response);
        ok(result.usedLocalModel,"genuine model result incorporated");
        ok(result.prompt.contains("both lions retreat"),"new story stage");
        ok(result.prompt.contains("Wide action framing"),"dynamic camera");
        ok(result.prompt.contains("EXACTLY 2"),"hard cast count retained");
        ok(result.prompt.contains("MUST NOT lick"),"hard semantic negation retained");
        ok(result.negatives.contains("licking lions"),"dynamic negative supplement");
        ok(result.cleanupRequested,"local photo preprocessing");
        ok(!result.requiresAudio,"silent action remains silent");
        ok(QwenPlanContract.compile(hard,"malformed").usedLocalModel==false,
            "bad model JSON falls back");
        ok(!QwenPlanContract.compile(hard,
            "{\"action\":\"hi\",\"steps\":[],\"camera\":\"x\"}").usedLocalModel,
            "incomplete scene does not override hard contract");
        ok(!QwenPlanContract.compile(hard,"{invalid json}").usedLocalModel,
            "malformed JSON never reaches video engine");
        ok(QwenPlanContract.compile(hard,"{}").prompt.equals(hard.compiledPrompt),
            "safe fallback still functional");
        String huge=" ".repeat(20000);
        ok(!QwenPlanContract.compile(hard,huge).usedLocalModel,"bound model output length");
        QwenPlanContract.Result audio=QwenPlanContract.compile(hard,
            response.replace("\"requires_audio\":false","\"requires_audio\":true"));
        ok(audio.requiresAudio,"new sound demand is detected before muted video generation");
        ok(audio.prompt.contains("EXACTLY 2"),"even sound detection cannot erase lion count");
        System.out.println("PASS: "+checks+" LLM contract and offline model provenance checks");
    }
}
