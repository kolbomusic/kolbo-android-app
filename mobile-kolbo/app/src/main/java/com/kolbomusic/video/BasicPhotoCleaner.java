package com.kolbomusic.video;

import android.graphics.Bitmap;
import android.graphics.Color;

/**
 * Mild offline photo preparation before image-to-video, only if inferred from
 * the normal Hebrew request. Re-encodes no lost facial details and cannot
 * reconstruct blown highlights or correct severe motion blur.
 */
public final class BasicPhotoCleaner {
    private BasicPhotoCleaner() {}
    private static int bound(double n) {return (int)Math.max(0,Math.min(255,Math.round(n)));}

    public static Bitmap adjust(Bitmap input){
        final int width=input.getWidth(),height=input.getHeight();
        if(width<64||height<64)throw new IllegalArgumentException("small photo");
        final int count=width*height;
        if(count>1600000)throw new IllegalArgumentException("large photo");
        int[] source=new int[count],pixels=new int[count];
        input.getPixels(source,0,width,0,0,width,height);
        // Sample 10k pixels: avoid pushing already clipped whites even whiter.
        long sum=0;int overexposed=0,samples=0;
        for(int i=0;i<count;i+=Math.max(1,count/10000)){
            int p=source[i];
            int lum=(Color.red(p)*54+Color.green(p)*183+Color.blue(p)*19)>>8;
            sum+=lum;samples++;
            if(lum>=240)overexposed++;
        }
        double mean=sum/(double)Math.max(1,samples);
        double clipped=overexposed/(double)Math.max(1,samples);
        double exposure=clipped>0.22?0.88:(mean<77?1.10:1.00);
        // Light smoothing: 80% original detail, 20% 4-neighbor average.
        // Avoid sharpening/compression artifacts and preserving approximate tones.
        for(int y=0;y<height;y++){
            for(int x=0;x<width;x++){
                int idx=y*width+x;
                int original=source[idx];
                int left=source[y*width+Math.max(x-1,0)];
                int right=source[y*width+Math.min(x+1,width-1)];
                int up=source[Math.max(y-1,0)*width+x];
                int down=source[Math.min(y+1,height-1)*width+x];
                int r=bound(((Color.red(original)*0.80) +
                    (Color.red(left)+Color.red(right)+Color.red(up)+Color.red(down))*0.05)*exposure);
                int g=bound(((Color.green(original)*0.80) +
                    (Color.green(left)+Color.green(right)+Color.green(up)+Color.green(down))*0.05)*exposure);
                int blue=bound(((Color.blue(original)*0.80) +
                    (Color.blue(left)+Color.blue(right)+Color.blue(up)+Color.blue(down))*0.05)*exposure);
                pixels[idx]=Color.rgb(r,g,blue);
            }
        }
        Bitmap result=Bitmap.createBitmap(width,height,Bitmap.Config.ARGB_8888);
        result.setPixels(pixels,0,width,0,0,width,height);
        return result;
    }
}
