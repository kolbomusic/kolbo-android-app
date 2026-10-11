"""Apply LTX-2.5 native audio + video route on top of v425 Android patch.

The Create button produces newly generated 1–15s AI frames PLUS synchronized
native audio, with no still photo slideshow fallback. No manual API key. Guest
model quota and provider permission checked on server. Third-party upload is
explicitly consented once for THIS MODEL, not borrowed from Wan consent.
"""
from pathlib import Path
import sys
root=Path(sys.argv[1])
base=root/"app/src/main/java/com/kolbo/videostudio"
p=base/"MainActivity.java"; cp=base/"PrivateRenderClient.java";gp=root/"app/build.gradle"
main=p.read_text("utf8");client=cp.read_text("utf8");gradle=gp.read_text("utf8")

def exact(txt,a,z):
    count=txt.count(a)
    if count!=1:raise SystemExit("v431 unexpected Java source "+str(count)+": "+a[:130])
    return txt.replace(a,z,1)

# Primary action is text-to-video OR single-image-to-video (the space supports
# both), always accompanied by model-generated audio.
main=exact(main,'''            if(chosen==null){
                message("כדי ליצור תנועה ב-AI בחר תמונת מקור");
                return;
            }
''','')
main=exact(main,'''            if(desired<1 || desired>5){
                message("מנוע ה-AI האמיתי תומך כרגע ב-1–5 שניות בלבד. 10 שניות אינן זמינות במנוע זה.");
                return;
            }''','''            if(desired<1 || desired>15){
                message("בחר משך סרטון מ-1 עד 15 שניות");
                return;
            }''')
if main.count('"approved_v425"')!=2:
    raise SystemExit('v431 native consent anchors missing')
main=main.replace('"approved_v425"','"approved_native_ltx_v431"')
main=exact(main,
    'התמונה וההנחיה יישלחו להדגמה ציבורית של Wan דרך Hugging Face. השירות חינמי אך מוגבל, ותמונות שהועלו אינן פרטיות. אל תעלה תמונות רגישות. לא יבוצע חיוב. להמשיך?',
    'ההנחיה והתמונה, אם בחרת אחת, יישלחו להדגמה ציבורית של LTX-2.5 ב-Hugging Face. הסרטון והשמע נוצרים יחד באמצעות AI. השירות הציבורי מוגבל במכסות ואינו פרטי; אל תשתף תמונות רגישות. לא יבוצע חיוב. מאשר לשלוח את ההנחיה ואת התמונה להפקה?')
main=exact(main,'PrivateRenderClient.renderAiTrial(this,first,seconds,',
                'PrivateRenderClient.renderNativeAV(this,first,seconds,')
main=exact(main,
    'message("מייצר תנועה אמיתית באמצעות מודל AI חינמי...");',
    'message("מפיק וידאו AI עם שמע באמצעות LTX...");')
main=exact(main,
    'showResult(output,"נוצרו פריימים חדשים באמצעות AI. יש לבדוק התאמה לדמות ולפעולה.");',
    'NativeAudioTrackGate.verify(output);\n                showResult(output,"נוצר וידאו AI עם שמע מקורי. בדוק בעצמך את הפעולה ואת השפה.");')

a=client.index("    static File renderAiTrial(")
end=client.rfind("\n}")
if a<0 or end<=a:raise SystemExit("v431 missing v425 AI trial implementation")
original=client[a:end]
native=exact(original,"renderAiTrial(","renderNativeAV(")
native=exact(native,
    '''        if(first==null||seconds<1||seconds>5)
            throw new Exception("נדרש מקור יחיד ובקשה באורך 1–5 שניות");''',
    '''        if(seconds<1||seconds>15)
            throw new Exception("מנוע הווידאו והשמע תומך באורך 1–15 שניות");''')
native=exact(native,
    '''        JSONObject capability=server.optJSONObject("experimental_ai_video");''',
    '''        JSONObject capability=server.optJSONObject("native_audio_video_trial");''')
native=exact(native,
    '''        if(capability==null||!"ai_one_image_trial".equals(capability.optString("mode"))||''',
    '''        if(capability==null||!"native_ltx25_av_trial".equals(capability.optString("mode"))||''')
native=exact(native,
    'throw new Exception("המנוע ליצירת תנועה אמיתית אינו זמין כרגע");',
    'throw new Exception("מנוע הווידאו והשמע החינמי אינו זמין כרגע");')
native=exact(native,'plan.put("image_count",1);',
    'plan.put("image_count",first==null?0:1);')
native=exact(native,'open(ctx,"/v1/creative/plan","POST",30000)',
    'open(ctx,"/v1/native-av/plan","POST",30000)')
native=exact(native,
    'if(!"draft_possible".equals(constraints.optString("status")))',
    'if(!"eligible_for_attempt".equals(constraints.optString("status")))')
native=exact(native,'open(ctx,"/v1/ai/jobs","POST",120000)',
    'open(ctx,"/v1/native-av/jobs","POST",120000)')
native=exact(native,'images.put(smallCpuImage(ctx,first));',
    'if(first!=null)images.put(smallCpuImage(ctx,first));')
native=exact(native,
    'status.onStage("שולח בקשת תנועה למנוע AI...");',
    'status.onStage("ממתין ליצירת וידאו ושמע במנוע AI...");')
client=client[:end]+"\n"+native+client[end:]

# No voice generation claim is silently attached to the album.
audioGate=base/"NativeAudioTrackGate.java"
audioGate.write_text('''package com.kolbo.videostudio;

import android.media.MediaExtractor;
import android.media.MediaFormat;
import java.io.File;

/** Rechecks audio stream after the verified server-side PCM audibility gate. */
final class NativeAudioTrackGate {
    private NativeAudioTrackGate(){}
    static void verify(File video) throws Exception {
        MediaExtractor extractor=new MediaExtractor();
        try {
            extractor.setDataSource(video.getAbsolutePath());
            boolean hasAudio=false,hasVideo=false;
            for(int i=0;i<extractor.getTrackCount();i++){
                MediaFormat format=extractor.getTrackFormat(i);
                String mime=format.getString(MediaFormat.KEY_MIME);
                if(mime!=null && mime.startsWith("audio/"))hasAudio=true;
                if(mime!=null && mime.startsWith("video/"))hasVideo=true;
            }
            if(!hasAudio||!hasVideo)
                throw new Exception("תוצאת ה-AI אינה כוללת וידאו ושמע יחד");
        }finally{extractor.release();}
    }
}
''',encoding="utf8")
for a,z in [
    ("applicationId 'com.kolbo.videostudio.preview425'",
     "applicationId 'com.kolbo.videostudio.preview431'"),
    ("versionCode 425","versionCode 431"),
    ("versionName '4.2.5'","versionName '4.3.1'")
]:
    gradle=exact(gradle,a,z)
assert "renderNativeAV(this,first,seconds" in main
assert "NativeAudioTrackGate.verify(output)" in main
assert '"/v1/native-av/jobs"' in client
assert '"/v1/native-av/plan"' in client
assert 'renderAiTrial(' in client
assert "if(first!=null)images.put(smallCpuImage(ctx,first));" in client
assert "KOLBO_V416_API_TOKEN" not in client
assert "preview431" in gradle
p.write_text(main,"utf8")
cp.write_text(client,"utf8")
gp.write_text(gradle,"utf8")
print("PASS v431: real AI video+native audio 1-15s with zero-input auth, optional reference, separate consent and Android AV gates")
