"""v419 zero-input, restricted guest CPU connection (applied AFTER v418).
Master bearer must NEVER be present in APK. Auto tokens only permit 2–12s
bounded CPU photo editing, never the AI/video provider route.
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

def once(source,old,new):
    n=source.count(old)
    if n!=1:
        raise SystemExit('v419 expected exactly one anchor; found '+str(n)+': '+old[:110])
    return source.replace(old,new,1)

main=once(main,
    '''                File output=PrivateRenderClient.renderPhotoMotion(this,first,second,''',
    '''                PrivateRenderClient.ensureAutoConnected(this);
                File output=PrivateRenderClient.renderPhotoMotion(this,first,second,''')
main=once(main,
    '''            if(!PrivateRenderClient.configured(this)){
                message("יש לחבר תחילה את שרת הניסוי המאובטח בהגדרות המתקדמות");
                return;
            }
            if(chosen==null){''',
    '''            // The public CPU-only guest connection is acquired in the
            // background. Never ask users for a URL or admin API key.
            if(chosen==null){''')
main=once(main,
    '''        final int desired=durationSeconds;
        if(cpuPhotoRequested){''',
    '''        final int desired=durationSeconds;
        // The primary button must never silently downgrade a singing,
        // dialogue or actor-motion prompt to Ken Burns still-picture motion.
        if(!cpuPhotoRequested && !PrivateRenderClient.manualEngineConfigured(this)){
            new AlertDialog.Builder(this)
                .setTitle("הפקת AI מלאה עדיין אינה זמינה")
                .setMessage("השרת החינמי מחובר אוטומטית לעריכת תמונות: תנועת מצלמה עם תמונה אחת או שתיים, ללא הנפשת דמויות, דיבור או שירה. ההנחיה שהקלדת לא תהפוך לסרטון AI. תרצה לבחור במפורש עריכת תמונות במקום?")
                .setPositiveButton("כן, עריכת תמונות",(d,w)->{
                    cpuPhotoRequested=true;
                    createVideo();
                })
                .setNegativeButton("לא, להישאר עם בקשת AI",(d,w)->{
                    message("אין כעת מנוע AI חינמי מאומת שתומך בבקשתך. הבקשה לא תישלח כעריכת תמונות.");
                })
                .show();
            return;
        }
        if(cpuPhotoRequested){''')
main=once(main,
    '''                            if("ready".equals(check.optString("status"))){
                                String provider=check.optString("provider","comfy");
                                if(provider.startsWith("agnes"))
                                    message("שער Agnes מחובר; התור, ההרשאות והמחיר בפועל לא אומתו בהפקה חיה.");
                                else message("שרת ההפקה מחובר; איכות הסרטון עדיין טעונה בדיקה.");
                            }else message("החיבור נשמר, אבל שרת ההפקה עדיין לא מוכן: "
                                +check.optString("detail","חסרים נתוני שרת או מנוע וידאו"));''',
    '''                            if(check.optJSONObject("cpu_photo_studio")!=null){
                                message("מנוע עריכת התמונות החינמי מוכן. מנוע יצירת וידאו AI עדיין אינו פעיל.");
                            }else if("ready".equals(check.optString("status")))
                                message("שרת ה־AI העצמאי מחובר ומוכן");
                            else message("השרת מחובר, אך אין מנוע הפקה זמין: "
                                +check.optString("detail",""));''')
# A full private AI engine is still an explicitly entered expert configuration,
# not the auto guest token that may never submit to /v1/jobs.
client=once(client,
    '''    private static final String KEY_ALIAS="kolbo_private_video_gateway_key";''',
    '''    private static final String KEY_ALIAS="kolbo_private_video_gateway_key";
    private static final String AUTO_SERVER="https://kolbo-video-wan416-staging.onrender.com";
    private static final String AUTO_MARKER="kolbo_auto_guest_cpu_only";
    private static final String AUTO_EXPIRY="kolbo_auto_guest_expiry_ms";
    private static final String INSTALL_ID="kolbo_guest_install_random_id";''')
client=once(client,
    '''    static void clear(Context ctx) {''',
    '''    static boolean autoGuest(Context ctx){
        return ctx.getSharedPreferences(PREFS,Context.MODE_PRIVATE)
            .getBoolean(AUTO_MARKER,false);
    }
    static boolean manualEngineConfigured(Context ctx){
        return configured(ctx) && !autoGuest(ctx);
    }
    private static String installId(Context ctx){
        SharedPreferences preferences=ctx.getSharedPreferences(PREFS,Context.MODE_PRIVATE);
        String id=preferences.getString(INSTALL_ID,"");
        if(id.matches("[0-9a-f]{32}"))return id;
        byte[] fresh=new byte[16];
        new java.security.SecureRandom().nextBytes(fresh);
        StringBuilder hex=new StringBuilder(32);
        for(byte c:fresh)hex.append(String.format(Locale.ROOT,"%02x",c&255));
        id=hex.toString();
        preferences.edit().putString(INSTALL_ID,id).apply();
        return id;
    }
    static void ensureAutoConnected(Context ctx) throws Exception {
        // A manually entered private GPU server takes precedence; no changes.
        if(manualEngineConfigured(ctx))return;
        SharedPreferences preferences=ctx.getSharedPreferences(PREFS,Context.MODE_PRIVATE);
        if(autoGuest(ctx) && configured(ctx) &&
           System.currentTimeMillis()<preferences.getLong(AUTO_EXPIRY,0L)-90000L)
            return;
        URL url=new URL(AUTO_SERVER+"/v1/guest/bootstrap");
        HttpURLConnection connection=(HttpURLConnection)url.openConnection();
        connection.setInstanceFollowRedirects(false);
        connection.setConnectTimeout(15000);
        connection.setReadTimeout(30000);
        connection.setRequestMethod("POST");
        connection.setDoOutput(true);
        connection.setRequestProperty("Content-Type","application/json; charset=utf-8");
        connection.setRequestProperty("Accept","application/json");
        try{
            JSONObject hello=new JSONObject();
            hello.put("install_id",installId(ctx));
            byte[] payload=hello.toString().getBytes(StandardCharsets.UTF_8);
            connection.setFixedLengthStreamingMode(payload.length);
            try(OutputStream out=connection.getOutputStream()){out.write(payload);}
            int status=connection.getResponseCode();
            if(status!=200)
                throw new Exception("שרת החיבור הזמני אינו זמין כעת (HTTP "+status+")");
            byte[] response;
            try(InputStream in=connection.getInputStream()){
                response=limited(in,20000);
            }
            JSONObject result=new JSONObject(new String(response,StandardCharsets.UTF_8));
            String token=result.getString("token");
            if(!token.startsWith("g1.") ||
               !"cpu_photo_motion".equals(result.optString("mode")))
                throw new Exception("השרת לא החזיר הרשאה לעריכת תמונות");
            int valid=result.optInt("expires_in_seconds",0);
            if(valid<120||valid>7200)throw new Exception("תוקף הרשאת העריכה אינו תקין");
            save(ctx,AUTO_SERVER,token);
            preferences.edit().putBoolean(AUTO_MARKER,true)
                .putLong(AUTO_EXPIRY,System.currentTimeMillis()+valid*1000L).apply();
        }finally{connection.disconnect();}
    }
    static void clear(Context ctx) {''')
client=once(client,
    '''        conn.setRequestProperty("User-Agent","KolboVideo/4.0.8");''',
    '''        conn.setRequestProperty("User-Agent","KolboVideo/4.1.9");''')
gradle=once(gradle,"applicationId 'com.kolbo.videostudio.preview418'",
    "applicationId 'com.kolbo.videostudio.preview419'")
gradle=once(gradle,"versionCode 418","versionCode 419")
gradle=once(gradle,"versionName '4.1.8'","versionName '4.1.9'")
main_file.write_text(main,encoding='utf-8')
client_file.write_text(client,encoding='utf-8')
gradle_file.write_text(gradle,encoding='utf-8')
assert 'AUTO_SERVER="https://kolbo-video-wan416-staging.onrender.com"' in client
assert 'KOLBO_V416_API_TOKEN' not in client
assert 'manualEngineConfigured' in main
assert 'ensureAutoConnected(this)' in main
assert "preview419" in gradle
print("PASS v419: zero-key-entry guest CPU bootstrap, honest AI status, main prompt never silently downgraded")
