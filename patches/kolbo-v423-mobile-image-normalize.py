"""v423: normalize gallery images to 1280px max BEFORE CPU upload.

Decodes photo through Android ContentResolver with sampling and EXIF orientation.
Produces bounded JPEG, avoids common 12/48MP phone photo rejection by tiny Free
Render CPU host. Does not alter original Uri or change AI/private provider path.
"""
from pathlib import Path
import sys
root=Path(sys.argv[1])
base=root/"app/src/main/java/com/kolbo/videostudio"
target=base/"PrivateRenderClient.java"
gradle_file=root/"app/build.gradle"
s=target.read_text(encoding="utf-8")
gradle=gradle_file.read_text(encoding="utf-8")
def once(old,new):
    global s
    n=s.count(old)
    if n!=1:raise SystemExit(f"v423 anchor count {n}: {old[:75]}")
    s=s.replace(old,new,1)

once(
'''    private static JSONObject image(Context ctx,Uri uri) throws Exception {''',
'''    private static JSONObject smallCpuImage(Context ctx,Uri uri) throws Exception {
        // Free Render cgroup memory <=512 MiB. Downsampling must happen BEFORE
        // uploading. Never send full-resolution phone photos to CPU edit path.
        String declared=mime(ctx,uri);
        android.graphics.BitmapFactory.Options bounds=
            new android.graphics.BitmapFactory.Options();
        bounds.inJustDecodeBounds=true;
        try(InputStream first=ctx.getContentResolver().openInputStream(uri)){
            if(first==null)throw new Exception("התמונה שנבחרה אינה נגישה");
            android.graphics.BitmapFactory.decodeStream(first,null,bounds);
        }
        int w=bounds.outWidth,h=bounds.outHeight;
        if(w<20||h<20||w>30000||h>30000)
            throw new Exception("לא ניתן לפענח את גודל תמונת המקור");
        int sample=1;
        while(Math.max(w/sample,h/sample)>1600 && sample<256)sample*=2;
        android.graphics.BitmapFactory.Options decode=
            new android.graphics.BitmapFactory.Options();
        decode.inSampleSize=sample;
        decode.inPreferredConfig=android.graphics.Bitmap.Config.RGB_565;
        android.graphics.Bitmap bitmap;
        try(InputStream content=ctx.getContentResolver().openInputStream(uri)){
            if(content==null)throw new Exception("לא ניתן לקרוא את תמונת המקור");
            bitmap=android.graphics.BitmapFactory.decodeStream(content,null,decode);
        }
        if(bitmap==null)throw new Exception("נכשלה הכנת תמונה קטנה לשרת");
        int orientation=1;
        if(android.os.Build.VERSION.SDK_INT>=24) {
            try(InputStream exifStream=ctx.getContentResolver().openInputStream(uri)){
                if(exifStream!=null){
                    android.media.ExifInterface exif=new android.media.ExifInterface(exifStream);
                    orientation=exif.getAttributeInt(
                        android.media.ExifInterface.TAG_ORIENTATION,1);
                }
            }catch(Exception ignored){orientation=1;}
        }
        android.graphics.Bitmap adjusted=null,small=null;
        try{
            android.graphics.Matrix rotation=new android.graphics.Matrix();
            if(orientation==3)rotation.postRotate(180);
            else if(orientation==6)rotation.postRotate(90);
            else if(orientation==8)rotation.postRotate(270);
            else if(orientation==2)rotation.preScale(-1,1);
            else if(orientation==4)rotation.preScale(1,-1);
            else if(orientation==5){rotation.preScale(-1,1);rotation.postRotate(270);}
            else if(orientation==7){rotation.preScale(-1,1);rotation.postRotate(90);}
            adjusted=android.graphics.Bitmap.createBitmap(
                bitmap,0,0,bitmap.getWidth(),bitmap.getHeight(),rotation,true);
            int longEdge=Math.max(adjusted.getWidth(),adjusted.getHeight());
            float ratio=Math.min(1.0f,1280.0f/longEdge);
            int rw=Math.max(1,Math.round(adjusted.getWidth()*ratio));
            int rh=Math.max(1,Math.round(adjusted.getHeight()*ratio));
            small=android.graphics.Bitmap.createScaledBitmap(adjusted,rw,rh,true);
            ByteArrayOutputStream compressed=new ByteArrayOutputStream();
            if(!small.compress(android.graphics.Bitmap.CompressFormat.JPEG,82,compressed))
                throw new Exception("דחיסת תמונת המקור נכשלה");
            byte[] data=compressed.toByteArray();
            if(data.length>4_800_000||data.length<100)
                throw new Exception("תמונת המקור גדולה מדי גם לאחר התאמה לשרת");
            JSONObject result=new JSONObject();
            result.put("mime_type","image/jpeg");
            result.put("data_base64",Base64.encodeToString(data,Base64.NO_WRAP));
            return result;
        }finally{
            if(small!=null && small!=adjusted && small!=bitmap)small.recycle();
            if(adjusted!=null && adjusted!=bitmap)adjusted.recycle();
            bitmap.recycle();
        }
    }
    private static JSONObject image(Context ctx,Uri uri) throws Exception {''')

once('''        images.put(image(ctx,photoOne));
        if(photoTwo!=null)images.put(image(ctx,photoTwo));''',
'''        // CPU path only; original photos remain on-device untouched.
        images.put(smallCpuImage(ctx,photoOne));
        if(photoTwo!=null)images.put(smallCpuImage(ctx,photoTwo));''')

for old,new in [
    ("applicationId 'com.kolbo.videostudio.preview422'",
     "applicationId 'com.kolbo.videostudio.preview423'"),
    ("versionCode 422","versionCode 423"),
    ("versionName '4.2.2'","versionName '4.2.3'")
]:
    n=gradle.count(old)
    if n!=1:raise SystemExit(f"v423 version mismatch {old}: {n}")
    gradle=gradle.replace(old,new,1)
assert 'smallCpuImage(ctx,photoOne)' in s and 'image(ctx,subjectOne)' in s
assert 'smallCpuImage(ctx,photoTwo)' in s
assert 'android.media.ExifInterface' in s
assert '1280.0f/longEdge' in s
assert 'preview423' in gradle
target.write_text(s,encoding='utf-8')
gradle_file.write_text(gradle,encoding='utf-8')
print("PASS v423: photo inputs downscaled and rotated on device, separate AI provider path untouched")
