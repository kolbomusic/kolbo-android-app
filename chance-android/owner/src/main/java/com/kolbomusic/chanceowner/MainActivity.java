package com.kolbomusic.chanceowner;

import android.app.Activity;
import android.app.KeyguardManager;
import android.os.Bundle;
import android.content.Intent;
import android.graphics.Color;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.webkit.WebResourceRequest;
import android.webkit.JavascriptInterface;
import android.widget.Toast;
import android.view.WindowManager;

public final class MainActivity extends Activity {
    private static final int VERIFY_UNLOCK = 441;
    private WebView web;
    private long unlocked = 0L;
    private boolean authenticating = false;

    @Override public void onCreate(Bundle b){
        super.onCreate(b);
        getWindow().addFlags(WindowManager.LayoutParams.FLAG_SECURE);
        getWindow().setStatusBarColor(Color.rgb(12,18,33));
        getWindow().setNavigationBarColor(Color.rgb(12,18,33));
        authenticate();
    }
    private void authenticate(){
        KeyguardManager guard=(KeyguardManager)getSystemService(KEYGUARD_SERVICE);
        if(guard==null || !guard.isKeyguardSecure()){
            Toast.makeText(this,"נדרשת נעילת מסך במכשיר להפעלת מסך הבעלים.",Toast.LENGTH_LONG).show();
            finish();
            return;
        }
        Intent check=guard.createConfirmDeviceCredentialIntent("Kolbo Chance Owner","יש לאמת את זהות בעל המכשיר.");
        if(check==null){finish();return;}
        authenticating=true;
        startActivityForResult(check,VERIFY_UNLOCK);
    }
    private void showAdmin(){
        if(web!=null)return;
        web=new WebView(this);
        web.setBackgroundColor(Color.rgb(11,17,32));
        WebSettings settings=web.getSettings();
        settings.setJavaScriptEnabled(true);
        settings.setDomStorageEnabled(true);
        settings.setAllowFileAccess(true);
        settings.setAllowFileAccessFromFileURLs(false);
        settings.setAllowUniversalAccessFromFileURLs(false);
        settings.setMixedContentMode(WebSettings.MIXED_CONTENT_NEVER_ALLOW);
        web.setWebViewClient(new WebViewClient(){
            @Override public boolean shouldOverrideUrlLoading(WebView v,WebResourceRequest request){return true;}
        });
        web.addJavascriptInterface(new OwnerBridge(),"KolboOwnerBridge");
        setContentView(web);
        web.loadUrl("file:///android_asset/index.html");
    }
    final class OwnerBridge {
        @JavascriptInterface public void share(String text){
            if(text==null||text.isEmpty())return;
            runOnUiThread(()->{
                Intent share=new Intent(Intent.ACTION_SEND);
                share.setType("text/plain");
                share.putExtra(Intent.EXTRA_TEXT,text.substring(0,Math.min(text.length(),6000)));
                try{startActivity(Intent.createChooser(share,"שיתוף המלצה"));}
                catch(Exception ex){Toast.makeText(MainActivity.this,"לא ניתן לפתוח שיתוף",Toast.LENGTH_SHORT).show();}
            });
        }
    }
    @Override protected void onActivityResult(int request,int result,Intent data){
        super.onActivityResult(request,result,data);
        if(request==VERIFY_UNLOCK){
            authenticating=false;
            if(result==RESULT_OK){unlocked=android.os.SystemClock.elapsedRealtime();showAdmin();}
            else finish();
        }
    }
    @Override protected void onResume(){
        super.onResume();
        if(web!=null && !authenticating
           && android.os.SystemClock.elapsedRealtime()-unlocked>5*60*1000L){authenticate();}
    }
    @Override protected void onDestroy(){if(web!=null){web.destroy();web=null;}super.onDestroy();}
}
