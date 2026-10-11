"""Add an explicitly separate CPU PHOTO MOTION button after v416 Android patch.

No ads and no paid GPU. This is not video acting or singing; users must opt in
to the truthful photo-animation capability, and authorize their own media.
The existing private service token remains in AndroidKeyStore, never baked APK.
"""
from pathlib import Path
import sys

root=Path(sys.argv[1])
base=root/'app/src/main/java/com/kolbo/videostudio'
main_file=base/'MainActivity.java'
client_file=base/'PrivateRenderClient.java'
gradle_file=root/'app/build.gradle'
main=main_file.read_text(encoding='utf-8')
client=client_file.read_text(encoding='utf-8')
gradle=gradle_file.read_text(encoding='utf-8')

def once(content,old,new):
    if content.count(old)!=1:
        raise SystemExit('v418 missing unique anchor: '+old[:95])
    return content.replace(old,new,1)

main=once(main,'        diagnostics=button("הצג אבחון טכני");',
'''        Button cpuPhotoButton=button("סרטון מתמונות בחינם (ללא יצירת AI)");
        advancedPanel.addView(cpuPhotoButton,StudioVisuals.spaced(this,52,8));
        cpuPhotoButton.setOnClickListener(v->{
            cpuPhotoRequested=true;
            createVideo();
        });
        diagnostics=button("הצג אבחון טכני");''')

main=once(main,'    private TextView sectionLabel(String heading){',
'''    private boolean cpuPhotoRequested=false;
    private void startCpuPhotoMotion(Uri first,Uri second,int seconds){
        executor.execute(()->{
            try{
                message("מפיק סרטון עריכת תמונות אמיתי במעבד השרת...");
                File output=PrivateRenderClient.renderPhotoMotion(this,first,second,
                    seconds,getCacheDir(),stage->message(stage));
                OutputLengthGate.verify(output,seconds);
                showResult(output,"נערכה תנועת מצלמה על תמונות המקור. זה אינו סרטון AI עם דמויות מדברות או שרות.");
            }catch(Exception e){
                message("עריכת התמונות נכשלה: "+e.getMessage());
                busy(false);
            }
        });
    }
    private TextView sectionLabel(String heading){''')

main=once(main,'        final int desired=durationSeconds;',
'''        final int desired=durationSeconds;
        if(cpuPhotoRequested){
            cpuPhotoRequested=false;
            if(!PrivateRenderClient.configured(this)){
                message("יש לחבר תחילה את שרת הניסוי המאובטח בהגדרות המתקדמות");
                return;
            }
            if(chosen==null){
                message("נדרשת תמונה אחת לפחות לעריכת סרטון מתמונות");
                return;
            }
            if(desired<2||desired>12){
                message("עריכת תמונות חינמית תומכת ב־2 עד 12 שניות. לא נשנה את האורך שביקשת.");
                return;
            }
            new AlertDialog.Builder(this)
                .setTitle("יצירת וידאו מתמונות — ללא AI")
                .setMessage("אפיק סרטון תנועת מצלמה מתוך התמונות שבחרת בלבד, ללא דיבור, שירה או פעולות של הדמויות. העיבוד יתבצע בשרת שלך ולא יישלח למנוע AI חיצוני. עליך להחזיק בזכויות השימוש בתמונות. אין הבטחת שימוש בלתי מוגבל בשרת Free. להמשיך?")
                .setPositiveButton("מאשר ויוצר",(d,w)->{
                    busy(true);
                    startCpuPhotoMotion(chosen,second,desired);
                })
                .setNegativeButton("ביטול",(d,w)->{})
                .show();
            return;
        }''')

start='        HttpURLConnection conn=open(ctx,"/v1/jobs","POST",120000);'
end='\n    }\n}'
a=client.index(start)
z=client.rfind(end)
if a<0 or z<0 or z<=a:raise SystemExit('v418 cannot extract existing secured job flow')
job=client[a:z] # POST, polling, signed result verification
job=job.replace('open(ctx,"/v1/jobs","POST",120000)',
                'open(ctx,"/v1/studio/jobs","POST",120000)',1)
if '/v1/studio/jobs' not in job:raise SystemExit('CPU endpoint absent')
method='''    static File renderPhotoMotion(Context ctx,Uri photoOne,Uri photoTwo,
        int duration,File cache,Status status) throws Exception {
        if(photoOne==null)throw new Exception("יש לבחור תמונה אחת לפחות");
        if(duration<2||duration>12)throw new Exception("נדרשות 2–12 שניות");
        JSONObject info=check(ctx).optJSONObject("cpu_photo_studio");
        if(info==null||!"cpu_photo_motion".equals(info.optString("mode","")))
            throw new Exception("שרת העריכה אינו תומך במסלול תמונות CPU");
        JSONObject payload=new JSONObject();
        payload.put("mode","cpu_photo_motion");
        payload.put("seconds",duration);
        payload.put("media_rights_attested",true);
        JSONArray images=new JSONArray();
        images.put(image(ctx,photoOne));
        if(photoTwo!=null)images.put(image(ctx,photoTwo));
        payload.put("images",images);
        // No audio claims. User soundtrack WAV upload will be a separate opt-in.
''' + job + '\n    }\n'
client=client[:z+len('\n    }')]+ '\n' + method + client[z+len('\n    }'):]
for old,new in [
    ("applicationId 'com.kolbo.videostudio.preview416'",
     "applicationId 'com.kolbo.videostudio.preview418'"),
    ("versionCode 416","versionCode 418"),
    ("versionName '4.1.6'","versionName '4.1.8'"),
]:
    gradle=once(gradle,old,new)
assert 'cpuPhotoRequested' in main
assert 'static File renderPhotoMotion' in client
assert '"/v1/studio/jobs"' in client
assert 'AndroidKeyStore' in client
assert 'media_rights_attested' in client
main_file.write_text(main,encoding='utf-8')
client_file.write_text(client,encoding='utf-8')
gradle_file.write_text(gradle,encoding='utf-8')
print('PASS v418 Android: explicit honest CPU photo button, unchanged AI route, separate provider-free API')
