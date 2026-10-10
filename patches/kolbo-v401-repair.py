from pathlib import Path
import sys

root=Path(sys.argv[1])
main=root/'app/src/main/java/com/kolbo/videostudio/MainActivity.java'
gradle=root/'app/build.gradle'
s=main.read_text(encoding='utf-8')

def replace_one(old,new):
    global s
    if s.count(old)!=1: raise SystemExit(f'Patch input mismatch for {old[:80]!r}: {s.count(old)}')
    s=s.replace(old,new,1)

# Preserve full-body dance and singing instructions. The old code accidentally
# overwrote this with the original plain-English prompt.
replace_one('No split-screen, no inserted portraits, no reaction cutaways and NO additional bystanders. " + englishPrompt;',
            'No split-screen, no inserted portraits, no reaction cutaways and NO additional bystanders. " + scenePrompt;')

# Retain a generated MP4 as a transparently labeled draft on motion-only QA
# failure instead of discarding the generated result as a total failure.
replace_one('private void finalMix(File raw,File speech,String instruction,boolean failedTts){',
            'private void finalMix(File raw,File speech,String instruction,boolean failedTts,String qualityWarning){')
replace_one('showResult(raw,"הסרטון התקבל · אין אפקטים נוספים לבצע. בדוק שהסצנה מתאימה לבקשה.");return;',
            'showResult(raw,(qualityWarning!=null?qualityWarning:"הסרטון התקבל · אין אפקטים נוספים לבצע. בדוק שהסצנה מתאימה לבקשה."));return;')
replace_one('String report="הסרטון הושלם";',
            'String report=qualityWarning!=null?qualityWarning:"הסרטון הושלם";')
replace_one('showResult(raw,"הווידאו התקבל, אך שילוב האודיו נכשל: "+e.getMessage()+" · אפשר לשמור את הקובץ המקורי");',
            'showResult(raw,(qualityWarning!=null?qualityWarning+" · ":"")+"הווידאו התקבל, אך שילוב האודיו נכשל: "+e.getMessage()+" · אפשר לשמור את הקובץ המקורי");')
replace_one('private void audioAfterVideo(File raw,String instruction){',
            'private void audioAfterVideo(File raw,String instruction,String qualityWarning){')
replace_one('if(phrase==null){finalMix(raw,null,instruction,false);return;}',
            'if(phrase==null){finalMix(raw,null,instruction,false,qualityWarning);return;}')
replace_one('if(!voiceAvailable||hebrewVoice==null){finalMix(raw,null,instruction,true);return;}',
            'if(!voiceAvailable||hebrewVoice==null){finalMix(raw,null,instruction,true,qualityWarning);return;}')
replace_one('executor.execute(() -> finalMix(raw,voice,instruction,false));',
            'executor.execute(() -> finalMix(raw,voice,instruction,false,qualityWarning));')
if s.count('executor.execute(() -> finalMix(raw,null,instruction,true));')!=2:
    raise SystemExit('TTS callbacks changed')
s=s.replace('executor.execute(() -> finalMix(raw,null,instruction,true));',
            'executor.execute(() -> finalMix(raw,null,instruction,true,qualityWarning));')
replace_one('''                if(second!=null) {
                    // Count is only a coarse guard; ML Kit does NOT verify who people are.
                    message("בודק שלא נוספו דמויות נוספות בסרטון...");
                    TwoPersonComposer.checkVideoCount(combined);
                    if(wantsGroupDance(originalInstruction)) {
                        message("בודק ששתי הדמויות זזות מספיק לאורך הסרטון...");
                        DuoDanceMotionGate.requireVisibleDuoMovement(combined);
                    }
                }
                audioAfterVideo(combined,originalInstruction);''', '''                String motionWarning=null;
                if(second!=null) {
                    // Count is only a coarse guard; ML Kit does NOT verify who people are.
                    message("בודק שלא נוספו דמויות נוספות בסרטון...");
                    TwoPersonComposer.checkVideoCount(combined);
                    if(wantsGroupDance(originalInstruction)) {
                        message("בודק ששתי הדמויות זזות מספיק לאורך הסרטון...");
                        try {
                            DuoDanceMotionGate.requireVisibleDuoMovement(combined);
                        } catch(Exception insufficientMotion) {
                            // Preserve MP4, but never label an unsupported dance a success.
                            motionWarning="נוצר סרטון, אך הוא לא עומד בדרישת הריקוד של שתי הדמויות. "+insufficientMotion.getMessage()+" ניתן לצפות ולשמור טיוטה בלבד.";
                        }
                    }
                }
                audioAfterVideo(combined,originalInstruction,motionWarning);''')
main.write_text(s,encoding='utf-8')

# Android MediaMetadataRetriever OPTION_CLOSEST_SYNC may return the exact
# same keyframe for several requested times. Sample nearby real frames instead.
motion_file=root/'app/src/main/java/com/kolbo/videostudio/DuoDanceMotionGate.java'
motion=motion_file.read_text(encoding='utf-8')
old='retriever.getFrameAtTime(t*1000L,MediaMetadataRetriever.OPTION_CLOSEST_SYNC)'
if motion.count(old)!=1: raise SystemExit('Motion sampler changed')
motion=motion.replace(old,'retriever.getFrameAtTime(t*1000L,MediaMetadataRetriever.OPTION_CLOSEST)')
motion_file.write_text(motion,encoding='utf-8')

g=gradle.read_text(encoding='utf-8')
for old,new in [("versionCode 400","versionCode 401"),("versionName '4.0.0'","versionName '4.0.1'")]:
    if g.count(old)!=1: raise SystemExit('Version metadata changed')
    g=g.replace(old,new)
gradle.write_text(g,encoding='utf-8')

assert 'NO additional bystanders. " + englishPrompt;' not in s
assert 'NO additional bystanders. " + scenePrompt;' in s
assert 'audioAfterVideo(combined,originalInstruction,motionWarning);' in s
print('PASS v4.0.1: dance prompt no longer overwritten; QA failure leaves inspectable draft')
