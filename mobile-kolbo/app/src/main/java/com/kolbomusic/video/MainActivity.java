package com.kolbomusic.video;

import android.app.Activity;
import android.content.ClipData;
import android.content.Intent;
import android.graphics.Color;
import android.graphics.drawable.GradientDrawable;
import android.net.Uri;
import android.os.Bundle;
import android.view.Gravity;
import android.view.View;
import android.view.ViewGroup;
import android.widget.Button;
import android.widget.CheckBox;
import android.widget.EditText;
import android.widget.ImageView;
import android.widget.LinearLayout;
import android.widget.ProgressBar;
import android.widget.ScrollView;
import android.widget.Spinner;
import android.widget.ArrayAdapter;
import android.widget.TextView;
import android.widget.Toast;
import android.media.MediaMetadataRetriever;
import android.widget.MediaController;
import androidx.media3.common.MediaItem;
import androidx.media3.common.Player;
import androidx.media3.exoplayer.ExoPlayer;
import androidx.media3.ui.PlayerView;

import java.io.File;
import java.io.FileInputStream;
import java.io.OutputStream;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

/** Real Android studio in Hebrew, not an embedded English Gradio website. */
public final class MainActivity extends Activity {
    private static final int CHOOSE_IMAGE=469;
    private static final int SAVE_VIDEO=470;
    private static final int BG=Color.rgb(17,20,32);
    private static final int PANEL=Color.rgb(35,42,65);
    private static final int TEXT=Color.rgb(247,249,255);
    private static final int MUTED=Color.rgb(190,199,224);
    private static final int ACCENT=Color.rgb(111,63,215);
    private final ExecutorService worker=Executors.newSingleThreadExecutor();
    private WanNativeClient engine=new WanNativeClient();
    private Uri image;
    private File video;
    private boolean busy=false;
    private boolean afterFailed=false;
    private boolean unknownAcceptance=false;
    private ScrollView scroll;
    private LinearLayout panel;
    private EditText prompt;
    private Spinner duration;
    private CheckBox consent;
    private ImageView photoPreview;
    private TextView photoLabel,status,limits;
    private ProgressBar progress;
    private PlayerView preview;
    private ExoPlayer playback;
    private TextView interpretation;
    private int requestedSeconds=2;
    private Button generate,save,review,recover;

    private int dp(int x){return Math.round(x*getResources().getDisplayMetrics().density);}
    private GradientDrawable shape(int color,int radius){
        GradientDrawable g=new GradientDrawable();
        g.setColor(color);g.setCornerRadius(dp(radius));return g;
    }
    private TextView text(String t,int size,int color){
        TextView v=new TextView(this);
        v.setText(t);v.setTextColor(color);v.setTextSize(size);
        v.setGravity(Gravity.RIGHT);v.setTextDirection(View.TEXT_DIRECTION_RTL);
        v.setLineSpacing(dp(3),1.05f);return v;
    }
    private void gap(int height){
        View v=new View(this);
        panel.addView(v,new LinearLayout.LayoutParams(1,dp(height)));
    }
    private Button button(String name,boolean secondary){
        Button b=new Button(this);
        b.setText(name);b.setAllCaps(false);
        b.setTextSize(16);b.setTextColor(TEXT);
        b.setBackground(shape(secondary?PANEL:ACCENT,15));
        panel.addView(b,new LinearLayout.LayoutParams(
            ViewGroup.LayoutParams.MATCH_PARENT,dp(54)));
        return b;
    }
    private void toast(String t){Toast.makeText(this,t,Toast.LENGTH_LONG).show();}
    private void show(String t){runOnUiThread(()->status.setText(t));}
    private void setBusy(boolean active){
        busy=active;
        progress.setVisibility(active?View.VISIBLE:View.GONE);
        generate.setEnabled(!active);
        recover.setEnabled(!active);
        generate.setAlpha(active?.5f:1f);
    }
    @Override public void onCreate(Bundle bundle){
        super.onCreate(bundle);
        getWindow().setStatusBarColor(BG);
        getWindow().setNavigationBarColor(BG);
        scroll=new ScrollView(this);
        scroll.setFillViewport(true);
        scroll.setBackgroundColor(BG);
        scroll.setLayoutDirection(View.LAYOUT_DIRECTION_RTL);
        panel=new LinearLayout(this);
        panel.setOrientation(LinearLayout.VERTICAL);
        panel.setPadding(dp(18),dp(24),dp(18),dp(28));
        scroll.addView(panel);
        setContentView(scroll);

        TextView title=text("כלבו וידאו AI",30,TEXT);
        title.setTypeface(null,android.graphics.Typeface.BOLD);
        panel.addView(title);
        panel.addView(text("אולפן יצירת וידאו · בעברית · ללא אתר בתוך האפליקציה",14,MUTED));
        gap(22);

        TextView label=text("1. הוסף תמונת ייחוס",19,TEXT);
        label.setTypeface(null,android.graphics.Typeface.BOLD);
        panel.addView(label);gap(8);
        photoPreview=new ImageView(this);
        photoPreview.setBackground(shape(PANEL,16));
        photoPreview.setScaleType(ImageView.ScaleType.CENTER_INSIDE);
        photoPreview.setVisibility(View.GONE);
        panel.addView(photoPreview,new LinearLayout.LayoutParams(
            ViewGroup.LayoutParams.MATCH_PARENT,dp(210)));
        gap(7);
        photoLabel=text("עדיין לא נבחרה תמונה. לתנועת גוף מלאה מומלץ צילום גוף מלא ולא תקריב פנים.",14,MUTED);
        panel.addView(photoLabel);gap(12);
        button("בחר תמונה מהטלפון",true).setOnClickListener(v->selectImage());
        gap(22);

        TextView story=text("2. תאר מה באמת צריך לקרות בסרטון",19,TEXT);
        story.setTypeface(null,android.graphics.Typeface.BOLD);
        panel.addView(story);gap(9);
        prompt=new EditText(this);
        prompt.setGravity(Gravity.RIGHT|Gravity.TOP);
        prompt.setTextDirection(View.TEXT_DIRECTION_RTL);
        prompt.setTextColor(TEXT);prompt.setHintTextColor(MUTED);
        prompt.setHint("מה תרצה שיקרה בסרטון? פשוט כתוב במילים שלך.");
        prompt.setTextSize(16);
        prompt.setMinLines(4);prompt.setMaxLines(8);
        prompt.setInputType(android.text.InputType.TYPE_CLASS_TEXT|
            android.text.InputType.TYPE_TEXT_FLAG_MULTI_LINE);
        prompt.setPadding(dp(16),dp(16),dp(16),dp(16));
        prompt.setBackground(shape(PANEL,15));
        panel.addView(prompt);
        gap(8);
        interpretation=text("כתוב בחופשיות — האפליקציה תזהה את האירועים והדמויות.",14,MUTED);
        panel.addView(interpretation);
        prompt.addTextChangedListener(new android.text.TextWatcher(){
            @Override public void beforeTextChanged(CharSequence x,int a,int c,int n){}
            @Override public void onTextChanged(CharSequence x,int a,int before,int count){
                if(x.length()<3) {
                    interpretation.setText("כתוב במילים שלך, ללא ניסוח מיוחד.");return;
                }
                try{
                    HebrewStoryDirector.Plan p=HebrewStoryDirector.understand(x.toString());
                    interpretation.setText("הבנתי: "+p.visibleSummary +
                       (p.complexScene ? "\nסצנה מורכבת: מנוע הניסוי עשוי לא להצליח בכל הפרטים." : ""));
                }catch(RuntimeException e){interpretation.setText("הוסף מה תרצה שיקרה.");}
            }
            @Override public void afterTextChanged(android.text.Editable x){}
        });
        gap(20);

        TextView time=text("3. משך הסרטון",19,TEXT);
        time.setTypeface(null,android.graphics.Typeface.BOLD);
        panel.addView(time);gap(8);
        duration=new Spinner(this);
        String[] choices={"2 שניות","3 שניות","4 שניות","5 שניות"};
        ArrayAdapter<String> adapter=new ArrayAdapter<>(this,
            android.R.layout.simple_spinner_dropdown_item,choices);
        duration.setAdapter(adapter);
        duration.setSelection(0); // 2s was proven on public ZeroGPU; 5s may exceed quota.
        duration.setBackground(shape(PANEL,12));
        panel.addView(duration,new LinearLayout.LayoutParams(
            ViewGroup.LayoutParams.MATCH_PARENT,dp(50)));
        gap(13);

        limits=text("ניסוי וידאו אילם מתמונה אחת, 2–5 שניות. "+
            "שמע, שתי דמויות ודיוק מלא בהוראות אינם נתמכים כרגע.",13,MUTED);
        panel.addView(limits);gap(11);

        consent=new CheckBox(this);
        consent.setText("אני מאשר לשלוח את תמונת הייחוס למנוע החיצוני של Hugging Face לצורך ההפקה.");
        consent.setTextColor(TEXT);
        consent.setTextSize(14);
        consent.setButtonTintList(android.content.res.ColorStateList.valueOf(
            Color.rgb(178,142,255)));
        panel.addView(consent);gap(15);

        generate=button("צור סרטון AI",false);
        generate.setOnClickListener(v->begin());
        gap(12);
        recover=button("בדוק משימה קודמת בלי לשלוח מחדש",true);
        recover.setOnClickListener(v->recoverPending());
        gap(15);
        progress=new ProgressBar(this);
        progress.setVisibility(View.GONE);panel.addView(progress);
        status=text("מוכן. הפעולה תישלח רק כשתלחץ על יצירה.",15,MUTED);
        panel.addView(status);gap(14);

        preview=new PlayerView(this);
        preview.setUseController(true);
        preview.setResizeMode(androidx.media3.ui.AspectRatioFrameLayout.RESIZE_MODE_FIT);
        preview.setVisibility(View.GONE);
        preview.setBackground(shape(PANEL,12));
        panel.addView(preview,new LinearLayout.LayoutParams(
            ViewGroup.LayoutParams.MATCH_PARENT,dp(240)));
        gap(10);
        save=button("שמור סרטון לטלפון",true);
        save.setVisibility(View.GONE);
        save.setOnClickListener(v->saveVideo());
        gap(8);
        review=button("הסרטון לא ביצע את ההנחיה",true);
        review.setVisibility(View.GONE);
        review.setOnClickListener(v->{
            show("הסרטון סומן כלא תואם. לא תבוצע יצירה חוזרת או חיוב אוטומטי. "+
                "אפשר לנסח מחדש פעולה פיזית מפורטת לפני ניסיון ידני נוסף.");
            afterFailed=true;
        });
        gap(10);
        panel.addView(text("התרגום מתבצע במכשיר; הורדת מודל ראשונית דורשת אינטרנט. "+
            "ההפקה בענן הציבורי כפופה למכסה. אין תשלום אוטומטי.",12,MUTED));

        prompt.setText(getPreferences(MODE_PRIVATE).getString("draft",""));
        if(getPreferences(MODE_PRIVATE).getBoolean("uncertain_submission",false))
            status.setText("ייתכן שבקשה קודמת התקבלה במנוע. בדוק אותה לפני ניסיון נוסף.");
        recover.setVisibility(getPreferences(MODE_PRIVATE).getString("last_event","").isEmpty()
            ?View.GONE:View.VISIBLE);
    }
    private void selectImage(){
        if(busy)return;
        Intent i=new Intent(Intent.ACTION_OPEN_DOCUMENT);
        i.setType("image/*");i.addCategory(Intent.CATEGORY_OPENABLE);
        i.putExtra(Intent.EXTRA_ALLOW_MULTIPLE,false);
        try{startActivityForResult(i,CHOOSE_IMAGE);}
        catch(Exception e){toast("לא ניתן לפתוח את התמונות");}
    }
    private String unsupported(String text){
        String p=text.toLowerCase(java.util.Locale.ROOT);
        if(p.contains("שר ")||p.contains("שרה")||p.contains("לשיר")||
            p.contains("שירה")||p.contains("מדבר")||p.contains("אומר")||
            p.contains("בקול")||p.contains("דיבור")||p.contains("קולות")||
            p.contains("בוכרית")||p.contains("מוזיקה")||p.contains("שומעים"))
            return "הבקשה מחייבת קול או שירה; המנוע הנוכחי מפיק וידאו אילם בלבד.";
        if(p.contains("שתי דמויות")||p.contains("שני אנשים")||
            p.contains("2 דמויות")||p.contains("שתי תמונות"))
            return "המנוע הנוכחי אינו מסוגל לשמור שתי דמויות נפרדות מתמונות שונות.";
        return null;
    }
    private void begin(){
        if(busy)return;
        if(image==null){toast("יש לבחור תמונה תחילה");return;}
        String story=prompt.getText().toString().trim();
        if(story.length()<5){toast("כתוב מה תרצה שיקרה בסרטון");return;}
        HebrewStoryDirector.Plan plan=HebrewStoryDirector.understand(story);
        String blocker=plan.supportedLimit();
        if(blocker!=null){show(blocker+" לא נשלחה בקשה.");return;}
        if(!consent.isChecked()){
            show("לפני העלאת התמונה יש לאשר העברה לספק החיצוני.");return;
        }
        if(getPreferences(MODE_PRIVATE).getBoolean("uncertain_submission",false)){
            show("נותרה בקשה שייתכן שהתקבלה. בדוק אותה לפני ניסיון חדש.");return;
        }
        final int seconds=duration.getSelectedItemPosition()+2;
        requestedSeconds=seconds;
        getPreferences(MODE_PRIVATE).edit().putInt("requested_seconds",seconds).apply();
        getPreferences(MODE_PRIVATE).edit().putString("draft",story).apply();
        setBusy(true);preview.setVisibility(View.GONE);
        save.setVisibility(View.GONE);review.setVisibility(View.GONE);
        worker.execute(()->{
            try{
                WanNativeClient.Result result=engine.create(this,image,story,seconds,
                    new WanNativeClient.Progress(){
                        @Override public void status(String value){show(value);}
                        @Override public void beforeSubmission(){
                            // Persist before network POST: after a crash an accepted job is uncertain.
                            boolean saved=getPreferences(MODE_PRIVATE).edit()
                                .putBoolean("uncertain_submission",true).commit();
                            if(!saved)throw new IllegalStateException(
                                "לא ניתן לשמור מצב משימה בבטחה; ההפקה לא נשלחה");
                        }
                        @Override public void jobCreated(String id){
                            getPreferences(MODE_PRIVATE).edit()
                                .putString("last_event",id).commit();
                            runOnUiThread(()->recover.setVisibility(View.VISIBLE));
                        }
                    });
                getPreferences(MODE_PRIVATE).edit().putBoolean("uncertain_submission",false)
                    .putString("last_event","").apply();
                runOnUiThread(()->onVideo(result));
            }catch(Exception e){
                if(e instanceof WanNativeClient.FinalProviderRejection) {
                    // A Gradio 'error' event TERMINATED this job: no rerun, but a
                    // later explicit user request may create a fresh job.
                    getPreferences(MODE_PRIVATE).edit()
                        .putBoolean("uncertain_submission",false)
                        .remove("last_event").commit();
                    runOnUiThread(()->recover.setVisibility(View.GONE));
                }
                String error=e.getMessage()==null?"שגיאה לא צפויה":e.getMessage();
                runOnUiThread(()->show("לא נוצר סרטון: "+error+
                   "\nלא נעשה ניסיון אוטומטי נוסף."));
            }finally{runOnUiThread(()->setBusy(false));}
        });
    }
    private void recoverPending(){
        if(busy)return;
        String id=getPreferences(MODE_PRIVATE).getString("last_event","");
        if(id.isEmpty()){show("אין מזהה משימה קודם. לא תישלח בקשת יצירה חדשה.");return;}
        setBusy(true);
        worker.execute(()->{
            try{
                WanNativeClient.Result result=engine.resume(this,id,this::show);
                getPreferences(MODE_PRIVATE).edit().putString("last_event","")
                    .putBoolean("uncertain_submission",false).apply();
                runOnUiThread(()->onVideo(result));
            }catch(Exception e){
                if(e instanceof WanNativeClient.FinalProviderRejection) {
                    getPreferences(MODE_PRIVATE).edit().remove("last_event")
                        .putBoolean("uncertain_submission",false).commit();
                    runOnUiThread(()->recover.setVisibility(View.GONE));
                }
                show("לא ניתן לשחזר: "+(e.getMessage()==null?"השרת לא זמין":e.getMessage()));
            }finally{runOnUiThread(()->setBusy(false));}
        });
    }
    private void onVideo(WanNativeClient.Result result){
        video=result.video;
        if(playback!=null){playback.release();playback=null;}
        playback=new ExoPlayer.Builder(this).build();
        preview.setPlayer(playback);
        preview.setVisibility(View.VISIBLE);
        playback.addListener(new Player.Listener(){
            @Override public void onPlayerError(androidx.media3.common.PlaybackException error){
                show("הסרטון הורד, אבל הניגון הפנימי נכשל. שמור אותו לטלפון לצפייה.");
            }
        });
        playback.setMediaItem(MediaItem.fromUri(Uri.fromFile(video)));
        playback.prepare();
        playback.play();
        save.setVisibility(View.VISIBLE);review.setVisibility(View.VISIBLE);
        long actualMs=0;
        MediaMetadataRetriever retriever=new MediaMetadataRetriever();
        try{
            retriever.setDataSource(video.getAbsolutePath());
            String metadata=retriever.extractMetadata(MediaMetadataRetriever.METADATA_KEY_DURATION);
            if(metadata!=null)actualMs=Long.parseLong(metadata);
        }catch(Exception ignored){}finally{try{retriever.release();}catch(Exception ignored){}}
        int selected=getPreferences(MODE_PRIVATE).getInt("requested_seconds",requestedSeconds);
        String durationInfo=actualMs>0
            ? "ביקשת "+selected+" שניות; התקבלו "+
              String.format(java.util.Locale.ROOT,"%.2f",actualMs/1000.0)+" שניות. "
            : "משך הווידאו בפועל לא אומת. ";
        String mismatch=actualMs>0&&actualMs+400 < selected*1000L
            ? "התוצאה קצרה מהבקשה ולכן חלקית. ":"";
        show(durationInfo+mismatch+"לא בוצעה בדיקת ציות חזותי אוטומטית. "+
             "בדוק שהדמויות והפעולה הנדרשות אכן מופיעות.");
    }
    private void saveVideo(){
        if(video==null||!video.isFile()){toast("אין סרטון זמין לשמירה");return;}
        Intent intent=new Intent(Intent.ACTION_CREATE_DOCUMENT);
        intent.addCategory(Intent.CATEGORY_OPENABLE);
        intent.setType("video/mp4");
        intent.putExtra(Intent.EXTRA_TITLE,"Kolbo-Video-AI.mp4");
        try{startActivityForResult(intent,SAVE_VIDEO);}
        catch(Exception e){toast("לא ניתן לבחור מקום לשמירת הסרטון");}
    }
    @Override protected void onActivityResult(int req,int code,Intent data){
        super.onActivityResult(req,code,data);
        if(req==CHOOSE_IMAGE&&code==RESULT_OK&&data!=null&&data.getData()!=null){
            image=data.getData();
            photoPreview.setImageURI(image);
            photoPreview.setVisibility(View.VISIBLE);
            photoLabel.setText("התמונה נבחרה מקומית. טרם הועלתה לספק.");
            consent.setChecked(false);
            return;
        }
        if(req==SAVE_VIDEO&&code==RESULT_OK&&data!=null&&data.getData()!=null&&
            video!=null&&video.isFile()){
            File source=video;
            Uri dest=data.getData();
            worker.execute(()->{
                try(FileInputStream in=new FileInputStream(source);
                    OutputStream out=getContentResolver().openOutputStream(dest,"w")){
                    if(out==null)throw new Exception("אין גישה לתיקיית השמירה");
                    byte[] buf=new byte[32768];int n;
                    while((n=in.read(buf))!=-1)out.write(buf,0,n);
                    out.flush();
                    runOnUiThread(()->toast("הסרטון נשמר במכשיר"));
                }catch(Exception ex){runOnUiThread(()->toast("שמירת הסרטון נכשלה"));}
            });
        }
    }
    @Override protected void onDestroy(){
        if(playback!=null){playback.release();playback=null;}
        worker.shutdown();
        super.onDestroy();
    }
}
