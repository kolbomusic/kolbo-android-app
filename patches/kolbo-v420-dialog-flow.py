"""Fix v419 Android dead-end from real screenshot, applied AFTER v419.

- CPU mode never requires irrelevant natural-language prompt.
- Primary "Yes, photo edit" routes straight to one rights confirmation.
- CPU dedicated button and primary button share one helper.
- No misleading AI success path and no master secrets embedded.
"""
from pathlib import Path
import sys

root=Path(sys.argv[1])
base=root/'app/src/main/java/com/kolbo/videostudio'
main_file=base/'MainActivity.java'
gradle_file=root/'app/build.gradle'
main=main_file.read_text(encoding='utf-8')
gradle=gradle_file.read_text(encoding='utf-8')

def replace_once(old,new):
    global main
    if main.count(old)!=1:
        raise SystemExit('v420 UI anchor mismatch ('+str(main.count(old))+'): '+old[:120])
    main=main.replace(old,new,1)

replace_once(
'''        if(instruction.isEmpty()) {message("כתוב תחילה מה תרצה לראות בסרטון");return;}''',
'''        // Editing existing photos is NOT prompt-to-video and MUST NOT require text.
        if(instruction.isEmpty() && !cpuPhotoRequested
                && PrivateRenderClient.manualEngineConfigured(this)) {
            message("כתוב תחילה מה תרצה לראות בסרטון");return;
        }''')

replace_once(
'''                .setPositiveButton("כן, עריכת תמונות",(d,w)->{
                    cpuPhotoRequested=true;
                    createVideo();
                })
                .setNegativeButton("לא, להישאר עם בקשת AI",(d,w)->{
                    message("אין כעת מנוע AI חינמי מאומת שתומך בבקשתך. הבקשה לא תישלח כעריכת תמונות.");
                })''',
'''                .setPositiveButton("כן, עריכת תמונות",(d,w)->{
                    // No recursion through createVideo: prompt may be empty,
                    // and a second navigation cycle previously looked broken.
                    confirmCpuPhotoFlow(chosen,second,desired);
                })
                .setNegativeButton("חזור להנחיית AI",(d,w)->{
                    new AlertDialog.Builder(this)
                        .setTitle("אין עדיין מנוע AI שתומך בבקשה")
                        .setMessage("ההנחיה שלך נשארת במסך העריכה, אבל אין כרגע מנוע AI מאומת ליצירת דיבור, שירה, תנועת דמויות או סצנה חדשה. לא הופק סרטון ולא הועלו התמונות.")
                        .setPositiveButton("הבנתי",(dismiss,which)->{})
                        .show();
                })''')

replace_once(
'''        if(cpuPhotoRequested){
            cpuPhotoRequested=false;
            // The public CPU-only guest connection is acquired in the
            // background. Never ask users for a URL or admin API key.
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
        }''',
'''        if(cpuPhotoRequested){
            cpuPhotoRequested=false;
            confirmCpuPhotoFlow(chosen,second,desired);
            return;
        }''')

replace_once(
'''    private void createVideo() {''',
'''    private void confirmCpuPhotoFlow(Uri chosen,Uri second,int desired){
        if(running){
            message("קיימת כרגע הפקה פעילה. יש להמתין לסיומה.");
            return;
        }
        if(chosen==null){
            new AlertDialog.Builder(this)
                .setTitle("נדרשת תמונה לעריכה")
                .setMessage("כדי להפיק סרטון תנועת מצלמה, בחר תחילה תמונה אחת או שתיים בחלק העליון של המסך.")
                .setPositiveButton("הבנתי",(d,w)->{})
                .show();
            return;
        }
        if(desired<2 || desired>12){
            new AlertDialog.Builder(this)
                .setTitle("משך שאינו נתמך")
                .setMessage("מסלול עריכת התמונות החינמי תומך ב־2–12 שניות בלבד. שנה את משך הסרטון ונסה שוב; האפליקציה לא תקצר עבורך את הסרטון ללא רשות.")
                .setPositiveButton("הבנתי",(d,w)->{})
                .show();
            return;
        }
        new AlertDialog.Builder(this)
            .setTitle("אישור יצירת סרטון מתמונות")
            .setMessage("יופק וידאו מתמונותיך עם תנועת מצלמה בלבד, לא אנימציית AI. אין שירה, דיבור או משחק דמויות. הקובץ ייערך בשרת שלנו ללא ספק AI חיצוני; עליך לוודא שיש לך זכויות שימוש בתמונות. האם להפיק עכשיו?")
            .setPositiveButton("צור סרטון MP4 עכשיו",(d,w)->{
                busy(true);
                startCpuPhotoMotion(chosen,second,desired);
            })
            .setNegativeButton("ביטול",(d,w)->{
                message("עריכת התמונות בוטלה; שום סרטון לא נשלח.");
            })
            .show();
    }
    private void createVideo() {''')

for old,new in [
    ("applicationId 'com.kolbo.videostudio.preview419'","applicationId 'com.kolbo.videostudio.preview420'"),
    ("versionCode 419","versionCode 420"),
    ("versionName '4.1.9'","versionName '4.2.0'"),
]:
    if gradle.count(old)!=1:
        raise SystemExit('v420 Android version anchor missing: '+old)
    gradle=gradle.replace(old,new,1)

assert 'if(instruction.isEmpty() && !cpuPhotoRequested' in main
assert 'confirmCpuPhotoFlow(chosen,second,desired);' in main
assert 'cpuPhotoRequested=true;\n                    createVideo();' not in main
assert 'startCpuPhotoMotion(chosen,second,desired);' in main
assert 'ensureAutoConnected(this)' in main
main_file.write_text(main,encoding='utf-8')
gradle_file.write_text(gradle,encoding='utf-8')
print('PASS v420: no prompt dependency for photo editor, direct confirmed flow, one rights dialog, explicit unavailable AI')
