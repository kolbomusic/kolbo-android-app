package com.kolbomusic.video;

public final class WanProviderCatalogTest {
    private static int count=0;
    private static void ok(boolean condition,String reason){
        count++;if(!condition)throw new AssertionError(reason);
    }
    public static void main(String[] args){
        ok(WanProviderCatalog.ALL.size()==2,"two allowlisted providers");
        ok(WanProviderCatalog.FAST.parameters.length==9,"original 9-parameter contract");
        ok(WanProviderCatalog.LIGHTNING.parameters.length==16,"lightning 16-parameter contract");
        ok(WanProviderCatalog.FAST.host.endsWith(".hf.space"),"fast is public HF Space");
        ok(WanProviderCatalog.LIGHTNING.host.endsWith(".hf.space"),"lightning public HF Space");
        ok(WanProviderCatalog.FAST.origin().startsWith("https://"),"TLS fast");
        ok(WanProviderCatalog.LIGHTNING.origin().startsWith("https://"),"TLS lightning");
        ok(WanProviderCatalog.order(null,false).get(0)==WanProviderCatalog.FAST,
            "simple task prioritizes verified fast video engine");
        ok(WanProviderCatalog.order(null,true).get(0)==WanProviderCatalog.LIGHTNING,
            "complex action can choose lower step engine first");
        ok(WanProviderCatalog.order("fast",false).get(0)==WanProviderCatalog.LIGHTNING,
            "next user action may prefer alternate after previous fast failure");
        ok(WanProviderCatalog.order("lightning",true).get(0)==WanProviderCatalog.FAST,
            "next user action may prefer fast after lightning failure");
        ok(WanProviderCatalog.order("other",false).get(0)==WanProviderCatalog.FAST,
            "unknown marker cannot select another arbitrary host");
        try{
            WanProviderCatalog.byId("https://attacker.invalid/");
            throw new AssertionError("Untrusted URL accepted");
        }catch(IllegalArgumentException expected){count++;}
        ok(WanProviderCatalog.byId("fast")==WanProviderCatalog.FAST,"resolve fast");
        ok(WanProviderCatalog.byId("lightning")==WanProviderCatalog.LIGHTNING,
           "resolve lightning");
        ok("last_image".equals(WanProviderCatalog.LIGHTNING.parameters[1]),
           "second input must be explicitly null when not provided");
        ok("video_component".equals(WanProviderCatalog.LIGHTNING.parameters[15]),
           "video output has distinct schema");
        System.out.println("PASS: "+count+" GPU routing, identity and API-contract checks");
    }
}
