package com.kolbomusic.video;

import android.app.DownloadManager;
import android.content.Context;
import android.database.Cursor;
import android.net.Uri;
import android.os.Environment;
import android.os.StatFs;
import java.io.File;
import java.io.FileInputStream;
import java.security.MessageDigest;

/** Download once, verify cryptographic provenance, then run fully offline.
 * The Apache 2.0 language model is not embedded in the APK (330MB).
 * Deliberately Wi-Fi only: no unexpected 5G mobile data charges.
 */
public final class LocalBrainModelManager {
    private LocalBrainModelManager() {}
    public static final String MODEL_NAME="Qwen3-0.6B_dynamic_wi4b32_afp32.litertlm";
    public static final long EXPECTED_SIZE=344671744L;
    public static final String EXPECTED_SHA256=
        "03e7da1eb1108b50dffaa9bb52cc7bcbad2eb0c66ca990267f480c1e545d2856";
    public static final String URL="https://huggingface.co/litert-community/Qwen3-0.6B/resolve/main/"+
        MODEL_NAME+"?download=true";
    private static final String PREF="kolbo-local-qwen";
    private static final String ID="download_id";
    private static final String CHECKED="model_digest_verified";

    public static File modelFile(Context ctx){
        File root=ctx.getExternalFilesDir(Environment.DIRECTORY_DOWNLOADS);
        if(root==null)throw new IllegalStateException("אין גישה לאחסון האפליקציה");
        return new File(root,MODEL_NAME);
    }
    public static boolean isVerified(Context ctx) {
        File f=modelFile(ctx);
        if(!f.isFile() || f.length()!=EXPECTED_SIZE)return false;
        String saved=ctx.getSharedPreferences(PREF,Context.MODE_PRIVATE)
            .getString(CHECKED,"");
        if(EXPECTED_SHA256.equals(saved))return true;
        // Size alone is not sufficient; an untrusted network response may be HTML.
        try(FileInputStream input=new FileInputStream(f)){
            MessageDigest digest=MessageDigest.getInstance("SHA-256");
            byte[] buffer=new byte[1024*1024];int length;
            while((length=input.read(buffer))!=-1)digest.update(buffer,0,length);
            byte[] hash=digest.digest();
            StringBuilder sb=new StringBuilder(64);
            for(byte x:hash)sb.append(String.format(java.util.Locale.ROOT,"%02x",x&0xff));
            boolean safe=EXPECTED_SHA256.equals(sb.toString());
            if(safe)ctx.getSharedPreferences(PREF,Context.MODE_PRIVATE)
                .edit().putString(CHECKED,EXPECTED_SHA256).commit();
            return safe;
        }catch(Exception e){return false;}
    }

    public static String downloadStatus(Context ctx){
        if(isVerified(ctx))return "מוח Qwen מאומת ומוכן";
        long id=ctx.getSharedPreferences(PREF,Context.MODE_PRIVATE).getLong(ID,-1);
        if(id<0)return "המוח החינמי עדיין לא הורד";
        DownloadManager mgr=(DownloadManager)ctx.getSystemService(Context.DOWNLOAD_SERVICE);
        if(mgr==null)return "אין שירות הורדות במכשיר";
        DownloadManager.Query query=new DownloadManager.Query().setFilterById(id);
        try(Cursor cursor=mgr.query(query)){
            if(cursor!=null && cursor.moveToFirst()){
                int state=cursor.getInt(cursor.getColumnIndexOrThrow(DownloadManager.COLUMN_STATUS));
                if(state==DownloadManager.STATUS_SUCCESSFUL)
                    return "הורדת המודל הסתיימה — נדרש אימות הקובץ";
                if(state==DownloadManager.STATUS_FAILED)
                    return "ההורדה נכשלה. אפשר להתחיל הורדה חדשה ב-Wi-Fi.";
                return "מודל השפה מורד ברקע ב-Wi-Fi; כ־329MB פעם אחת.";
            }
        }catch(Exception ignored){}
        return "מצב הורדה לא ידוע";
    }
    public static synchronized long startWiFiDownload(Context ctx) {
        if(isVerified(ctx))return -2;
        DownloadManager manager=(DownloadManager)ctx.getSystemService(Context.DOWNLOAD_SERVICE);
        if(manager==null)throw new IllegalStateException("DownloadManager לא זמין");
        long previous=ctx.getSharedPreferences(PREF,Context.MODE_PRIVATE).getLong(ID,-1);
        if(previous>=0){
            try(Cursor cursor=manager.query(
                new DownloadManager.Query().setFilterById(previous))){
                if(cursor!=null&&cursor.moveToFirst()){
                    int status=cursor.getInt(
                       cursor.getColumnIndexOrThrow(DownloadManager.COLUMN_STATUS));
                    if(status==DownloadManager.STATUS_PENDING||
                       status==DownloadManager.STATUS_RUNNING||
                       status==DownloadManager.STATUS_PAUSED)return previous;
                }
            }
            // Remove a stale or malformed completion to allow an explicit retry.
            manager.remove(previous);
        }
        File target=modelFile(ctx);
        if(target.exists()&&!target.delete())
            throw new IllegalStateException("אי אפשר להסיר קובץ מודל פגום");
        StatFs disk=new StatFs(target.getParentFile().getAbsolutePath());
        if(disk.getAvailableBytes()<EXPECTED_SIZE+180_000_000L)
            throw new IllegalStateException("נדרשים לפחות 500MB פנויים להתקנת מודל השפה");
        DownloadManager.Request request=new DownloadManager.Request(Uri.parse(URL));
        request.setAllowedNetworkTypes(DownloadManager.Request.NETWORK_WIFI);
        request.setAllowedOverRoaming(false);
        request.setAllowedOverMetered(false);
        request.setTitle("Kolbo מוח שפה חינמי — Qwen3");
        request.setDescription("מודל Apache 2.0 מקומי, הורדה חד-פעמית, ללא עלות שרת");
        request.setNotificationVisibility(
            DownloadManager.Request.VISIBILITY_VISIBLE_NOTIFY_COMPLETED);
        request.setDestinationUri(Uri.fromFile(target));
        long id=manager.enqueue(request);
        ctx.getSharedPreferences(PREF,Context.MODE_PRIVATE).edit()
            .putLong(ID,id).remove(CHECKED).commit();
        return id;
    }
}
