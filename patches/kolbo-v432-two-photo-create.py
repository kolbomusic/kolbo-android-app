"""Fix v431 Create: two selected photos must not silently abort AI creation.

The free native LTX endpoint accepts ONE optional reference image. On Android
we assemble two selected portraits into one bounded JPEG, after EXIF-safe
sampling; we send exactly ONE reference to LTX and never claim identity lock.
This still depends on public GPU quota and one-time INFORMED consent.
"""
from pathlib import Path
import sys
root=Path(sys.argv[1])
base=root/"app/src/main/java/com/kolbo/videostudio"
main_file=base/"MainActivity.java"
client_file=base/"PrivateRenderClient.java"
gradle_file=root/"app/build.gradle"
main=main_file.read_text("utf8")
client=client_file.read_text("utf8")
gradle=gradle_file.read_text("utf8")

def replace_one(content,original,replacement):
    count=content.count(original)
    if count!=1:
        raise SystemExit("v432 exact anchor mismatch ("+str(count)+"): "+original[:110])
    return content.replace(original,replacement,1)

main=replace_one(main,
'''            if(second!=null){
                message("שתי דמויות מתמונות נפרדות עדיין אינן נתמכות במנוע ה-AI החינמי");
                return;
            }
''',
'''            // LTX accepts one reference; two portraits become one reference.
            // Never silently replace AI video with still-image animation.
''')
main=replace_one(main,"approveOnceAndGenerateAi(chosen,desired,instruction);",
    "approveOnceAndGenerateAi(chosen,second,desired,instruction);")
main=replace_one(main,
    "private void approveOnceAndGenerateAi(Uri first,int seconds,String instruction){",
    "private void approveOnceAndGenerateAi(Uri first,Uri second,int seconds,String instruction){")
if main.count('"approved_native_ltx_v431"')!=2:
    raise SystemExit("v432 one-time approval must have matching read/write keys")
main=main.replace('"approved_native_ltx_v431"','"approved_native_ltx_duo_v432"')
if main.count("prepareRealAiTrial(first,seconds,instruction);")!=2:
    raise SystemExit("v432 expected both approval branches")
main=main.replace("prepareRealAiTrial(first,seconds,instruction);",
                  "prepareRealAiTrial(first,second,seconds,instruction);")
main=replace_one(main,
    "private void prepareRealAiTrial(Uri first,int seconds,String original){",
    "private void prepareRealAiTrial(Uri first,Uri second,int seconds,String original){")
main=replace_one(main,"startRealAiTrial(first,seconds,original);",
    "startRealAiTrial(first,second,seconds,original);")
main=replace_one(main,"startRealAiTrial(first,seconds,translated);",
    "startRealAiTrial(first,second,seconds,translated);")
main=replace_one(main,
    "private void startRealAiTrial(Uri first,int seconds,String translated){",
    "private void startRealAiTrial(Uri first,Uri second,int seconds,String translated){")
main=replace_one(main,
    "PrivateRenderClient.renderNativeAV(this,first,seconds,",
    "PrivateRenderClient.renderNativeAV(this,first,second,seconds,")
main=replace_one(main,
'''ההנחיה והתמונה, אם בחרת אחת, יישלחו להדגמה ציבורית של LTX-2.5 ב-Hugging Face. הסרטון והשמע נוצרים יחד באמצעות AI. השירות הציבורי מוגבל במכסות ואינו פרטי; אל תשתף תמונות רגישות. לא יבוצע חיוב. מאשר לשלוח את ההנחיה ואת התמונה להפקה?''',
'''ההנחיה והתמונות יישלחו לשירות AI ציבורי (LTX-2.5 ב-Hugging Face). שתי תמונות יאוחדו במכשיר לתמונת פתיחה אחת. המנוע ינסה להנפיש את שתי הדמויות, אך אינו מבטיח שמירת פנים, שירה בשפה שביקשת או סנכרון מדויק. השירות ציבורי; אל תעלה תמונות רגישות. יש מכסות חינמיות, ללא חיוב. מאשר הפקה?''')
main=replace_one(main,
'''    private void prepareRealAiTrial(Uri first,Uri second,int seconds,String original){
        if(!hasHebrew(original)){''',
'''    private void prepareRealAiTrial(Uri first,Uri second,int seconds,String original){
        status.setText(second!=null
            ?"מכין שתי דמויות ליצירת וידאו ושמע AI..."
            :"מכין וידאו ושמע AI...");
        if(!hasHebrew(original)){''')

helper='''    private static JSONObject composeDuoReference(Context ctx,Uri left,Uri right)
            throws Exception {
        JSONObject a=smallCpuImage(ctx,left);
        JSONObject b=smallCpuImage(ctx,right);
        byte[] ab=Base64.decode(a.getString("data_base64"),Base64.DEFAULT);
        byte[] bb=Base64.decode(b.getString("data_base64"),Base64.DEFAULT);
        android.graphics.Bitmap first=android.graphics.BitmapFactory.decodeByteArray(
            ab,0,ab.length);
        android.graphics.Bitmap second=android.graphics.BitmapFactory.decodeByteArray(
            bb,0,bb.length);
        if(first==null||second==null){
            if(first!=null)first.recycle();
            if(second!=null)second.recycle();
            throw new Exception("אחת התמונות אינה נגישה לשילוב הדמויות");
        }
        android.graphics.Bitmap combined=null;
        try {
            combined=android.graphics.Bitmap.createBitmap(768,768,
                android.graphics.Bitmap.Config.RGB_565);
            android.graphics.Canvas canvas=new android.graphics.Canvas(combined);
            canvas.drawColor(android.graphics.Color.rgb(25,27,41));
            android.graphics.Paint paint=new android.graphics.Paint(
                android.graphics.Paint.ANTI_ALIAS_FLAG |
                android.graphics.Paint.FILTER_BITMAP_FLAG);
            drawFittedPortrait(canvas,first,
                new android.graphics.RectF(12,18,375,749),paint);
            drawFittedPortrait(canvas,second,
                new android.graphics.RectF(393,18,756,749),paint);
            paint.setColor(android.graphics.Color.rgb(130,134,140));
            canvas.drawLine(384,20,384,748,paint);
            java.io.ByteArrayOutputStream bytes=new java.io.ByteArrayOutputStream();
            if(!combined.compress(android.graphics.Bitmap.CompressFormat.JPEG,85,bytes))
                throw new Exception("שילוב תמונות המקור נכשל");
            byte[] output=bytes.toByteArray();
            if(output.length<100||output.length>4_800_000)
                throw new Exception("תמונת שתי הדמויות חורגת ממגבלת השרת");
            JSONObject joined=new JSONObject();
            joined.put("mime_type","image/jpeg");
            joined.put("data_base64",Base64.encodeToString(output,Base64.NO_WRAP));
            return joined;
        }finally{
            first.recycle();
            second.recycle();
            if(combined!=null)combined.recycle();
        }
    }
    private static void drawFittedPortrait(android.graphics.Canvas canvas,
            android.graphics.Bitmap person,android.graphics.RectF slot,
            android.graphics.Paint paint){
        int w=person.getWidth(),h=person.getHeight();
        float ratio=Math.min(slot.width()/w,slot.height()/h);
        float dw=w*ratio,dh=h*ratio;
        canvas.drawBitmap(person,null,new android.graphics.RectF(
            slot.centerX()-dw/2,slot.centerY()-dh/2,
            slot.centerX()+dw/2,slot.centerY()+dh/2),paint);
    }
'''
client=replace_one(client,
    "    static File renderNativeAV(Context ctx,Uri first,int seconds,",
    helper+"    static File renderNativeAV(Context ctx,Uri first,Uri second,int seconds,")
# Modify ONLY the native-AI renderer, keeping CPU photo and old Wan code intact.
pos=client.index("    static File renderNativeAV(")
head,body=client[:pos],client[pos:]
body=replace_one(body,'plan.put("image_count",first==null?0:1);',
                 'plan.put("image_count",(first!=null||second!=null)?1:0);')
body=replace_one(body,
'''        if(first!=null)images.put(smallCpuImage(ctx,first));
        payload.put("images",images);''',
'''        if(first!=null && second!=null){
            status.onStage("משלב את שתי הדמויות לתמונת ייחוס אחת...");
            images.put(composeDuoReference(ctx,first,second));
        }else if(first!=null){
            images.put(smallCpuImage(ctx,first));
        }else if(second!=null){
            images.put(smallCpuImage(ctx,second));
        }
        payload.put("images",images);''')
body=replace_one(body,
'''        payload.put("prompt",instruction);
        payload.put("seconds",seconds);
        payload.put("fps",16);''',
'''        String effectivePrompt=first!=null && second!=null
            ?("The starting reference depicts TWO DIFFERENT people, "
                +"person on the LEFT and person on the RIGHT. "
                +"Show BOTH moving and performing the requested action "
                +"in ONE connected cinematic scene, without blending or duplicating faces. "
                +"Synchronize the audible soundtrack to the action. "+instruction)
            :instruction;
        payload.put("prompt",effectivePrompt);
        payload.put("seconds",seconds);
        payload.put("fps",16);''')
client=head+body
# The screenshots also show a 30-second preset although native AI supports
# up to 15. Align the visible controls to the actual service capability.
main=replace_one(main,"durationBar.setMax(59);","durationBar.setMax(14);")
main=replace_one(main,
    'משך הסרטון בשניות, מאחת עד שישים',
    'משך הסרטון בשניות, מאחת עד חמש עשרה')
main=replace_one(main,
    'for(int number:new int[]{5,10,15,30})',
    'for(int number:new int[]{5,10,12,15})')
for a,z in [
    ("applicationId 'com.kolbo.videostudio.preview431'",
     "applicationId 'com.kolbo.videostudio.preview432'"),
    ("versionCode 431","versionCode 432"),
    ("versionName '4.3.1'","versionName '4.3.2'")
]:
    gradle=replace_one(gradle,a,z)
assert "שתי דמויות מתמונות נפרדות עדיין אינן נתמכות" not in main
assert 'approveOnceAndGenerateAi(chosen,second,desired,instruction)' in main
assert "renderNativeAV(this,first,second,seconds" in main
assert 'composeDuoReference(ctx,first,second)' in client
assert '"approved_native_ltx_duo_v432"' in main
assert 'KOLBO_V416_API_TOKEN' not in client
main_file.write_text(main,encoding="utf8")
client_file.write_text(client,encoding="utf8")
gradle_file.write_text(gradle,encoding="utf8")
print("PASS v432 two-photo Create no-op fixed; composite is uploaded only after fresh informed consent")
