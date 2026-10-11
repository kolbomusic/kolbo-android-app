from pathlib import Path
import sys

root = Path(sys.argv[1])
base = root / "app/src/main/java/com/kolbo/videostudio"
client = base / "PrivateRenderClient.java"
gradle = root / "app/build.gradle"

source = client.read_text(encoding="utf-8")

def one(text, old, new):
    if text.count(old) != 1:
        raise SystemExit("v416: expected exactly one anchor: " + old[:90])
    return text.replace(old, new, 1)

source = one(source,
    '        JSONObject health=check(ctx);\n        if(!"ready".equals(health.optString("status","")))',
    '''        JSONObject health=check(ctx);
        // Validate server-advertised capabilities before exposing photos
        // or submitting a potentially quota-consuming request. Legacy
        // private gateways without this metadata are left unchanged.
        int imageCount=(subjectOne!=null?1:0)+(subjectTwo!=null?1:0);
        JSONArray supported=health.optJSONArray("supported_image_counts");
        if(supported!=null){
            boolean found=false;
            for(int i=0;i<supported.length();i++)
                if(supported.optInt(i,-1)==imageCount)found=true;
            if(!found)throw new Exception("המנוע המחובר אינו תומך ב־"
                +imageCount+" תמונות ייחוס עצמאיות. לא תישלח בקשת הפקה חלקית.");
        }
        int min=health.optInt("min_seconds",0);
        int max=health.optInt("max_seconds",0);
        if((min>0&&duration<min)||(max>0&&duration>max))
            throw new Exception("משך הסרטון המבוקש אינו נתמך במנוע המחובר"
                +(min>0&&max>0?": "+min+"–"+max+" שניות":"")+
                ". אין קיצור אוטומטי או השלמת סרטון מדומה.");
        if(!"ready".equals(health.optString("status","")))''')
source = one(source,
    '        payload.put("images",images);',
    '''        payload.put("images",images);
        // MainActivity shows an explicit consent confirmation before this
        // method. A staging backend must independently require this field.
        payload.put("third_party_transfer_consent",true);''')
client.write_text(source, encoding="utf-8")
g = gradle.read_text(encoding="utf-8")
for old, new in [
    ("applicationId 'com.kolbo.videostudio.preview409'",
     "applicationId 'com.kolbo.videostudio.preview416'"),
    ("versionCode 409", "versionCode 416"),
    ("versionName '4.0.9'", "versionName '4.1.6'"),
]:
    g = one(g, old, new)
gradle.write_text(g, encoding="utf-8")
assert "third_party_transfer_consent" in source
assert 'supported_image_counts' in source
assert 'max_seconds' in source
print("PASS v416: client honors advertised references/duration; new preview app ID; explicit third-party consent field")
