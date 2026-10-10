from pathlib import Path
import shutil,sys
root=Path(sys.argv[1])
base=root/'app/src/main/java/com/kolbo/videostudio'
main=base/'MainActivity.java'
s=main.read_text(encoding='utf-8')

def change(old,new):
    global s
    if s.count(old)!=1:raise SystemExit("MSR patch input mismatch "+str(s.count(old))+": "+old[:100])
    s=s.replace(old,new,1)

change('private volatile boolean identityReviewRequired;',
       'private volatile boolean identityReviewRequired;\n    private volatile boolean useMultiReferenceProvider;')
change('if(second!=null){previewDuoBeforeUpload(instruction,chosen,second,desired);return;}',
       '''if(second!=null){
            new AlertDialog.Builder(this)
                .setTitle("שתי דמויות — מנוע רב-ייחוס")
                .setMessage("שתי התמונות שבחרת יוצגו בנפרד למנוע MSR רב-ייחוסים ציבורי של Hugging Face. בניגוד למנוע הישן לא נבנה קולאז' בין שתי הדמויות. השירות כפוף לעומסים ולמכסת GPU משותפת, והפקה אינה מובטחת. התמונות יישלחו לספק חיצוני רק אחרי אישורך. גם עם MSR אין הבטחת זהות מושלמת, ריקוד מדויק או שירה בבוכרית. אפשר לשמור תוצאה כטיוטה לבדיקה.")
                .setPositiveButton("נסה MSR עם שתי התמונות",(d,w)->{
                    useMultiReferenceProvider=true;
                    approvedComposite=null;
                    beginGeneration(instruction,chosen,second,desired);
                })
                .setNeutralButton("מנוע ישן (לא מומלץ)",(d,w)->{
                    useMultiReferenceProvider=false;
                    previewDuoBeforeUpload(instruction,chosen,second,desired);
                })
                .setNegativeButton("ביטול",(d,w)->{})
                .show();
            return;
        }''')
change('if(!hasHebrew(instruction)) { startRemoteVideo(instruction,chosen,second,instruction,requestedSeconds);return; }',
       'if(!hasHebrew(instruction)) { if(second!=null&&useMultiReferenceProvider)startMSRVideo(instruction,chosen,second,instruction,requestedSeconds); else startRemoteVideo(instruction,chosen,second,instruction,requestedSeconds);return; }')
change('startRemoteVideo(enhanced,chosen,second,instruction,requestedSeconds);',
       '''if(second!=null&&useMultiReferenceProvider){
                      if(originalRequestIsBukharianSinging(instruction)) enhanced+=" Image 1 and Image 2 must sing in BUKHORI (Bukharian Judeo-Tajik), not English. No unrelated English captions.";
                      startMSRVideo(enhanced,chosen,second,instruction,requestedSeconds);
                  }else startRemoteVideo(enhanced,chosen,second,instruction,requestedSeconds);''')
change('private static boolean wantsGroupDance(String text){',
       '''private static boolean originalRequestIsBukharianSinging(String text){
        return text.contains("בוכר") && wantsSinging(text);
    }
    private void startMSRVideo(String translatedPrompt,Uri first,Uri second,
            String originalInstruction,int desiredSeconds){
        message("MSR: מכין שתי תמונות ייחוס נפרדות...");
        executor.execute(() -> {
            List<File> clips=new ArrayList<>();
            try {
                if(first==null||second==null)throw new Exception("חסרה אחת משתי תמונות המקור");
                final byte[] firstBytes=imageBytes(first),secondBytes=imageBytes(second);
                final String firstMime=getContentResolver().getType(first);
                final String secondMime=getContentResolver().getType(second);
                String common="Generate one cinematic shared scene with exactly TWO distinct characters. "
                    +"Image 1 is character 1; Image 2 is character 2. Preserve visual attributes and clothing "
                    +"of EACH corresponding original person, never swap identities, duplicate a subject, "
                    +"invent an additional person or replace either subject with a uniformed actor. "
                    +"Keep both in one location and show both performing the requested actions. "
                    +(wantsGroupDance(originalInstruction)?
                      "Both people dance together with visibly moving legs, feet and arms. ":"")
                    +(originalRequestIsBukharianSinging(originalInstruction)?
                      "Both sing in the Bukhori language, without English dialogue. ":"")
                    +translatedPrompt;
                int remaining=desiredSeconds,part=0;
                while(remaining>0){
                    part++;
                    int secs=Math.min(8,remaining);
                    message("MSR יוצר מקטע "+part+" ("+secs+" שניות) · שתי תמונות מקור");
                    // Each segment receives the TWO unmodified original reference images.
                    // Longer output may have visible discontinuities between chunks.
                    File clip=MultiSubjectReferenceClient.generate(firstBytes,firstMime,secondBytes,secondMime,
                        (part==1?common:"Continue the same two-character performance and clothing. "+common),
                        secs,getCacheDir(),detail->message(detail));
                    clips.add(clip);
                    remaining-=secs;
                }
                File output;
                if(clips.size()==1)output=clips.get(0);
                else {
                    message("משלב "+clips.size()+" מקטעי MSR; ייתכנו קפיצות בין מקטעים");
                    output=new File(getCacheDir(),"kolbo-msr-joined-"+System.currentTimeMillis()+".mp4");
                    ClipConcatenator.combine(clips,output,desiredSeconds);
                    for(File c:clips)c.delete();
                }
                ClipConcatenator.validateLength(output,desiredSeconds);
                String review="הסרטון הופק באמצעות MSR עם שתי תמונות ייחוס נפרדות. זהות הפנים, תנועת השפתיים ושפת השירה עדיין לא אומתו.";
                try {
                    TwoPersonComposer.checkVideoCount(output);
                } catch(Exception e) {
                    review+=" מספר הדמויות לא אומת: "+e.getMessage();
                }
                if(wantsGroupDance(originalInstruction)){
                    try{DuoDanceMotionGate.requireVisibleDuoMovement(output);}
                    catch(Exception e){review+=" התנועה אינה מספקת לפי בדיקת התנועה: "+e.getMessage();}
                }
                audioAfterVideo(output,originalInstruction,review);
            } catch(Exception e){
                message("הפקת MSR לא הושלמה: "+(e.getMessage()==null?e.getClass().getSimpleName():e.getMessage())
                    +" · השירות הציבורי עשוי להיות עמוס או מוגבל. לא הוחלף אוטומטית למנוע קולאז׳.");
                busy(false);
            }
        });
    }
    private static boolean wantsGroupDance(String text){''')
# Install separate multi-ref adapter into extracted Android source.
shutil.copyfile('patches/MultiSubjectReferenceClient.java',base/'MultiSubjectReferenceClient.java')
main.write_text(s,encoding='utf-8')
assert 'startMSRVideo(enhanced,chosen,second,instruction,requestedSeconds)' in s
assert 'MultiSubjectReferenceClient.generate(firstBytes,firstMime,secondBytes,secondMime' in s
assert 'imageMeta=uploadImageBytes(reference!=null?reference:jointReference(first,second)' in s
assert 'if(second!=null&&useMultiReferenceProvider)' in s
assert (base/'MultiSubjectReferenceClient.java').exists()
print('PASS v4.0.2: native dual-reference adapter; no single-image collage on MSR path; explicit opt-in')
