"""Integrate explicit opt-in CPU sound into existing v420 photo editor flow.

Voice/lipsync/singing requests are NOT fulfilled by this optional synthetic
sound effect feature. No external media supplier, no paid API credentials.
"""
from pathlib import Path
import sys

root=Path(sys.argv[1])
base=root/"app/src/main/java/com/kolbo/videostudio"
main_file=base/"MainActivity.java"
client_file=base/"PrivateRenderClient.java"
gradle_file=root/"app/build.gradle"
main=main_file.read_text(encoding="utf-8")
client=client_file.read_text(encoding="utf-8")
gradle=gradle_file.read_text(encoding="utf-8")

def rep(which,anchor,changed):
    values={"main":main,"client":client,"gradle":gradle}
    data=values[which]
    n=data.count(anchor)
    if n!=1:raise SystemExit("v421 wrong anchor "+which+" "+str(n)+": "+anchor[:120])
    return data.replace(anchor,changed,1)

main=rep("main",
    '                PrivateRenderClient.ensureAutoConnected(this);\n                File output=PrivateRenderClient.renderPhotoMotion(this,first,second,\n                    seconds,getCacheDir(),stage->message(stage));',
    '''                PrivateRenderClient.ensureAutoConnected(this);
                File output=PrivateRenderClient.renderPhotoMotion(this,first,second,
                    seconds,cpuEffectDescription,getCacheDir(),stage->message(stage));''')
main=rep("main",
    '    private void startCpuPhotoMotion(Uri first,Uri second,int seconds){',
    '''    private void startCpuPhotoMotion(Uri first,Uri second,int seconds){
        final String cpuEffectDescription=prompt.getText().toString().trim();''')
main=rep("main",
    '            .setMessage("יופק וידאו מתמונותיך עם תנועת מצלמה בלבד, לא אנימציית AI. אין שירה, דיבור או משחק דמויות. הקובץ ייערך בשרת שלנו ללא ספק AI חיצוני; עליך לוודא שיש לך זכויות שימוש בתמונות. האם להפיק עכשיו?")',
    '            .setMessage("יופק וידאו מתמונותיך עם תנועת מצלמה בלבד, לא אנימציית AI. אין שירה, דיבור או משחק דמויות. אם ההנחיה מזכירה במפורש נפיחה, גשם, מחיאות כפיים או ציוץ יתווסף צליל מלאכותי מסונתז, לא קול אמיתי של הדמות. הקובץ ייערך בשרת שלנו ללא ספק AI חיצוני; עליך לוודא שיש לך זכויות שימוש בתמונות. האם להפיק עכשיו?")')
client=rep("client",
    '    static File renderPhotoMotion(Context ctx,Uri photoOne,Uri photoTwo,\n        int duration,File cache,Status status) throws Exception {',
    '''    static File renderPhotoMotion(Context ctx,Uri photoOne,Uri photoTwo,
        int duration,String effectDescription,File cache,Status status) throws Exception {''')
client=rep("client",
    '        payload.put("media_rights_attested",true);\n        JSONArray images=new JSONArray();',
    '''        payload.put("media_rights_attested",true);
        // A narrow, server-verified, procedural SFX request. It never changes
        // the requested video action, creates narration or calls AI providers.
        if(effectDescription!=null && effectDescription.length()>0){
            payload.put("include_procedural_effect",true);
            payload.put("sound_effect_description",
                effectDescription.substring(0,Math.min(effectDescription.length(),3000)));
        }
        JSONArray images=new JSONArray();''')
for old,new in [
    ("applicationId 'com.kolbo.videostudio.preview420'",
     "applicationId 'com.kolbo.videostudio.preview421'"),
    ("versionCode 420","versionCode 421"),
    ("versionName '4.2.0'","versionName '4.2.1'")
]:
    gradle=rep("gradle",old,new)
assert 'cpuEffectDescription' in main
assert 'include_procedural_effect' in client
assert 'sound_effect_description' in client
assert 'No' not in [] 
main_file.write_text(main,encoding="utf-8")
client_file.write_text(client,encoding="utf-8")
gradle_file.write_text(gradle,encoding="utf-8")
print("PASS v421: user-approved synthesized sound effect wired to real CPU video, no voice/lipsync claim")
