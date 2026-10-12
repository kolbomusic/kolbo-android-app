package com.kolbomusic.video;

import android.app.Activity;
import android.os.Bundle;
import android.content.Intent;
import android.content.ClipData;
import android.content.SharedPreferences;
import android.graphics.Color;
import android.net.Uri;
import android.content.ContentResolver;
import android.database.Cursor;
import android.provider.OpenableColumns;
import android.view.View;
import android.view.Gravity;
import android.widget.Button;
import android.widget.CheckBox;
import android.widget.EditText;
import android.widget.ImageView;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.SeekBar;
import android.widget.TextView;
import android.widget.Toast;
import org.json.JSONObject;
import java.net.URL;
import java.net.HttpURLConnection;
import java.nio.charset.StandardCharsets;
import java.io.InputStream;
import java.io.ByteArrayOutputStream;
import java.util.ArrayList;
import java.util.HashSet;
import java.util.Locale;
import java.util.Set;

/** Zero-configuration Hebrew Android front end, with local-only drafts.
 *
 * This APK intentionally never submits media to the preview server. A real
 * authenticated upload protocol and an authorized GPU must be integrated and
 * verified before the create button can initiate a real generation.
 */
public final class MainActivity extends Activity {
    private static final int PICK_IMAGES=507;
    private static final String CONFIG_ENDPOINT=
        "https://kolbo-video-v450-safe-preview.onrender.com/v1/app-config";
    private static final int PURPLE=Color.rgb(104,37,208);
    private static final int DARK=Color.rgb(39,24,66);
    private static final int SOFT=Color.rgb(248,246,252);
    private final ArrayList<Uri> pictures=new ArrayList<>();
    private EditText prompt;
    private TextView durationLabel,photoLabel,infraLabel,draftLabel;
    private LinearLayout photosContainer;
    private CheckBox singing;
    private SeekBar duration;
    private Button createButton;
    private volatile boolean checking=false;
    private boolean verifiedGpu=false;
    private boolean verifiedStorage=false;
    private boolean preview=true;

    private int dp(float v){return Math.round(v*getResources().getDisplayMetrics().density);}
    private TextView text(String value,int sp,int color){
        TextView t=new TextView(this);
        t.setText(value);t.setTextSize(sp);t.setTextColor(color);
        return t;
    }
    private void addGap(LinearLayout parent,int height){
        View v=new View(this);
        parent.addView(v,new LinearLayout.LayoutParams(1,dp(height)));
    }
    private Button action(String label,boolean primary){
        Button b=new Button(this);
        b.setText(label);
        b.setTextSize(16);
        b.setAllCaps(false);
        if(primary){b.setBackgroundTintList(android.content.res.ColorStateList.valueOf(PURPLE));
            b.setTextColor(Color.WHITE);}
        else b.setTextColor(DARK);
        return b;
    }
    @Override public void onCreate(Bundle state){
        super.onCreate(state);
        getWindow().setStatusBarColor(SOFT);
        getWindow().setNavigationBarColor(Color.rgb(36,29,52));
        getWindow().getDecorView().setSystemUiVisibility(View.SYSTEM_UI_FLAG_LIGHT_STATUS_BAR);
        ScrollView scroll=new ScrollView(this);
        scroll.setFillViewport(true);
        scroll.setBackgroundColor(SOFT);
        LinearLayout body=new LinearLayout(this);
        body.setOrientation(LinearLayout.VERTICAL);
        body.setLayoutDirection(View.LAYOUT_DIRECTION_RTL);
        body.setPadding(dp(20),dp(26),dp(20),dp(28));
        scroll.addView(body);
        setContentView(scroll);
        TextView brand=text("Kolbo Video",28,DARK);
        brand.setGravity(Gravity.RIGHT);body.addView(brand);
        TextView subtitle=text("יוצרים סרטון מהסיפור שלך",15,Color.DKGRAY);
        body.addView(subtitle);
        addGap(body,20);
        infraLabel=text("בודק אוטומטית את מנוע ההפקה…",14,DARK);
        infraLabel.setPadding(dp(15),dp(14),dp(15),dp(14));
        infraLabel.setBackgroundTintList(null);
        infraLabel.setBackgroundColor(Color.rgb(235,225,250));
        body.addView(infraLabel);
        addGap(body,23);
        body.addView(text("מה קורה בסרטון?",18,DARK));
        prompt=new EditText(this);
        prompt.setHint("לדוגמה: שתי הדמויות רוקדות ושרות בעברית ליד פסנתר…");
        prompt.setTextSize(16);
        prompt.setGravity(Gravity.TOP|Gravity.RIGHT);
        prompt.setMinLines(4);
        prompt.setMaxLines(7);
        prompt.setBackgroundTintList(android.content.res.ColorStateList.valueOf(PURPLE));
        prompt.setInputType(android.text.InputType.TYPE_CLASS_TEXT|
            android.text.InputType.TYPE_TEXT_FLAG_MULTI_LINE|
            android.text.InputType.TYPE_TEXT_FLAG_CAP_SENTENCES);
        body.addView(prompt);
        addGap(body,17);
        body.addView(text("תמונות הדמויות (עד 2)",18,DARK));
        photoLabel=text("לא נבחרו תמונות",14,Color.DKGRAY);
        body.addView(photoLabel);
        photosContainer=new LinearLayout(this);
        photosContainer.setOrientation(LinearLayout.HORIZONTAL);
        photosContainer.setLayoutDirection(View.LAYOUT_DIRECTION_RTL);
        body.addView(photosContainer);
        Button pick=action("הוסף או החלף תמונות",false);
        pick.setOnClickListener(v->pickImages());
        body.addView(pick);
        addGap(body,16);
        durationLabel=text("אורך הסרטון: 8 שניות",18,DARK);
        body.addView(durationLabel);
        duration=new SeekBar(this);
        duration.setMax(14);
        duration.setProgress(7);
        duration.setOnSeekBarChangeListener(new SeekBar.OnSeekBarChangeListener(){
            public void onProgressChanged(SeekBar bar,int progress,boolean fromUser){
                durationLabel.setText("אורך הסרטון: "+(progress+1)+" שניות");
            }
            public void onStartTrackingTouch(SeekBar bar){}
            public void onStopTrackingTouch(SeekBar bar){}
        });
        body.addView(duration);
        singing=new CheckBox(this);
        singing.setText("כולל שירה / דיבור מסונכרן כשמנוע מתאים יהיה זמין");
        singing.setTextColor(DARK);
        body.addView(singing);
        addGap(body,18);
        createButton=action("צור את הסרטון שלי",true);
        createButton.setOnClickListener(v->submitOrDraft());
        body.addView(createButton);
        Button save=action("שמור טיוטה בטלפון",false);
        save.setOnClickListener(v->saveDraftOnly());
        body.addView(save);
        addGap(body,9);
        draftLabel=text("",13,Color.DKGRAY);
        body.addView(draftLabel);
        addGap(body,18);
        TextView privacy=text("פרטיות: התמונות והבקשה נשארות בטלפון. אין העלאה אוטומטית לספק חיצוני, אין מנוי ואין חיוב. טיוטה אינה הפקת וידאו.",13,Color.DKGRAY);
        body.addView(privacy);
        Button refresh=action("בדיקת מנוע ההפקה מחדש",false);
        refresh.setOnClickListener(v->refreshCapacity());
        body.addView(refresh);
        restoreDraft();
        refreshCapacity();
    }
    private void pickImages(){
        Intent i=new Intent(Intent.ACTION_OPEN_DOCUMENT);
        i.setType("image/*");
        i.addCategory(Intent.CATEGORY_OPENABLE);
        i.putExtra(Intent.EXTRA_ALLOW_MULTIPLE,true);
        i.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION|Intent.FLAG_GRANT_PERSISTABLE_URI_PERMISSION);
        try{startActivityForResult(i,PICK_IMAGES);}
        catch(Exception e){Toast.makeText(this,"בחירת תמונות אינה זמינה",Toast.LENGTH_LONG).show();}
    }
    @Override protected void onActivityResult(int request,int result,Intent data){
        super.onActivityResult(request,result,data);
        if(request!=PICK_IMAGES||result!=RESULT_OK||data==null)return;
        ArrayList<Uri> chosen=new ArrayList<>();
        ClipData clips=data.getClipData();
        if(clips!=null){
            if(clips.getItemCount()>2){Toast.makeText(this,"אפשר לבחור עד שתי תמונות",Toast.LENGTH_LONG).show();return;}
            for(int j=0;j<clips.getItemCount();j++)chosen.add(clips.getItemAt(j).getUri());
        }else if(data.getData()!=null)chosen.add(data.getData());
        Set<String> seen=new HashSet<>();
        for(Uri item:chosen){
            if(!"content".equals(item.getScheme())||!seen.add(item.toString())||
                !validImage(item)){Toast.makeText(this,"בחר תמונות JPG/PNG/WEBP שגודלן עד 12MB",Toast.LENGTH_LONG).show();return;}
        }
        int flags=data.getFlags()&Intent.FLAG_GRANT_READ_URI_PERMISSION;
        for(Uri item:chosen){
            try{getContentResolver().takePersistableUriPermission(item,flags);}
            catch(SecurityException e){Toast.makeText(this,"לא ניתן לשמור גישה לתמונה שנבחרה",Toast.LENGTH_LONG).show();return;}
        }
        pictures.clear();pictures.addAll(chosen);
        renderPhotos();
    }
    private boolean validImage(Uri u){
        try{
            String type=getContentResolver().getType(u);
            if(!("image/jpeg".equals(type)||"image/png".equals(type)||"image/webp".equals(type)))return false;
            try(Cursor c=getContentResolver().query(u,new String[]{OpenableColumns.SIZE},null,null,null)){
                if(c!=null&&c.moveToFirst()&&!c.isNull(0)){
                    long bytes=c.getLong(0);return bytes>0&&bytes<=12_000_000L;
                }
            }
            return false;
        }catch(Exception e){return false;}
    }
    private void renderPhotos(){
        photosContainer.removeAllViews();
        photoLabel.setText(pictures.size()==0?"לא נבחרו תמונות":("נבחרו "+pictures.size()+" מתוך 2 תמונות"));
        for(Uri uri:pictures){
            ImageView image=new ImageView(this);
            image.setScaleType(ImageView.ScaleType.CENTER_CROP);
            try{image.setImageURI(uri);}catch(Exception ignored){}
            LinearLayout.LayoutParams lp=new LinearLayout.LayoutParams(dp(100),dp(100));
            lp.setMargins(dp(2),dp(8),dp(10),dp(8));photosContainer.addView(image,lp);
        }
    }
    private void saveDraftOnly(){
        String p=prompt.getText().toString().trim();
        if(p.length()<5){Toast.makeText(this,"כתוב תיאור של לפחות 5 תווים",Toast.LENGTH_SHORT).show();return;}
        SharedPreferences.Editor ed=getPreferences(MODE_PRIVATE).edit();
        ed.putString("draft_prompt",p).putInt("draft_seconds",duration.getProgress()+1)
          .putBoolean("draft_singing",singing.isChecked())
          .putInt("draft_pictures_count",pictures.size());
        for(int j=0;j<2;j++)ed.putString("draft_picture_"+j,j<pictures.size()?pictures.get(j).toString():"");
        ed.apply();
        draftLabel.setText("הטיוטה נשמרה בטלפון. היא עדיין לא נשלחה להפקה.");
        Toast.makeText(this,"הטיוטה נשמרה בטלפון",Toast.LENGTH_SHORT).show();
    }
    private void restoreDraft(){
        SharedPreferences pref=getPreferences(MODE_PRIVATE);
        prompt.setText(pref.getString("draft_prompt",""));
        int secs=Math.min(15,Math.max(1,pref.getInt("draft_seconds",8)));
        duration.setProgress(secs-1);
        singing.setChecked(pref.getBoolean("draft_singing",false));
        for(int j=0;j<2;j++){
            String u=pref.getString("draft_picture_"+j,"");
            if(!u.isEmpty()){
                Uri uri=Uri.parse(u);
                if(validImage(uri))pictures.add(uri);
            }
        }
        renderPhotos();
        if(!pref.getString("draft_prompt","").isEmpty())
            draftLabel.setText("נטענה הטיוטה האחרונה שנשמרה בטלפון");
    }
    private void submitOrDraft(){
        saveDraftOnly();
        if(prompt.getText().toString().trim().length()<5)return;
        String blocker;
        if(!verifiedStorage||!verifiedGpu||preview)
            blocker="לא ניתן להפיק עדיין: לא אומתו GPU ואחסון הפקה. הטיוטה נשמרה מקומית בלבד.";
        else blocker="מנוע נמצא, אך אימות משתמש והעברת מדיה טרם הושלמו. הטיוטה לא נשלחה.";
        infraLabel.setText(blocker);
        Toast.makeText(this,"הפקה אמיתית עדיין אינה פעילה",Toast.LENGTH_LONG).show();
    }
    private void refreshCapacity(){
        if(checking)return;
        checking=true;
        infraLabel.setText("בודק את שרת Kolbo אוטומטית…");
        new Thread(()->{
            boolean valid=false,gpu=false,store=false,previewOnly=true;
            try{
                URL url=new URL(CONFIG_ENDPOINT);
                HttpURLConnection c=(HttpURLConnection)url.openConnection();
                c.setConnectTimeout(7000);c.setReadTimeout(7000);
                c.setInstanceFollowRedirects(false);
                c.setRequestProperty("Accept","application/json");
                try{
                    if(c.getResponseCode()==200&&
                       "https".equalsIgnoreCase(c.getURL().getProtocol())){
                        InputStream in=c.getInputStream();
                        ByteArrayOutputStream output=new ByteArrayOutputStream();
                        byte[] buf=new byte[1024];int n;
                        while((n=in.read(buf))>=0){
                            if(output.size()+n>8192)throw new IllegalArgumentException("Excess config");
                            output.write(buf,0,n);
                        }
                        in.close();
                        JSONObject obj=new JSONObject(output.toString("UTF-8"));
                        valid="kolbo-volunteer-mesh".equals(obj.optString("service"))&&
                            obj.optInt("api_contract",0)>=449&&
                            obj.optBoolean("paid_gpu_fallback_enabled",true)==false;
                        previewOnly=obj.optBoolean("preview_only",true);
                        gpu=obj.optBoolean("gpu_ready",false)&&obj.optBoolean("real_video_generation_verified",false);
                        store=obj.optBoolean("persistent_storage_ready",false)&&
                            obj.optBoolean("private_media_upload_enabled",false);
                    }
                }finally{c.disconnect();}
            }catch(Exception ignored){}
            final boolean ok=valid,hasGpu=gpu,hasStorage=store,isPreview=previewOnly;
            runOnUiThread(()->{
                checking=false;
                verifiedGpu=ok&&hasGpu;
                verifiedStorage=ok&&hasStorage;
                preview=!ok||isPreview;
                if(!ok)infraLabel.setText("החיבור למנוע ההפקה אינו זמין כרגע. הטיוטות נשארות בטלפון.");
                else if(preview||!verifiedStorage||!verifiedGpu)
                    infraLabel.setText("האפליקציה מחוברת אוטומטית ל־Kolbo. טרם הופעל מנוע GPU ואחסון הפקה מאומתים. אין יצירת AI בשלב זה.");
                else infraLabel.setText("מנוע ההפקה זמין; הפעלת העברת מדיה מחייבת השלמת אימות מאובטח.");
            });
        },"KolboReadiness").start();
    }
    @Override protected void onResume(){super.onResume();if(infraLabel!=null)refreshCapacity();}
}
