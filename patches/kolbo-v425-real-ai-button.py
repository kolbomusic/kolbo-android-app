"""v425: the main Create button now targets REAL motion, never camera pans.

One-time brief consent for uploading private images to a public third-party
ZeroGPU demo. Anonymous, very low free quotas; never hardcode owner/admin key.
No paid GPU, misleading 10s story, silent photo substitute or repeated dialog.
Applied after v424 in Android CI.
"""
from pathlib import Path
import shutil,sys
root=Path(sys.argv[1])
base=root/'app/src/main/java/com/kolbo/videostudio'
main_file=base/'MainActivity.java'
client_file=base/'PrivateRenderClient.java'
gradle_file=root/'app/build.gradle'
main=main_file.read_text('utf8')
client=client_file.read_text('utf8')
gradle=gradle_file.read_text('utf8')

shutil.copyfile('patches/AiMotionGate.java',base/'AiMotionGate.java')
start=main.index('        if(!cpuPhotoRequested && !PrivateRenderClient.manualEngineConfigured(this)){')
end=main.index('        if(cpuPhotoRequested){',start)
old=main[start:end]
if 'כן, עריכת תמונות' not in old or 'new AlertDialog.Builder' not in old:
    raise SystemExit('v425: unexpected legacy AI-to-photo downgrade block')
new= '''        if(!cpuPhotoRequested && !PrivateRenderClient.manualEngineConfigured(this)){
            // The PRIMARY action is real AI creation ONLY. Never substitute
            // a moving camera over a still-picture collage.
            if(chosen==null){
                message("כדי ליצור תנועה ב-AI בחר תמונת מקור");
                return;
            }
            if(second!=null){
                message("שתי דמויות מתמונות נפרדות עדיין אינן נתמכות במנוע ה-AI החינמי");
                return;
            }
            if(desired<1 || desired>5){
                message("מנוע ה-AI האמיתי תומך כרגע ב-1–5 שניות בלבד. 10 שניות אינן זמינות במנוע זה.");
                return;
            }
            if(instruction.isEmpty()){
                message("כתוב מה הדמות צריכה לעשות בסרטון");
                return;
            }
            approveOnceAndGenerateAi(chosen,desired,instruction);
            return;
        }
'''
main=main[:start]+new+main[end:]

method='''    private void approveOnceAndGenerateAi(Uri first,int seconds,String instruction){
        android.content.SharedPreferences prefs=getSharedPreferences(
            "kolbo_ai_external_consent",MODE_PRIVATE);
        if(prefs.getBoolean("approved_v425",false)){
            prepareRealAiTrial(first,seconds,instruction);
            return;
        }
        new AlertDialog.Builder(this)
            .setTitle("אישור חד-פעמי ליצירת AI אמיתית")
            .setMessage("התמונה וההנחיה יישלחו להדגמה ציבורית של Wan דרך Hugging Face. השירות חינמי אך מוגבל, ותמונות שהועלו אינן פרטיות. אל תעלה תמונות רגישות. לא יבוצע חיוב. להמשיך?")
            .setPositiveButton("מאשר ויוצר",(d,w)->{
                prefs.edit().putBoolean("approved_v425",true).apply();
                prepareRealAiTrial(first,seconds,instruction);
            })
            .setNegativeButton("ביטול",(d,w)->{})
            .show();
    }
    private void prepareRealAiTrial(Uri first,int seconds,String original){
        if(!hasHebrew(original)){
            startRealAiTrial(first,seconds,original);
            return;
        }
        message("מתאים את ההנחיה בעברית למנוע יצירת הווידאו...");
        TranslatorOptions opts=new TranslatorOptions.Builder()
            .setSourceLanguage(TranslateLanguage.HEBREW)
            .setTargetLanguage(TranslateLanguage.ENGLISH).build();
        final Translator translator=Translation.getClient(opts);
        translator.downloadModelIfNeeded()
            .addOnSuccessListener(nothing->
                translator.translate(original)
                    .addOnSuccessListener(translated->{
                        translator.close();
                        if(translated==null||translated.trim().length()<5||
                                hasHebrew(translated)){
                            message("לא ניתן לתרגם את ההנחיה ליצירת AI.");
                            return;
                        }
                        startRealAiTrial(first,seconds,translated);
                    })
                    .addOnFailureListener(e->{
                        translator.close();
                        message("התרגום לא זמין כעת; לא נשלח תוכן שגוי.");
                    }))
            .addOnFailureListener(e->{
                translator.close();
                message("יש צורך במודל תרגום עברית מקומי לפני יצירת AI.");
            });
    }
    private void startRealAiTrial(Uri first,int seconds,String translated){
        busy(true);
        executor.execute(()->{
            try{
                message("מייצר תנועה אמיתית באמצעות מודל AI חינמי...");
                PrivateRenderClient.ensureAutoConnected(this);
                File output=PrivateRenderClient.renderAiTrial(this,first,seconds,
                    translated,getCacheDir(),stage->message(stage));
                OutputLengthGate.verify(output,seconds);
                AiMotionGate.verify(output);
                showResult(output,"נוצרו פריימים חדשים באמצעות AI. יש לבדוק התאמה לדמות ולפעולה.");
            }catch(Exception e){
                message("לא נוצר סרטון AI: "+e.getMessage());
                busy(false);
            }
        });
    }
'''
anchor='    private void startCpuPhotoMotion(Uri first,Uri second,int seconds){'
if main.count(anchor)!=1:raise SystemExit('v425: existing CPU photo method missing')
main=main.replace(anchor,method+anchor,1)

loc=client.index('    static File renderPhotoMotion(')
end=client.rfind('\n}')
if loc<0 or end<loc:raise SystemExit('v425: cannot copy secure job polling')
photoMethod=client[loc:end]
http='        HttpURLConnection conn=open(ctx,"/v1/studio/jobs","POST",120000);'
a=photoMethod.index(http)
flow=photoMethod[a:photoMethod.rfind('\n    }')].replace(
    'open(ctx,"/v1/studio/jobs","POST",120000)',
    'open(ctx,"/v1/ai/jobs","POST",120000)',1)
flow=flow.replace('שולח בקשה לשרת ההפקה הפרטי','שולח בקשת תנועה למנוע AI',1)
aiMethod='''    static File renderAiTrial(Context ctx,Uri first,int seconds,
        String instruction,File cache,Status status) throws Exception{
        if(first==null||seconds<1||seconds>5)
            throw new Exception("נדרש מקור יחיד ובקשה באורך 1–5 שניות");
        if(instruction==null||instruction.trim().length()<5)
            throw new Exception("חסרה הוראת תנועה");
        JSONObject server=check(ctx);
        JSONObject capability=server.optJSONObject("experimental_ai_video");
        if(capability==null||!"ai_one_image_trial".equals(capability.optString("mode"))||
            !capability.optBoolean("ready",false))
            throw new Exception("המנוע ליצירת תנועה אמיתית אינו זמין כרגע");
        JSONObject plan=new JSONObject();
        plan.put("prompt",instruction);
        plan.put("seconds",seconds);
        plan.put("image_count",1);
        plan.put("third_party_transfer_consent",true);
        HttpURLConnection preview=open(ctx,"/v1/creative/plan","POST",30000);
        preview.setDoOutput(true);
        preview.setRequestProperty("Content-Type","application/json; charset=UTF-8");
        byte[] request=plan.toString().getBytes(StandardCharsets.UTF_8);
        preview.setFixedLengthStreamingMode(request.length);
        try(OutputStream out=preview.getOutputStream()){out.write(request);}
        JSONObject constraints=new JSONObject(fetch(preview));
        if(!"draft_possible".equals(constraints.optString("status")))
            throw new Exception("המנוע אינו מסוגל לבצע את ההנחיה: "
                +constraints.optJSONArray("blockers"));
        JSONObject payload=new JSONObject();
        payload.put("prompt",instruction);
        payload.put("seconds",seconds);
        payload.put("fps",16);
        payload.put("third_party_transfer_consent",true);
        payload.put("commercial_use",false);
        JSONArray images=new JSONArray();
        // Bounded phone picture; the full original is retained on the device.
        images.put(smallCpuImage(ctx,first));
        payload.put("images",images);
''' + flow + '\n    }\n'
client=client[:end]+'\n'+aiMethod+client[end:]
for old,new in [
    ("applicationId 'com.kolbo.videostudio.preview424'",
     "applicationId 'com.kolbo.videostudio.preview425'"),
    ("versionCode 424","versionCode 425"),
    ("versionName '4.2.4'","versionName '4.2.5'"),
]:
    if gradle.count(old)!=1:raise SystemExit('Version mismatch: '+old)
    gradle=gradle.replace(old,new,1)

assert 'approveOnceAndGenerateAi(chosen,desired,instruction)' in main
assert 'AiMotionGate.verify(output)' in main
assert 'yes, photo editing' not in main.lower()
assert 'renderAiTrial' in client and '/v1/ai/jobs' in client
assert 'KOLBO_V416_API_TOKEN' not in client
assert 'third_party_transfer_consent' in client
assert 'כן, עריכת תמונות' not in main[main.index('if(!cpuPhotoRequested && !PrivateRenderClient.manualEngineConfigured'):main.index('if(cpuPhotoRequested){',main.index('if(!cpuPhotoRequested && !PrivateRenderClient.manualEngineConfigured'))]
main_file.write_text(main,'utf8')
client_file.write_text(client,'utf8')
gradle_file.write_text(gradle,'utf8')
print("PASS v425: main button runs only real image-to-video AI when supported; no photo fallback or modal loop")
