from pathlib import Path
import shutil,sys
root=Path(sys.argv[1])
base=root/'app/src/main/java/com/kolbo/videostudio'
main=base/'MainActivity.java'
gradle=root/'app/build.gradle'
s=main.read_text(encoding='utf-8')

def change(before,after):
    global s
    count=s.count(before)
    if count!=1:raise SystemExit('v403 patch mismatch (%s) on: %s'%(count,before[:110]))
    s=s.replace(before,after,1)

# Show a deterministic, locally prepared shot plan BEFORE the cloud request.
change('.setMessage("שתי התמונות שבחרת יוצגו בנפרד למנוע MSR רב-ייחוסים ציבורי של Hugging Face. בניגוד למנוע הישן לא נבנה קולאז\' בין שתי הדמויות. השירות כפוף לעומסים ולמכסת GPU משותפת, והפקה אינה מובטחת. התמונות יישלחו לספק חיצוני רק אחרי אישורך. גם עם MSR אין הבטחת זהות מושלמת, ריקוד מדויק או שירה בבוכרית. אפשר לשמור תוצאה כטיוטה לבדיקה.")',
       '.setMessage("תוכנית הפעולות לפי הסדר (תכנון ראשוני, לא הבטחת ביצוע):\\n"+StoryboardPlanner.plan(instruction,desired).preview()+"\\n\\nהתמונות יישלחו בנפרד ל-MS R ציבורי לאחר אישור. השירות מוגבל במכסות GPU, ושמירת זהות או ביצוע פעולות אינם מובטחים. אין הפקה אוטומטית במנוע חלופי כאשר MSR מוגבל.".replace("MS R","MSR"))')
# Use a distinct stage prompt for each planned action, not the entire story again.
begin=s.index('                int remaining=desiredSeconds,part=0;\n',s.index('private void startMSRVideo('))
end=s.index('                File output;\n',begin)
old=s[begin:end]
new='''                StoryboardPlanner.Plan plan=StoryboardPlanner.plan(translatedPrompt,desiredSeconds);
                int part=0;
                for(StoryboardPlanner.Scene scene:plan.scenes){
                    int inScene=scene.seconds;
                    while(inScene>0){
                        int secs=Math.min(8,inScene);part++;
                        message("מתוכנן שלב "+scene.index+"/"+plan.scenes.size()
                            +" · מקטע "+part+" ("+secs+" שניות)");
                        String scenePrompt=common+" "+StoryboardPlanner.stagePrompt(scene,plan.scenes.size(),true);
                        File clip=MultiSubjectReferenceClient.generate(firstBytes,firstMime,secondBytes,secondMime,
                            scenePrompt,secs,getCacheDir(),detail->message(detail));
                        clips.add(clip);
                        inScene-=secs;
                    }
                }
'''
s=s[:begin]+new+s[end:]
change('String review="הסרטון הופק באמצעות MSR עם שתי תמונות ייחוס נפרדות. זהות הפנים, תנועת השפתיים ושפת השירה עדיין לא אומתו.";',
       'String review="הופקו "+plan.scenes.size()+" שלבי תוכנית. זהות האנשים, רצף הפעולות, תנועת השפתיים ושפת השירה לא אומתו. ייתכנו מעברים לא רציפים.";')
change('''                message("הפקת MSR לא הושלמה: "+(e.getMessage()==null?e.getClass().getSimpleName():e.getMessage())
                    +" · השירות הציבורי עשוי להיות עמוס או מוגבל. לא הוחלף אוטומטית למנוע קולאז׳.");
                busy(false);''',
       '''                message(ProviderFailure.explain(e));
                if(!clips.isEmpty() && clips.get(0).exists()){
                    // Preserve work completed before reaching a provider quota.
                    // Never label partial video as a completed requested film.
                    showResult(clips.get(0),"טיוטה חלקית בלבד, לא באורך המבוקש. "+ProviderFailure.explain(e));
                }else busy(false);''')
# Apply a per-shot plan to all non-MSR routes too, including text-only.
begin=s.index('                int remaining=requestedSeconds;\n',s.index('private void startRemoteVideo('))
end=s.index('                File combined;\n',begin)
old=s[begin:end]
new='''                StoryboardPlanner.Plan plan=StoryboardPlanner.plan(englishPrompt,requestedSeconds);
                int part=0;
                for(StoryboardPlanner.Scene scene:plan.scenes){
                    int inScene=scene.seconds;
                    while(inScene>0){
                        int seconds=Math.min(inScene,SEGMENT_MAX);
                        part++;
                        message("מנוע בסיסי · שלב "+scene.index+"/"+plan.scenes.size()
                            +" · מקטע "+part+" ("+seconds+" שניות)");
                        String chunkPrompt=plan.scenes.size()==1
                            ?scenePrompt
                            :StoryboardPlanner.stagePrompt(scene,plan.scenes.size(),second!=null);
                        if(part>1)chunkPrompt="Continue from the supplied initial frame with the SAME characters and environment. "+chunkPrompt;
                        String event=submit(chunkPrompt,imageMeta,seconds);
                        String media=awaitResult(event);
                        File file=getVideo(media);clips.add(file);
                        inScene-=seconds;
                        if(part>0 && (inScene>0 || scene.index<plan.scenes.size())){
                            // Continue from an actual output frame in the original single-image provider.
                            imageMeta=uploadImageBytes(lastFrameJpeg(file),"image/jpeg");
                        }
                    }
                }
'''
s=s[:begin]+new+s[end:]
change('String motionWarning=null;\n                if(second!=null) {',
       'String motionWarning=plan.scenes.size()>1?"הוידאו הורכב ממקטעי סטוריבורד; רצף הפעולות אינו מאומת. ":null;\n                if(second!=null) {')
change('''                String review="הופקו "+plan.scenes.size()+" שלבי תוכנית.''','''                String review="הופקו "+plan.scenes.size()+" שלבי תוכנית.''')
# Clearly label provider status in generic errors too.
change('message("ההפקה לא הושלמה — לא יוצג סרטון קצר מהמבוקש: "+(e.getMessage()!=null?e.getMessage():e.getClass().getSimpleName()));',
       'message("ההפקה לא הושלמה: "+ProviderFailure.explain(e));')
shutil.copyfile('patches/StoryboardPlanner.java',base/'StoryboardPlanner.java')
shutil.copyfile('patches/ProviderFailure.java',base/'ProviderFailure.java')
main.write_text(s,encoding='utf-8')
g=gradle.read_text(encoding='utf-8')
for old,new in [
    ("applicationId 'com.kolbo.videostudio.preview402'","applicationId 'com.kolbo.videostudio.preview403'"),
    ("versionCode 402","versionCode 403"),
    ("versionName '4.0.2'","versionName '4.0.3'")
]:
    if g.count(old)!=1: raise SystemExit('Version patch mismatch '+old)
    g=g.replace(old,new)
gradle.write_text(g,encoding='utf-8')
assert 'StoryboardPlanner.plan(translatedPrompt,desiredSeconds)' in s
assert 'StoryboardPlanner.plan(englishPrompt,requestedSeconds)' in s
assert 'ProviderFailure.explain(e)' in s
print('PASS v403: bounded storyboard planning and transparent quota handling for all routes')
