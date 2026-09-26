package com.ofirgilboa.kolyaakov;

import android.app.Activity;
import android.content.Intent;
import android.graphics.Color;
import android.net.Uri;
import android.os.Bundle;
import android.webkit.JavascriptInterface;
import android.webkit.ValueCallback;
import android.webkit.WebChromeClient;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;

import java.io.OutputStream;
import java.nio.charset.StandardCharsets;

public class MainActivity extends Activity {
    private static final int FILE_CHOOSER = 301;
    private static final int CREATE_FILE = 302;

    private WebView webView;
    private ValueCallback<Uri[]> fileChooser;
    private String pendingFileName = "kol-yaakov-backup.json";
    private String pendingText = "";

    @Override
    public void onCreate(Bundle state) {
        super.onCreate(state);
        getWindow().setStatusBarColor(Color.rgb(9, 13, 24));
        getWindow().setNavigationBarColor(Color.rgb(9, 13, 24));

        webView = new WebView(this);
        setContentView(webView);

        WebSettings s = webView.getSettings();
        s.setJavaScriptEnabled(true);
        s.setDomStorageEnabled(true);
        s.setDatabaseEnabled(true);
        s.setAllowFileAccess(true);
        s.setAllowContentAccess(true);
        s.setMediaPlaybackRequiresUserGesture(false);
        s.setBuiltInZoomControls(false);
        s.setDisplayZoomControls(false);

        webView.setWebViewClient(new WebViewClient());
        webView.addJavascriptInterface(new Bridge(), "KolYaakovAndroid");
        webView.setWebChromeClient(new WebChromeClient() {
            @Override
            public boolean onShowFileChooser(WebView view, ValueCallback<Uri[]> callback, FileChooserParams params) {
                if (fileChooser != null) fileChooser.onReceiveValue(null);
                fileChooser = callback;
                try {
                    startActivityForResult(params.createIntent(), FILE_CHOOSER);
                    return true;
                } catch (Exception e) {
                    fileChooser = null;
                    return false;
                }
            }
        });

        webView.loadUrl("file:///android_asset/index.html");
    }

    public class Bridge {
        @JavascriptInterface
        public void saveTextFile(String name, String text) {
            runOnUiThread(() -> {
                pendingFileName = (name == null || name.isEmpty()) ? "kol-yaakov-backup.json" : name;
                pendingText = text == null ? "" : text;
                Intent i = new Intent(Intent.ACTION_CREATE_DOCUMENT);
                i.addCategory(Intent.CATEGORY_OPENABLE);
                i.setType("application/json");
                i.putExtra(Intent.EXTRA_TITLE, pendingFileName);
                startActivityForResult(i, CREATE_FILE);
            });
        }
    }

    @Override
    protected void onActivityResult(int requestCode, int resultCode, Intent data) {
        super.onActivityResult(requestCode, resultCode, data);
        if (requestCode == FILE_CHOOSER) {
            if (fileChooser != null) {
                fileChooser.onReceiveValue(WebChromeClient.FileChooserParams.parseResult(resultCode, data));
                fileChooser = null;
            }
        } else if (requestCode == CREATE_FILE && resultCode == RESULT_OK && data != null && data.getData() != null) {
            try (OutputStream out = getContentResolver().openOutputStream(data.getData())) {
                if (out != null) out.write(pendingText.getBytes(StandardCharsets.UTF_8));
            } catch (Exception ignored) { }
        }
    }

    @Override
    public void onBackPressed() {
        if (webView != null && webView.canGoBack()) webView.goBack();
        else super.onBackPressed();
    }

    @Override
    protected void onDestroy() {
        if (webView != null) {
            webView.removeJavascriptInterface("KolYaakovAndroid");
            webView.destroy();
            webView = null;
        }
        super.onDestroy();
    }
}
