package com.kolbomusic.chanceai;

import android.app.Activity;
import android.app.job.JobInfo;
import android.app.job.JobScheduler;
import android.content.ComponentName;
import android.os.Build;
import java.io.File;
import java.nio.file.Files;
import android.os.Bundle;
import android.content.Intent;
import android.graphics.Color;
import android.net.Uri;
import android.webkit.JavascriptInterface;
import android.webkit.ValueCallback;
import android.webkit.WebChromeClient;
import android.webkit.WebResourceRequest;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.Toast;
import java.io.OutputStream;
import java.nio.charset.StandardCharsets;

public final class MainActivity extends Activity {
    private static final int CHOOSE_CSV = 501;
    private static final int SAVE_CSV = 502;
    private WebView web;
    private ValueCallback<Uri[]> uploadCallback;
    private String csvPending;

    @Override public void onCreate(Bundle state) {
        super.onCreate(state);
        getWindow().setStatusBarColor(Color.rgb(21, 26, 55));
        getWindow().setNavigationBarColor(Color.rgb(11, 16, 36));
        web = new WebView(this);
        web.setBackgroundColor(Color.rgb(11, 16, 36));
        setContentView(web);
        WebSettings settings = web.getSettings();
        settings.setJavaScriptEnabled(true);
        settings.setDomStorageEnabled(true);
        settings.setAllowFileAccess(true);
        settings.setAllowContentAccess(true);
        settings.setAllowFileAccessFromFileURLs(false);
        settings.setAllowUniversalAccessFromFileURLs(false);
        settings.setMixedContentMode(WebSettings.MIXED_CONTENT_NEVER_ALLOW);
        web.addJavascriptInterface(new NativeBridge(), "KolboNative");
        web.setWebViewClient(new WebViewClient() {
            @Override public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest request) {
                Uri uri = request.getUrl();
                if ("file".equals(uri.getScheme()) && "/android_asset/index.html".equals(uri.getPath())) return false;
                if ("https".equals(uri.getScheme()) || "http".equals(uri.getScheme())) {
                    try { startActivity(new Intent(Intent.ACTION_VIEW, uri)); }
                    catch (Exception ignored) { Toast.makeText(MainActivity.this, "לא נמצא דפדפן מתאים", Toast.LENGTH_LONG).show(); }
                }
                return true;
            }
        });
        web.setWebChromeClient(new WebChromeClient() {
            @Override public boolean onShowFileChooser(WebView view, ValueCallback<Uri[]> callback, FileChooserParams params) {
                if (uploadCallback != null) uploadCallback.onReceiveValue(null);
                uploadCallback = callback;
                try {
                    Intent picker = params.createIntent();
                    startActivityForResult(picker, CHOOSE_CSV);
                    return true;
                } catch (Exception e) {
                    uploadCallback = null;
                    callback.onReceiveValue(null);
                    Toast.makeText(MainActivity.this, "לא ניתן לפתוח את בחירת הקבצים", Toast.LENGTH_LONG).show();
                    return true;
                }
            }
        });
        web.loadUrl("file:///android_asset/index.html");
        final JobScheduler scheduler=(JobScheduler)getSystemService(JOB_SCHEDULER_SERVICE);
        if(scheduler != null) {
            JobInfo periodic=new JobInfo.Builder(92801,new ComponentName(this,ChanceSyncJob.class))
                .setRequiredNetworkType(JobInfo.NETWORK_TYPE_ANY)
                .setPersisted(true)
                .setPeriodic(24L*60L*60L*1000L)
                .build();
            scheduler.schedule(periodic);
        }
        // Refresh immediately at startup too; the periodic job covers closed-app days.
        new Thread(() -> {
            try {
                ChanceSyncJob.fetchAndStore(getApplicationContext());
                runOnUiThread(() -> {
                    if(web != null)web.evaluateJavascript("window.KolboAutoSyncFromNative && window.KolboAutoSyncFromNative()",null);
                });
            } catch(Exception ignored) {}
        }, "KolboChanceStartSync").start();
    }

    public final class NativeBridge {
        @JavascriptInterface public String getCsvCache() {
            try {
                File file=new File(getFilesDir(),"chance-current.csv");
                if(!file.exists() || file.length()>1500000) return "";
                return new String(Files.readAllBytes(file.toPath()),StandardCharsets.UTF_8);
            } catch(Exception ignored) { return ""; }
        }
        @JavascriptInterface public long getCsvUpdatedAt() {
            File file=new File(getFilesDir(),"chance-current.csv");
            return file.exists()?file.lastModified():0;
        }
        @JavascriptInterface public String getCsvSource() {
            try {
                File file=new File(getFilesDir(),"chance-source.txt");
                if(!file.exists() || file.length()>1000) return "מאגר מראה, מקור לא רשמי";
                return new String(Files.readAllBytes(file.toPath()), StandardCharsets.UTF_8);
            } catch(Exception ignored) {return "מאגר מראה, מקור לא רשמי";}
        }
        @JavascriptInterface public void saveCsv(String text) {
            runOnUiThread(() -> {
                csvPending = text;
                try {
                    Intent save = new Intent(Intent.ACTION_CREATE_DOCUMENT);
                    save.addCategory(Intent.CATEGORY_OPENABLE);
                    save.setType("text/csv");
                    save.putExtra(Intent.EXTRA_TITLE, "kolbo-chance-data.csv");
                    startActivityForResult(save, SAVE_CSV);
                } catch (Exception e) {
                    csvPending = null;
                    Toast.makeText(MainActivity.this, "לא ניתן לפתוח שמירת קבצים", Toast.LENGTH_LONG).show();
                }
            });
        }
    }

    @Override protected void onActivityResult(int request, int result, Intent data) {
        super.onActivityResult(request, result, data);
        if (request == CHOOSE_CSV) {
            if (uploadCallback != null) {
                uploadCallback.onReceiveValue(WebChromeClient.FileChooserParams.parseResult(result, data));
                uploadCallback = null;
            }
        } else if (request == SAVE_CSV) {
            if (result == RESULT_OK && data != null && data.getData() != null && csvPending != null) {
                try (OutputStream output = getContentResolver().openOutputStream(data.getData())) {
                    if (output == null) throw new IllegalStateException("No output stream");
                    output.write(csvPending.getBytes(StandardCharsets.UTF_8));
                    Toast.makeText(this, "הקובץ נשמר בהצלחה", Toast.LENGTH_SHORT).show();
                } catch (Exception e) {
                    Toast.makeText(this, "השמירה נכשלה", Toast.LENGTH_LONG).show();
                }
            }
            csvPending = null;
        }
    }

    @Override public void onBackPressed() {
        if (web != null && web.canGoBack()) web.goBack();
        else super.onBackPressed();
    }

    @Override protected void onDestroy() {
        if (uploadCallback != null) { uploadCallback.onReceiveValue(null); uploadCallback = null; }
        if (web != null) { web.destroy(); web = null; }
        super.onDestroy();
    }
}
