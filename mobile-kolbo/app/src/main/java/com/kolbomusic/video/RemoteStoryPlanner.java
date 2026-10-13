package com.kolbomusic.video;

import android.content.Context;
import org.json.JSONObject;

import java.io.BufferedReader;
import java.io.IOException;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;

/**
 * Very light client for a separately hosted model planner.
 *
 * Deliberately no on-device LLM, image model, GGUF, bundled weights,
 * hardware accelerator or phone-side reasoning jobs.
 *
 * An approved deployment is REQUIRED for this optional API.
 * The app discovers the approved HTTPS Worker URL from a small GitHub JSON
 * file, allowing deployment changes without another APK update.
 * The manifest is disabled until an actual, tested backend exists.
 */
public final class RemoteStoryPlanner {
    private RemoteStoryPlanner(){}
    // This is a *read-only* URL; the discovery document holds no user data.
    // Only a trusted GitHub repository owner may enable its Worker endpoint.
    private static final String DISCOVERY=
        "https://raw.githubusercontent.com/kolbomusic/kolbo-android-app/"+
        "kolbo-video-v520-lightweight-cloud-first-20261014/cloud-brain-worker/endpoint.json";

    public static boolean configured(){
        // True means the integration exists, NOT that a remote model is deployed.
        return true;
    }
    private static URL endpoint() throws IOException {
        String target=BuildConfig.CLOUD_PLANNER_URL;
        if(target==null || target.isEmpty()){
            HttpURLConnection lookup=(HttpURLConnection)new URL(DISCOVERY).openConnection();
            lookup.setInstanceFollowRedirects(false);
            lookup.setConnectTimeout(7000);
            lookup.setReadTimeout(7000);
            try{
                if(lookup.getResponseCode()!=200 || lookup.getContentLengthLong()>2200)
                    throw new IOException("הגדרת השרת אינה זמינה");
                StringBuilder text=new StringBuilder(800);
                try(InputStream in=lookup.getInputStream();
                    BufferedReader rd=new BufferedReader(
                        new InputStreamReader(in,StandardCharsets.UTF_8))){
                    char[] buf=new char[512];int n;
                    while((n=rd.read(buf))!=-1){
                        text.append(buf,0,n);
                        if(text.length()>2200)throw new IOException("הגדרת שרת ארוכה מדי");
                    }
                }
                JSONObject config=new JSONObject(text.toString());
                if(config.optInt("schema_version")!=1 || !config.optBoolean("enabled",false))
                    throw new IOException("שרת המוח עדיין לא הופעל. ממשיך בתכנון בסיסי.");
                target=config.optString("url","");
            }catch(org.json.JSONException e){
                throw new IOException("הגדרת שרת המוח אינה תקינה",e);
            }finally{lookup.disconnect();}
        }
        URL url=new URL(target);
        if(!"https".equalsIgnoreCase(url.getProtocol()) || url.getUserInfo()!=null ||
           (url.getPort()!=-1 && url.getPort()!=443) ||
           !url.getHost().endsWith(".workers.dev") ||
           !"/v1/plan".equals(url.getPath()) || url.getQuery()!=null)
            throw new IOException("שרת המוח אינו ברשימת מקורות Cloudflare מורשים");
        return url;
    }

    /** Lightweight readiness check. GET only, no user story or image transferred. */
    public static boolean isServiceHealthy(){
        try {
            URL original=endpoint();
            URL health=new URL(original.getProtocol(),original.getHost(),
                original.getPort(),"/health");
            HttpURLConnection c=(HttpURLConnection)health.openConnection();
            c.setInstanceFollowRedirects(false);
            c.setConnectTimeout(5500);
            c.setReadTimeout(5500);
            try{
                if(c.getResponseCode()!=200||c.getContentLengthLong()>1000)return false;
                StringBuilder answer=new StringBuilder(100);
                try(InputStream in=c.getInputStream();
                    BufferedReader r=new BufferedReader(
                        new InputStreamReader(in,StandardCharsets.UTF_8))){
                    char[] buf=new char[256];int n;
                    while((n=r.read(buf))!=-1){
                        answer.append(buf,0,n);
                        if(answer.length()>1000)return false;
                    }
                }
                JSONObject status=new JSONObject(answer.toString());
                return status.optBoolean("ready",false)&&status.optInt("version")==1;
            }finally{c.disconnect();}
        }catch(Exception e){return false;}
    }

    public static String plan(String hebrew,String english) throws IOException {
        if(hebrew==null||hebrew.length()>1600||english==null||english.length()>3200)
            throw new IOException("בקשת תכנון לא תקינה");
        final URL url=endpoint();
        HttpURLConnection c=(HttpURLConnection)url.openConnection();
        c.setInstanceFollowRedirects(false);
        c.setConnectTimeout(8000);
        c.setReadTimeout(55000);
        c.setRequestMethod("POST");
        c.setRequestProperty("Content-Type","application/json; charset=utf-8");
        c.setRequestProperty("Accept","application/json");
        c.setUseCaches(false);
        c.setDoOutput(true);
        JSONObject request=new JSONObject();
        try{
            request.put("hebrew_story",hebrew);
            request.put("english_translation",english);
            request.put("schema_version",1);
        }catch(Exception e){throw new IOException("שגיאת הכנת הבקשה",e);}
        byte[] bytes=request.toString().getBytes(StandardCharsets.UTF_8);
        try{
            c.setFixedLengthStreamingMode(bytes.length);
            try(OutputStream out=c.getOutputStream()){out.write(bytes);}
            if(c.getResponseCode()!=200)
                throw new IOException("שרת המוח לא השיב כראוי ("+c.getResponseCode()+")");
            if(c.getContentLengthLong()>16000)
                throw new IOException("תגובת שרת המוח ארוכה מדי");
            try(InputStream in=c.getInputStream();
                BufferedReader reader=new BufferedReader(
                    new InputStreamReader(in,StandardCharsets.UTF_8))){
                StringBuilder result=new StringBuilder(4000);
                char[] buffer=new char[2048];int n;
                while((n=reader.read(buffer))!=-1){
                    result.append(buffer,0,n);
                    if(result.length()>16000)
                        throw new IOException("התגובה גדולה מהגבלת הבטיחות");
                }
                JSONObject response=new JSONObject(result.toString());
                // Preserve QwenPlanContract's robust JSON validation and
                // original hard constraints in the calling code.
                if(response.has("plan") && response.optJSONObject("plan")!=null)
                    return response.getJSONObject("plan").toString();
                return response.toString();
            }
        }catch(org.json.JSONException e){
            throw new IOException("התקבלה תוכנית שאינה JSON תקין",e);
        }finally{c.disconnect();}
    }
}
