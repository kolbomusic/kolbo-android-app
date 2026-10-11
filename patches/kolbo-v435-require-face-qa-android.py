"""v435 Android: show user-friendly identity drift errors, fail closed on absent QA.

v433 still previews successful MP4 even if face identity is different; backend
v435 checks local YuNet/SFace stage and 3 video frames. Enforce receipt
presence on Android as defense in depth; never claim identities guaranteed.
"""
from pathlib import Path
import sys
root=Path(sys.argv[1])
base=root/"app/src/main/java/com/kolbo/videostudio"
main_path=base/"MainActivity.java";client_path=base/"PrivateRenderClient.java"
gradle_path=root/"app/build.gradle"
main=main_path.read_text("utf8")
client=client_path.read_text("utf8")
gradle=gradle_path.read_text("utf8")
def exactly(s,a,z):
    n=s.count(a)
    if n!=1:raise SystemExit(f"v435 unique Android anchor {n}: {a[:110]}")
    return s.replace(a,z,1)

if main.count('"approved_stage_then_video_v433"')!=2:
    raise SystemExit("Cannot safely migrate two-stage consent")
main=main.replace('"approved_stage_then_video_v433"',
                  '"approved_strict_face_comparison_v435"')
main=exactly(main,
'''זהות פנים, שפה וסנכרון השירה עדיין אינם מובטחים. אין חיוב. האם מאשר לשלוח את המדיה לשני השירותים?''',
'''לפני הצגת התוצאה, השרת יבצע בדיקת דמיון פנים מקומית מול שתי התמונות המקוריות ויפסול שינוי דמויות. זו אינה הבטחת זהות מושלמת. שירה ושפה אינן מאומתות. אין חיוב. האם מאשר לשלוח מדיה לשני השירותים?''')
main=exactly(main,
'''?"מכין במת הופעה משותפת — ולא קולאז׳ של תמונות..."''',
'''?"מכין במה ובודק שמירת שתי הפנים לפני יצירת סרטון..."''')
main=exactly(main,
'''showResult(output,"טיוטת וידאו AI עם שמע. הבמה והשירה דורשות בדיקת התאמה להנחיה; אם לא תואם, זו אינה הצלחה.");''',
'''showResult(output,second!=null
                    ?"טיוטת AI עברה בדיקת דמיון פנים מקומית, לא אימות זהות מושלם. בדוק שירה ותוכן."
                    :"טיוטת וידאו AI עם שמע. בדוק בעצמך התאמה להנחיה.");''')

pos=client.index("    static File renderNativeAV(")
head,tail=client[:pos],client[pos:]
tail=exactly(tail,
'''            if(state.equals("failed"))throw new Exception(
                "המנוע הפרטי נכשל: "+next.optString("error",next.optString("detail","")));
            if(state.equals("completed"))break;''',
'''            if(state.equals("failed"))throw new Exception(
                next.optString("detail","ההפקה נכשלה. אין להציג דמויות שהשתנו."));
            if(state.equals("completed")){
                if(first!=null&&second!=null){
                    JSONObject quality=next.optJSONObject("quality");
                    if(quality==null ||
                        !quality.optBoolean("face_similarity_check_passed",false) ||
                        !quality.has("face_video_scores") ||
                        quality.optJSONArray("face_video_scores")==null ||
                        quality.optJSONArray("face_video_scores").length()!=3){
                        throw new Exception("בדיקת התאמת שתי הדמויות חסרה. הסרטון לא יאושר.");
                    }
                }
                break;
            }''')
tail=exactly(tail,
'''        status.onStage("ממתין ליצירת וידאו ושמע במנוע AI...");''',
'''        status.onStage(first!=null&&second!=null
            ?"בודק שהפנים המקוריות נשמרות לאורך הסרטון..."
            :"ממתין ליצירת וידאו ושמע במנוע AI...");''')
client=head+tail
for old,new in [
    ("applicationId 'com.kolbo.videostudio.preview433'",
     "applicationId 'com.kolbo.videostudio.preview435'"),
    ("versionCode 433","versionCode 435"),
    ("versionName '4.3.3'","versionName '4.3.5'")
]:
    gradle=exactly(gradle,old,new)
assert 'face_similarity_check_passed' in client
assert 'face_video_scores' in client
assert 'approved_strict_face_comparison_v435' in main
assert 'KOLBO_V416_API_TOKEN' not in client
main_path.write_text(main,"utf8")
client_path.write_text(client,"utf8")
gradle_path.write_text(gradle,"utf8")
print("PASS v435: duel Face QA receipts required for success; friendly server details; no identity guarantee")
