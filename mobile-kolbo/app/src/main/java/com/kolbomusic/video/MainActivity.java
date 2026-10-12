package com.kolbomusic.video;

import android.app.Activity;
import android.os.Bundle;
import android.os.Build;
import android.content.Intent;
import android.content.ClipData;
import android.graphics.Color;
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
import android.widget.EditText;
import android.widget.TextView;
import android.widget.Button;
import android.widget.Toast;
import java.net.URI;
import java.util.Locale;

public final class MainActivity extends Activity {
    private static final int FILE_REQUEST=401;
    private WebView browser;
    private LinearLayout setup;
    private EditText server;
    private android.webkit.ValueCallback<Uri[]> pendingFiles;
    private String allowedHost="";
    private VideoExportBridge videoExport;
    private int dp(int n){return Math.round(n*getResources().getDisplayMetrics().density);}
    @Override public void onCreate(Bundle saved){
        super.onCreate(saved);
        getWindow().setStatusBarColor(Color.rgb(22,18,37));
        getWindow().setNavigationBarColor(Color.rgb(22,18,37));
        LinearLayout root=new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        root.setLayoutDirection(View.LAYOUT_DIRECTION_RTL);
        setup=new LinearLayout(this);
        setup.setOrientation(LinearLayout.VERTICAL);
        setup.setPadding(dp(18),dp(22),dp(18),dp(16));
        TextView title=new TextView(this);
        title.setText("Kolbo Video · התחברות לאולפן");
        title.setTextSize(23f);
        setup.addView(title);
        TextView info=new TextView(this);
        info.setText("דרוש שרת Kolbo Mesh פרטי ב־HTTPS ומנוע GPU מורשה. אין באפליקציה מנוע AI מובנה או חיוב.");
        info.setPadding(0,dp(12),0,dp(12));
        setup.addView(info);
        server=new EditText(this);
        server.setHint("https://your-server.example");
        server.setSingleLine(true);
        server.setInputType(android.text.InputType.TYPE_CLASS_TEXT|android.text.InputType.TYPE_TEXT_VARIATION_URI);
        server.setText(getPreferences(MODE_PRIVATE).getString("hub",""));
        setup.addView(server);
        Button open=new Button(this);
        open.setText("פתח את אולפן הווידאו");
        open.setOnClickListener(v->connect(server.getText().toString()));
        setup.addView(open);
        TextView gpuHeader=new TextView(this);
        gpuHeader.setText("ניסוי וידאו אמיתי — מחשוב GPU חינמי");
        gpuHeader.setTextSize(19f);
        gpuHeader.setPadding(0,dp(24),0,dp(8));
        setup.addView(gpuHeader);
        TextView gpuDisclosure=new TextView(this);
        gpuDisclosure.setText("פתיחת Hugging Face בדפדפן: שירות חיצוני עם מכסות זמן וזמינות משתנה. אין חיוב אוטומטי באפליקציה. תמונות יועברו רק אם תבחר להעלות אותן בשירות החיצוני; מומלץ להשתמש בתמונות שיש לך הרשאה להשתמש בהן.");
        gpuDisclosure.setTextSize(13f);
        gpuDisclosure.setPadding(0,0,0,dp(8));
        setup.addView(gpuDisclosure);
        Button officialFreeGpu=new Button(this);
        officialFreeGpu.setText("התנסות ב־GPU חינמי · וידאו עם שמע");
        officialFreeGpu.setOnClickListener(v->openApprovedGpuPage(
            "https://huggingface.co/spaces/Lightricks/LTX-2.5"));
        setup.addView(officialFreeGpu);
        Button duoGpu=new Button(this);
        duoGpu.setText("ניסוי שתי דמויות · מחשוב GPU חינמי");
        duoGpu.setOnClickListener(v->openApprovedGpuPage(
            "https://huggingface.co/spaces/hugging-apps/ltx25-multi-subject-reference"));
        setup.addView(duoGpu);
        root.addView(setup);
        browser=new WebView(this);
        videoExport=new VideoExportBridge(this);
        browser.addJavascriptInterface(videoExport,"KolboExport");
        browser.setVisibility(View.GONE);
        WebSettings s=browser.getSettings();
        s.setJavaScriptEnabled(true);
        s.setDomStorageEnabled(true);
        s.setAllowFileAccess(false);
        s.setAllowContentAccess(true);
        s.setAllowFileAccessFromFileURLs(false);
        s.setAllowUniversalAccessFromFileURLs(false);
        s.setMixedContentMode(WebSettings.MIXED_CONTENT_NEVER_ALLOW);
        s.setCacheMode(WebSettings.LOAD_NO_CACHE);
        if(Build.VERSION.SDK_INT>=26)s.setSafeBrowsingEnabled(true);
        WebView.setWebContentsDebuggingEnabled(false);
        CookieManager.getInstance().setAcceptThirdPartyCookies(browser,false);
        browser.setWebViewClient(new WebViewClient(){
            @Override public boolean shouldOverrideUrlLoading(WebView v,WebResourceRequest request){
                String host=request.getUrl().getHost();
                String scheme=request.getUrl().getScheme();
                int port=request.getUrl().getPort();
                if("https".equalsIgnoreCase(scheme)&&port==-1 || "https".equalsIgnoreCase(scheme)&&port==443){
                    if(host!=null&&host.equalsIgnoreCase(allowedHost))return false;
                }
                Toast.makeText(MainActivity.this,"מעבר לשרת חיצוני נחסם",Toast.LENGTH_SHORT).show();
                return true;
            }
            @Override public void onReceivedSslError(WebView v,android.webkit.SslErrorHandler handler,android.net.http.SslError error){
                handler.cancel();
                Toast.makeText(MainActivity.this,"אישור HTTPS אינו תקין",Toast.LENGTH_LONG).show();
            }
        });
        browser.setWebChromeClient(new WebChromeClient(){
            @Override public boolean onShowFileChooser(WebView web,android.webkit.ValueCallback<Uri[]> callback,FileChooserParams params){
                if(pendingFiles!=null)pendingFiles.onReceiveValue(null);
                pendingFiles=callback;
                try{
                    Intent intent=params.createIntent();
                    intent.addCategory(Intent.CATEGORY_OPENABLE);
                    startActivityForResult(intent,FILE_REQUEST);
                    return true;
                }catch(Exception err){
                    pendingFiles=null;
                    callback.onReceiveValue(null);
                    return false;
                }
            }
        });
        root.addView(browser,new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT,0,1));
        setContentView(root);
        String restored=server.getText().toString().trim();
        if(!restored.isEmpty())connect(restored);
    }
    /** Launch only trusted, static public ZeroGPU demos in the system browser.
     * No photos, owner authentication or private tokens are transmitted by this app.
     * The external provider controls its own quota, permissions and media retention.
     */
    private void openApprovedGpuPage(String candidate){
        final String first="https://huggingface.co/spaces/Lightricks/LTX-2.5";
        final String second="https://huggingface.co/spaces/hugging-apps/ltx25-multi-subject-reference";
        if(!candidate.equals(first)&&!candidate.equals(second)){
            Toast.makeText(this,"כתובת GPU אינה מאושרת",Toast.LENGTH_LONG).show();
            return;
        }
        try{
            Intent openPage=new Intent(Intent.ACTION_VIEW,Uri.parse(candidate));
            openPage.addCategory(Intent.CATEGORY_BROWSABLE);
            startActivity(openPage);
        }catch(Exception e){
            Toast.makeText(this,"לא נמצא דפדפן לפתיחת השירות החיצוני",Toast.LENGTH_LONG).show();
        }
    }
    private void connect(String candidate){
        try{
            URI uri=new URI(candidate.trim());
            if(!"https".equalsIgnoreCase(uri.getScheme())||uri.getHost()==null||
               uri.getRawUserInfo()!=null||uri.getRawQuery()!=null||uri.getRawFragment()!=null||
               (uri.getRawPath()!=null&&!uri.getRawPath().isEmpty()&&!uri.getRawPath().equals("/"))||
               (uri.getPort()!=-1&&uri.getPort()!=443))
                throw new IllegalArgumentException();
            String host=uri.getHost().toLowerCase(Locale.ROOT);
            if(host.equals("localhost")||host.endsWith(".local")||host.endsWith(".test"))
                throw new IllegalArgumentException();
            allowedHost=host;
            String origin="https://"+host;
            // Do not open an obsolete /studio endpoint; verify the v4.4.9 API first.
            Toast.makeText(this,"מאמת תאימות שרת...",Toast.LENGTH_SHORT).show();
            final String chosenHost=host;
            new Thread(()->{
                boolean contractOk=false;
                try{
                    java.net.HttpURLConnection connection=(java.net.HttpURLConnection)
                        new java.net.URL(origin+"/v1/app-config").openConnection();
                    connection.setConnectTimeout(6000);
                    connection.setReadTimeout(6000);
                    connection.setInstanceFollowRedirects(false);
                    connection.setRequestProperty("Accept","application/json");
                    try{
                        if(connection.getResponseCode()==200){
                            java.io.InputStream stream=connection.getInputStream();
                            java.io.ByteArrayOutputStream buf=new java.io.ByteArrayOutputStream();
                            byte[] bytes=new byte[1024]; int n;
                            while((n=stream.read(bytes))!=-1&&buf.size()<8192)buf.write(bytes,0,n);
                            stream.close();
                            org.json.JSONObject config=new org.json.JSONObject(buf.toString("UTF-8"));
                            contractOk="kolbo-volunteer-mesh".equals(config.optString("service")) &&
                                config.optInt("api_contract",0)==449 &&
                                config.optInt("minimum_android_client",9999)<=449 &&
                                config.optBoolean("owner_auth_required",false);
                        }
                    }finally{connection.disconnect();}
                }catch(Exception ignored){}
                final boolean compatible=contractOk;
                runOnUiThread(()->{
                    if(!compatible||!chosenHost.equals(allowedHost)){
                        Toast.makeText(this,"השרת אינו זמין או לא תואם ל־4.4.9",Toast.LENGTH_LONG).show();
                        return;
                    }
                    getPreferences(MODE_PRIVATE).edit().putString("hub",origin).apply();
                    setup.setVisibility(View.GONE);
                    browser.setVisibility(View.VISIBLE);
                    browser.loadUrl(origin+"/studio");
                });
            },"KolboContractCheck").start();
        }catch(Exception err){
            Toast.makeText(this,"יש להזין כתובת HTTPS תקינה",Toast.LENGTH_LONG).show();
        }
    }
    @Override protected void onActivityResult(int requestCode,int resultCode,Intent data){
        super.onActivityResult(requestCode,resultCode,data);
        if(requestCode==VideoExportBridge.SAVE_REQUEST){videoExport.handleSave(resultCode,data);return;}
        if(requestCode!=FILE_REQUEST||pendingFiles==null)return;
        Uri[] selected=null;
        if(resultCode==RESULT_OK&&data!=null){
            if(data.getClipData()!=null){
                ClipData clips=data.getClipData();
                selected=new Uri[clips.getItemCount()];
                for(int i=0;i<clips.getItemCount();i++)selected[i]=clips.getItemAt(i).getUri();
            }else if(data.getData()!=null)selected=new Uri[]{data.getData()};
        }
        pendingFiles.onReceiveValue(selected);
        pendingFiles=null;
    }
    @Override public void onBackPressed(){
        if(browser.getVisibility()==View.VISIBLE&&browser.canGoBack())browser.goBack();
        else if(browser.getVisibility()==View.VISIBLE){browser.setVisibility(View.GONE);setup.setVisibility(View.VISIBLE);}
        else super.onBackPressed();
    }
    @Override protected void onDestroy(){
        if(pendingFiles!=null)pendingFiles.onReceiveValue(null);
        pendingFiles=null;
        videoExport.abort();
        browser.destroy();
        super.onDestroy();
    }
}
