"""Version 4.2.2: show the REAL bounded compute capacity inside Android.

No new server URL, admin token, paid engine or manual configuration.
A guest compute readout uses only the auto-issued CPU-only token.
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

def single(source,old,new):
    if source.count(old)!=1:
        raise SystemExit("v422 missing/duplicate anchor "+old[:110]+": "+str(source.count(old)))
    return source.replace(old,new,1)

client=single(client,
'''    static JSONObject check(Context ctx) throws Exception {
        HttpURLConnection conn=open(ctx,"/v1/health","GET",30000);
        return new JSONObject(fetch(conn));
    }''',
'''    static JSONObject check(Context ctx) throws Exception {
        HttpURLConnection conn=open(ctx,"/v1/health","GET",30000);
        return new JSONObject(fetch(conn));
    }
    static JSONObject inspectCompute(Context ctx) throws Exception {
        // Protected capacity API. Never retries a failed upload or invents GPU.
        ensureAutoConnected(ctx);
        HttpURLConnection conn=open(ctx,"/v1/compute/capacity","GET",30000);
        return new JSONObject(fetch(conn));
    }''')
main=single(main,
'''        diagnostics=button("הצג אבחון טכני");''',
'''        Button computeCheckButton=button("בדוק את המחשוב החינמי");
        advancedPanel.addView(computeCheckButton,StudioVisuals.spaced(this,52,8));
        computeCheckButton.setOnClickListener(v->{
            message("בודק זיכרון, תור ומחשוב שרת בפועל...");
            executor.execute(()->{
                try{
                    org.json.JSONObject capacity=PrivateRenderClient.inspectCompute(this);
                    boolean cpu=capacity.optBoolean("cpu_editor_ready",false);
                    boolean gpu=capacity.optBoolean("gpu_verified_available",false);
                    double cores=capacity.optDouble("cpu_quota_cores",-1);
                    long free=capacity.optLong("memory_free_bytes",-1);
                    final String cpuText=cores>0?String.format(java.util.Locale.ROOT,"%.2f",cores)+" CPU":"לא אומת";
                    final String memoryText=free>=0?(free/1048576)+"MB":"לא אומת";
                    final String summary=
                        "שרת עריכת תמונות CPU: "+(cpu?"פנוי כרגע":"עמוס או מוגבל")
                        +"\\nמכסת מעבד: "+cpuText
                        +"\\nזיכרון פנוי נמדד: "+memoryText
                        +"\\nGPU מקצועי מאומת: "+(gpu?"כן":"לא")
                        +"\\nיכולת יצירת AI מלאה: לא זמינה כרגע"
                        +"\\nמספר הפקות במקביל: "+capacity.optInt("max_parallel_jobs",1)
                        +"\\nאחסון התוצרים זמני; שרת Free אינו מחשוב בלתי מוגבל."
                        +"\\nמצב טכני: "+capacity.optString("readiness_reason","לא ידוע");
                    runOnUiThread(()->new AlertDialog.Builder(this)
                        .setTitle("מצב המחשוב של Kolbo Video")
                        .setMessage(summary)
                        .setPositiveButton("סגור",(d,w)->{})
                        .show());
                }catch(Exception e){
                    message("בדיקת מצב המחשוב נכשלה: "+e.getMessage());
                }
            });
        });
        diagnostics=button("הצג אבחון טכני");''')
for old,new in [
    ("applicationId 'com.kolbo.videostudio.preview421'",
     "applicationId 'com.kolbo.videostudio.preview422'"),
    ("versionCode 421","versionCode 422"),
    ("versionName '4.2.1'","versionName '4.2.2'")
]:
    gradle=single(gradle,old,new)
assert 'inspectCompute' in main and 'inspectCompute' in client
assert 'KOLBO_V416_API_TOKEN' not in client
assert 'kolbo-video-wan416-staging.onrender.com' in client
main_file.write_text(main,encoding='utf-8')
client_file.write_text(client,encoding='utf-8')
gradle_file.write_text(gradle,encoding='utf-8')
print("PASS v422: Android one-tap honest compute capacity via existing auto guest auth")
