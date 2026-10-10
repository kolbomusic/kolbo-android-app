package com.kolbo.videostudio;

import org.json.JSONArray;
import org.json.JSONObject;
import java.io.*;
import java.net.*;
import java.nio.charset.StandardCharsets;

/** Experimental publicly accessible ZeroGPU Gradio adapter with two independent
 *  image reference slots. Fixed host allowlist; no API key and no proxy.
 *  Service can be busy, can change and is NOT guaranteed to preserve identities.
 */
final class MultiSubjectReferenceClient {
    interface Status { void update(String detail); }
    private static final String HOST="hugging-apps-ltx25-multi-subject-reference.hf.space";
    private static final String BASE="https://"+HOST;
    private static final int IMAGE_LIMIT=10*1024*1024;
    private static final int VIDEO_LIMIT=90*1024*1024;

    private MultiSubjectReferenceClient() {}
    static HttpURLConnection open(String url,String method,int timeout) throws Exception {
        URL u=new URL(url);
        if(!"https".equalsIgnoreCase(u.getProtocol()) || !HOST.equalsIgnoreCase(u.getHost()) || u.getPort()!=-1)
            throw new Exception("כתובת שרת MSR אינה מורשית");
        HttpURLConnection c=(HttpURLConnection)u.openConnection();
        c.setInstanceFollowRedirects(false);
        c.setConnectTimeout(18000);c.setReadTimeout(timeout);
        c.setRequestMethod(method);
        c.setUseCaches(false);
        c.setRequestProperty("User-Agent","KolboVideo/4.0.2");
        return c;
    }
    private static byte[] bytes(InputStream in,int limit) throws Exception {
        try(ByteArrayOutputStream out=new ByteArrayOutputStream()){
            byte[] chunk=new byte[32768];int n;
            while((n=in.read(chunk))>=0) {
                if(out.size()+n>limit)throw new Exception("הנתונים חורגים ממגבלת הגודל");
                out.write(chunk,0,n);
            }
            return out.toByteArray();
        }
    }
    private static String response(HttpURLConnection c) throws Exception {
        int code=c.getResponseCode();
        if(code<200||code>=300){
            String detail="";
            try(InputStream e=c.getErrorStream()) {
                if(e!=null)detail=new String(bytes(e,1000),StandardCharsets.UTF_8);
            }catch(Exception ignored){}
            throw new Exception("שירות MSR אינו זמין (HTTP "+code+"): "+detail);
        }
        try(InputStream in=c.getInputStream()) {
            return new String(bytes(in,300000),StandardCharsets.UTF_8);
        }finally {c.disconnect();}
    }
    private static JSONObject upload(byte[] data,String mime) throws Exception {
        if(data==null||data.length<100||data.length>IMAGE_LIMIT)
            throw new Exception("תמונת מקור ריקה או גדולה מדי");
        if(mime==null||!(mime.equals("image/png")||mime.equals("image/jpeg")||mime.equals("image/webp")))
            throw new Exception("הספק תומך בתמונות JPG, PNG ו-WEBP בלבד");
        String name=mime.equals("image/png")?"subject.png":mime.equals("image/webp")?"subject.webp":"subject.jpg";
        String sep="----KolboMultiRef4b2e";
        HttpURLConnection c=open(BASE+"/gradio_api/upload","POST",120000);
        c.setDoOutput(true);
        c.setRequestProperty("Content-Type","multipart/form-data; boundary="+sep);
        try(OutputStream out=c.getOutputStream()) {
            out.write(("--"+sep+"\r\nContent-Disposition: form-data; name=\"files\"; filename=\""+name+"\"\r\nContent-Type: "+mime+"\r\n\r\n").getBytes(StandardCharsets.UTF_8));
            out.write(data);
            out.write(("\r\n--"+sep+"--\r\n").getBytes(StandardCharsets.UTF_8));
        }
        JSONArray result=new JSONArray(response(c));
        String path=result.getString(0);
        if(!path.startsWith("/")||path.contains("..")||path.length()>2048)
            throw new Exception("השרת החזיר כתובת קובץ שגויה");
        JSONObject meta=new JSONObject();meta.put("_type","gradio.FileData");
        JSONObject file=new JSONObject();
        file.put("path",path);file.put("mime_type",mime);file.put("orig_name",name);file.put("meta",meta);
        return file;
    }
    private static String submit(String prompt,JSONObject ref1,JSONObject ref2,int seconds) throws Exception {
        // Public /gradio_api/info schema, verified 2026-10-10. Index order matters.
        JSONArray p=new JSONArray();
        p.put(prompt);
        p.put(ref1);p.put(ref2);
        p.put(JSONObject.NULL); // scene_image
        p.put(JSONObject.NULL); // subject_3
        p.put(JSONObject.NULL); // subject_4
        p.put("1280 × 704 · 16:9");
        p.put((double)seconds); // Space supports 1..8 sec at 24 fps
        p.put(33);p.put(42);p.put(false);
        JSONObject request=new JSONObject();request.put("data",p);
        byte[] payload=request.toString().getBytes(StandardCharsets.UTF_8);
        HttpURLConnection c=open(BASE+"/gradio_api/call/generate","POST",60000);
        c.setDoOutput(true);c.setRequestProperty("Content-Type","application/json; charset=UTF-8");
        c.setFixedLengthStreamingMode(payload.length);
        try(OutputStream out=c.getOutputStream()){out.write(payload);}
        JSONObject result=new JSONObject(response(c));
        String event=result.optString("event_id","");
        if(!event.matches("[A-Za-z0-9_-]{6,120}"))
            throw new Exception("לא התקבל מספר עבודה תקין משירות MSR");
        return event;
    }
    private static String locateVideo(Object o,int depth) throws Exception {
        if(depth>10)return null;
        if(o instanceof JSONArray){
            JSONArray a=(JSONArray)o;
            for(int i=0;i<Math.min(a.length(),20);i++){
                String url=locateVideo(a.opt(i),depth+1);if(url!=null)return url;
            }
        }else if(o instanceof JSONObject){
            JSONObject j=(JSONObject)o;
            // Prefer a direct Gradio Video component URL.
            String url=j.optString("url","");
            if(url.startsWith(BASE+"/"))return url;
            String path=j.optString("path","");
            if(path.startsWith("/")&&!path.contains("..")&&path.length()<2048)
                return BASE+"/gradio_api/file="+URLEncoder.encode(path,"UTF-8");
            java.util.Iterator<String> it=j.keys();
            while(it.hasNext()){
                String k=it.next();
                String found=locateVideo(j.opt(k),depth+1);if(found!=null)return found;
            }
        }
        return null;
    }
    private static String awaitVideo(String event,Status status) throws Exception {
        HttpURLConnection c=open(BASE+"/gradio_api/call/generate/"+event,"GET",12*60*1000);
        c.setRequestProperty("Accept","text/event-stream");
        if(c.getResponseCode()!=200){
            int code=c.getResponseCode();c.disconnect();
            throw new Exception("שרת הווידאו לא קיבל את העבודה (HTTP "+code+")");
        }
        long deadline=System.currentTimeMillis()+12*60*1000;
        try(BufferedReader in=new BufferedReader(new InputStreamReader(c.getInputStream(),StandardCharsets.UTF_8))){
            String line,eventType="";StringBuilder body=new StringBuilder();
            while((line=in.readLine())!=null){
                if(System.currentTimeMillis()>deadline)throw new Exception("מנוע MSR לא סיים בזמן");
                if(line.startsWith("event:"))eventType=line.substring(6).trim();
                else if(line.startsWith("data:")) {
                    if(body.length()+line.length()>300000)throw new Exception("תגובה ארוכה מדי");
                    body.append(line.substring(5).trim());
                } else if(line.isEmpty()){
                    if("error".equals(eventType))
                        throw new Exception("שירות MSR החזיר כשל הפקה (ייתכן עומס או מכסת GPU): "+body.toString().substring(0,Math.min(180,body.length())));
                    if("complete".equals(eventType)){
                        String url=locateVideo(new JSONArray(body.toString()),0);
                        if(url==null)throw new Exception("מנוע MSR לא החזיר קובץ וידאו");
                        return url;
                    }
                    if("generating".equals(eventType))status.update("מנוע MSR מרנדר שתי דמויות בענן... תיתכן המתנה בתור");
                    eventType="";body.setLength(0);
                }
            }
            throw new Exception("הקשר עם שירות MSR הסתיים ללא קובץ");
        }finally{c.disconnect();}
    }
    private static File download(String url,File cache) throws Exception {
        HttpURLConnection c=open(url,"GET",120000);
        if(c.getResponseCode()!=200){int code=c.getResponseCode();c.disconnect();throw new Exception("הורדת MSR נכשלה: HTTP "+code);}
        File file=new File(cache,"kolbo-msr-"+System.currentTimeMillis()+".mp4");
        try(InputStream in=c.getInputStream();OutputStream out=new FileOutputStream(file)){
            byte[] buffer=new byte[32768];int count;long size=0;
            while((count=in.read(buffer))!=-1){
                size+=count;if(size>VIDEO_LIMIT)throw new Exception("סרטון MSR גדול מדי");
                out.write(buffer,0,count);
            }
            if(size<10000)throw new Exception("קובץ הווידאו ריק");
        } catch(Exception e){file.delete();throw e;}finally{c.disconnect();}
        try(java.io.RandomAccessFile f=new java.io.RandomAccessFile(file,"r")){
            byte[] head=new byte[12];f.readFully(head);
            if(head[4]!='f'||head[5]!='t'||head[6]!='y'||head[7]!='p')
                throw new Exception("התוצאה איננה MP4");
        }catch(Exception e){file.delete();throw e;}
        return file;
    }
    static File generate(byte[] originalOne,String mimeOne,byte[] originalTwo,String mimeTwo,
            String prompt,int seconds,File cache,Status status) throws Exception {
        if(seconds<1||seconds>8)throw new Exception("MSR מאפשר מקטעים בני 1–8 שניות");
        status.update("מעלה שני מקורות תמונה נפרדים לשרת MSR...");
        JSONObject a=upload(originalOne,mimeOne);
        JSONObject b=upload(originalTwo,mimeTwo);
        status.update("שולח בקשת הפקה עם שני מזהי מקור נפרדים...");
        String event=submit(prompt,a,b,seconds);
        String result=awaitVideo(event,status);
        status.update("מוריד את מקטע MSR...");
        return download(result,cache);
    }
}
