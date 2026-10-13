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
 * An approved deployment is REQUIRED for this optional API. The default
 * release BuildConfig.CLOUD_PLANNER_URL="" does not upload any story.
 * A valid, permitted endpoint must be deployed and configured at build time.
 */
public final class RemoteStoryPlanner {
    private RemoteStoryPlanner(){}
    public static boolean configured(){
        return BuildConfig.CLOUD_PLANNER_URL!=null
            && BuildConfig.CLOUD_PLANNER_URL.startsWith("https://");
    }

    public static String plan(String hebrew,String english) throws IOException {
        if(!configured())throw new IOException("שרת המוח עדיין לא חובר");
        if(hebrew==null||hebrew.length()>1600||english==null||english.length()>3200)
            throw new IOException("בקשת תכנון לא תקינה");
        final URL url=new URL(BuildConfig.CLOUD_PLANNER_URL);
        if(!"https".equalsIgnoreCase(url.getProtocol())||url.getUserInfo()!=null
           ||(url.getPort()!=-1 && url.getPort()!=443))
            throw new IOException("כתובת מנוע השפה אינה מאושרת");
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
