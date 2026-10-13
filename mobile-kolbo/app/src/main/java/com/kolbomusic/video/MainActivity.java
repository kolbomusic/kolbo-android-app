package com.kolbomusic.video;

import android.app.Activity;
import android.os.Bundle;
import android.os.Build;
import android.content.Intent;
import android.content.ClipData;
import android.graphics.Color;
import android.graphics.drawable.GradientDrawable;
import android.net.Uri;
import android.view.View;
import android.view.ViewGroup;
import android.webkit.CookieManager;
import android.webkit.WebChromeClient;
import android.webkit.WebResourceRequest;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.EditText;
import android.widget.TextView;
import android.widget.Button;
import android.widget.Spinner;
import android.widget.ArrayAdapter;
import android.widget.Toast;
import java.net.HttpURLConnection;
import java.net.URL;
import java.io.ByteArrayOutputStream;
import java.io.InputStream;

/** Zero-setup Kolbo studio. No user-supplied servers, providers, tokens or GPU quotas.
 * The real server is checked before the production studio can ever be opened.
 * No input image is uploaded while the server remains preview-only.
 */
public final class MainActivity extends Activity {
    private static final int WEB_FILE_REQUEST=401;
    private static final int IMAGE_PICK_REQUEST=405;
    private static final int CLIENT_CONTRACT=449;
    private static final String HUB_ORIGIN="https://kolbo-video-v450-safe-preview.onrender.com";
    private static final String HUB_HOST="kolbo-video-v450-safe-preview.onrender.com";
    private static final int BG=Color.rgb(20,17,32);
    private static final int PANEL=Color.rgb(41,33,60);
    private static final int TEXT=Color.rgb(244,239,255);
    private static final int MUTED=Color.rgb(189,174,210);
    private static final int ACCENT=Color.rgb(169,122,255);

    private LinearLayout root;
    private ScrollView scroll;
    private LinearLayout form;
    private TextView status, photoStatus;
    private Button generate;
    private EditText prompt;
    private Spinner duration;
    private WebView browser;
    private VideoExportBridge videoExport;
    private android.webkit.ValueCallback<Uri[]> webFiles;
    private Uri[] localImages=new Uri[0];
    private boolean engineReady=false;
    private boolean checking=false;

    private int dp(int px){return Math.round(px*getResources().getDisplayMetrics().density);}
    private GradientDrawable shape(int color,int radius){
        GradientDrawable g=new GradientDrawable();
        g.setColor(color);g.setCornerRadius(dp(radius));return g;
    }
    private TextView text(String value,int sp,int color){
        TextView v=new TextView(this);v.setText(value);v.setTextSize(sp);
        v.setTextColor(color);v.setGravity(android.view.Gravity.RIGHT);
        v.setTextDirection(View.TEXT_DIRECTION_RTL);return v;
    }
    private void addSpace(int h){
        View space=new View(this);form.addView(space,new LinearLayout.LayoutParams(1,dp(h)));
    }
    private Button button(String value,boolean secondary){
        Button b=new Button(this);
        b.setText(value);b.setAllCaps(false);b.setTextSize(15);
        b.setTextColor(TEXT);b.setBackground(shape(secondary?PANEL:Color.rgb(98,42,177),14));
        LinearLayout.LayoutParams p=new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT,dp(55));
        form.addView(b,p);return b;
    }
    @Override public void onCreate(Bundle state){
        super.onCreate(state);
        getWindow().setStatusBarColor(BG);
        getWindow().setNavigationBarColor(BG);
        root=new LinearLayout(this);root.setOrientation(LinearLayout.VERTICAL);
        root.setLayoutDirection(View.LAYOUT_DIRECTION_RTL);root.setBackgroundColor(BG);
        scroll=new ScrollView(this);scroll.setFillViewport(true);
        form=new LinearLayout(this);form.setOrientation(LinearLayout.VERTICAL);
        form.setPadding(dp(20),dp(26),dp(20),dp(38));
        scroll.addView(form);
        root.addView(scroll,new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT,0,1));

        TextView title=text("Kolbo Video",32,TEXT);title.setTypeface(null,android.graphics.Typeface.BOLD);
        form.addView(title);
        TextView subtitle=text("האולפן שלך · ממשק בעברית · ללא הגדרת שרת",15,MUTED);
        subtitle.setPadding(0,dp(5),0,0);form.addView(subtitle);
        addSpace(24);

        LinearLayout statusBox=new LinearLayout(this);
        statusBox.setPadding(dp(18),dp(18),dp(18),dp(18));
        statusBox.setOrientation(LinearLayout.VERTICAL);statusBox.setBackground(shape(PANEL,17));
        TextView statusTitle=text("מצב מנוע ההפקה",18,TEXT);
        statusTitle.setTypeface(null,android.graphics.Typeface.BOLD);
        statusBox.addView(statusTitle);
        status=text("בודק זמינות של מנוע ההפקה…",14,MUTED);
        status.setPadding(0,dp(10),0,dp(10));
        statusBox.addView(status);
        Button recheck=new Button(this);
        recheck.setText("בדוק זמינות מחדש");recheck.setAllCaps(false);
        recheck.setTextColor(TEXT);recheck.setBackground(shape(Color.rgb(76,56,111),12));
        recheck.setOnClickListener(v->checkEngine());
        statusBox.addView(recheck);
        form.addView(statusBox);
        addSpace(25);

        TextView label=text("מה תרצה ליצור?",21,TEXT);
        label.setTypeface(null,android.graphics.Typeface.BOLD);form.addView(label);
        addSpace(10);
        prompt=new EditText(this);
        prompt.setTextColor(TEXT);prompt.setHintTextColor(MUTED);
        prompt.setHint("למשל: שתי הדמויות רוקדות ושרות בבוכרית, עם תאורה קולנועית…");
        prompt.setTextSize(16);prompt.setGravity(android.view.Gravity.TOP|android.view.Gravity.RIGHT);
        prompt.setInputType(android.text.InputType.TYPE_CLASS_TEXT|android.text.InputType.TYPE_TEXT_FLAG_MULTI_LINE|
                android.text.InputType.TYPE_TEXT_FLAG_CAP_SENTENCES);
        prompt.setMinLines(4);prompt.setMaxLines(8);
        prompt.setPadding(dp(16),dp(16),dp(16),dp(16));
        prompt.setBackground(shape(PANEL,16));
        String saved=getPreferences(MODE_PRIVATE).getString("draft_prompt","");
        prompt.setText(saved);form.addView(prompt);
        addSpace(22);

        TextView images=text("תמונות ייחוס (עד 2)",19,TEXT);
        images.setTypeface(null,android.graphics.Typeface.BOLD);form.addView(images);
        photoStatus=text("לא נבחרו תמונות. לא נשלח שום קובץ לשרת.",13,MUTED);
        photoStatus.setPadding(0,dp(7),0,dp(10));form.addView(photoStatus);
        Button choose=button("בחר תמונות מהמכשיר",true);
        choose.setOnClickListener(v->chooseImages());
        addSpace(18);

        TextView durationLabel=text("אורך הסרטון המבוקש",19,TEXT);
        durationLabel.setTypeface(null,android.graphics.Typeface.BOLD);form.addView(durationLabel);
        addSpace(9);
        duration=new Spinner(this);
        String[] values=new String[]{"5 שניות","10 שניות","15 שניות"};
        ArrayAdapter<String> adapter=new ArrayAdapter<>(this,android.R.layout.simple_spinner_dropdown_item,values);
        duration.setAdapter(adapter);duration.setBackground(shape(PANEL,12));
        duration.setPadding(dp(12),dp(8),dp(12),dp(8));
        int savedDuration=getPreferences(MODE_PRIVATE).getInt("draft_duration",1);
        duration.setSelection(Math.min(2,Math.max(0,savedDuration)));
        form.addView(duration,new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT,dp(54)));
        addSpace(19);

        generate=button("הפק סרטון",false);
        generate.setEnabled(false);generate.setAlpha(0.58f);
        generate.setOnClickListener(v->openVerifiedStudio());
        addSpace(11);
        Button save=button("שמור רעיון בטלפון",true);
        save.setOnClickListener(v->saveDraft());
        addSpace(15);

        TextView note=text("ללא GPU מאומת לא ניתן לייצר סרטון אמיתי. ההנחיה נשמרת רק במכשיר לפי בחירתך; התמונות שנבחרו אינן מועלות בזמן שהמנוע אינו פעיל. אין מעבר אוטומטי לספק בתשלום.",13,MUTED);
        note.setLineSpacing(dp(4),1f);form.addView(note);

        initProtectedWebView();
        setContentView(root);
        checkEngine();
    }

    private void initProtectedWebView(){
        browser=new WebView(this);videoExport=new VideoExportBridge(this);
        browser.addJavascriptInterface(videoExport,"KolboExport");
        browser.setVisibility(View.GONE);
        WebSettings s=browser.getSettings();s.setJavaScriptEnabled(true);
        s.setDomStorageEnabled(true);s.setAllowFileAccess(false);
        s.setAllowContentAccess(true);s.setAllowFileAccessFromFileURLs(false);
        s.setAllowUniversalAccessFromFileURLs(false);
        s.setMixedContentMode(WebSettings.MIXED_CONTENT_NEVER_ALLOW);
        s.setCacheMode(WebSettings.LOAD_NO_CACHE);
        if(Build.VERSION.SDK_INT>=26)s.setSafeBrowsingEnabled(true);
        WebView.setWebContentsDebuggingEnabled(false);
        CookieManager.getInstance().setAcceptThirdPartyCookies(browser,false);
        browser.setWebViewClient(new WebViewClient(){
            @Override public boolean shouldOverrideUrlLoading(WebView w,WebResourceRequest r){
                Uri u=r.getUrl();
                if("https".equalsIgnoreCase(u.getScheme())&&HUB_HOST.equalsIgnoreCase(u.getHost())&&
                   (u.getPort()==-1||u.getPort()==443))return false;
                Toast.makeText(MainActivity.this,"מעבר לשרת אחר נחסם",Toast.LENGTH_SHORT).show();return true;
            }
            @Override public void onReceivedSslError(WebView w,android.webkit.SslErrorHandler h,android.net.http.SslError e){
                h.cancel();Toast.makeText(MainActivity.this,"אישור HTTPS אינו תקין",Toast.LENGTH_LONG).show();
            }
        });
        browser.setWebChromeClient(new WebChromeClient(){
            @Override public boolean onShowFileChooser(WebView w,android.webkit.ValueCallback<Uri[]> cb,FileChooserParams params){
                if(webFiles!=null)webFiles.onReceiveValue(null);
                webFiles=cb;
                try{
                    Intent i=params.createIntent();i.addCategory(Intent.CATEGORY_OPENABLE);
                    startActivityForResult(i,WEB_FILE_REQUEST);return true;
                }catch(Exception err){
                    webFiles=null;cb.onReceiveValue(null);return false;
                }
            }
        });
        root.addView(browser,new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT,0,1));
    }

    /** Only this project-controlled HTTPS host can activate production mode.
     * Strictly reject preview mode or any unproven media/GPU combination. */
    private void checkEngine(){
        if(checking)return;
        checking=true;engineReady=false;generate.setEnabled(false);generate.setAlpha(.58f);
        status.setText("בודק את שרת Kolbo באופן אוטומטי…");
        new Thread(()->{
            String message;
            boolean ready=false;
            try{
                HttpURLConnection conn=(HttpURLConnection)new URL(HUB_ORIGIN+"/v1/app-config").openConnection();
                conn.setInstanceFollowRedirects(false);
                conn.setConnectTimeout(12000);conn.setReadTimeout(12000);
                conn.setRequestProperty("Accept","application/json");
                try{
                    if(conn.getResponseCode()!=200)throw new Exception("bad HTTP status");
                    ByteArrayOutputStream bytes=new ByteArrayOutputStream();
                    try(InputStream in=conn.getInputStream()){
                        byte[] chunk=new byte[1024];int n;
                        while((n=in.read(chunk))!=-1){
                            if(bytes.size()+n>8192)throw new Exception("oversized config");
                            bytes.write(chunk,0,n);
                        }
                    }
                    org.json.JSONObject j=new org.json.JSONObject(bytes.toString("UTF-8"));
                    boolean trusted="kolbo-volunteer-mesh".equals(j.optString("service",""));
                    boolean contract=j.optInt("api_contract",0)==CLIENT_CONTRACT &&
                            j.optInt("minimum_android_client",Integer.MAX_VALUE)<=CLIENT_CONTRACT;
                    ready=NativeReadiness.canOpenStudio(
                            trusted,contract,j.optBoolean("owner_auth_required",false),
                            j.optBoolean("preview_only",true),j.optBoolean("gpu_ready",false),
                            j.optBoolean("persistent_storage_ready",false),
                            j.optBoolean("private_media_upload_enabled",false),
                            j.optBoolean("real_video_generation_verified",false),
                            j.optBoolean("paid_gpu_fallback_enabled",true));
                    if(ready)message="המנוע דיווח על מוכנות. ניתן לפתוח את האולפן. האישור הסופי מתבצע בשרת.";
                    else if(j.optBoolean("preview_only",true))
                        message="השרת מחובר, אך פועל במצב בדיקה בלבד. אין כרגע GPU מאומת ולכן ההפקה אינה זמינה.";
                    else
                        message="שרת Kolbo זמין, אך טרם אומתו כל תנאי האחסון, ה־GPU והבטיחות. הפקה חסומה.";
                }finally{conn.disconnect();}
            }catch(Exception error){
                message="לא ניתן לאמת כרגע מנוע הפקה פעיל. בדוק חיבור לאינטרנט ונסה שוב; הטיוטה נשארת בטלפון.";
            }
            final boolean available=ready;final String shown=message;
            runOnUiThread(()->{
                if(isFinishing()||isDestroyed())return;
                checking=false;engineReady=available;
                status.setText(shown);
                generate.setEnabled(available);generate.setAlpha(available?1f:.58f);
            });
        },"KolboAutoProvisionStatus").start();
    }

    private void chooseImages(){
        try{
            Intent i=new Intent(Intent.ACTION_GET_CONTENT);
            i.setType("image/*");i.addCategory(Intent.CATEGORY_OPENABLE);
            i.putExtra(Intent.EXTRA_ALLOW_MULTIPLE,true);
            startActivityForResult(Intent.createChooser(i,"בחר עד שתי תמונות"),IMAGE_PICK_REQUEST);
        }catch(Exception e){
            Toast.makeText(this,"לא ניתן לפתוח בורר תמונות",Toast.LENGTH_LONG).show();
        }
    }

    private void saveDraft(){
        String text=prompt.getText().toString().trim();
        if(text.length()>2000)text=text.substring(0,2000);
        getPreferences(MODE_PRIVATE).edit()
           .putString("draft_prompt",text)
           .putInt("draft_duration",duration.getSelectedItemPosition()).apply();
        Toast.makeText(this,"הרעיון נשמר מקומית. התמונות לא נשלחו.",Toast.LENGTH_LONG).show();
    }

    private void openVerifiedStudio(){
        if(!engineReady){
            Toast.makeText(this,"אין כרגע מנוע GPU מאומת להפקה",Toast.LENGTH_LONG).show();return;
        }
        // Production studio authenticates and validates the job server-side.
        saveDraft();scroll.setVisibility(View.GONE);
        browser.setVisibility(View.VISIBLE);
        browser.loadUrl(HUB_ORIGIN+"/studio");
    }

    @Override protected void onActivityResult(int req,int result,Intent data){
        super.onActivityResult(req,result,data);
        if(req==VideoExportBridge.SAVE_REQUEST){
            videoExport.handleSave(result,data);return;
        }
        if(req==IMAGE_PICK_REQUEST){
            if(result!=RESULT_OK||data==null)return;
            ClipData clips=data.getClipData();
            if(clips!=null){
                int count=Math.min(2,clips.getItemCount());
                localImages=new Uri[count];
                for(int i=0;i<count;i++)localImages[i]=clips.getItemAt(i).getUri();
                if(clips.getItemCount()>2)
                    Toast.makeText(this,"אפשר לבחור שתי תמונות בלבד",Toast.LENGTH_LONG).show();
            }else if(data.getData()!=null)localImages=new Uri[]{data.getData()};
            photoStatus.setText("נבחרו "+localImages.length+" תמונות. לא הועלו לשרת.");
            return;
        }
        if(req==WEB_FILE_REQUEST&&webFiles!=null){
            Uri[] values=null;
            if(result==RESULT_OK&&data!=null){
                ClipData clips=data.getClipData();
                if(clips!=null){
                    values=new Uri[clips.getItemCount()];
                    for(int i=0;i<clips.getItemCount();i++)values[i]=clips.getItemAt(i).getUri();
                }else if(data.getData()!=null)values=new Uri[]{data.getData()};
            }
            webFiles.onReceiveValue(values);webFiles=null;
        }
    }

    @Override public void onBackPressed(){
        if(browser.getVisibility()==View.VISIBLE&&browser.canGoBack())browser.goBack();
        else if(browser.getVisibility()==View.VISIBLE){
            browser.setVisibility(View.GONE);scroll.setVisibility(View.VISIBLE);
        }else super.onBackPressed();
    }
    @Override protected void onDestroy(){
        if(webFiles!=null)webFiles.onReceiveValue(null);webFiles=null;
        if(videoExport!=null)videoExport.abort();
        if(browser!=null)browser.destroy();
        super.onDestroy();
    }
}
