package com.kolbo.videostudio;

import android.security.keystore.KeyGenParameterSpec;
import android.security.keystore.KeyProperties;
import android.util.Base64;
import org.json.JSONObject;
import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.KeyStore;
import java.security.SecureRandom;
import java.security.Signature;
import java.security.interfaces.ECPublicKey;
import java.security.spec.ECGenParameterSpec;

/**
 * No code entry, no permanent shared APK secret.
 * Public-key fingerprints require separate Render operator approval.
 * Never silently approve an arbitrary installation or create a video.
 */
final class DeviceAutoPair {
    static final String SERVER="https://kolbo-video-agnes-gateway.onrender.com";
    private static final String ALIAS="kolbo_video_owner_device_p256_v1";
    private static final SecureRandom random=new SecureRandom();
    private static String sessionToken;
    private static long expiresAtMs;
    private DeviceAutoPair(){}

    static synchronized String accessToken() throws Exception{
        if(sessionToken!=null && System.currentTimeMillis()+60000L<expiresAtMs)
            return sessionToken;
        KeyPair pair=pair();
        String pub=Base64.encodeToString(pair.getPublic().getEncoded(),Base64.NO_WRAP);
        JSONObject request=new JSONObject();request.put("public_key_b64",pub);
        JSONObject enrollment=post("/v1/device/register",request);
        if(!"approved".equals(enrollment.optString("status")))
            throw new IllegalStateException("ממתינים לאישור אוטומטי של המכשיר בשרת Kolbo Video. אין צורך להזין קוד.");
        long timestamp=System.currentTimeMillis()/1000L;
        byte[] nonceBytes=new byte[24];random.nextBytes(nonceBytes);
        String nonce=Base64.encodeToString(nonceBytes,Base64.URL_SAFE|Base64.NO_WRAP|Base64.NO_PADDING);
        byte[] message=("KOLBO-DEVICE-V1\n"+timestamp+"\n"+nonce).getBytes(StandardCharsets.US_ASCII);
        Signature signing=Signature.getInstance("SHA256withECDSA");
        signing.initSign(pair.getPrivate());signing.update(message);
        JSONObject signed=new JSONObject();
        signed.put("public_key_b64",pub);
        signed.put("timestamp",timestamp);
        signed.put("nonce",nonce);
        signed.put("signature_b64",Base64.encodeToString(signing.sign(),Base64.NO_WRAP));
        JSONObject credentials=post("/v1/device/session",signed);
        String value=credentials.optString("access_token","");
        int ttl=credentials.optInt("expires_in",0);
        if(value.length()<40 || ttl<60 || ttl>86400)
            throw new IllegalStateException("שרת Kolbo Video לא החזיר הרשאת מכשיר תקינה");
        sessionToken=value;
        expiresAtMs=System.currentTimeMillis()+ttl*1000L;
        return sessionToken;
    }
    static synchronized void invalidate(){
        sessionToken=null;expiresAtMs=0;
    }
    private static KeyPair pair() throws Exception{
        KeyStore store=KeyStore.getInstance("AndroidKeyStore");store.load(null);
        if(store.containsAlias(ALIAS)){
            KeyStore.PrivateKeyEntry stored=(KeyStore.PrivateKeyEntry)store.getEntry(ALIAS,null);
            return new KeyPair(stored.getCertificate().getPublicKey(),stored.getPrivateKey());
        }
        KeyPairGenerator gen=KeyPairGenerator.getInstance(KeyProperties.KEY_ALGORITHM_EC,"AndroidKeyStore");
        gen.initialize(new KeyGenParameterSpec.Builder(ALIAS,KeyProperties.PURPOSE_SIGN)
            .setAlgorithmParameterSpec(new ECGenParameterSpec("secp256r1"))
            .setDigests(KeyProperties.DIGEST_SHA256).build());
        return gen.generateKeyPair();
    }
    private static JSONObject post(String path,JSONObject json) throws Exception{
        HttpURLConnection conn=(HttpURLConnection)new URL(SERVER+path).openConnection();
        conn.setInstanceFollowRedirects(false);
        conn.setConnectTimeout(16000);conn.setReadTimeout(16000);
        conn.setRequestMethod("POST");conn.setDoOutput(true);
        conn.setRequestProperty("Content-Type","application/json; charset=utf-8");
        conn.setRequestProperty("Accept","application/json");
        byte[] request=json.toString().getBytes(StandardCharsets.UTF_8);
        conn.setFixedLengthStreamingMode(request.length);
        try {
            try(OutputStream output=conn.getOutputStream()){output.write(request);}
            int status=conn.getResponseCode();
            if(status<200||status>=300)
                throw new IllegalStateException(status==403
                    ?"המכשיר ממתין לאישור בשרת. אין צורך להזין קוד."
                    :"חיבור שרת Kolbo Video נכשל (HTTP "+status+")");
            try(InputStream in=conn.getInputStream()){
                ByteArrayOutputStream all=new ByteArrayOutputStream();
                byte[] b=new byte[4096];int n;
                while((n=in.read(b))!=-1){
                    if(all.size()+n>16000)throw new IllegalStateException("תגובת שרת גדולה מדי");
                    all.write(b,0,n);
                }
                return new JSONObject(new String(all.toByteArray(),StandardCharsets.UTF_8));
            }
        }finally{conn.disconnect();}
    }
}
