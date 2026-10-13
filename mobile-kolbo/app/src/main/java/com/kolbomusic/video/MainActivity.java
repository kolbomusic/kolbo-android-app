package com.kolbomusic.video;

import android.app.Activity;
import android.app.DownloadManager;
import android.content.ClipData;
import android.content.Context;
import android.content.Intent;
import android.graphics.Color;
import android.graphics.drawable.GradientDrawable;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.os.Environment;
import android.view.Gravity;
import android.view.View;
import android.view.ViewGroup;
import android.webkit.CookieManager;
import android.webkit.DownloadListener;
import android.webkit.SslErrorHandler;
import android.webkit.WebChromeClient;
import android.webkit.WebResourceRequest;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.ProgressBar;
import android.widget.ScrollView;
import android.widget.TextView;
import android.widget.Toast;

import java.util.UUID;

/**
 * Kolbo Video 4.6.8: an honest, direct window into a demonstrated AI video model.
 *
 * This APK does not impersonate a GPU or claim the 15-second + 2-person + singing
 * experience is solved. It allows an actual hosted model to perform generation
 * through its own public, first-party Gradio UI. No app-owned server, account,
 * payment proxy, API key, auto retries, or unsolicited photo upload.
 */
public final class MainActivity extends Activity {
    private static final String PROVIDER_HOST =
        "zerogpu-aoti-wan2-2-fp8da-aoti-faster.hf.space";
    private static final String PROVIDER_URL =
        "https://" + PROVIDER_HOST + "/";
    private static final int PICK_IMAGES = 468;
    private static final int BG = Color.rgb(15, 18, 31);
    private static final int PANEL = Color.rgb(31, 39, 61);
    private static final int TEXT = Color.rgb(249, 248, 255);
    private static final int MUTED = Color.rgb(185, 194, 215);
    private static final int VIOLET = Color.rgb(102, 53, 211);

    private LinearLayout root, home;
    private TextView message;
    private WebView browser;
    private ProgressBar loading;
    private android.webkit.ValueCallback<Uri[]> waitingForImage;
    private boolean inStudio = false;
    private boolean pageLoaded = false;

    private int dp(int x) {
        return Math.round(x * getResources().getDisplayMetrics().density);
    }
    private GradientDrawable bg(int color, int radius) {
        GradientDrawable shape = new GradientDrawable();
        shape.setColor(color);
        shape.setCornerRadius(dp(radius));
        return shape;
    }
    private TextView text(String content, int sp, int color) {
        TextView t = new TextView(this);
        t.setText(content);
        t.setTextSize(sp);
        t.setTextColor(color);
        t.setTextDirection(View.TEXT_DIRECTION_RTL);
        t.setGravity(Gravity.RIGHT);
        return t;
    }
    private Button button(String caption, Runnable action, boolean secondary) {
        Button b = new Button(this);
        b.setText(caption);
        b.setAllCaps(false);
        b.setTextColor(TEXT);
        b.setTextSize(16);
        b.setBackground(bg(secondary ? PANEL : VIOLET, 14));
        b.setOnClickListener(v -> action.run());
        return b;
    }
    private void space(int height) {
        View v = new View(this);
        home.addView(v, new LinearLayout.LayoutParams(1, dp(height)));
    }
    private void toast(String message) {
        Toast.makeText(this, message, Toast.LENGTH_LONG).show();
    }
    private void openExternally() {
        try {
            Intent i = new Intent(Intent.ACTION_VIEW, Uri.parse(PROVIDER_URL));
            i.addCategory(Intent.CATEGORY_BROWSABLE);
            startActivity(i);
        } catch (Exception e) {
            toast("לא נמצא דפדפן זמין");
        }
    }
    @Override public void onCreate(Bundle state) {
        super.onCreate(state);
        getWindow().setStatusBarColor(BG);
        getWindow().setNavigationBarColor(BG);
        root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        root.setLayoutDirection(View.LAYOUT_DIRECTION_RTL);
        root.setBackgroundColor(BG);

        ScrollView scroll = new ScrollView(this);
        scroll.setFillViewport(true);
        home = new LinearLayout(this);
        home.setOrientation(LinearLayout.VERTICAL);
        home.setPadding(dp(20), dp(27), dp(20), dp(30));
        scroll.addView(home);
        root.addView(scroll, new LinearLayout.LayoutParams(
            ViewGroup.LayoutParams.MATCH_PARENT, 0, 1));

        TextView title = text("Kolbo Video AI", 30, TEXT);
        title.setTypeface(null, android.graphics.Typeface.BOLD);
        home.addView(title);
        space(6);
        home.addView(text("הפקת תנועה אמיתית באמצעות מנוע AI בענן", 16, MUTED));
        space(23);

        LinearLayout info = new LinearLayout(this);
        info.setPadding(dp(16), dp(15), dp(16), dp(18));
        info.setOrientation(LinearLayout.VERTICAL);
        info.setBackground(bg(PANEL, 16));
        TextView heading = text("ניסוי פעיל — Wan2.2 Fast", 19, TEXT);
        heading.setTypeface(null, android.graphics.Typeface.BOLD);
        info.addView(heading);
        TextView detail = text(
            "מנוע הווידאו הפיק אצלנו MP4 אמיתי עם תנועה. " +
            "הוא פועל בשרת ציבורי של Hugging Face, ולכן היצירה תלויה בזמינות ובמכסה שלו." +
            "\n\nמה ניתן לעשות: להוסיף תמונה אחת, לכתוב הנחיה ולבקש סרטון קצר (עד כ־5 שניות)." +
            "\n\nעדיין לא נתמך בניסוי: שתי תמונות של דמויות שונות, 15 שניות, שמע, דיבור, " +
            "שירה וסנכרון שפתיים. לא ייווצר במקומם סרטון מדומה.",
            14, MUTED);
        detail.setLineSpacing(dp(5), 1f);
        detail.setPadding(0, dp(10), 0, 0);
        info.addView(detail);
        home.addView(info);
        space(22);

        home.addView(button("פתח אולפן AI אמיתי", this::openStudio, false));
        space(10);
        home.addView(button("פתח את המנוע בדפדפן", this::openExternally, true));
        space(18);
        message = text("אין העלאה של תמונות עד שאתה בוחר אותן באולפן של הספק.", 14, MUTED);
        message.setLineSpacing(dp(4), 1);
        home.addView(message);
        space(18);
        home.addView(text("השירות החיצוני עשוי לבקש התחברות או להפעיל מגבלות יומיות. " +
            "Kolbo Video אינה עוקפת מגבלות ספקים ואינה מפעילה מסלול בתשלום.", 13, MUTED));

        LinearLayout studioBar = new LinearLayout(this);
        studioBar.setPadding(dp(8), dp(8), dp(8), dp(8));
        studioBar.setOrientation(LinearLayout.HORIZONTAL);
        studioBar.setBackgroundColor(PANEL);
        Button close = button("חזור", this::closeStudio, true);
        studioBar.addView(close, new LinearLayout.LayoutParams(0, dp(44), 1));
        Button reload = button("רענן", () -> {
            if (browser != null) browser.reload();
        }, true);
        studioBar.addView(reload, new LinearLayout.LayoutParams(0, dp(44), 1));
        Button external = button("דפדפן", this::openExternally, true);
        studioBar.addView(external, new LinearLayout.LayoutParams(0, dp(44), 1));
        studioBar.setVisibility(View.GONE);
        root.addView(studioBar);

        loading = new ProgressBar(this, null, android.R.attr.progressBarStyleHorizontal);
        loading.setIndeterminate(true);
        loading.setVisibility(View.GONE);
        root.addView(loading, new LinearLayout.LayoutParams(
            ViewGroup.LayoutParams.MATCH_PARENT, dp(3)));

        browser = new WebView(this);
        browser.setVisibility(View.GONE);
        browser.setBackgroundColor(BG);
        WebSettings settings = browser.getSettings();
        settings.setJavaScriptEnabled(true);
        settings.setDomStorageEnabled(true);
        settings.setMediaPlaybackRequiresUserGesture(false);
        settings.setJavaScriptCanOpenWindowsAutomatically(false);
        settings.setSupportMultipleWindows(false);
        settings.setMixedContentMode(WebSettings.MIXED_CONTENT_NEVER_ALLOW);
        settings.setAllowFileAccess(false);
        settings.setAllowContentAccess(true); // Android document picker image URIs.
        settings.setAllowFileAccessFromFileURLs(false);
        settings.setAllowUniversalAccessFromFileURLs(false);
        if (Build.VERSION.SDK_INT >= 26) settings.setSafeBrowsingEnabled(true);
        WebView.setWebContentsDebuggingEnabled(false);
        CookieManager.getInstance().setAcceptThirdPartyCookies(browser, false);
        browser.setWebChromeClient(new WebChromeClient() {
            @Override public boolean onShowFileChooser(
                WebView view, android.webkit.ValueCallback<Uri[]> callback,
                FileChooserParams params) {
                if (waitingForImage != null) waitingForImage.onReceiveValue(null);
                waitingForImage = callback;
                try {
                    Intent choose = new Intent(Intent.ACTION_OPEN_DOCUMENT);
                    choose.addCategory(Intent.CATEGORY_OPENABLE);
                    choose.setType("image/*");
                    choose.putExtra(Intent.EXTRA_ALLOW_MULTIPLE, false);
                    startActivityForResult(choose, PICK_IMAGES);
                    return true;
                } catch (Exception error) {
                    waitingForImage = null;
                    callback.onReceiveValue(null);
                    toast("לא ניתן לבחור תמונה");
                    return false;
                }
            }
            @Override public void onProgressChanged(WebView view, int progress) {
                loading.setVisibility(progress >= 100 ? View.GONE : View.VISIBLE);
            }
        });
        browser.setWebViewClient(new WebViewClient() {
            @Override public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest request) {
                Uri u = request.getUrl();
                if (approved(u)) return false;
                if ("https".equalsIgnoreCase(u.getScheme())) {
                    try { startActivity(new Intent(Intent.ACTION_VIEW, u)); }
                    catch (Exception e) { toast("לא ניתן לפתוח קישור חיצוני"); }
                }
                return true;
            }
            @Override public void onPageFinished(WebView view, String url) {
                if (approved(Uri.parse(url))) {
                    pageLoaded = true;
                    loading.setVisibility(View.GONE);
                }
            }
            @Override public void onReceivedSslError(
                WebView view, SslErrorHandler handler, android.net.http.SslError error) {
                handler.cancel();
                toast("אישור האבטחה של שרת הווידאו אינו תקין");
            }
            @Override public void onReceivedHttpError(
                WebView view, WebResourceRequest request,
                android.webkit.WebResourceResponse response) {
                if (request.isForMainFrame() && response.getStatusCode() >= 400) {
                    toast("השרת החיצוני החזיר שגיאת " + response.getStatusCode() +
                        ". אפשר לפתוח בדפדפן ולבדוק זמינות.");
                }
            }
        });
        browser.setDownloadListener(new DownloadListener() {
            @Override public void onDownloadStart(String url, String userAgent,
                String contentDisposition, String mimeType, long length) {
                requestDownload(url, mimeType, length);
            }
        });
        root.addView(browser, new LinearLayout.LayoutParams(
            ViewGroup.LayoutParams.MATCH_PARENT, 0, 1));
        setContentView(root);

        // Hold UI references for returning without reloading provider jobs.
        this.scroll = scroll;
        this.studioBar = studioBar;
    }
    private ScrollView scroll;
    private LinearLayout studioBar;

    private boolean approved(Uri u) {
        return u != null && "https".equalsIgnoreCase(u.getScheme())
            && PROVIDER_HOST.equalsIgnoreCase(u.getHost())
            && (u.getPort() == -1 || u.getPort() == 443);
    }
    private void openStudio() {
        scroll.setVisibility(View.GONE);
        studioBar.setVisibility(View.VISIBLE);
        browser.setVisibility(View.VISIBLE);
        inStudio = true;
        if (!pageLoaded) {
            loading.setVisibility(View.VISIBLE);
            browser.loadUrl(PROVIDER_URL);
        }
    }
    private void closeStudio() {
        browser.setVisibility(View.GONE);
        studioBar.setVisibility(View.GONE);
        loading.setVisibility(View.GONE);
        scroll.setVisibility(View.VISIBLE);
        inStudio = false;
    }
    /** Only download links on the vetted Space's HTTPS host are acceptable. */
    private void requestDownload(String raw, String mime, long length) {
        Uri uri;
        try { uri = Uri.parse(raw); }
        catch (Exception e) { toast("קישור ההורדה אינו תקין"); return; }
        if (!approved(uri) || length > 150_000_000L ||
            !(("video/mp4".equalsIgnoreCase(mime)) ||
              (raw.contains("/file") && raw.toLowerCase().contains(".mp4")))) {
            toast("לא ניתן לאמת הורדת MP4 מהספק. נסה פתיחה בדפדפן.");
            return;
        }
        try {
            DownloadManager.Request request = new DownloadManager.Request(uri);
            request.setMimeType("video/mp4");
            request.setTitle("Kolbo Video AI");
            request.setDescription("קובץ MP4 שהופק במנוע AI חיצוני");
            request.setNotificationVisibility(
                DownloadManager.Request.VISIBILITY_VISIBLE_NOTIFY_COMPLETED);
            request.addRequestHeader("User-Agent", browser.getSettings().getUserAgentString());
            String cookies = CookieManager.getInstance().getCookie(PROVIDER_URL);
            if (cookies != null && !cookies.isEmpty()) request.addRequestHeader("Cookie", cookies);
            String filename = "Kolbo-Video-" + UUID.randomUUID().toString().substring(0,8) + ".mp4";
            // Public Downloads on scoped storage, app-private fallback on Android 8.
            if (Build.VERSION.SDK_INT >= 29) {
                request.setDestinationInExternalPublicDir(Environment.DIRECTORY_DOWNLOADS,filename);
            } else {
                request.setDestinationInExternalFilesDir(MainActivity.this,
                    Environment.DIRECTORY_MOVIES,filename);
            }
            DownloadManager mgr=(DownloadManager)getSystemService(Context.DOWNLOAD_SERVICE);
            if (mgr == null) throw new IllegalStateException("Download Manager missing");
            mgr.enqueue(request);
            toast("הורדת הסרטון התחילה. בדוק את ההורדות של המכשיר.");
        } catch (Exception e) {
            toast("ההורדה לא הופעלה. נסה דרך הדפדפן.");
        }
    }
    @Override protected void onActivityResult(int request, int result, Intent data) {
        super.onActivityResult(request,result,data);
        if (request == PICK_IMAGES && waitingForImage != null) {
            Uri[] files=null;
            if (result == RESULT_OK && data != null && data.getData()!=null) {
                files = new Uri[]{data.getData()};
            }
            waitingForImage.onReceiveValue(files);
            waitingForImage=null;
        }
    }
    @Override public void onBackPressed() {
        if (inStudio && browser.canGoBack()) browser.goBack();
        else if (inStudio) closeStudio();
        else super.onBackPressed();
    }
    @Override protected void onDestroy() {
        if (waitingForImage != null) waitingForImage.onReceiveValue(null);
        waitingForImage=null;
        if (browser != null) {
            browser.setDownloadListener(null);
            browser.destroy();
        }
        super.onDestroy();
    }
}
