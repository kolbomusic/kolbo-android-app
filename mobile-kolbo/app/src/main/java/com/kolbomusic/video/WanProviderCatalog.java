package com.kolbomusic.video;

import java.util.Arrays;
import java.util.Collections;
import java.util.List;

/** Fixed, audited, public Gradio image-to-video endpoints only.
 * No user-defined host or self-hosted billing fallback.
 * This catalog is an allowlist, NOT a guarantee of available GPU.
 */
public final class WanProviderCatalog {
    private WanProviderCatalog(){}
    public static final class Engine {
        public final String id, name, host;
        public final String[] parameters;
        Engine(String id,String name,String host,String[] args){
            this.id=id;this.name=name;this.host=host;this.parameters=args;
        }
        public String origin(){return "https://"+host;}
        public boolean isLightning(){return "lightning".equals(id);}
    }
    public static final Engine FAST=new Engine("fast","Wan מהיר",
        "zerogpu-aoti-wan2-2-fp8da-aoti-faster.hf.space",
        new String[]{"input_image","prompt","steps","negative_prompt",
            "duration_seconds","guidance_scale","guidance_scale_2",
            "seed","randomize_seed"});
    public static final Engine LIGHTNING=new Engine("lightning","Wan Lightning",
        "saravutw-wan2-2-i2v-lightning-4-8step-custom.hf.space",
        new String[]{"input_image","last_image","prompt","steps","negative_prompt",
            "duration_seconds","guidance_scale","guidance_scale_2","seed",
            "randomize_seed","quality","scheduler","flow_shift",
            "frame_multiplier","safe_mode","video_component"});
    public static final List<Engine> ALL=Collections.unmodifiableList(
        Arrays.asList(FAST,LIGHTNING));
    public static Engine byId(String id){
        for(Engine e:ALL)if(e.id.equals(id))return e;
        throw new IllegalArgumentException("Unapproved video provider");
    }
    /**
     * Called only for an explicit NEW user generation, never while polling
     * an earlier event ID. Preference after a definite provider failure is
     * to TRY a different contract first, not to increase ZeroGPU quota.
     */
    public static List<Engine> order(String lastFailed,boolean complexScene){
        // No automatic resubmission and NO assumption that either GPU is available.
        if("fast".equals(lastFailed))return Arrays.asList(LIGHTNING,FAST);
        if("lightning".equals(lastFailed))return Arrays.asList(FAST,LIGHTNING);
        // The experimental Lightning engine uses fewer diffusion steps for
        // complicated action. Only API availability, not story adherence,
        // has been verified; the user sees the chosen provider before upload.
        if(complexScene)return Arrays.asList(LIGHTNING,FAST);
        return Arrays.asList(FAST,LIGHTNING);
    }
}
