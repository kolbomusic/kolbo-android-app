package com.kolbomusic.chanceai;

import android.content.Context;
import org.json.JSONArray;
import org.json.JSONObject;
import java.io.ByteArrayOutputStream;
import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.io.InputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.text.SimpleDateFormat;
import java.util.Date;
import java.util.Locale;
import java.util.TimeZone;

/** Read-only public historical brief, not an owner-authorized subscriber message. */
public final class DailyPublicFeed {
    private static final String URL =
        "https://raw.githubusercontent.com/kolbomusic/kolbo-android-app/main/chance-data/daily-recommendation.json";
    private static final String CACHE = "public-historical-daily.json";
    private DailyPublicFeed() {}

    public static String israelDate() {
        SimpleDateFormat date = new SimpleDateFormat("yyyy-MM-dd", Locale.US);
        date.setTimeZone(TimeZone.getTimeZone("Asia/Jerusalem"));
        return date.format(new Date());
    }

    private static boolean validCards(JSONObject part, int required) {
        if(part == null)return false;
        JSONArray cards=part.optJSONArray("cards");
        if(cards == null || cards.length()!=required)return false;
        if(part.optInt("sample_draws",0)<40)return false;
        if(part.optInt("historical_hits",0)<1)return false;
        for(int i=0;i<required;i++){
            JSONObject card=cards.optJSONObject(i);
            if(card == null)return false;
            String suit=card.optString("suit","");
            String rank=card.optString("rank","");
            if(!("♣♦♥♠".contains(suit) && suit.length()==1))return false;
            if(!rank.matches("7|8|9|10|J|Q|K|A"))return false;
        }
        return true;
    }

    private static boolean valid(JSONObject obj){
        return obj.optInt("schema_version",0)==1
            && israelDate().equals(obj.optString("date_israel",""))
            && validCards(obj.optJSONObject("pair"),2)
            && validCards(obj.optJSONObject("triple"),3)
            && obj.optString("kind","").equals("historical-frequency-not-prediction");
    }

    public static String cache(Context context){
        try {
            File file=new File(context.getFilesDir(),CACHE);
            if(!file.exists() || file.length()>24000)return "";
            ByteArrayOutputStream output=new ByteArrayOutputStream();
            try(FileInputStream in=new FileInputStream(file)){
                byte[] buf=new byte[2048];int n;
                while((n=in.read(buf))!=-1)output.write(buf,0,n);
            }
            String data=new String(output.toByteArray(),StandardCharsets.UTF_8);
            return valid(new JSONObject(data))?data:"";
        }catch(Exception ignored){return "";}
    }

    public static boolean fetch(Context context){
        HttpURLConnection connection=null;
        try {
            connection=(HttpURLConnection)new URL(URL).openConnection();
            connection.setConnectTimeout(10000);
            connection.setReadTimeout(12000);
            connection.setUseCaches(false);
            connection.setRequestProperty("Accept","application/json");
            if(connection.getResponseCode()!=200)return false;
            ByteArrayOutputStream output=new ByteArrayOutputStream();
            try(InputStream in=connection.getInputStream()){
                byte[] buf=new byte[2048];int n;
                while((n=in.read(buf))!=-1){
                    if(output.size()+n>24000)return false;
                    output.write(buf,0,n);
                }
            }
            String body=new String(output.toByteArray(),StandardCharsets.UTF_8);
            if(!valid(new JSONObject(body)))return false;
            File target=new File(context.getFilesDir(),CACHE);
            File temp=new File(context.getFilesDir(),CACHE+".tmp");
            try(FileOutputStream out=new FileOutputStream(temp)){
                out.write(body.getBytes(StandardCharsets.UTF_8));
                out.getFD().sync();
            }
            if(!temp.renameTo(target)){
                if(!target.delete() || !temp.renameTo(target))return false;
            }
            return true;
        }catch(Exception ignored){return false;}
        finally{if(connection!=null)connection.disconnect();}
    }
}
