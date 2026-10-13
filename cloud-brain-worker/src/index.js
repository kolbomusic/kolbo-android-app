const MODEL = "@cf/zai-org/glm-4.7-flash";
const HEADERS = {"content-type":"application/json; charset=utf-8","cache-control":"no-store"};
const MAX_BYTES=4500;

function parsePlan(raw) {
  if (typeof raw !== "string" || raw.length > 12000) throw new Error("invalid AI response");
  const first=raw.indexOf("{"),last=raw.lastIndexOf("}");
  if(first<0||last<=first)throw new Error("no JSON response");
  const p=JSON.parse(raw.slice(first,last+1));
  if(typeof p.action!=="string"||p.action.trim().length<8||p.action.length>600)
    throw new Error("invalid action");
  if(typeof p.camera!=="string"||p.camera.length>180)throw new Error("invalid camera");
  if(!Array.isArray(p.steps)||p.steps.length<1||p.steps.length>3||
     p.steps.some(x=>typeof x!=="string"||x.length<4||x.length>160))
    throw new Error("invalid scene sequence");
  return {
    action:p.action.trim(),camera:p.camera.trim(),
    avoid:typeof p.avoid==="string"?p.avoid.slice(0,250):"",
    steps:p.steps.map(x=>x.trim()),
    cleanup:p.cleanup===true,
    requires_audio:p.requires_audio===true
  };
}

export { parsePlan };

export default {
  async fetch(request,env) {
    const url=new URL(request.url);
    if(url.pathname==="/health"&&request.method==="GET")
      return new Response(JSON.stringify({service:"kolbo-cloud-story",ready:Boolean(env.AI),
        model:MODEL,version:1}),{headers:HEADERS});
    if(url.pathname!=="/v1/plan"||request.method!=="POST")
      return new Response(JSON.stringify({error:"not_found"}),{status:404,headers:HEADERS});
    if(!env.AI)return new Response(JSON.stringify({error:"ai_not_configured"}),
                                   {status:503,headers:HEADERS});
    // Never collect an image, photo or video: planning only, text under 4.5KB.
    if(Number(request.headers.get("content-length")||0)>MAX_BYTES)
      return new Response(JSON.stringify({error:"too_large"}),{status:413,headers:HEADERS});
    // Built-in edge limiters: do not expose a publicly usable free-GPU faucet.
    // Requests WITHOUT configured limiter bindings fail closed by default.
    if(!env.USER_RATE || !env.GLOBAL_RATE)
      return new Response(JSON.stringify({error:"rate_limiter_not_configured"}),
                          {status:503,headers:HEADERS});
    const originIP=(request.headers.get("cf-connecting-ip")||"unknown").slice(0,90);
    try {
      const [individual,whole] = await Promise.all([
        env.USER_RATE.limit({key:originIP}),
        env.GLOBAL_RATE.limit({key:"kolbo-story-planner"})
      ]);
      if(!individual.success || !whole.success)
        return new Response(JSON.stringify({error:"rate_limited",retry:false}),
                           {status:429,headers:HEADERS});
    } catch(_) {
      return new Response(JSON.stringify({error:"rate_limiter_unavailable"}),
                         {status:503,headers:HEADERS});
    }
    let body;
    try{
      const text=await request.text();
      if(text.length>MAX_BYTES)return new Response(JSON.stringify({error:"too_large"}),
                            {status:413,headers:HEADERS});
      body=JSON.parse(text);
      if(typeof body.hebrew_story!=="string"||
         body.hebrew_story.length<2||body.hebrew_story.length>1600||
         typeof body.english_translation!=="string"||
         body.english_translation.length<2||body.english_translation.length>3200||
         body.schema_version!==1)throw new Error("input");
    }catch(_){
      return new Response(JSON.stringify({error:"bad_request"}),{status:400,headers:HEADERS});
    }
    const instructions=[
      "You are a professional movie scene director. Interpret Hebrew or translated natural language without requiring special prompt syntax.",
      "Produce ONE JSON object only with: action (English text), camera (English text), avoid (English text), steps (array of 1 to 3 English visual beats), cleanup (boolean), requires_audio (boolean).",
      "Preserve all specified subjects and quantities, action order, physical interactions and the requested outcome. Never replace fighting with licking, petting or mere facial motions.",
      "Don't invent people, animals or plot details. The mobile app separately validates hard constraints. No markdown, no code fences."
    ].join(" ");
    try{
      const output=await env.AI.run(MODEL,{
        messages:[
          {role:"system",content:instructions},
          {role:"user",content:JSON.stringify({
            original_hebrew:body.hebrew_story,
            english_translation:body.english_translation
          })}
        ],
        stream:false,temperature:0.1,max_completion_tokens:450,
        reasoning_effort:null,chat_template_kwargs:{enable_thinking:false}
      });
      const response=typeof output?.response==="string" ? output.response
        : output?.choices?.[0]?.message?.content;
      const plan=parsePlan(response);
      return new Response(JSON.stringify({schema_version:1,plan}),{headers:HEADERS});
    }catch(_){
      // Do not expose provider errors or sensitive prompt contents.
      return new Response(JSON.stringify({error:"planner_unavailable",retry:false}),
                          {status:503,headers:HEADERS});
    }
  }
};
