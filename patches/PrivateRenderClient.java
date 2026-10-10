package com.kolbo.videostudio;

import android.content.Context;
import android.content.SharedPreferences;
import android.net.Uri;
import android.security.keystore.KeyGenParameterSpec;
import android.security.keystore.KeyProperties;
import android.util.Base64;
import org.json.JSONArray;
import org.json.JSONObject;
import java.io.*;
import java.net.*;
import java.nio.charset.StandardCharsets;
import java.security.KeyStore;
import java.util.Locale;
import javax.crypto.Cipher;
import javax.crypto.KeyGenerator;
import javax.crypto.SecretKey;
import javax.crypto.spec.GCMParameterSpec;

/**
 * Optional independent GPU server client. Never silently falls back to public
 * quota-limited providers. HTTPS only, encrypted token in Android Keystore.
 * It cannot render without a reachable, configured GPU workflow.
 */
final class PrivateRenderClient {
    interface Status { void onStage(String stage); }
    private static final String PREFS="kolbo_private_engine_v1";
    private static final String KEY_ALIAS="kolbo_private_video_gateway_key";
    private static final int MAX_IMAGE=10*1024*1024;
    private static final int MAX_VIDEO=300*1024*1024;
    private PrivateRenderClient() {}

    static String normalizeUrl(String source) throws Exception {
        if(source==null)throw new Exception("נדרשת כתובת שרת");
        String v=source.trim();
        URL parsed=new URL(v);
        if(!"https".equalsIgnoreCase(parsed.getProtocol())||parsed.getHost().trim().isEmpty()
            ||parsed.getUserInfo()!=null||parsed.getQuery()!=null||parsed.getRef()!=null
            ||!(parsed.getPath().isEmpty()||parsed.getPath().equals("/")))
            throw new Exception("נדרשת כתובת HTTPS של שרת פרטי, ללא נתיב או פרטי משתמש");
        if(parsed.getPort()!=-1&&parsed.getPort()!=443)
            throw new Exception("מטעמי אבטחה נדרש HTTPS בפורט 443");
        return "https://"+parsed.getHost().toLowerCase(Locale.ROOT);
    }
    private static SecretKey key() throws Exception {
        KeyStore store=KeyStore.getInstance("AndroidKeyStore");store.load(null);
        if(store.containsAlias(KEY_ALIAS))
            return ((KeyStore.SecretKeyEntry)store.getEntry(KEY_ALIAS,null)).getSecretKey();
        KeyGenerator gen=KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES,"AndroidKeyStore");
        gen.init(new KeyGenParameterSpec.Builder(KEY_ALIAS,
            KeyProperties.PURPOSE_ENCRYPT|KeyProperties.PURPOSE_DECRYPT)
            .setBlockModes(KeyProperties.BLOCK_MODE_GCM)
            .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
            .setKeySize(256).build());
        return gen.generateKey();
    }
    private static String encrypt(String value) throws Exception {
        Cipher c=Cipher.getInstance("AES/GCM/NoPadding");c.init(Cipher.ENCRYPT_MODE,key());
        byte[] encrypted=c.doFinal(value.getBytes(StandardCharsets.UTF_8));
        byte[] iv=c.getIV();byte[] combined=new byte[iv.length+encrypted.length];
        System.arraycopy(iv,0,combined,0,iv.length);
        System.arraycopy(encrypted,0,combined,iv.length,encrypted.length);
        return Base64.encodeToString(combined,Base64.NO_WRAP);
    }
    private static String decrypt(String ciphertext) throws Exception {
        byte[] all=Base64.decode(ciphertext,Base64.NO_WRAP);
        if(all.length<29)throw new Exception("מפתח חיבור מוצפן אינו תקין");
        byte[] iv=new byte[12],value=new byte[all.length-12];
        System.arraycopy(all,0,iv,0,12);
        System.arraycopy(all,12,value,0,value.length);
        Cipher c=Cipher.getInstance("AES/GCM/NoPadding");
        c.init(Cipher.DECRYPT_MODE,key(),new GCMParameterSpec(128,iv));
        return new String(c.doFinal(value),StandardCharsets.UTF_8);
    }
    static void save(Context ctx,String url,String token) throws Exception {
        String normal=normalizeUrl(url);
        if(token==null||token.trim().length()<24)
            throw new Exception("מפתח החיבור חייב להכיל לפחות 24 תווים");
        String secret=encrypt(token.trim());
        ctx.getSharedPreferences(PREFS,Context.MODE_PRIVATE).edit()
            .putString("url",normal).putString("secret",secret).apply();
    }
    static void clear(Context ctx) {
        ctx.getSharedPreferences(PREFS,Context.MODE_PRIVATE).edit().clear().apply();
    }
    static String configuredUrl(Context ctx){
        return ctx.getSharedPreferences(PREFS,Context.MODE_PRIVATE).getString("url","");
    }
    static boolean configured(Context ctx) {
        SharedPreferences pref=ctx.getSharedPreferences(PREFS,Context.MODE_PRIVATE);
        return !pref.getString("url","").isEmpty()&&!pref.getString("secret","").isEmpty();
    }
    private static String token(Context ctx) throws Exception {
        String secret=ctx.getSharedPreferences(PREFS,Context.MODE_PRIVATE).getString("secret","");
        if(secret.isEmpty())throw new Exception("שרת פרטי עדיין לא חובר");
        return decrypt(secret);
    }
    private static HttpURLConnection open(Context ctx,String path,String method,int timeout) throws Exception {
        String base=normalizeUrl(configuredUrl(ctx));
        if(!path.startsWith("/v1/")||path.contains(".."))
            throw new Exception("נתיב בקשה לא מורשה");
        URL url=new URL(base+path);
        HttpURLConnection conn=(HttpURLConnection)url.openConnection();
        conn.setInstanceFollowRedirects(false);
        conn.setConnectTimeout(18000);conn.setReadTimeout(timeout);
        conn.setRequestMethod(method);
        conn.setUseCaches(false);
        conn.setRequestProperty("Authorization","Bearer "+token(ctx));
        conn.setRequestProperty("User-Agent","KolboVideo/4.0.8");
        return conn;
    }
    private static byte[] limited(InputStream in,int max) throws Exception {
        try(ByteArrayOutputStream b=new ByteArrayOutputStream()){
            byte[] buf=new byte[32768];int n;
            while((n=in.read(buf))!=-1){
                if(b.size()+n>max)throw new Exception("קובץ גדול מדי");
                b.write(buf,0,n);
            }
            return b.toByteArray();
        }
    }
    private static String fetch(HttpURLConnection conn) throws Exception {
        try{
            int code=conn.getResponseCode();
            if(code<200||code>=300){
                String msg="";
                try(InputStream input=conn.getErrorStream()){
                    if(input!=null)msg=new String(limited(input,1200),StandardCharsets.UTF_8);
                }catch(Exception ignored){}
                throw new Exception("שרת עצמאי החזיר שגיאה HTTP "+code+" "+msg);
            }
            try(InputStream in=conn.getInputStream()){
                return new String(limited(in,180000),StandardCharsets.UTF_8);
            }
        }finally{conn.disconnect();}
    }
    static JSONObject check(Context ctx) throws Exception {
        HttpURLConnection conn=open(ctx,"/v1/health","GET",30000);
        return new JSONObject(fetch(conn));
    }
    private static String mime(Context ctx,Uri uri) throws Exception {
        String contentType=ctx.getContentResolver().getType(uri);
        if(contentType==null||!(contentType.equals("image/jpeg")||contentType.equals("image/png")||
            contentType.equals("image/webp")))
            throw new Exception("השרת תומך בתמונות JPG, PNG ו־WEBP");
        return contentType;
    }
    private static JSONObject image(Context ctx,Uri uri) throws Exception {
        String type=mime(ctx,uri);
        try(InputStream in=ctx.getContentResolver().openInputStream(uri)){
            if(in==null)throw new Exception("התמונה אינה נגישה");
            byte[] content=limited(in,MAX_IMAGE);
            JSONObject record=new JSONObject();
            record.put("mime_type",type);
            record.put("data_base64",Base64.encodeToString(content,Base64.NO_WRAP));
            return record;
        }
    }
    static File render(Context ctx,String prompt,Uri subjectOne,Uri subjectTwo,
        int duration,File cache,Status status) throws Exception {
        JSONObject health=check(ctx);
        if(!"ready".equals(health.optString("status","")))
            throw new Exception("השרת הפרטי עדיין לא מוכן. יש לחבר GPU, ComfyUI ותבנית עבודה תקינה.");
        JSONObject payload=new JSONObject();
        payload.put("prompt",prompt);payload.put("seconds",duration);payload.put("fps",24);
        JSONArray images=new JSONArray();
        if(subjectOne!=null)images.put(image(ctx,subjectOne));
        if(subjectTwo!=null)images.put(image(ctx,subjectTwo));
        payload.put("images",images);
        HttpURLConnection conn=open(ctx,"/v1/jobs","POST",120000);
        conn.setDoOutput(true);
        conn.setRequestProperty("Content-Type","application/json; charset=UTF-8");
        byte[] json=payload.toString().getBytes(StandardCharsets.UTF_8);
        if(json.length>31*1024*1024)throw new Exception("קובצי התמונות גדולים מדי");
        conn.setFixedLengthStreamingMode(json.length);
        status.onStage("שולח בקשה לשרת ההפקה הפרטי...");
        try(OutputStream out=conn.getOutputStream()){out.write(json);}
        String id=new JSONObject(fetch(conn)).optString("job_id","");
        if(!id.matches("[0-9a-fA-F\\-]{36}"))
            throw new Exception("השרת לא החזיר מספר עבודה תקין");
        long limit=System.currentTimeMillis()+22*60*1000L;
        while(System.currentTimeMillis()<limit){
            if(Thread.currentThread().isInterrupted())throw new InterruptedException();
            Thread.sleep(2500);
            JSONObject next=new JSONObject(fetch(open(ctx,"/v1/jobs/"+id,"GET",30000)));
            String state=next.optString("state","");
            if(state.equals("failed"))throw new Exception(
                "המנוע הפרטי נכשל: "+next.optString("error",next.optString("detail","")));
            if(state.equals("completed"))break;
            if(!state.equals("queued")&&!state.equals("running"))
                throw new Exception("השרת החזיר מצב עבודה לא מוכר");
            status.onStage(next.optString("detail","מרנדר את הסרטון..."));
        }
        if(System.currentTimeMillis()>=limit)throw new Exception("עבר זמן ההפקה המותר בשרת");
        HttpURLConnection download=open(ctx,"/v1/jobs/"+id+"/result","GET",120000);
        File file=new File(cache,"kolbo-private-"+System.currentTimeMillis()+".mp4");
        try{
            int code=download.getResponseCode();
            if(code!=200)throw new Exception("הורדת תוצאת ההפקה נכשלה: "+code);
            try(InputStream in=download.getInputStream();OutputStream out=new FileOutputStream(file)){
                byte[] b=new byte[32768];int n;long sum=0;
                while((n=in.read(b))!=-1){
                    sum+=n;if(sum>MAX_VIDEO)throw new Exception("סרטון גדול מדי");
                    out.write(b,0,n);
                }
            }
            if(file.length()<10000)throw new Exception("לא התקבל סרטון");
            try(java.io.RandomAccessFile f=new java.io.RandomAccessFile(file,"r")){
                byte[] head=new byte[8];f.readFully(head);
                if(head[4]!='f'||head[5]!='t'||head[6]!='y'||head[7]!='p')
                    throw new Exception("תוצאת השרת אינה MP4 תקין");
            }
            return file;
        }catch(Exception e){file.delete();throw e;}
        finally{download.disconnect();}
    }
}
