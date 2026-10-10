package com.kolbo.videostudio;
/** Pure, testable duration acceptance policy; no fabricated frames/repeated stills. */
public final class DurationPolicy {
    private DurationPolicy(){}
    public static final int TOLERANCE_MS=500;
    public static boolean acceptable(long actualMs,int requestedSeconds) {
        if(requestedSeconds<1||requestedSeconds>60||actualMs<=0)return false;
        return Math.abs(actualMs-(requestedSeconds*1000L))<=TOLERANCE_MS;
    }
}
