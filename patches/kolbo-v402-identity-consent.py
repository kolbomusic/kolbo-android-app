from pathlib import Path
import re,sys
root=Path(sys.argv[1])
main=root/'app/src/main/java/com/kolbo/videostudio/MainActivity.java'
gradle=root/'app/build.gradle'
s=main.read_text(encoding='utf-8')

def change(old,new):
    global s
    n=s.count(old)
    if n!=1: raise SystemExit("Expected exactly one match (%d): %s"%(n,old[:100]))
    s=s.replace(old,new,1)

change('import android.widget.VideoView;', 'import android.widget.VideoView;\nimport android.widget.ImageView;')
change('private TextView secondSelected;', 'private TextView secondSelected;\n    private ImageView photoOnePreview,photoTwoPreview;\n    private volatile byte[] approvedComposite;\n    private volatile boolean identityReviewRequired;')
change('selected = label("ללא תמונה — יצירה מטקסט בלבד", 13, false);root.addView(selected);',
       'selected = label("ללא תמונה — יצירה מטקסט בלבד", 13, false);root.addView(selected);\n        photoOnePreview=new ImageView(this);photoOnePreview.setAdjustViewBounds(true);photoOnePreview.setVisibility(View.GONE);root.addView(photoOnePreview,new LinearLayout.LayoutParams(-1,dp(140)));')
change('secondSelected = label("דמות 2: לא נבחרה תמונה",13,false);root.addView(secondSelected);',
       'secondSelected = label("דמות 2: לא נבחרה תמונה",13,false);root.addView(secondSelected);\n        photoTwoPreview=new ImageView(this);photoTwoPreview.setAdjustViewBounds(true);photoTwoPreview.setVisibility(View.GONE);root.addView(photoTwoPreview,new LinearLayout.LayoutParams(-1,dp(140)));')
change('download = button("הורד MP4");', 'download = button("הורד MP4");')
change('private void createVideo() {',"""private void previewDuoBeforeUpload(String instruction,Uri first,Uri second,int seconds){
        // The preview consists exclusively of cutouts from the selected photos.
        // Nothing is sent to the internet until the user explicitly approves.
        busy(true);
        message("מכין תצוגה מקדימה משתי התמונות המקומיות...");
        executor.execute(() -> {
            try {
                byte[] bytes=jointReference(first,second);
                Bitmap preview=BitmapFactory.decodeByteArray(bytes,0,bytes.length);
                if(preview==null)throw new Exception("תמונת השילוב אינה תקינה");
                ui.post(() -> {
                    if(stopping){preview.recycle();busy(false);return;}
                    busy(false);
                    ImageView view=new ImageView(this);
                    view.setImageBitmap(preview);
                    view.setAdjustViewBounds(true);
                    view.setPadding(dp(12),dp(8),dp(12),dp(8));
                    new AlertDialog.Builder(this)
                      .setTitle("בדיקת שתי הדמויות לפני יצירה")
                      .setMessage("אלה שתי הדמויות שנבחרו משתי התמונות. לחץ 'נסה' רק אם הן נראות נכון כאן. מנוע הווידאו החינמי מקבל תמונה משולבת אחת, ועלול להחליף אותן בדמויות אחרות. הווידאו יישמר כטיוטה לא מאומתת, ולא כהצלחה. שירה בבוכרית אינה מובטחת.")
                      .setView(view)
                      .setPositiveButton("נסה הפקה ניסיונית",(d,w)->{
                          approvedComposite=bytes;
                          beginGeneration(instruction,first,second,seconds);
                      })
                      .setNegativeButton("ביטול",(d,w)->{
                          approvedComposite=null;
                          preview.recycle();
                          message("היצירה בוטלה: התמונות לא נשלחו לספק הווידאו");
                      })
                      .setOnCancelListener(d->{approvedComposite=null;preview.recycle();})
                      .show();
                });
            } catch(Exception e){
                approvedComposite=null;
                message("נכשלה הכנת שתי הדמויות: "+e.getMessage());
                busy(false);
            }
        });
    }
    private void createVideo() {""")
pattern=r'        if\(second!=null\)\{\s*new AlertDialog.Builder\(this\).*?\.show\(\);return;\s*\}\n        if\(chosen!=null && mayConflictWithImage'
repl='        if(second!=null){previewDuoBeforeUpload(instruction,chosen,second,desired);return;}\n        if(chosen!=null && mayConflictWithImage'
s,n=re.subn(pattern,repl,s,flags=re.S)
if n!=1: raise SystemExit('Two-image consent dialog patch failed: '+str(n))
change('private void beginGeneration(String instruction, Uri chosen, Uri second, int requestedSeconds) {\n        if(running)return;',
       'private void beginGeneration(String instruction, Uri chosen, Uri second, int requestedSeconds) {\n        if(running)return;\n        identityReviewRequired=(second!=null);')
change('imageMeta=uploadImageBytes(jointReference(first,second),"image/jpeg");',
       'byte[] reference=approvedComposite;\n                    approvedComposite=null;\n                    imageMeta=uploadImageBytes(reference!=null?reference:jointReference(first,second),"image/jpeg");')
change('private void showResult(File file,String notice){\n        resultFile=file;',
       'private void showResult(File file,String notice){\n        resultFile=file;\n        final boolean unverified=identityReviewRequired;\n        final String displayNotice=unverified?("טיוטת AI לא מאומתת: לא ניתן לקבוע שהדמויות נשמרו מתמונות המקור. השווה את שתי התמונות לסרטון לפני השימוש. "+notice):notice;')
change('download.setVisibility(View.VISIBLE);\n            status.setText(notice);',
       'download.setVisibility(View.VISIBLE);\n            download.setText(unverified?"שמור טיוטת MP4 (זהות לא אומתה)":"הורד MP4");\n            status.setText(displayNotice);')
change('message("הסרטון נשמר בהצלחה");',
       'message(identityReviewRequired?"טיוטת MP4 נשמרה. שמירת זהות הדמויות ושירתן לא אומתו.":"הסרטון נשמר בהצלחה");')
change('image=data.getData();\n            selected.setText("נבחרה תמונה לדמות 1");',
       'image=data.getData();\n            approvedComposite=null;\n            selected.setText("נבחרה תמונה לדמות 1 — תצוגת מקור");\n            photoOnePreview.setImageURI(image);\n            photoOnePreview.setVisibility(View.VISIBLE);')
change('imageTwo=data.getData();\n            secondSelected.setText("נבחרה תמונה לדמות 2");',
       'imageTwo=data.getData();\n            approvedComposite=null;\n            secondSelected.setText("נבחרה תמונה לדמות 2 — תצוגת מקור");\n            photoTwoPreview.setImageURI(imageTwo);\n            photoTwoPreview.setVisibility(View.VISIBLE);')
main.write_text(s,encoding='utf-8')
g=gradle.read_text(encoding='utf-8')
for old,new in [("applicationId 'com.kolbo.videostudio.preview401'","applicationId 'com.kolbo.videostudio.preview402'"),("versionCode 401","versionCode 402"),("versionName '4.0.1'","versionName '4.0.2'")]:
    if g.count(old)!=1: raise SystemExit('Gradle identity/version changed: '+old)
    g=g.replace(old,new)
gradle.write_text(g,encoding='utf-8')

assert 'imageMeta=uploadImageBytes(reference!=null?reference:jointReference(first,second)' in s
assert 'final boolean unverified=identityReviewRequired;' in s
assert 'view.setImageBitmap(preview);' in s
print('PASS 4.0.2: source thumbnails, offline duo composition preview, explicit consent, unverified-draft UI, side-by-side APK')
