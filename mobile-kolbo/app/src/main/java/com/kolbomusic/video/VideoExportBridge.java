package com.kolbomusic.video;
import android.app.Activity;
import android.content.Intent;
import android.net.Uri;
import android.util.Base64;
import android.webkit.JavascriptInterface;
import android.widget.Toast;
import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.io.IOException;
import java.io.OutputStream;
import java.util.UUID;

/** Bounded app-private MP4 transfer. User selects the final destination with Android Save As. */
public final class VideoExportBridge {
    public static final int SAVE_REQUEST=402;
    private static final long MAX_BYTES=120_000_000L;
    private static final int MAX_CHUNK=65536;
    private final Activity activity;
    private final Object guard=new Object();
    private File temporary;
    private FileOutputStream stream;
    private long expected,written;
    private boolean collecting;
    public VideoExportBridge(Activity activity){this.activity=activity;}
    @JavascriptInterface public void begin(long bytes){
        synchronized(guard){
            reset();
            if(bytes<10000||bytes>MAX_BYTES)return;
            try{
                temporary=File.createTempFile("kolbo-", ".mp4", activity.getCacheDir());
                stream=new FileOutputStream(temporary);
                expected=bytes;written=0;collecting=true;
            }catch(IOException e){reset();}
        }
    }
    @JavascriptInterface public boolean chunk(String base64){
        synchronized(guard){
            if(!collecting||base64==null||base64.length()>90000)return false;
            try{
                byte[] bytes=Base64.decode(base64,Base64.NO_WRAP);
                if(bytes.length==0||bytes.length>MAX_CHUNK||written+bytes.length>expected){reset();return false;}
                stream.write(bytes);written+=bytes.length;return true;
            }catch(Exception e){reset();return false;}
        }
    }
    @JavascriptInterface public boolean finish(){
        synchronized(guard){
            if(!collecting||written!=expected){reset();return false;}
            try{
                stream.flush();stream.close();stream=null;
                try(FileInputStream in=new FileInputStream(temporary)){
                    byte[] header=new byte[12];
                    if(in.read(header)!=12||header[4]!='f'||header[5]!='t'||header[6]!='y'||header[7]!='p'){
                        reset();return false;
                    }
                }
                collecting=false;
                activity.runOnUiThread(()->{
                    Intent picker=new Intent(Intent.ACTION_CREATE_DOCUMENT);
                    picker.setType("video/mp4");
                    picker.addCategory(Intent.CATEGORY_OPENABLE);
                    picker.putExtra(Intent.EXTRA_TITLE,"Kolbo-Video-"+UUID.randomUUID().toString().substring(0,8)+".mp4");
                    try{activity.startActivityForResult(picker,SAVE_REQUEST);}
                    catch(Exception e){abort();toast("לא ניתן לבחור מיקום שמירה");}
                });
                return true;
            }catch(IOException e){reset();return false;}
        }
    }
    @JavascriptInterface public void abort(){synchronized(guard){reset();}}
    public void handleSave(int resultCode,Intent data){
        File file;
        synchronized(guard){file=temporary;temporary=null;}
        if(file==null)return;
        if(resultCode!=Activity.RESULT_OK||data==null||data.getData()==null){file.delete();return;}
        Uri target=data.getData();
        new Thread(()->{
            boolean ok=false;
            try(FileInputStream input=new FileInputStream(file);
                OutputStream output=activity.getContentResolver().openOutputStream(target,"w")){
                if(output==null)throw new IOException("No destination");
                byte[] buffer=new byte[65536];int n;
                while((n=input.read(buffer))!=-1)output.write(buffer,0,n);
                output.flush();ok=true;
            }catch(Exception e){
                try{android.provider.DocumentsContract.deleteDocument(activity.getContentResolver(),target);}
                catch(Exception ignored){}
            }finally{
                file.delete();final boolean success=ok;
                activity.runOnUiThread(()->toast(success?"הסרטון נשמר":"שמירת הסרטון נכשלה"));
            }
        },"KolboVideoSave").start();
    }
    private void toast(String msg){Toast.makeText(activity,msg,Toast.LENGTH_LONG).show();}
    private void reset(){
        collecting=false;expected=0;written=0;
        if(stream!=null)try{stream.close();}catch(IOException ignored){}
        stream=null;
        if(temporary!=null)temporary.delete();
        temporary=null;
    }
}
