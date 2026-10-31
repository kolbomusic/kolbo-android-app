package com.kolbomusic.trancestudio;

import android.app.Activity;
import android.content.ClipData;
import android.content.ContentValues;
import android.content.Intent;
import android.database.Cursor;
import android.graphics.Color;
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

import org.json.JSONArray;

import java.io.ByteArrayInputStream;
import java.io.InputStream;
import java.io.OutputStream;
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
    private static final long MAX_FILE_BYTES=15L*1024L*1024L;
    private final ExecutorService io=Executors.newSingleThreadExecutor();
    private final List<Uri> incoming=Collections.synchronizedList(new ArrayList<>());
    private WebView webView;
    private ProgressBar loading;
    private android.webkit.ValueCallback<Uri[]> fileCallback;

    @Override public void onCreate(Bundle state){
        super.onCreate(state);
        getWindow().setStatusBarColor(Color.rgb(18,10,34));
        getWindow().setNavigationBarColor(Color.rgb(12,8,22));
        LinearLayout root=new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        root.setBackgroundColor(Color.rgb(12,8,22));
        loading=new ProgressBar(this,null,android.R.attr.progressBarStyleHorizontal);
        loading.setIndeterminate(true);
        root.addView(loading,new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT,5));
        webView=new WebView(this);
        root.addView(webView,new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT,0,1f));
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
                loading.setVisibility(progress>=100?android.view.View.GONE:android.view.View.VISIBLE);
            }
        });
        webView.setWebViewClient(new WebViewClient(){
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
                    if(type==null||type.isEmpty())type="audio/ogg";
                    InputStream stream=getContentResolver().openInputStream(uri);
                    if(stream==null)return failStream();
                    Map<String,String> headers=new HashMap<>();
                    headers.put("Cache-Control","no-store, max-age=0");
                    headers.put("Access-Control-Allow-Origin",SITE);
                    return new WebResourceResponse(type,"UTF-8",200,"OK",headers,stream);
                }catch(Exception ex){return failStream();}
            }
            @Override public void onPageFinished(WebView view,String url){
                if(url!=null&&url.startsWith(STUDIO))importIncoming();
            }
            @Override public void onReceivedSslError(WebView view,SslErrorHandler handler,SslError error){
                handler.cancel();
                toast("שגיאת אבטחה בחיבור לאתר");
            }
            @Override public void onReceivedError(WebView view,WebResourceRequest req,android.webkit.WebResourceError err){
                if(req.isForMainFrame())toast("אין חיבור לסטודיו. בדוק את האינטרנט ונסה שוב");
            }
        });
        collectIncoming(getIntent());
        webView.loadUrl(STUDIO);
    }
    private WebResourceResponse failStream(){
        return new WebResourceResponse("text/plain","UTF-8",404,"Not Found",
                Collections.singletonMap("Cache-Control","no-store"),
                new ByteArrayInputStream(new byte[0]));
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
        for(Uri uri:candidates){
            if(incoming.size()>=4)break;
            if(!"content".equals(uri.getScheme()))continue;
            if(contentLength(uri)>MAX_FILE_BYTES)continue;
            incoming.add(uri);
        }
        if(!candidates.isEmpty()&&incoming.isEmpty())toast("הקובץ המשותף גדול מדי או אינו נתמך");
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
            if(name.toLowerCase(Locale.ROOT).matches(".*\\.(opus|ogg|oga|mp3|m4a|mp4|wav|webm|flac|aac)$"))return name;
        }
        String mime=getContentResolver().getType(uri);
        String ext=mime!=null&&mime.contains("mpeg")?".mp3":mime!=null&&mime.contains("mp4")?".m4a":".opus";
        return "WhatsApp-Voice-"+(i+1)+ext;
    }
    private void importIncoming(){
        ArrayList<Uri> snapshot;
        synchronized(incoming){snapshot=new ArrayList<>(incoming);}
        if(snapshot.isEmpty())return;
        JSONArray names=new JSONArray();
        for(int i=0;i<snapshot.size();i++)names.put(audioName(snapshot.get(i),i));
        String js="(async function(){try{var names="+names.toString()+";var clips=[];"
                +"for(var i=0;i<names.length;i++){var r=await fetch('/native-shared-audio/'+i,{cache:'no-store'});"
                +"if(!r.ok)throw Error('קובץ לא זמין');var b=await r.blob();"
                +"clips.push(new File([b],names[i],{type:b.type||'audio/ogg'}));}"
                +"if(window.kolboImportSharedAudio)window.kolboImportSharedAudio(clips);"
                +"}catch(e){console.error('Import from WhatsApp',e);}})();";
        webView.evaluateJavascript(js,null);
    }
    @Override protected void onNewIntent(Intent intent){
        super.onNewIntent(intent);
        setIntent(intent);
        collectIncoming(intent);
        webView.loadUrl(STUDIO);
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
        @JavascriptInterface public void downloadMix(String relative){saveMix(relative,false);}
        @JavascriptInterface public void shareMix(String relative){saveMix(relative,true);}
    }
    private void saveMix(String relative,boolean share){
        if(relative==null||!relative.matches("/api/jobs/[0-9a-f]{48}/audio")){
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
                c.setRequestProperty("Accept","audio/mpeg");
                String cookie=CookieManager.getInstance().getCookie(SITE);
                if(cookie!=null)c.setRequestProperty("Cookie",cookie);
                if(c.getResponseCode()!=200)throw new Exception("ההורדה נכשלה ("+c.getResponseCode()+")");
                ContentValues meta=new ContentValues();
                meta.put(MediaStore.MediaColumns.DISPLAY_NAME,"Kolbo-Trance-"+System.currentTimeMillis()+".mp3");
                meta.put(MediaStore.MediaColumns.MIME_TYPE,"audio/mpeg");
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
                        if(total>40L*1024L*1024L)throw new Exception("קובץ MP3 גדול מדי");
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
                        send.setType("audio/mpeg");
                        send.putExtra(Intent.EXTRA_STREAM,ready);
                        send.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION);
                        try{startActivity(Intent.createChooser(send,"שיתוף המיקס"));}
                        catch(Exception e){toast("השיתוף אינו זמין. המיקס נשמר בהורדות.");}
                    }else toast("המיקס נשמר בתיקיית הורדות / Kolbo Trance");
                });
            }catch(Exception e){
                if(output!=null)try{getContentResolver().delete(output,null,null);}catch(Exception ignored){}
                toast("בעיה בשמירת המיקס: "+e.getMessage());
            }finally{if(c!=null)c.disconnect();}
        });
    }
    @Override public void onBackPressed(){
        if(webView!=null&&webView.canGoBack())webView.goBack();else super.onBackPressed();
    }
    @Override protected void onDestroy(){
        if(webView!=null){webView.removeJavascriptInterface("KolboAndroid");webView.destroy();}
        io.shutdown();
        super.onDestroy();
    }
}
