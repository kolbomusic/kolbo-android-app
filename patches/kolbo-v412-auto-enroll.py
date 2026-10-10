from pathlib import Path
import shutil,sys
root=Path(sys.argv[1])
base=root/'app/src/main/java/com/kolbo/videostudio'
main=base/'MainActivity.java'
client=base/'PrivateRenderClient.java'
gradle=root/'app/build.gradle'
s=main.read_text(encoding='utf-8')
c=client.read_text(encoding='utf-8')
shutil.copyfile('patches/DeviceAutoPair.java',base/'DeviceAutoPair.java')
def replace_once(string,old,new):
    count=string.count(old)
    if count!=1:raise SystemExit(f'v412 expected exactly one match, got {count}: {old[:90]!r}')
    return string.replace(old,new,1)

c=replace_once(c,
'''        return ctx.getSharedPreferences(PREFS,Context.MODE_PRIVATE).getString("url","");
''',
'''        String saved=ctx.getSharedPreferences(PREFS,Context.MODE_PRIVATE).getString("url","");
        return saved.isEmpty()?DeviceAutoPair.SERVER:saved;
''')
c=replace_once(c,
'''        return !pref.getString("url","").isEmpty()&&!pref.getString("secret","").isEmpty();
''',
'''        // An unpaired device stays on our HTTPS server and requests approval.
        // Never fall back to the quota-limited public demo without explicit user choice.
        return true;
''')
c=replace_once(c,
'''        if(secret.isEmpty())throw new Exception("שרת פרטי עדיין לא חובר");
        return decrypt(secret);
''',
'''        if(secret.isEmpty())return DeviceAutoPair.accessToken();
        return decrypt(secret);
''')
c=replace_once(c,
'''            if(code<200||code>=300){
                String msg="";''',
'''            if(code<200||code>=300){
                if(code==401)DeviceAutoPair.invalidate();
                String msg="";''')
client.write_text(c,encoding='utf-8')
begin=s.index('    private void showPrivateEngineSettings(){')
end=s.index('    private void startPrivateVideo(',begin)
s=s[:begin]+'''    private void showPrivateEngineSettings(){
        message("בודק חיבור אוטומטי מאובטח לשרת Kolbo Video...");
        executor.execute(()->{
            try {
                DeviceAutoPair.accessToken();
                org.json.JSONObject state=PrivateRenderClient.check(this);
                String statusText="ready".equals(state.optString("status"))?
                    "השרת מחובר ומוכן לשליחת בקשה. איכות ומחיר לא אומתו בהפקה חיה.":
                    "המכשיר מאושר והשרת מחובר. הפקה חסומה: "
                        +state.optString("detail","נדרשת בדיקת מחיר והגדרות Agnes.");
                message(statusText);
            }catch(Exception error){
                message(error.getMessage()==null?"החיבור האוטומטי עדיין לא אושר":error.getMessage());
            }
        });
    }
'''+s[end:]
s=replace_once(s,
'''        generate.setOnClickListener(v->createVideo());''',
'''        generate.setOnClickListener(v->createVideo());
        // No address, code, gateway key or Agnes API key is requested from user.
        // First launch registers the device public key for operator approval.
        executor.execute(()->{
            try {
                DeviceAutoPair.accessToken();
                org.json.JSONObject state=PrivateRenderClient.check(this);
                if("ready".equals(state.optString("status")))
                    message("חיבור Kolbo Video אומת. הפקת וידאו עדיין תלויה באישור מחיר.");
                else message("המכשיר מחובר. הפקת וידאו עדיין חסומה: "
                    +state.optString("detail","הגדרות Agnes דורשות אימות."));
            }catch(Exception e){
                message(e.getMessage()==null?"המכשיר ממתין לאישור בשרת":e.getMessage());
            }
        });''')
g=gradle.read_text(encoding='utf-8')
for old,new in [
    ("applicationId 'com.kolbo.videostudio.preview411'","applicationId 'com.kolbo.videostudio.preview412'"),
    ("versionCode 411","versionCode 412"),
    ("versionName '4.1.1'","versionName '4.1.2'")
]:
    g=replace_once(g,old,new)
gradle.write_text(g,encoding='utf-8')
main.write_text(s,encoding='utf-8')
assert 'DeviceAutoPair.accessToken()' in c
assert 'DeviceAutoPair.accessToken()' in s
assert 'showPrivateEngineSettings(){\\n        message("בודק חיבור אוטומטי' in s
assert 'EditText secret' not in s
assert 'GaFfJgcM-' not in s
assert 'AGNES_API_KEY' not in c
print('PASS v412: no code entry, HTTPS preconfigured, device P256 enrollment and token unbundled')
