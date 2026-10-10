from pathlib import Path
import sys
root=Path(sys.argv[1]);main=root/'app/src/main/java/com/kolbo/videostudio/MainActivity.java';gradle=root/'app/build.gradle'
s=main.read_text(encoding='utf-8')
def once(old,new):
    global s
    n=s.count(old)
    if n!=1:raise SystemExit('v411 expected exactly one location ('+str(n)+'): '+old[:80])
    s=s.replace(old,new,1)
once('''address.setHint("https://video.example.com");''','''address.setHint("https://kolbo-video-agnes-gateway.onrender.com");''')
once('''address.setText(PrivateRenderClient.configuredUrl(this));''',
'''String connectedServer=PrivateRenderClient.configuredUrl(this);
        address.setText(connectedServer.isEmpty()
            ?"https://kolbo-video-agnes-gateway.onrender.com":connectedServer);''')
once('''secret.setHint("מפתח חיבור פרטי");''',
'''secret.setHint("מפתח חיבור לשער Kolbo Video");''')
once('''TextView instruction=label("ניתן לחבר שרת HTTPS ייעודי שמפעיל GPU פרטי או מפנה אל Agnes Flash. במסלול Agnes התמונות נשלחות גם לספק חיצוני דרך קישורים זמניים, בכפוף לתנאי שימוש, עומס, מכסות ומחיר המבצע בחשבון. לא כלול שרת מוכן או מנוי.",13,false);''',
'''TextView instruction=label("שרת Kolbo Video בענן כבר הוכן עבורך, וכתובתו מוזנת מראש. לצורך חיבור מאובטח יש להזין פעם אחת את מפתח שער Kolbo (לא את מפתח Agnes). הוא נשמר מוצפן במכשיר. השרת עדיין אינו מורשה ליצור סרטונים עד להפעלת Agnes ואישור מחיר אפס. אם Agnes יופעל, התמונות יישלחו אליו כספק חיצוני.",13,false);''')
once('''message("שער Agnes מחובר; התור, ההרשאות והמחיר בפועל לא אומתו בהפקה חיה.");''',
'''message("החיבור המאובטח לשרת Kolbo Video הצליח. יצירה ב־Agnes חסומה עד לאימות הרשאות ומחיר.");''')
once('''        .setTitle("חיבור שרת הפקה")''','''        .setTitle("חיבור מאובטח לשרת Kolbo Video")''') if '        .setTitle("חיבור שרת הפקה")' in s else None
# Keep secret entirely out of the repository and APK.
assert 'GaFfJgcM-' not in s
g=gradle.read_text(encoding='utf-8')
for a,b in [("applicationId 'com.kolbo.videostudio.preview409'","applicationId 'com.kolbo.videostudio.preview411'"),("versionCode 409","versionCode 411"),("versionName '4.0.9'","versionName '4.1.1'")]:
    if g.count(a)!=1:raise SystemExit('version mismatch '+a)
    g=g.replace(a,b,1)
gradle.write_text(g,encoding='utf-8');main.write_text(s,encoding='utf-8')
print('PASS v411: gateway URL preconfigured, secret entered only on handset')
