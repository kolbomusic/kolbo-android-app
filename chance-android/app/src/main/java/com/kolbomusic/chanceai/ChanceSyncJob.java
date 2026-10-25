package com.kolbomusic.chanceai;

import android.app.job.JobParameters;
import android.app.job.JobService;
import android.content.Context;
import java.io.ByteArrayOutputStream;
import java.io.File;
import java.io.FileOutputStream;
import java.io.InputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.util.HashSet;
import java.util.Set;

public final class ChanceSyncJob extends JobService {
    private static final String DATA_URL =
        "https://raw.githubusercontent.com/kolbomusic/kolbo-android-app/main/chance-data/chance-latest.csv";
    private static final String SOURCE_URL =
        "https://raw.githubusercontent.com/kolbomusic/kolbo-android-app/main/chance-data/source.txt";
    private static final int MAX_CSV_BYTES = 1500000;
    private Thread worker;

    private static String download(String path, int limit) throws Exception {
        HttpURLConnection connection=(HttpURLConnection)new URL(path).openConnection();
        connection.setConnectTimeout(12000);
        connection.setReadTimeout(16000);
        connection.setRequestProperty("Accept","text/csv,text/plain");
        connection.setRequestProperty("User-Agent","KolboChanceAndroid/1.1");
        try {
            if(connection.getResponseCode()!=200)throw new IllegalStateException("HTTP "+connection.getResponseCode());
            ByteArrayOutputStream output=new ByteArrayOutputStream();
            try(InputStream stream=connection.getInputStream()){
                byte[] buffer=new byte[8192]; int read;
                while((read=stream.read(buffer))!=-1){
                    if(output.size()+read>limit)throw new IllegalStateException("CSV too large");
                    output.write(buffer,0,read);
                }
            }
            return new String(output.toByteArray(), StandardCharsets.UTF_8);
        } finally {connection.disconnect();}
    }

    private static boolean isRank(String s){
        return s.matches("7|8|9|10|J|Q|K|A");
    }

    private static int largestDrawId(String text){
        if(text==null||text.length()<100)return -1;
        String[] rows=text.replace("\uFEFF","").split("\\r?\\n");
        if(rows.length<11 || !rows[0].contains("תלתן") ||
           !rows[0].contains("יהלום") || !rows[0].contains("עלה") ||
           !rows[0].contains("מספר הגרלה"))return -1;
        int max=-1,count=0;
        Set<String> seen=new HashSet<>();
        for(int i=1;i<rows.length;i++){
            if(rows[i].trim().isEmpty())continue;
            String[] cell=rows[i].replace("\"","").split(",",-1);
            if(cell.length!=6)return -1;
            String id=cell[0].trim();
            if(!id.matches("[0-9]{4,9}") || !cell[1].trim().matches("[0-9]{1,2}/[0-9]{1,2}/[0-9]{4}"))return -1;
            for(int j=2;j<6;j++)if(!isRank(cell[j].trim().toUpperCase()))return -1;
            if(!seen.add(id))return -1;
            max=Math.max(max,Integer.parseInt(id));
            count++;
        }
        return count>=10 ? max : -1;
    }

    private static void writeAtomic(File destination, String content) throws Exception {
        File temp=new File(destination.getParentFile(),destination.getName()+".new");
        try(FileOutputStream stream=new FileOutputStream(temp)){
            stream.write(content.getBytes(StandardCharsets.UTF_8));
            stream.getFD().sync();
        }
        if(!temp.renameTo(destination)) {
            if(!destination.delete() || !temp.renameTo(destination)){
                throw new IllegalStateException("Cannot replace validated cache");
            }
        }
    }

    public static boolean fetchAndStore(Context context) {
        try {
            String csv=download(DATA_URL, MAX_CSV_BYTES);
            int newest=largestDrawId(csv);
            if(newest<0)return false;
            File target=new File(context.getFilesDir(),"chance-current.csv");
            if(target.exists() && target.length()<=MAX_CSV_BYTES) {
                String old=new String(Files.readAllBytes(target.toPath()),StandardCharsets.UTF_8);
                if(newest<largestDrawId(old))return false;
            }
            String provenance="מאגר מראה חיצוני — לא רשמי; לאישור תוצאות יש לבדוק מול מפעל הפיס.";
            try {
                String downloadedSource=download(SOURCE_URL,1000).trim();
                if(!downloadedSource.isEmpty())provenance=downloadedSource;
            } catch(Exception ignored){}
            writeAtomic(target,csv);
            writeAtomic(new File(context.getFilesDir(),"chance-source.txt"),provenance);
            return true;
        } catch(Exception ignored) {return false;}
    }

    @Override public boolean onStartJob(JobParameters params) {
        worker=new Thread(() -> {
            boolean success=fetchAndStore(getApplicationContext());
            jobFinished(params,!success);
        },"KolboChanceDailySync");
        worker.start();
        return true;
    }

    @Override public boolean onStopJob(JobParameters params){
        if(worker!=null)worker.interrupt();
        return true;
    }
}
