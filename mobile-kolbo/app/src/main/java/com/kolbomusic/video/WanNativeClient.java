package com.kolbomusic.video;

import android.content.Context;
import android.graphics.Bitmap;
import android.graphics.BitmapFactory;
import android.net.Uri;
import android.util.Base64;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.BufferedReader;
import java.io.ByteArrayOutputStream;
import java.io.File;
import java.io.FileOutputStream;
import java.io.FileInputStream;
import java.io.IOException;
import java.io.InputStream;
import java.io.InputStreamReader;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.util.Locale;
import java.util.UUID;

/**
 * Native, direct, one-shot public Gradio API client. No WebView, proxy, payment,
 * API key, hidden retry, telemetry or automatic private-photo transfer.
 * Provider capacity and semantic adherence remain external/unverified.
 */
public final class WanNativeClient {
    public static final String HOST="zerogpu-aoti-wan2-2-fp8da-aoti-faster.hf.space";
    private WanProviderCatalog.Engine engine=WanProviderCatalog.FAST;
    private String origin(){return engine.origin();}
    public String providerId(){return engine.id;}
    public String providerName(){return engine.name;}
    public void useForExistingJob(String id){
        engine=WanProviderCatalog.byId(id);
    }
    private static final int MAX_JSON=700_000;
    private static final int MAX_VIDEO=100_000_000;
    private static final int MAX_UPLOAD=4_000_000;

    public interface Progress {
        void status(String text);
        default void beforeSubmission() {}
        default void providerSelected(String providerId,String providerName) {}
        default void jobCreated(String id) {}
    }
    public static final class Result {
        public final File video;
        public final String eventId;
        public final String warning;
        Result(File v,String id,String w){video=v;eventId=id;warning=w;}
    }

    /** Definitive provider terminal error; never automatically retry the same job. */
    public static final class FinalProviderRejection extends IOException {
        public final String reasonCode;
        public final String providerId;
        FinalProviderRejection(ProviderErrorClassifier.Result result,String providerId) {
            super(result.hebrew);
            this.reasonCode=result.code;
            this.providerId=providerId;
        }
    }

    private HttpURLConnection connection(String url,String method,int readTimeout) throws IOException {
        URL input=new URL(url);
        if(!"https".equalsIgnoreCase(input.getProtocol()) ||
            !engine.host.equalsIgnoreCase(input.getHost()) ||
            (input.getPort()!=-1&&input.getPort()!=443) ||
            input.getUserInfo()!=null) throw new IOException("כתובת הספק אינה מורשית");
        HttpURLConnection c=(HttpURLConnection)input.openConnection();
        c.setInstanceFollowRedirects(false);
        c.setRequestMethod(method);
        c.setConnectTimeout(18000);
        c.setReadTimeout(readTimeout);
        c.setRequestProperty("Accept","application/json, text/event-stream");
        c.setRequestProperty("User-Agent","KolboVideoNative/4.7.4");
        c.setUseCaches(false);
        return c;
    }

    private static String utf8(InputStream in,int max) throws IOException {
        try(InputStream stream=in;ByteArrayOutputStream out=new ByteArrayOutputStream()){
            byte[] chunk=new byte[4096];int n;
            while((n=stream.read(chunk))!=-1){
                if(out.size()+n>max)throw new IOException("תגובת השרת גדולה מדי");
                out.write(chunk,0,n);
            }
            return out.toString("UTF-8");
        }
    }

    private static String body(HttpURLConnection c,int max) throws IOException {
        int code=c.getResponseCode();
        if(code==401||code==403||code==429)
            throw new IOException("שירות הווידאו דורש הרשאה או שהמכסה התמלאה ("+code+")");
        if(code<200||code>=300)
            throw new IOException("שירות הווידאו החזיר שגיאה HTTP "+code);
        return utf8(c.getInputStream(),max);
    }

    /** Network GET only; this checks exact public parameter names and order. */
    public void preflight() throws Exception {
        HttpURLConnection c=connection(origin()+"/gradio_api/info","GET",18000);
        try{
            JSONObject document=new JSONObject(body(c,MAX_JSON));
            JSONObject apis=document.optJSONObject("named_endpoints");
            JSONObject endpoint=apis==null?null:apis.optJSONObject("/generate_video");
            JSONArray parameters=endpoint==null?null:endpoint.optJSONArray("parameters");
            if(parameters==null||parameters.length()!=engine.parameters.length)
                throw new IOException("ממשק המנוע השתנה; לא נשלחה תמונה");
            for(int i=0;i<engine.parameters.length;i++){
                JSONObject entry=parameters.optJSONObject(i);
                if(entry==null||!engine.parameters[i].equals(entry.optString("parameter_name")))
                    throw new IOException("ממשק המנוע השתנה; לא נשלחה תמונה");
            }
        }finally{c.disconnect();}
    }

    public byte[] compressPhoto(Context context,Uri uri,boolean cleanPhoto) throws Exception {
        if(uri==null || !"content".equalsIgnoreCase(uri.getScheme()))
            throw new IOException("נדרשת תמונה שנבחרה דרך הטלפון");
        BitmapFactory.Options options=new BitmapFactory.Options();
        options.inJustDecodeBounds=true;
        try(InputStream in=context.getContentResolver().openInputStream(uri)){
            if(in==null)throw new IOException("קובץ התמונה לא נפתח");
            BitmapFactory.decodeStream(in,null,options);
        }
        if(options.outWidth<64||options.outHeight<64||options.outWidth>10000||
            options.outHeight>10000)
            throw new IOException("מידות התמונה אינן מתאימות");
        int sample=1;
        while(Math.max(options.outWidth,options.outHeight)/sample>1440)sample*=2;
        options.inJustDecodeBounds=false;
        options.inSampleSize=sample;
        Bitmap bitmap;
        try(InputStream in=context.getContentResolver().openInputStream(uri)){
            bitmap=BitmapFactory.decodeStream(in,null,options);
        }
        if(bitmap==null)throw new IOException("התמונה אינה תקינה");
        Bitmap reduced=bitmap;
        int longest=Math.max(bitmap.getWidth(),bitmap.getHeight());
        if(longest>1024){
            float scale=1024f/longest;
            reduced=Bitmap.createScaledBitmap(bitmap,
                Math.max(1,Math.round(bitmap.getWidth()*scale)),
                Math.max(1,Math.round(bitmap.getHeight()*scale)),true);
            bitmap.recycle();
        }
        if(cleanPhoto){
            Bitmap cleaned=BasicPhotoCleaner.adjust(reduced);
            reduced.recycle();
            reduced=cleaned;
        }
        try{
            ByteArrayOutputStream out=new ByteArrayOutputStream();
            if(!reduced.compress(Bitmap.CompressFormat.JPEG,88,out))
                throw new IOException("דחיסת התמונה נכשלה");
            byte[] photo=out.toByteArray();
            if(photo.length==0||photo.length>MAX_UPLOAD)
                throw new IOException("התמונה גדולה מדי");
            return photo;
        }finally{reduced.recycle();}
    }

    private String upload(byte[] jpeg) throws Exception {
        String boundary="Kolbo"+UUID.randomUUID().toString().replace("-","");
        HttpURLConnection c=connection(origin()+"/gradio_api/upload","POST",30000);
        c.setDoOutput(true);
        c.setChunkedStreamingMode(32*1024);
        c.setRequestProperty("Content-Type","multipart/form-data; boundary="+boundary);
        String head="--"+boundary+"\r\n"+
                "Content-Disposition: form-data; name=\"files\"; filename=\"kolbo-photo.jpg\"\r\n"+
                "Content-Type: image/jpeg\r\n\r\n";
        try{
            try(OutputStream out=c.getOutputStream()){
                out.write(head.getBytes(StandardCharsets.UTF_8));
                out.write(jpeg);
                out.write(("\r\n--"+boundary+"--\r\n").getBytes(StandardCharsets.UTF_8));
            }
            JSONArray files=new JSONArray(body(c,100_000));
            String path=files.optString(0,"");
            if(path.isEmpty()||path.length()>2048||!path.startsWith("/"))
                throw new IOException("השרת לא קיבל את התמונה");
            return path;
        }finally{c.disconnect();}
    }

    private static String promptForProvider(String directedStoryboard){
        // Semantic director owns subject counts, action and outcome.
        return directedStoryboard;
    }

    private String submit(String path,String prompt,String negative,int seconds) throws Exception {
        JSONObject image=new JSONObject();
        image.put("path",path);
        image.put("orig_name","kolbo-photo.jpg");
        image.put("mime_type","image/jpeg");
        image.put("is_stream",false);
        image.put("meta",new JSONObject().put("_type","gradio.FileData"));
        JSONArray args=new JSONArray();
        String neg=negative;
        args.put(image);
        if(engine.isLightning()){
            // Exact, separately audited 16-input contract. No guesswork across providers.
            args.put(JSONObject.NULL);                  // last_image optional
            args.put(promptForProvider(prompt));        // prompt
            args.put(4);                                // lightning step budget
            args.put(neg);                              // negative prompt
            args.put((double)seconds);                  // actual requested seconds
            args.put(1.0);args.put(1.0);                // guidance scales
            args.put(42);args.put(false);               // seed and randomize
            args.put(5);                                // output quality
            args.put("UniPCMultistep");                 // scheduler
            args.put(3.0);                              // flow shift
            args.put(16);                               // 16 fps; no extra frame interpolation
            args.put(false);                            // no 30% extra GPU time
            args.put(true);                             // gr.Video output
        }else{
            args.put(promptForProvider(prompt));args.put(8);
            args.put(neg);args.put((double)seconds);
            args.put(1.0);args.put(1.0);args.put(42);args.put(false);
        }
        JSONObject payload=new JSONObject().put("data",args);
        HttpURLConnection c=connection(origin()+"/gradio_api/call/generate_video","POST",35000);
        c.setDoOutput(true);
        c.setRequestProperty("Content-Type","application/json; charset=UTF-8");
        byte[] bytes=payload.toString().getBytes(StandardCharsets.UTF_8);
        c.setFixedLengthStreamingMode(bytes.length);
        try{
            try(OutputStream out=c.getOutputStream()){out.write(bytes);}
            JSONObject response=new JSONObject(body(c,40_000));
            String id=response.optString("event_id","");
            if(!id.matches("[a-zA-Z0-9_-]{4,160}"))
                throw new IOException("לא התקבל מזהה משימה מהמנוע");
            return id;
        }finally{c.disconnect();}
    }

    private String poll(String id,Progress progress) throws Exception {
        HttpURLConnection c=connection(origin()+"/gradio_api/call/generate_video/"+id,"GET",400_000);
        try{
            int code=c.getResponseCode();
            if(code!=200)throw new IOException("קריאת תוצאת הווידאו נכשלה ("+code+")");
            String event="";
            long total=0,begin=System.currentTimeMillis();
            try(BufferedReader reader=new BufferedReader(
                new InputStreamReader(c.getInputStream(),StandardCharsets.UTF_8))){
                String line;
                while((line=reader.readLine())!=null){
                    total+=line.length();
                    if(total>MAX_JSON)throw new IOException("תשובת המנוע גדולה מדי");
                    if(System.currentTimeMillis()-begin>420_000L)
                        throw new IOException("תם זמן ההמתנה; ייתכן שהמשימה התקבלה. אין ניסיון חוזר אוטומטי.");
                    if(line.startsWith("event:"))event=line.substring(6).trim();
                    if(line.startsWith("data:")){
                        String data=line.substring(5).trim();
                        if("complete".equals(event))return extractVideoUrl(data);
                        if("error".equals(event))
                            throw new FinalProviderRejection(
                                ProviderErrorClassifier.classify(data),engine.id);
                        if("heartbeat".equals(event))progress.status("מנוע ה־AI עדיין עובד…");
                    }
                }
            }
            throw new IOException("לא התקבלה תוצאת וידאו. אין לשלוח שוב ללא בדיקה.");
        }finally{c.disconnect();}
    }

    private String extractVideoUrl(String data) throws Exception {
        JSONArray outputs=new JSONArray(data);
        // Gradio video components can return FileData under video:{...},
        // or a separate downloadable FileData item. Do not trust arbitrary
        // client URLs or off-host paths, including for the second provider.
        for(int i=0;i<Math.min(3,outputs.length());i++){
            Object current=outputs.opt(i);
            JSONObject value=current instanceof JSONObject?(JSONObject)current:null;
            if(value==null)continue;
            JSONObject nested=value.optJSONObject("video");
            JSONObject file=nested!=null?nested:value;
            String url=file.optString("url","");
            if(url.isEmpty()){
                String path=file.optString("path","");
                if(path.isEmpty()||path.length()>2048)continue;
                if(path.startsWith("/"))url=origin()+"/gradio_api/file="+path;
                else if(path.startsWith("https://"))url=path;
                else continue;
            }
            URL resolved=new URL(url);
            if(!"https".equalsIgnoreCase(resolved.getProtocol())
                ||!engine.host.equalsIgnoreCase(resolved.getHost())
                || (resolved.getPort()!=-1&&resolved.getPort()!=443)
                || resolved.getUserInfo()!=null)
                throw new IOException("מקור סרטון לא מורשה");
            return url;
        }
        throw new IOException("המנוע לא החזיר קובץ וידאו תקין");
    }

    private File download(String url, Context context,Progress progress) throws Exception {
        HttpURLConnection c=connection(url,"GET",35000);
        File result=new File(context.getCacheDir(),"kolbo-output-"+UUID.randomUUID()+".mp4");
        try{
            int code=c.getResponseCode();
            if(code!=200)throw new IOException("לא ניתן להוריד את תוצאת הווידאו");
            int size=0;
            try(InputStream in=c.getInputStream();FileOutputStream out=new FileOutputStream(result)){
                byte[] buffer=new byte[32*1024];int n;
                while((n=in.read(buffer))!=-1){
                    size+=n;
                    if(size>MAX_VIDEO)throw new IOException("הסרטון גדול מדי");
                    out.write(buffer,0,n);
                }
            }
            if(size<3000)throw new IOException("לא התקבל קובץ וידאו שלם");
            try(FileInputStream probe=new FileInputStream(result)){
                byte[] header=new byte[12];
                if(probe.read(header)!=12 || header[4]!='f'||header[5]!='t'||
                    header[6]!='y'||header[7]!='p')
                    throw new IOException("התקבל קובץ שאינו MP4 תקין");
            }
            progress.status("הסרטון התקבל — יש לבדוק שהוא תואם לבקשה");
            return result;
        }catch(Exception e){result.delete();throw e;}
        finally{c.disconnect();}
    }

    /**
     * Probe both known contracts using GET only, before any photo upload.
     * Changing engine AFTER a submitted job is forbidden.
     * A provider marked failed is skipped only for the user's next EXPLICIT job.
     */
    public void selectForNewJob(String lastFailed,boolean complexScene,Progress progress) throws Exception {
        IOException last=null;
        for(WanProviderCatalog.Engine candidate:WanProviderCatalog.order(lastFailed,complexScene)){
            engine=candidate;
            try {
                progress.status("בודק אפשרות הפקה ב־"+candidate.name+"…");
                preflight();
                progress.providerSelected(candidate.id,candidate.name);
                progress.status("מנוע נבחר: "+candidate.name+
                    ". זמינות API אינה מבטיחה GPU או מכסה פנויה.");
                return;
            }catch(Exception e){
                last=new IOException("בדיקת המנוע "+candidate.name+" נכשלה",e);
            }
        }
        throw new IOException("שני ממשקי הווידאו הציבוריים אינם זמינים או שונו. לא נשלחה תמונה.",last);
    }

    public Result create(Context context,Uri image,String hebrew,int seconds,Progress progress) throws Exception {
        if(hebrew==null||hebrew.trim().length()<2||hebrew.length()>1200)
            throw new IOException("כתוב במילים שלך מה תרצה לראות בסרטון");
        if(seconds<1||seconds>5)throw new IOException("המנוע הנוכחי תומך רק בעד 5 שניות");
        HebrewIntentBrain.Scene scene=HebrewIntentBrain.interpret(hebrew.trim());
        if(scene.soundtrack)throw new IOException("הבקשה כוללת שמע או דיבור, אך המנוע הנוכחי אילם.");
        if(scene.multiPhoto)throw new IOException("המנוע החיצוני מקבל כרגע תמונה אחת בלבד.");
        progress.status("האפליקציה הבינה: "+scene.summary);
        String english=HebrewActionTranslator.translate(scene.actionText,progress);
        V5SceneContract contract=V5SceneContract.compile(scene,english,seconds);
        String localAdvice=null;
        try {
            if(LocalBrainModelManager.isVerified(context)){
                progress.status("מוח השפה Qwen3 מתכנן את הסיפור באופן מקומי, ללא API בתשלום…");
                localAdvice=QwenScenePlanner.plan(context,english,hebrew.trim());
            }
        }catch(Exception | LinkageError e){
            // Optional model failure is not a reason to waste a GPU request,
            // and never gets silently presented as successful Qwen inference.
            progress.status("המוח המקומי לא היה זמין; משתמש בתכנון הגיבוי, ללא חיוב.");
        }
        QwenPlanContract.Result plan=QwenPlanContract.compile(contract,localAdvice);
        if(plan.requiresAudio)
            throw new IOException("הבקשה דורשת שמע או שירה; מנוע הווידאו המחובר אילם.");
        progress.status(plan.usedLocalModel ? "תוכנית הפקה נבנתה על ידי Qwen3" :
            "מוח הגיבוי מבין פעולות בסיסיות; אפשר להפעיל מודל שפה חינמי.");
        String modelInstruction=plan.prompt;
        progress.status("בודק את תמונת המקור לפני הפקה…");
        V5SourceAudit.Result source=V5SourceAudit.examine(context,image,contract.requiresNewBody);
        if(!source.safeToAttempt())
            throw new IOException(source.explanation+" לא נשלחה תמונה לשרת.");
        if(!"OK".equals(source.level)) progress.status(source.explanation);
        // An explicit user action is required for EACH new inference.
        String lastFailed=context.getSharedPreferences("gpu_provider",Context.MODE_PRIVATE)
            .getString("last_failed",null);
        selectForNewJob(lastFailed,scene.complex,progress);
        progress.status("מכין את התמונה בטלפון…");
        if(plan.cleanupRequested)progress.status("מנקה רעש ומתאים בהירות בתמונת המקור…");
        byte[] bytes=compressPhoto(context,image,plan.cleanupRequested);
        progress.status("מעלה תמונת ייחוס אחת לספק החיצוני…");
        String path=upload(bytes);
        progress.status("שולח בקשה יחידה למנוע AI…");
        progress.beforeSubmission();
        String id=submit(path,modelInstruction,plan.negatives,seconds);
        progress.jobCreated(id);
        progress.status("המשימה התקבלה, ממתין לסרטון…");
        String videoUrl=poll(id,progress);
        progress.status("מוריד סרטון AI מקורי…");
        File video=download(videoUrl,context,progress);
        return new Result(video,id,"התוצאה חייבת לעבור בדיקת קובץ, תנועה ותוכן. קרב וניצחון אינם מאומתים אוטומטית.");
    }

    public Result resume(Context context,String eventId,String selectedProvider,Progress progress) throws Exception {
        useForExistingJob(selectedProvider);
        if(eventId==null||!eventId.matches("[a-zA-Z0-9_-]{4,160}"))
            throw new IOException("מזהה משימה אינו תקין");
        String url=poll(eventId,progress);
        File video=download(url,context,progress);
        return new Result(video,eventId,"המשימה שוחזרה ללא בקשת הפקה נוספת.");
    }
}
