package com.kolbo.videostudio;

import android.animation.ValueAnimator;
import android.content.Context;
import android.content.res.ColorStateList;
import android.graphics.Canvas;
import android.graphics.Color;
import android.graphics.LinearGradient;
import android.graphics.Paint;
import android.graphics.Shader;
import android.graphics.drawable.GradientDrawable;
import android.graphics.drawable.RippleDrawable;
import android.view.View;
import android.view.animation.LinearInterpolator;
import android.widget.Button;
import android.widget.LinearLayout;

/** Lightweight, native Android studio styling, with no external fonts/assets. */
final class StudioVisuals {
    static final int INK=0xff23183C, MUTED=0xff716985, PRIMARY=0xff6825D0,
            SECONDARY=0xff28B9B5, SURFACE=0xffffffff, BG=0xffF5F2FA,
            STROKE=0xffEAE3F3, ERROR=0xffB3263E;
    private StudioVisuals(){}
    static int px(Context context,int dp) {
        return Math.round(dp*context.getResources().getDisplayMetrics().density);
    }
    static GradientDrawable round(int color,int radiusPx) {
        GradientDrawable d=new GradientDrawable();
        d.setColor(color);d.setCornerRadius(radiusPx);return d;
    }
    static GradientDrawable outline(int color,int radiusPx,int stroke,int strokeWidth) {
        GradientDrawable d=round(color,radiusPx);d.setStroke(strokeWidth,stroke);return d;
    }
    static void card(LinearLayout layout,Context c) {
        layout.setPadding(px(c,17),px(c,14),px(c,17),px(c,15));
        layout.setBackground(outline(SURFACE,px(c,22),STROKE,px(c,1)));
        layout.setElevation(px(c,2));
    }
    static void action(Button b,Context c,boolean primary){
        b.setAllCaps(false);
        b.setTextSize(16);
        b.setTextColor(primary?Color.WHITE:INK);
        b.setMinHeight(px(c,52));
        b.setPadding(px(c,14),px(c,10),px(c,14),px(c,10));
        GradientDrawable bg;
        if(primary){
            bg=new GradientDrawable(GradientDrawable.Orientation.TL_BR,
                new int[]{0xff7B39EB,PRIMARY,0xff4D15A4});
            bg.setCornerRadius(px(c,17));
            b.setElevation(px(c,4));
        }else {
            bg=outline(0xffF0EBF8,px(c,17),0xffDED4ED,px(c,1));
            b.setElevation(0);
        }
        b.setBackground(new RippleDrawable(ColorStateList.valueOf(
            primary?0x66FFFFFF:0x226825D0),bg,null));
        b.setContentDescription(b.getText());
    }
    static LinearLayout.LayoutParams spaced(Context c,int height,int top){
        LinearLayout.LayoutParams p=new LinearLayout.LayoutParams(-1,height<0?height:px(c,height));
        p.topMargin=px(c,top);
        return p;
    }
    static final class AmbientMotionView extends View {
        private final Paint paint=new Paint(Paint.ANTI_ALIAS_FLAG);
        private ValueAnimator animator;
        private float phase=0;
        AmbientMotionView(Context c){
            super(c);
            setContentDescription("אנימציית אור עדינה בזמן יצירת הסרטון");
            setImportantForAccessibility(IMPORTANT_FOR_ACCESSIBILITY_NO);
        }
        void start(){
            if(animator!=null&&animator.isRunning())return;
            if(!ValueAnimator.areAnimatorsEnabled()){phase=0.5f;invalidate();return;}
            animator=ValueAnimator.ofFloat(0f,1f);
            animator.setDuration(3200);
            animator.setRepeatCount(ValueAnimator.INFINITE);
            animator.setInterpolator(new LinearInterpolator());
            animator.addUpdateListener(a->{phase=(Float)a.getAnimatedValue();invalidate();});
            animator.start();
        }
        void stop(){
            if(animator!=null){animator.cancel();animator=null;}
            phase=0;invalidate();
        }
        @Override protected void onDraw(Canvas canvas){
            super.onDraw(canvas);
            final float density=getResources().getDisplayMetrics().density;
            float w=getWidth(),h=getHeight(),x=w*0.5f,y=h*0.50f;
            float t=phase*(float)(Math.PI*2);
            float breathing=(float)Math.sin(t);
            paint.setShader(null);
            for(int i=3;i>=0;i--){
                float rad=(32f+i*16f+3f*breathing)*density;
                int alpha=Math.max(5,37-i*9);
                paint.setColor(Color.argb(alpha,104,37,208));
                canvas.drawCircle(x,y,rad,paint);
            }
            int[] colors={PRIMARY,SECONDARY,0xffF4A943};
            for(int i=0;i<3;i++){
                float a=t+i*(float)(2*Math.PI/3);
                float radius=(23+4*(float)Math.sin(t+i))*density;
                float ox=x+(float)Math.cos(a)*radius;
                float oy=y+(float)Math.sin(a)*radius*0.57f;
                float circle=(10f+(float)Math.sin(t+i)*1.5f)*density;
                paint.setShader(new LinearGradient(ox-circle,oy-circle,ox+circle,oy+circle,
                    new int[]{0xCCFFFFFF,colors[i]},null,Shader.TileMode.CLAMP));
                canvas.drawCircle(ox,oy,circle,paint);
            }
            paint.setShader(null);
            paint.setColor(0xffFFFFFF);
            canvas.drawCircle(x,y,7*density,paint);
        }
        @Override protected void onDetachedFromWindow(){
            stop();super.onDetachedFromWindow();
        }
    }
}
