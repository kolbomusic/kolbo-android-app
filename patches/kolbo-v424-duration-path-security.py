"""v424: no silent AI provider fallback and actionable exact-length failures.

All changes applied AFTER v423 source normalizer. No extra cloud hardware,
third-party quota retries or API key embedded in the APK.
"""
from pathlib import Path
import sys

root=Path(sys.argv[1])
base=root/'app/src/main/java/com/kolbo/videostudio'
main_file=base/'MainActivity.java'
client_file=base/'PrivateRenderClient.java'
length_file=base/'OutputLengthGate.java'
gradle_file=root/'app/build.gradle'
main=main_file.read_text(encoding='utf-8')
client=client_file.read_text(encoding='utf-8')
gate=length_file.read_text(encoding='utf-8')
gradle=gradle_file.read_text(encoding='utf-8')

def one(src,a,z):
    if src.count(a)!=1:
        raise SystemExit("v424 unique source anchor mismatch %d %s" % (src.count(a),a[:115]))
    return src.replace(a,z,1)

# Prevent any older provider route (Gradio/MSR/Agnes) being invoked by the
# anonymous CPU-only connection. Never call startRemoteVideo on a singing request
# when a verified backend has no GPU or synchronized singing support.
main=one(main,
'''    private void beginGeneration(String instruction, Uri chosen, Uri second, int requestedSeconds) {
        if(running)return;''',
'''    private void beginGeneration(String instruction, Uri chosen, Uri second, int requestedSeconds) {
        if(running)return;
        if(!PrivateRenderClient.manualEngineConfigured(this)){
            generationInFlight=false;
            new AlertDialog.Builder(this)
                .setTitle("מנוע ה-AI עדיין אינו זמין")
                .setMessage("בקשתך נשארה ללא שינוי. השרת החינמי יודע לערוך תמונות לתנועת מצלמה בלבד; אין בו מנוע AI שמסוגל לייצר שירה, משחק דמויות או במה עם קהל. לא נשלחה בקשת וידאו לספק חיצוני, ולא נוצר סרטון קצר במקום הסרטון שביקשת. בחר בנפרד בעריכת תמונות רק אם זה מה שאתה רוצה.")
                .setPositiveButton("הבנתי",(d,w)->{})
                .show();
            return;
        }''')

# Photo CPU job has server-side ffprobe and SHA-256 result evidence. The
# previous client also rejected legitimate tiny MP4s simply for being <10KB,
# while the duration policy's metadata reader required >12KB. Both gates must
# use the same byte floor as the server, rather than rejecting based on file size.
pos=client.find('    static File renderPhotoMotion(')
if pos<0:raise SystemExit('v424 CPU method missing')
head,tail=client[:pos],client[pos:]
if tail.count('if(file.length()<10000)')!=1:
    raise SystemExit('v424 cannot isolate old 10KB CPU threshold')
tail=tail.replace('if(file.length()<10000)','if(file.length()<3000)',1)
client=head+tail
gate=one(gate,'f.length()<12000','f.length()<3000')

# Surface the actual terminal exception behind the generic red-card headline,
# not an unhelpful retry that sends the same unsupported or quota-bound request.
main=one(main,
'''        failureSubtitle.setText("לא נוצר סרטון. אפשר לנסות שוב או לפתוח פרטים נוספים.");
        failureCard.setVisibility(View.VISIBLE);''',
'''        String reason=technical==null||technical.trim().isEmpty()
            ?"לא התקבל סרטון תקין. אין לנסות שוב אוטומטית.":technical.trim();
        if(reason.length()>360)reason=reason.substring(0,360)+"…";
        final String detail=reason;
        failureSubtitle.setText("לא הופק סרטון. סיבת הדחייה: "+detail);
        retryCreation.setText("הצג סיבת כישלון");
        retryCreation.setOnClickListener(v->
            new AlertDialog.Builder(this)
                .setTitle("פרטי כישלון ההפקה")
                .setMessage(detail+"\\n\\nלא תישלח בקשה נוספת אוטומטית. בדוק שהמשימה נתמכת לפני ניסיון חדש.")
                .setPositiveButton("סגור",(d,w)->{})
                .show());
        failureCard.setVisibility(View.VISIBLE);''')

for old,new in [
    ("applicationId 'com.kolbo.videostudio.preview423'",
     "applicationId 'com.kolbo.videostudio.preview424'"),
    ("versionCode 423","versionCode 424"),
    ("versionName '4.2.3'","versionName '4.2.4'"),
]:
    gradle=one(gradle,old,new)
assert 'if(!PrivateRenderClient.manualEngineConfigured(this))' in main
assert 'אין בו מנוע AI שמסוגל לייצר שירה' in main
assert 'retryCreation.setText("הצג סיבת כישלון");' in main
assert 'if(file.length()<3000)' in client
assert 'f.length()<3000' in gate
assert 'renderPhotoMotion(' in client
assert 'KOLBO_V416_API_TOKEN' not in client

main_file.write_text(main,encoding='utf-8')
client_file.write_text(client,encoding='utf-8')
length_file.write_text(gate,encoding='utf-8')
gradle_file.write_text(gradle,encoding='utf-8')
print("PASS v424: unsupported AI cannot reach provider; actual failure details surfaced, small verified MP4 not rejected")
