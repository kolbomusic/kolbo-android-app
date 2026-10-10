from pathlib import Path
import sys
root=Path(sys.argv[1])
main=root/'app/src/main/java/com/kolbo/videostudio/MainActivity.java'
gradle=root/'app/build.gradle'
s=main.read_text(encoding='utf-8')
def once(old,new):
    global s
    count=s.count(old)
    if count!=1: raise SystemExit(f'v409 expected one match ({count}): {old[:100]!r}')
    s=s.replace(old,new,1)

# Never describe Agnes-backed generation as solely a private self-controlled model.
once('privateSettings=button("חיבור מנוע הפקה עצמאי");',
     'privateSettings=button("חיבור שרת הפקה (GPU / Agnes)");')
once('''TextView instruction=label("שרת GPU בשליטתך, עם ComfyUI ומודל וידאו. נדרש HTTPS. אין מכסת קרדיטים בתוך האפליקציה, אך חומרת השרת מגבילה ביצועים. לא קיים שרת מובנה שמופעל בחינם.",13,false);''',
     '''TextView instruction=label("ניתן לחבר שרת HTTPS ייעודי שמפעיל GPU פרטי או מפנה אל Agnes Flash. במסלול Agnes התמונות נשלחות גם לספק חיצוני דרך קישורים זמניים, בכפוף לתנאי שימוש, עומס, מכסות ומחיר המבצע בחשבון. לא כלול שרת מוכן או מנוי.",13,false);''')
once('''            .setTitle("מנוע וידאו עצמאי")
            .setView(form)''',
     '''            .setTitle("חיבור שרת הפקה")
            .setView(form)''')
once('''                            if("ready".equals(check.optString("status")))
                                message("השרת הפרטי מחובר ומוכן ליצירה");
                            else message("החיבור נשמר, אבל המנוע עדיין לא מוכן: "
                                +check.optString("detail","נדרש GPU ו־Workflow"));''',
     '''                            if("ready".equals(check.optString("status"))){
                                String provider=check.optString("provider","comfy");
                                if(provider.startsWith("agnes"))
                                    message("שער Agnes מחובר; התור, ההרשאות והמחיר בפועל לא אומתו בהפקה חיה.");
                                else message("שרת ההפקה מחובר; איכות הסרטון עדיין טעונה בדיקה.");
                            }else message("החיבור נשמר, אבל שרת ההפקה עדיין לא מוכן: "
                                +check.optString("detail","חסרים נתוני שרת או מנוע וידאו"));''')
once('''                .setTitle("יצירה במנוע הפרטי")
                .setMessage("התמונות וההנחיה יישלחו רק לשרת העצמאי שהגדרת. להמשיך?")''',
     '''                .setTitle("יצירה דרך שרת הפקה")
                .setMessage("התמונות וההנחיה יישלחו לשרת שהגדרת. אם הוא משתמש ב־Agnes או בספק AI בענן, התמונות יישלחו גם לספק החיצוני דרך קישורים זמניים. שירותים אלה עשויים להיות עמוסים, מוגבלים או בתשלום כאשר מבצע מסתיים. האם אתה מסכים להמשיך?")''')
once('''message("מכינים סרטון במנוע הפרטי...");''',
     '''message("שולחים בקשה לשרת ההפקה...");''')
once('''recordSubmittedPrompt("שרת וידאו עצמאי",compiled);''',
     '''recordSubmittedPrompt("שרת הפקה מחובר (GPU או Agnes)",compiled);''')
once('''showResult(output,"נוצר במנוע פרטי. הפנים, התוכן והשמע עדיין דורשים בדיקה.");''',
     '''showResult(output,"הסרטון חזר משרת ההפקה. הפנים, התוכן והשמע עדיין דורשים בדיקה.");''')
once('''message("ההפקה במנוע הפרטי לא הושלמה: "+e.getMessage());''',
     '''message("ההפקה בשרת המחובר לא הושלמה: "+e.getMessage());''')
g=gradle.read_text(encoding='utf-8')
for old,new in [
    ("applicationId 'com.kolbo.videostudio.preview408'","applicationId 'com.kolbo.videostudio.preview409'"),
    ("versionCode 408","versionCode 409"),
    ("versionName '4.0.8'","versionName '4.0.9'")
]:
    if g.count(old)!=1:raise SystemExit('Android version patch mismatch '+old)
    g=g.replace(old,new,1)
gradle.write_text(g,encoding='utf-8')
main.write_text(s,encoding='utf-8')
assert "אם הוא משתמש ב־Agnes או בספק AI בענן" in s
assert 'recordSubmittedPrompt("שרת הפקה מחובר (GPU או Agnes)"' in s
assert "price" not in [] # prevent missing assert template
print('PASS v4.0.9: explicit third-party photo transfer consent; provider/price transparency; no engine fallback claims')
