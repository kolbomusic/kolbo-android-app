"""Android v4.3.3: two-person AI Create MUST build a shared stage first.

Previous v4.3.2 assembled a rectangular two-photo collage and asked LTX
to animate it directly; user's actual 8.04s video preserved both static
photo panels and violated the request. Now server performs a FLUX AI scene
edit BEFORE the LTX video+sound model; if stage builder unavailable, fails
without GPU job or slideshow substitution. Clear new consent explicitly
names BOTH public services and non-guaranteed identities/lyrics.
"""
from pathlib import Path
import sys
root=Path(sys.argv[1])
base=root/"app/src/main/java/com/kolbo/videostudio"
mainfile=base/"MainActivity.java"
clientfile=base/"PrivateRenderClient.java"
gradlefile=root/"app/build.gradle"
main=mainfile.read_text("utf8")
client=clientfile.read_text("utf8")
gradle=gradlefile.read_text("utf8")

def replace_one(s,a,z):
    n=s.count(a)
    if n!=1:
        raise SystemExit("v433 Android source anchor count "+str(n)+": "+a[:100])
    return s.replace(a,z,1)

# Renew informed consent; stage image is uploaded to a DIFFERENT public
# service, even though LTX was already approved in previous releases.
if main.count('"approved_native_ltx_duo_v432"')!=2:
    raise SystemExit("Expected both read/write uses of v432 privacy approval")
main=main.replace('"approved_native_ltx_duo_v432"',
                  '"approved_stage_then_video_v433"')
main=replace_one(main,
'''ההנחיה והתמונות יישלחו לשירות AI ציבורי (LTX-2.5 ב-Hugging Face). שתי תמונות יאוחדו במכשיר לתמונת פתיחה אחת. המנוע ינסה להנפיש את שתי הדמויות, אך אינו מבטיח שמירת פנים, שירה בשפה שביקשת או סנכרון מדויק. השירות ציבורי; אל תעלה תמונות רגישות. יש מכסות חינמיות, ללא חיוב. מאשר הפקה?''',
'''שתי תמונות ישולבו במכשיר. כדי ליצור במה משותפת אמיתית, תמונת המקור וההנחיה יישלחו קודם ל-FLUX Kontext הציבורי ב-Hugging Face, ולאחר מכן התמונה החדשה תישלח ל-LTX-2.5 הציבורי להפקת תנועה ושמע. השירותים אינם פרטיים ויש להם מכסות. אל תעלה תמונות רגישות. זהות פנים, שפה וסנכרון השירה עדיין אינם מובטחים. אין חיוב. האם מאשר לשלוח את המדיה לשני השירותים?''')
main=replace_one(main,
    'status.setText(second!=null\n            ?"מכין שתי דמויות ליצירת וידאו ושמע AI..."',
    'status.setText(second!=null\n            ?"מכין במת הופעה משותפת — ולא קולאז׳ של תמונות..."')
main=replace_one(main,
'''showResult(output,"נוצר וידאו AI עם שמע מקורי. בדוק בעצמך את הפעולה ואת השפה.");''',
'''showResult(output,"טיוטת וידאו AI עם שמע. הבמה והשירה דורשות בדיקת התאמה להנחיה; אם לא תואם, זו אינה הצלחה.");''')

pos=client.index("    static File renderNativeAV(")
head,tail=client[:pos],client[pos:]
tail=replace_one(tail,
'''        plan.put("image_count",(first!=null||second!=null)?1:0);''',
'''        plan.put("image_count",(first!=null||second!=null)?1:0);
        // Request the dedicated stage creator; NEVER silently animate
        // the two portrait panels as the final scene.
        plan.put("requires_shared_stage_scene",first!=null&&second!=null);''')
tail=replace_one(tail,
'''        payload.put("third_party_transfer_consent",true);''',
'''        payload.put("third_party_transfer_consent",true);
        payload.put("requires_shared_stage_scene",first!=null&&second!=null);''')
tail=replace_one(tail,
'''            status.onStage("משלב את שתי הדמויות לתמונת ייחוס אחת...");''',
'''            status.onStage("מכין תמונת ייחוס זמנית; ייבנה ממנה סטילס של במה משותפת...");''')
client=head+tail

for old,new in [
    ("applicationId 'com.kolbo.videostudio.preview432'",
     "applicationId 'com.kolbo.videostudio.preview433'"),
    ("versionCode 432","versionCode 433"),
    ("versionName '4.3.2'","versionName '4.3.3'")
]:
    gradle=replace_one(gradle,old,new)
assert 'approved_stage_then_video_v433' in main
assert 'requires_shared_stage_scene' in client
assert 'composeDuoReference(ctx,first,second)' in client
assert '"/v1/native-av/plan"' in client
assert '"/v1/native-av/jobs"' in client
assert "KOLBO_V416_API_TOKEN" not in client
mainfile.write_text(main,"utf8")
clientfile.write_text(client,"utf8")
gradlefile.write_text(gradle,"utf8")
print("PASS v433: no direct split-portrait animation; shared AI stage first, explicit 2-service consent")
