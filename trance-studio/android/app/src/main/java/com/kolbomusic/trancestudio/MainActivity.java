package com.kolbomusic.trancestudio;

import android.app.Activity;
import android.content.ClipData;
import android.content.ContentValues;
import android.content.Intent;
import android.database.Cursor;
import android.graphics.Color;
import android.graphics.Bitmap;
import android.net.Uri;
import android.os.Bundle;
import android.os.Environment;
import android.os.Handler;
import android.os.Looper;
import android.provider.MediaStore;
import android.provider.OpenableColumns;
import android.webkit.CookieManager;
import android.webkit.JavascriptInterface;
import android.webkit.WebChromeClient;
import android.webkit.WebResourceRequest;
import android.webkit.WebResourceResponse;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.webkit.SslErrorHandler;
import android.net.http.SslError;
import android.widget.Toast;
import android.view.ViewGroup;
import android.widget.LinearLayout;
import android.widget.ProgressBar;
import android.widget.Button;
import android.widget.TextView;
import android.view.Gravity;
import android.view.View;
import android.widget.FrameLayout;
import android.webkit.WebResourceError;
import android.util.Base64;

import org.json.JSONArray;
import org.json.JSONObject;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

import java.io.ByteArrayInputStream;
import java.io.InputStream;
import java.io.OutputStream;
import java.nio.charset.StandardCharsets;
import java.net.HttpURLConnection;
import java.net.URL;
import java.util.ArrayList;
import java.util.Collections;
import java.util.HashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.concurrent.Executors;
import java.util.concurrent.ExecutorService;

public final class MainActivity extends Activity {
    private static final String HOST="kolbo-trance-studio.onrender.com";
    private static final String SITE="https://"+HOST;
    private static final String STUDIO=SITE+"/studio";
    private static final int PICK_AUDIO=119;
    private static final long MAX_AUDIO_BYTES=15L*1024L*1024L;
    private static final long MAX_VIDEO_BYTES=45L*1024L*1024L;
    private static final long MAX_TOTAL_BYTES=60L*1024L*1024L;
    private final ExecutorService io=Executors.newSingleThreadExecutor();
    private final List<Uri> incoming=Collections.synchronizedList(new ArrayList<>());
    private WebView webView;
    private ProgressBar loading;
    private LinearLayout offlinePanel;
    private LinearLayout startupPanel;
    private TextView startupMessage;
    private TextView offlineDetails;
    private final Handler mainHandler=new Handler(Looper.getMainLooper());
    private long navigationId=0;
    private long incomingVersion=0;
    private String incomingSharedLink=null;
    private long sharedLinkVersion=0;
    private long deliveredSharedLinkVersion=-1;
    private long deliveredLinkNavigation=-1;
    private long lastImportedVersion=-1;
    private long lastImportNavigation=-1;
    private int automaticRetries=0;
    private boolean pageReady;
    private boolean pageLoadFailed;
    private long readinessPollingNavigation=-1;
    private android.webkit.ValueCallback<Uri[]> fileCallback;

    @Override public void onCreate(Bundle state){
        super.onCreate(state);
        getWindow().setStatusBarColor(Color.rgb(18,10,34));
        getWindow().setNavigationBarColor(Color.rgb(12,8,22));
        LinearLayout root=new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        root.setBackgroundColor(Color.rgb(12,8,22));
        root.setLayoutDirection(View.LAYOUT_DIRECTION_RTL);
        loading=new ProgressBar(this,null,android.R.attr.progressBarStyleHorizontal);
        loading.setIndeterminate(true);
        root.addView(loading,new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT,5));
        FrameLayout stage=new FrameLayout(this);
        root.addView(stage,new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT,0,1f));
        webView=new WebView(this);
        webView.setBackgroundColor(Color.rgb(24,16,39));
        stage.addView(webView,new FrameLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,ViewGroup.LayoutParams.MATCH_PARENT));
        startupPanel=new LinearLayout(this);
        startupPanel.setOrientation(LinearLayout.VERTICAL);
        startupPanel.setGravity(Gravity.CENTER);
        startupPanel.setPadding(36,50,36,50);
        startupPanel.setBackgroundColor(Color.rgb(24,16,39));
        TextView startupTitle=new TextView(this);
        startupTitle.setText("Kolbo Trance Story");
        startupTitle.setTextColor(Color.WHITE);
        startupTitle.setTextSize(25f);
        startupTitle.setGravity(Gravity.CENTER);
        startupPanel.addView(startupTitle,new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,ViewGroup.LayoutParams.WRAP_CONTENT));
        ProgressBar spinner=new ProgressBar(this);
        LinearLayout.LayoutParams spinnerParams=new LinearLayout.LayoutParams(72,72);
        spinnerParams.gravity=Gravity.CENTER;
        spinnerParams.setMargins(0,30,0,20);
        startupPanel.addView(spinner,spinnerParams);
        startupMessage=new TextView(this);
        startupMessage.setText("מתחבר לשרת ומכין את סביבת היצירה...");
        startupMessage.setTextColor(Color.rgb(228,208,244));
        startupMessage.setTextSize(18f);
        startupMessage.setGravity(Gravity.CENTER);
        startupPanel.addView(startupMessage,new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,ViewGroup.LayoutParams.WRAP_CONTENT));
        Button browserStartup=new Button(this);
        browserStartup.setText("פתיחה בדפדפן במקרה של בעיית טעינה");
        browserStartup.setAllCaps(false);
        browserStartup.setOnClickListener(v->openStudioInBrowser());
        LinearLayout.LayoutParams browserStartupLayout=new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,ViewGroup.LayoutParams.WRAP_CONTENT);
        browserStartupLayout.setMargins(0,20,0,0);
        startupPanel.addView(browserStartup,browserStartupLayout);
        stage.addView(startupPanel,new FrameLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,ViewGroup.LayoutParams.MATCH_PARENT));
        offlinePanel=new LinearLayout(this);
        offlinePanel.setOrientation(LinearLayout.VERTICAL);
        offlinePanel.setGravity(Gravity.CENTER);
        offlinePanel.setPadding(42,50,42,50);
        offlinePanel.setBackgroundColor(Color.rgb(24,16,39));
        offlinePanel.setVisibility(View.GONE);
        TextView offlineTitle=new TextView(this);
        offlineTitle.setText("אין חיבור ל־Kolbo Trance Story");
        offlineTitle.setTextColor(Color.WHITE);
        offlineTitle.setTextSize(23f);
        offlineTitle.setGravity(Gravity.CENTER);
        offlinePanel.addView(offlineTitle,new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT,ViewGroup.LayoutParams.WRAP_CONTENT));
        TextView offlineHelp=new TextView(this);
        offlineHelp.setText("ההקלטות נשמרות במכשיר. אפשר לנסות חיבור מחדש בלי להפעיל יצירה.");
        offlineDetails=offlineHelp;
        offlineHelp.setTextColor(Color.rgb(220,204,237));
        offlineHelp.setTextSize(16f);
        offlineHelp.setGravity(Gravity.CENTER);
        LinearLayout.LayoutParams hintLayout=new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT,ViewGroup.LayoutParams.WRAP_CONTENT);
        hintLayout.setMargins(0,16,0,24);
        offlinePanel.addView(offlineHelp,hintLayout);
        Button retry=new Button(this);
        retry.setText("נסה שוב להתחבר");
        retry.setAllCaps(false);
        retry.setTextSize(16f);
        retry.setOnClickListener(v->beginLoad(true));
        offlinePanel.addView(retry,new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT,ViewGroup.LayoutParams.WRAP_CONTENT));
        Button browserOffline=new Button(this);
        browserOffline.setText("פתח את האולפן בדפדפן");
        browserOffline.setAllCaps(false);
        browserOffline.setOnClickListener(v->openStudioInBrowser());
        offlinePanel.addView(browserOffline,new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,ViewGroup.LayoutParams.WRAP_CONTENT));
        stage.addView(offlinePanel,new FrameLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT,ViewGroup.LayoutParams.MATCH_PARENT));
        setContentView(root);
        WebSettings settings=webView.getSettings();
        settings.setJavaScriptEnabled(true);
        settings.setDomStorageEnabled(true);
        settings.setAllowFileAccess(false);
        settings.setAllowContentAccess(true);
        settings.setMixedContentMode(WebSettings.MIXED_CONTENT_NEVER_ALLOW);
        settings.setSupportMultipleWindows(false);
        settings.setMediaPlaybackRequiresUserGesture(true);
        CookieManager.getInstance().setAcceptCookie(true);
        CookieManager.getInstance().setAcceptThirdPartyCookies(webView,false);
        webView.addJavascriptInterface(new AudioBridge(),"KolboAndroid");
        webView.setWebChromeClient(new WebChromeClient(){
            @Override public boolean onShowFileChooser(WebView view,android.webkit.ValueCallback<Uri[]> cb,FileChooserParams params){
                if(fileCallback!=null)fileCallback.onReceiveValue(null);
                fileCallback=cb;
                try{
                    Intent pick=params.createIntent();
                    pick.setType("*/*");
                    pick.addCategory(Intent.CATEGORY_OPENABLE);
                    startActivityForResult(pick,PICK_AUDIO);
                }catch(Exception e){
                    fileCallback=null;
                    cb.onReceiveValue(null);
                    toast("לא ניתן לפתוח את בחירת הקבצים");
                }
                return true;
            }
            @Override public void onProgressChanged(WebView view,int progress){
                if(!pageReady&&!pageLoadFailed)loading.setVisibility(View.VISIBLE);
            }
        });
        webView.setWebViewClient(new WebViewClient(){
            @Override public void onPageStarted(WebView view,String url,Bitmap favicon){
                pageLoadFailed=false;
                pageReady=false;
                offlinePanel.setVisibility(View.GONE);
                startupPanel.setVisibility(View.VISIBLE);
                startupMessage.setText("מתחבר לשרת ומכין את סביבת היצירה...");
                loading.setVisibility(View.VISIBLE);
                webView.setVisibility(View.VISIBLE);
            }
            @Override public boolean shouldOverrideUrlLoading(WebView view,WebResourceRequest request){
                Uri u=request.getUrl();
                if("https".equalsIgnoreCase(u.getScheme())&&HOST.equalsIgnoreCase(u.getHost()))return false;
                if("https".equalsIgnoreCase(u.getScheme())){
                    try{startActivity(new Intent(Intent.ACTION_VIEW,u));}catch(Exception ignored){}
                }
                return true;
            }
            @Override public WebResourceResponse shouldInterceptRequest(WebView view,WebResourceRequest request){
                Uri u=request.getUrl();
                if(!"https".equalsIgnoreCase(u.getScheme())||!HOST.equalsIgnoreCase(u.getHost()))return null;
                final String prefix="/native-shared-audio/";
                String path=u.getPath();
                if(path==null||!path.startsWith(prefix))return null;
                try{
                    int index=Integer.parseInt(path.substring(prefix.length()));
                    if(index<0||index>=4)return failStream();
                    Uri uri;
                    synchronized(incoming){
                        if(index>=incoming.size())return failStream();
                        uri=incoming.get(index);
                    }
                    String type=getContentResolver().getType(uri);
                    if(type==null||type.isEmpty()){
                        String name=audioName(uri,index).toLowerCase(Locale.ROOT);
                        type=name.endsWith(".mp4")?"video/mp4":
                             name.endsWith(".webm")?"video/webm":"audio/ogg";
                    }
                    InputStream stream=getContentResolver().openInputStream(uri);
                    if(stream==null)return failStream();
                    Map<String,String> headers=new HashMap<>();
                    headers.put("Cache-Control","no-store, max-age=0");
                    headers.put("Access-Control-Allow-Origin",SITE);
                    return new WebResourceResponse(type,"UTF-8",200,"OK",headers,stream);
                }catch(Exception ex){return failStream();}
            }
            @Override public void onPageFinished(WebView view,String url){
                if(pageLoadFailed||url==null||!url.startsWith(STUDIO))return;
                final long token=navigationId;
                // A finished network load does not guarantee that the page's
                // JavaScript handlers are ready in Android WebView. Poll
                // for readiness instead of failing after one early callback.
                if(readinessPollingNavigation==token)return;
                readinessPollingNavigation=token;
                pollStudioReady(token,0);
            }
            @Override public void onReceivedSslError(WebView view,SslErrorHandler handler,SslError error){
                handler.cancel();
                showOffline("חיבור HTTPS לא מאובטח. לא נעקוף שגיאת תעודה.");
            }
            @Override public void onReceivedHttpError(WebView view,WebResourceRequest req,
                                                      WebResourceResponse response){
                if(req.isForMainFrame()&&response.getStatusCode()>=400){
                    recoverConnection("שרת היצירה אינו זמין זמנית (HTTP "+response.getStatusCode()+").");
                }
            }
            @Override public void onReceivedError(WebView view,WebResourceRequest req,
                                                  WebResourceError err){
                if(req.isForMainFrame()){
                    recoverConnection("לא ניתן להתחבר לשרת. בדוק אינטרנט או נסה שוב.");
                }
            }
        });
        collectIncoming(getIntent());
        beginLoad(false);
    }


    private void openStudioInBrowser(){
        try{
            startActivity(new Intent(Intent.ACTION_VIEW,Uri.parse(STUDIO)));
        }catch(Exception ex){
            toast("לא ניתן לפתוח את הדפדפן במכשיר");
        }
    }

    private void pollStudioReady(final long token,final int attempt){
        if(token!=navigationId||pageReady||pageLoadFailed)return;
        webView.evaluateJavascript(
            "(function(){try{var button=document.getElementById('generate');" +
            "return !!(document.body&&document.querySelector('main')&&" +
            "document.getElementById('result')&&button&&" +
            "typeof window.kolboImportSharedAudio==='function'&&" +
            "typeof window.kolboCanImportSharedAudio==='function'&&" +
            "typeof button.onclick==='function');}catch(e){return false}})()",
            response->{
                if(token!=navigationId||pageReady||pageLoadFailed)return;
                if("true".equals(response)){
                    pageReady=true;
                    automaticRetries=0;
                    loading.setVisibility(View.GONE);
                    startupPanel.setVisibility(View.GONE);
                    offlinePanel.setVisibility(View.GONE);
                    importIncoming(); // WhatsApp share only imports, never auto-creates
                    importSharedLink();
                }else if(attempt<35){
                    if(attempt==8){
                        startupMessage.setText("האולפן נפתח. מכין רכיבי יצירה ושיתוף...");
                    }
                    mainHandler.postDelayed(()->pollStudioReady(token,attempt+1),700);
                }else{
                    recoverConnection("ממשק היצירה לא סיים להיטען במכשיר. ניתן גם לפתוח בדפדפן.");
                }
            });
    }


    /**
     * Render Free may respond with its temporary 200-OK loading page for
     * ~60 seconds after idle. Android WebView used to treat that page as
     * Studio HTML, time out waiting for its Create button, then get stuck.
     *
     * Wake the cloud with a bounded native health probe before navigating.
     * Unlike the user-facing studio, health checks send NO WhatsApp media and
     * never start mix generation. They are also independent of WebView cache.
     */
    private void probeCloudBeforeLoad(final long token,final int attempt){
        if(token!=navigationId||pageReady||pageLoadFailed||isDestroyed())return;
        io.execute(()->{
            boolean ready=false;
            HttpURLConnection connection=null;
            try{
                URL health=new URL(SITE+"/health?androidWake="+(attempt+1));
                connection=(HttpURLConnection)health.openConnection();
                connection.setInstanceFollowRedirects(false);
                connection.setConnectTimeout(8000);
                connection.setReadTimeout(8000);
                connection.setRequestProperty("Accept","application/json");
                if(connection.getResponseCode()==200&&
                   String.valueOf(connection.getContentType()).contains("application/json")){
                    try(InputStream data=connection.getInputStream()){
                        byte[] raw=data.readNBytes(1024);
                        JSONObject status=new JSONObject(new String(raw,StandardCharsets.UTF_8));
                        ready=status.optBoolean("ok",false)&&
                              "kolbo-trance-studio".equals(status.optString("service",""));
                    }
                }
            }catch(Exception expectedDuringColdStart){
                // Never bypass TLS failures or trust an HTML/proxy response.
            }finally{
                if(connection!=null)connection.disconnect();
            }
            final boolean online=ready;
            mainHandler.post(()->{
                if(token!=navigationId||pageReady||pageLoadFailed||isDestroyed())return;
                if(online){
                    startupMessage.setText("השרת התעורר. פותח את האולפן...");
                    webView.loadUrl(STUDIO+"?android=2481&load="+token);
                }else if(attempt<11){
                    startupMessage.setText("שרת הענן החינמי מתעורר... בודק חיבור "+
                            (attempt+2)+" מתוך 12. ההקלטות לא יישלחו לפני יצירה.");
                    mainHandler.postDelayed(
                        ()->probeCloudBeforeLoad(token,attempt+1),4500);
                }else{
                    recoverConnection("שרת העיבוד עדיין לא השיב לבדיקת הזמינות.");
                }
            });
        });
    }

    private void beginLoad(boolean manuallyRequested){
        if(manuallyRequested){
            automaticRetries=0;
            // Manual retry bypasses any cached error page from sleeping Render.
            webView.clearCache(true);
        }
        final long current=++navigationId;
        readinessPollingNavigation=-1;
        pageReady=false;
        pageLoadFailed=false;
        offlinePanel.setVisibility(View.GONE);
        startupPanel.setVisibility(View.VISIBLE);
        startupMessage.setText("מתחבר לשרת ומכין את סביבת היצירה...");
        loading.setVisibility(View.VISIBLE);
        webView.setVisibility(View.VISIBLE);
        probeCloudBeforeLoad(current,0);
        mainHandler.postDelayed(()->{
            if(navigationId==current&&!pageReady&&!pageLoadFailed){
                startupMessage.setText("שרת הענן החינמי מתעורר. ההקלטות שלך נשארות במכשיר...");
            }
        },15000);
        mainHandler.postDelayed(()->{
            if(navigationId==current&&!pageReady&&!pageLoadFailed){
                recoverConnection("החיבור לשרת נמשך זמן רב מדי.");
            }
        },240000);
    }

    private void recoverConnection(String reason){
        if(pageLoadFailed||pageReady)return;
        pageLoadFailed=true;
        if(automaticRetries<1){
            automaticRetries++;
            final long failedNavigation=navigationId;
            startupPanel.setVisibility(View.VISIBLE);
            startupMessage.setText(reason+" מנסה להתחבר פעם נוספת...");
            mainHandler.postDelayed(()->{
                if(navigationId==failedNavigation&&!pageReady){
                    webView.clearCache(true); // discard a stale partial page
                    beginLoad(false);
                }
            },6500);
        }else{
            showOffline(reason);
        }
    }

    private void showOffline(String reason){
        pageLoadFailed=true;
        pageReady=false;
        ++navigationId; // ignore stale JS callbacks and old timeout tasks
        loading.setVisibility(View.GONE);
        startupPanel.setVisibility(View.GONE);
        webView.setVisibility(View.GONE);
        offlinePanel.setVisibility(View.VISIBLE);
        startupMessage.setText(reason);
        if(offlineDetails!=null)offlineDetails.setText(reason+"\nההקלטות נשמרות במכשיר. לחץ על ניסיון חוזר כדי להתחבר.");
    }

    private WebResourceResponse failStream(){
        return new WebResourceResponse("text/plain","UTF-8",404,"Not Found",
                Collections.singletonMap("Cache-Control","no-store"),
                new ByteArrayInputStream(new byte[0]));
    }
    private static String firstHttpsLink(String text){
        if(text==null||text.length()>8192)return null;
        Matcher match=Pattern.compile("https://\\S+",Pattern.CASE_INSENSITIVE).matcher(text);
        if(!match.find())return null;
        String link=match.group();
        while(link.endsWith(".")||link.endsWith(",")||
              link.endsWith(")")||link.endsWith("]"))
            link=link.substring(0,link.length()-1);
        try{
            Uri target=Uri.parse(link);
            String authority=target.getAuthority();
            if("https".equalsIgnoreCase(target.getScheme())&&
                target.getHost()!=null&&authority!=null&&
                !authority.contains("@")&&link.length()<=2048)return link;
        }catch(Exception ignored){}
        return null;
    }
    private void collectIncoming(Intent intent){
        if(intent==null)return;
        String action=intent.getAction();
        if(!Intent.ACTION_SEND.equals(action)&&!Intent.ACTION_SEND_MULTIPLE.equals(action))return;
        ArrayList<Uri> candidates=new ArrayList<>();
        if(Intent.ACTION_SEND.equals(action)){
            Uri one=intent.getParcelableExtra(Intent.EXTRA_STREAM);
            if(one!=null)candidates.add(one);
        }else{
            ArrayList<Uri> many=intent.getParcelableArrayListExtra(Intent.EXTRA_STREAM);
            if(many!=null)candidates.addAll(many);
        }
        if(candidates.isEmpty()&&intent.getClipData()!=null){
            ClipData clip=intent.getClipData();
            for(int i=0;i<Math.min(4,clip.getItemCount());i++){
                Uri uri=clip.getItemAt(i).getUri();
                if(uri!=null)candidates.add(uri);
            }
        }
        incoming.clear();
        incomingVersion++;
        long totalBytes=0;
        for(Uri uri:candidates){
            if(incoming.size()>=4)break;
            if(uri==null||!"content".equals(uri.getScheme()))continue;
            String type=getContentResolver().getType(uri);
            String name=audioName(uri,incoming.size()).toLowerCase(Locale.ROOT);
            boolean video=(type!=null&&type.toLowerCase(Locale.ROOT).startsWith("video/"))
                ||name.matches(".*\\.(mp4|webm|mov|3gp|3gpp)");
            boolean audio=(type!=null&&(type.startsWith("audio/")||
                           "application/ogg".equalsIgnoreCase(type)))
                ||name.matches(".*\\.(opus|ogg|oga|mp3|m4a|wav|flac|aac)");
            // A social app may put a text document URI into ClipData.
            // Never turn text/plain into a fake WhatsApp .opus file.
            if(!video&&!audio)continue;
            long bytes=contentLength(uri);
            if(bytes>(video?MAX_VIDEO_BYTES:MAX_AUDIO_BYTES)
               ||totalBytes+bytes>MAX_TOTAL_BYTES)continue;
            totalBytes+=bytes;
            incoming.add(uri);
        }
        // Resolve a social URL only when there is no usable media stream.
        // Prefer actual video/audio bytes over captions or post URLs.
        String link=null;
        if(incoming.isEmpty()){
            link=firstHttpsLink(intent.getStringExtra(Intent.EXTRA_TEXT));
            if(link==null&&intent.getClipData()!=null){
                for(int i=0;i<Math.min(4,intent.getClipData().getItemCount());i++){
                    CharSequence raw=intent.getClipData().getItemAt(i).getText();
                    link=firstHttpsLink(raw==null?null:raw.toString());
                    if(link!=null)break;
                }
            }
        }
        incomingSharedLink=link;
        sharedLinkVersion++;
        if(!candidates.isEmpty()&&incoming.isEmpty()&&link==null)
            toast("הקובץ המשותף גדול מדי או אינו נתמך");
    }
    private long contentLength(Uri uri){
        try(Cursor c=getContentResolver().query(uri,new String[]{OpenableColumns.SIZE},null,null,null)){
            if(c!=null&&c.moveToFirst()&&!c.isNull(0))return c.getLong(0);
        }catch(Exception ignored){}
        return 0;
    }
    private String audioName(Uri uri,int i){
        String name=null;
        try(Cursor c=getContentResolver().query(uri,new String[]{OpenableColumns.DISPLAY_NAME},null,null,null)){
            if(c!=null&&c.moveToFirst())name=c.getString(0);
        }catch(Exception ignored){}
        if(name!=null){
            name=name.replaceAll("[^\\p{L}\\p{N}._ -]","_");
            if(name.length()>70)name=name.substring(name.length()-70);
            if(name.toLowerCase(Locale.ROOT).matches(".*\\.(opus|ogg|oga|mp3|m4a|mp4|wav|webm|flac|aac|3gp|3gpp|mov)$"))return name;
        }
        String mime=getContentResolver().getType(uri);
        String ext=mime!=null&&mime.startsWith("video/")?
                (mime.contains("webm")?".webm":".mp4"):
                mime!=null&&mime.contains("mpeg")?".mp3":
                mime!=null&&mime.contains("mp4")?".m4a":".opus";
        return "WhatsApp-"+(i+1)+ext;
    }
    private void importIncoming(){
        ArrayList<Uri> snapshot;
        synchronized(incoming){snapshot=new ArrayList<>(incoming);}
        if(snapshot.isEmpty())return;
        if(lastImportedVersion==incomingVersion&&lastImportNavigation==navigationId)return;
        lastImportedVersion=incomingVersion;
        lastImportNavigation=navigationId;
        JSONArray names=new JSONArray();
        for(int i=0;i<snapshot.size();i++)names.put(audioName(snapshot.get(i),i));
        // WhatsApp sharing imports clips only. Creation is started only by
        // an explicit press on the web form Create button, never by Android.
        String js="(async function(){try{var names="+names.toString()+";var clips=[];"
                +"for(var i=0;i<names.length;i++){var r=await fetch('/native-shared-audio/'+i,{cache:'no-store'});"
                +"if(!r.ok)throw Error('קובץ לא זמין');var b=await r.blob();"
                +"clips.push(new File([b],names[i],{type:b.type||'audio/ogg'}));}"
                +"if(window.kolboImportSharedAudio)window.kolboImportSharedAudio(clips);"
                +"}catch(e){console.error('Import from WhatsApp',e);"
                +"if(window.KolboAndroid)window.KolboAndroid.importFailure();}})();";
        webView.evaluateJavascript(js,null);
    }
    private void importSharedLink(){
        if(!pageReady||incomingSharedLink==null)return;
        if(deliveredSharedLinkVersion==sharedLinkVersion&&
           deliveredLinkNavigation==navigationId)return;
        deliveredSharedLinkVersion=sharedLinkVersion;
        deliveredLinkNavigation=navigationId;
        // Escape across Java/JS boundary; never evaluate text as code.
        String script="if(window.kolboReceiveSharedLink)window.kolboReceiveSharedLink("+
                JSONObject.quote(incomingSharedLink)+");";
        webView.evaluateJavascript(script,null);
    }
    @Override protected void onNewIntent(Intent intent){
        super.onNewIntent(intent);
        setIntent(intent);
        if(intent==null)return;
        String action=intent.getAction();
        boolean isShare=Intent.ACTION_SEND.equals(action)||
                        Intent.ACTION_SEND_MULTIPLE.equals(action);
        if(!isShare){
            // Tapping the launcher must not destroy an in-progress remix.
            if(!pageReady&&offlinePanel.getVisibility()==View.VISIBLE)beginLoad(true);
            return;
        }
        if(pageReady){
            // A new WhatsApp share must never reload the page, clear its
            // active audio job or overwrite a result the user has not saved.
            webView.evaluateJavascript(
                "(function(){return !!(window.kolboCanImportSharedAudio&&window.kolboCanImportSharedAudio());})()",
                allowed->{
                    if(!pageReady)return;
                    if(!"true".equals(allowed)){
                        toast("מיקס פעיל כעת. שמור את התוצאה לפני שיתוף הקלטה חדשה.");
                        return;
                    }
                    collectIncoming(intent);
                    importIncoming();
                    importSharedLink();
                });
        }else{
            // Keep the shared URI for import after slow Render cold start.
            collectIncoming(intent);
            if(offlinePanel.getVisibility()==View.VISIBLE)beginLoad(true);
        }
    }
    @Override protected void onActivityResult(int requestCode,int resultCode,Intent data){
        super.onActivityResult(requestCode,resultCode,data);
        if(requestCode==PICK_AUDIO&&fileCallback!=null){
            fileCallback.onReceiveValue(WebChromeClient.FileChooserParams.parseResult(resultCode,data));
            fileCallback=null;
        }
    }
    private void toast(String s){runOnUiThread(()->Toast.makeText(this,s,Toast.LENGTH_LONG).show());}
    private class AudioBridge{
        @JavascriptInterface public void saveStudioAudio(String encoded){
            if(encoded==null||encoded.length()>9*1024*1024){
                toast("תוצאת המאסטרינג גדולה מדי לשמירה במכשיר");return;
            }
            io.execute(()->{
                Uri dest=null;
                try{
                    byte[] bytes=Base64.decode(encoded,Base64.DEFAULT);
                    if(bytes.length<2048||bytes.length>7*1024*1024)
                        throw new IllegalArgumentException("גודל קובץ אינו תקין");
                    ContentValues values=new ContentValues();
                    values.put(MediaStore.MediaColumns.DISPLAY_NAME,
                               "Kolbo-Studio-"+System.currentTimeMillis()+".mp3");
                    values.put(MediaStore.MediaColumns.MIME_TYPE,"audio/mpeg");
                    values.put(MediaStore.MediaColumns.RELATIVE_PATH,
                               Environment.DIRECTORY_DOWNLOADS+"/Kolbo Trance");
                    values.put(MediaStore.MediaColumns.IS_PENDING,1);
                    dest=getContentResolver().insert(MediaStore.Downloads.EXTERNAL_CONTENT_URI,values);
                    if(dest==null)throw new IllegalStateException("MediaStore unavailable");
                    try(OutputStream output=getContentResolver().openOutputStream(dest)){
                        if(output==null)throw new IllegalStateException("Output stream unavailable");
                        output.write(bytes);
                    }
                    ContentValues finish=new ContentValues();
                    finish.put(MediaStore.MediaColumns.IS_PENDING,0);
                    getContentResolver().update(dest,finish,null,null);
                    toast("קובץ המאסטרינג נשמר בהורדות / Kolbo Trance");
                }catch(Exception err){
                    if(dest!=null)try{getContentResolver().delete(dest,null,null);}
                    catch(Exception ignored){}
                    toast("שמירת הקובץ נכשלה. ניתן לנסות שוב.");
                }
            });
        }
        @JavascriptInterface public void importFailure(){
            toast("לא ניתן לקרוא את הקובץ המשותף. אפשר לבחור אותו שוב או לנסות חיבור מחדש.");
        }
        @JavascriptInterface public void downloadMix(String relative){saveMix(relative,false);}
        @JavascriptInterface public void shareMix(String relative){saveMix(relative,true);}
        @JavascriptInterface public void downloadVideo(String relative){saveOutput(relative,false,true);}
        @JavascriptInterface public void shareVideo(String relative){saveOutput(relative,true,true);}
    }
    private void saveMix(String relative,boolean share){saveOutput(relative,share,false);}
    private void saveOutput(String relative,boolean share,boolean video){
        String expected="/api/jobs/[0-9a-f]{48}/"+(video?"video":"audio");
        if(relative==null||!relative.matches(expected)){
            toast("קישור להורדה אינו תקין");return;
        }
        io.execute(()->{
            HttpURLConnection c=null;
            Uri output=null;
            try{
                c=(HttpURLConnection)new URL(SITE+relative).openConnection();
                c.setConnectTimeout(25000);
                c.setReadTimeout(180000);
                c.setInstanceFollowRedirects(false);
                c.setRequestProperty("Accept",video?"video/mp4":"audio/mpeg");
                String cookie=CookieManager.getInstance().getCookie(SITE);
                if(cookie!=null)c.setRequestProperty("Cookie",cookie);
                if(c.getResponseCode()!=200)throw new Exception("ההורדה נכשלה ("+c.getResponseCode()+")");
                ContentValues meta=new ContentValues();
                meta.put(MediaStore.MediaColumns.DISPLAY_NAME,"Kolbo-Trance-"+System.currentTimeMillis()+(video?".mp4":".mp3"));
                meta.put(MediaStore.MediaColumns.MIME_TYPE,video?"video/mp4":"audio/mpeg");
                meta.put(MediaStore.MediaColumns.RELATIVE_PATH,Environment.DIRECTORY_DOWNLOADS+"/Kolbo Trance");
                meta.put(MediaStore.MediaColumns.IS_PENDING,1);
                output=getContentResolver().insert(MediaStore.Downloads.EXTERNAL_CONTENT_URI,meta);
                if(output==null)throw new Exception("לא ניתן לפתוח קובץ להורדה");
                try(InputStream in=c.getInputStream();OutputStream out=getContentResolver().openOutputStream(output)){
                    if(out==null)throw new Exception("לא ניתן לכתוב את הקובץ");
                    byte[] buffer=new byte[32768];int n;long total=0;
                    while((n=in.read(buffer))>=0){
                        if(n==0)continue;
                        total+=n;
                        if(total>(video?160L:40L)*1024L*1024L)throw new Exception("קובץ גדול מדי");
                        out.write(buffer,0,n);
                    }
                }
                ContentValues done=new ContentValues();
                done.put(MediaStore.MediaColumns.IS_PENDING,0);
                getContentResolver().update(output,done,null,null);
                final Uri ready=output;
                runOnUiThread(()->{
                    if(share){
                        Intent send=new Intent(Intent.ACTION_SEND);
                        send.setType(video?"video/mp4":"audio/mpeg");
                        send.putExtra(Intent.EXTRA_STREAM,ready);
                        send.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION);
                        try{startActivity(Intent.createChooser(send,video?"שיתוף סרטון Kolbo Trance":"שיתוף המיקס"));}
                        catch(Exception e){toast("השיתוף אינו זמין. המיקס נשמר בהורדות.");}
                    }else toast(video?"הסרטון נשמר בהורדות / Kolbo Trance":"המיקס נשמר בתיקיית הורדות / Kolbo Trance");
                });
            }catch(Exception e){
                if(output!=null)try{getContentResolver().delete(output,null,null);}catch(Exception ignored){}
                toast((video?"בעיה בשמירת הסרטון: ":"בעיה בשמירת המיקס: ")+e.getMessage());
            }finally{if(c!=null)c.disconnect();}
        });
    }
    @Override public void onBackPressed(){
        if(webView!=null&&webView.canGoBack())webView.goBack();else super.onBackPressed();
    }
    @Override protected void onDestroy(){
        mainHandler.removeCallbacksAndMessages(null);
        if(webView!=null){webView.removeJavascriptInterface("KolboAndroid");webView.destroy();}
        io.shutdown();
        super.onDestroy();
    }
}
