package com.kolbomusic.chanceowner;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.app.job.JobParameters;
import android.app.job.JobService;
import android.content.Context;
import android.content.Intent;
import android.os.Build;
import org.json.JSONObject;
import java.io.ByteArrayOutputStream;
import java.io.File;
import java.io.FileOutputStream;
import java.io.InputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.text.SimpleDateFormat;
import java.util.Date;
import java.util.Locale;
import java.util.TimeZone;

public final class OwnerDailyJob extends JobService {
    private static final String FEED_URL =
      "https://raw.githubusercontent.com/kolbomusic/kolbo-android-app/main/chance-data/daily-recommendation.json";
    private static final String FILE_NAME = "owner-daily-feed.json";
    private static final String CHANNEL_ID = "chance-owner-daily";
    private Thread worker;

    public static String todayIsrael() {
        SimpleDateFormat fmt = new SimpleDateFormat("yyyy-MM-dd", Locale.US);
        fmt.setTimeZone(TimeZone.getTimeZone("Asia/Jerusalem"));
        return fmt.format(new Date());
    }

    public static String getCache(Context ctx) {
        try {
            File f = new File(ctx.getFilesDir(), FILE_NAME);
            if(!f.exists() || f.length() > 20000) return "";
            byte[] bytes = new byte[(int)f.length()];
            try(java.io.FileInputStream input = new java.io.FileInputStream(f)) {
                int total = 0, got;
                while(total < bytes.length && (got = input.read(bytes,total,bytes.length-total)) > 0)total+=got;
                if(total != bytes.length)return "";
            }
            return new String(bytes, StandardCharsets.UTF_8);
        } catch(Exception e) { return ""; }
    }

    private static void notifyNew(Context context, String date, String description) {
        try {
            NotificationManager manager = (NotificationManager) context.getSystemService(Context.NOTIFICATION_SERVICE);
            if(manager==null)return;
            if(Build.VERSION.SDK_INT>=26){
                NotificationChannel channel=new NotificationChannel(CHANNEL_ID,"המלצות יומיות — Kolbo Chance",NotificationManager.IMPORTANCE_DEFAULT);
                channel.setDescription("עדכון נתוני זוגות ושלשות לפי שכיחות עבר");
                manager.createNotificationChannel(channel);
            }
            Intent open=new Intent(context,MainActivity.class);
            PendingIntent pending=PendingIntent.getActivity(context,1020,open,PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE);
            Notification.Builder b=Build.VERSION.SDK_INT>=26?
                new Notification.Builder(context,CHANNEL_ID):new Notification.Builder(context);
            b.setContentTitle("סקירת הקלפים להיום מוכנה")
             .setContentText(description)
             .setSmallIcon(android.R.drawable.ic_popup_reminder)
             .setAutoCancel(true)
             .setContentIntent(pending)
             .setWhen(System.currentTimeMillis());
            manager.notify(3812,b.build());
        } catch(SecurityException ignored){}
    }

    public static boolean refresh(Context context, boolean notify) {
        HttpURLConnection c=null;
        try {
            c=(HttpURLConnection)new URL(FEED_URL).openConnection();
            c.setConnectTimeout(12000);
            c.setReadTimeout(14000);
            c.setRequestProperty("Accept","application/json");
            c.setUseCaches(false);
            if(c.getResponseCode()!=200)return false;
            ByteArrayOutputStream out=new ByteArrayOutputStream();
            try(InputStream stream=c.getInputStream()){
                byte[] buf=new byte[2048];int n;
                while((n=stream.read(buf))!=-1){
                    if(out.size()+n>20000)return false;
                    out.write(buf,0,n);
                }
            }
            String json=new String(out.toByteArray(),StandardCharsets.UTF_8);
            JSONObject obj=new JSONObject(json);
            String date=obj.optString("date_israel","");
            if(!date.matches("\\d{4}-\\d{2}-\\d{2}"))return false;
            if(!todayIsrael().equals(date))return false; // Never display yesterday as today's recommendation.
            if(obj.optInt("schema_version",0)!=1)return false;
            if(obj.optJSONObject("pair")==null || obj.optJSONObject("triple")==null)return false;
            if(obj.optJSONObject("pair").optJSONArray("cards")==null || obj.optJSONObject("triple").optJSONArray("cards")==null)return false;
            if(obj.optString("whatsapp_draft","").length()<30)return false;
            File finalFile=new File(context.getFilesDir(),FILE_NAME),tmp=new File(context.getFilesDir(),FILE_NAME+".tmp");
            try(FileOutputStream output=new FileOutputStream(tmp)){
                output.write(json.getBytes(StandardCharsets.UTF_8));
                output.getFD().sync();
            }
            if(!tmp.renameTo(finalFile)) {
                if(!finalFile.delete() || !tmp.renameTo(finalFile))return false;
            }
            String previous=context.getSharedPreferences("chance_owner_sync",Context.MODE_PRIVATE).getString("last_notified","");
            if(notify && !date.equals(previous)) {
                String desc="זוג היסטורי: "+obj.getJSONObject("pair").optString("label","")+" · ללא הבטחת זכייה";
                notifyNew(context,date,desc);
                context.getSharedPreferences("chance_owner_sync",Context.MODE_PRIVATE).edit().putString("last_notified",date).apply();
            }
            return true;
        }catch(Exception e){return false;}
        finally {if(c!=null)c.disconnect();}
    }

    @Override public boolean onStartJob(JobParameters params){
        worker=new Thread(()->{
            boolean ok=refresh(getApplicationContext(),true);
            jobFinished(params,!ok);
        },"ChanceOwnerDailySync");
        worker.start();
        return true;
    }
    @Override public boolean onStopJob(JobParameters p) {
        if(worker!=null)worker.interrupt();
        return true;
    }
}
