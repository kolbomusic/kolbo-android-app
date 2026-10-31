/* Kolbo Hebrew recognition — quantized multilingual Whisper.
 * Replaces a non-existent Hebrew-model ID. Work is performed on the SOURCE
 * WhatsApp voice, never the backing track. No fabricated transcripts.
 */
const MODEL_ID = 'onnx-community/whisper-tiny';
const RUNTIME_URL = 'https://cdn.jsdelivr.net/npm/@huggingface/transformers@3.8.1';
const CHUNK_SECONDS = 20;
const SAMPLE_RATE = 16000;
let pipelinePromise = null;

function send(id,type,extras={}) { self.postMessage({id,type,...extras}); }
function normalize(s) { return String(s||'').replace(/\s+/g,' ').trim(); }
function rms(x) {
  if (!x.length) return 0;
  let total=0;
  const stride=Math.max(1,Math.floor(x.length/48000));
  let count=0;
  for(let i=0;i<x.length;i+=stride){total+=x[i]*x[i];count++;}
  return Math.sqrt(total/Math.max(1,count));
}
async function getRecognizer(id) {
  if(!pipelinePromise){
    pipelinePromise=(async()=>{
      send(id,'stage',{label:'מאתחל מנוע תמלול עברי רב־לשוני'});
      const {pipeline,env} = await import(RUNTIME_URL);
      env.allowLocalModels=false;
      // A normal Android WebView is not cross-origin isolated; avoid WASM thread errors.
      if(env.backends?.onnx?.wasm)env.backends.onnx.wasm.numThreads=1;
      const recognizer = await pipeline('automatic-speech-recognition',MODEL_ID,{
        device:'wasm',
        dtype:'q8',
        progress_callback:p=>{
          if(p && p.status==='progress' && Number.isFinite(p.progress)){
            send(id,'model_progress',{percent:Math.min(99,Math.round(p.progress))});
          }
        }
      });
      send(id,'stage',{label:'מודל הדיבור נטען. מזהה את המילים...'});
      return recognizer;
    })().catch(e=>{pipelinePromise=null;throw e;});
  }
  return pipelinePromise;
}
self.onmessage=async event=>{
  const {id,data}=event.data||{};
  if(!id || !(data?.samples instanceof Float32Array))return;
  try{
    const samples=data.samples;
    if(data.sampleRate!==SAMPLE_RATE || samples.length<4000 || samples.length>125*SAMPLE_RATE){
      throw new Error('משך או פורמט ההקלטה אינם נתמכים לתמלול.');
    }
    if(rms(samples)<.0025){
      throw new Error('בהקלטה לא זוהה קול בעוצמה מספקת. בדוק שהיא אינה שקטה.');
    }
    const recognize=await getRecognizer(id);
    const chunks=[];
    const step=CHUNK_SECONDS*SAMPLE_RATE;
    for(let start=0;start<samples.length;start+=step){
      let segment=samples.slice(start,Math.min(samples.length,start+step));
      // Avoid excessively short final clips that trigger hallucinations.
      if(segment.length<SAMPLE_RATE*.4 && chunks.length)break;
      send(id,'stage',{label:'מזהה דיבור בעברית — קטע '+(1+Math.floor(start/step)),
                        percent:Math.min(95,Math.round(start/samples.length*100))});
      const recognized=await recognize(segment,{
        language:'hebrew',
        task:'transcribe',
        max_new_tokens:160,
        return_timestamps:false
      });
      const words=normalize(recognized?.text);
      if(words)chunks.push({start:start/SAMPLE_RATE,end:Math.min(samples.length,start+step)/SAMPLE_RATE,text:words});
    }
    const transcript=normalize(chunks.map(x=>x.text).join(' '));
    const hebrewCount=(transcript.match(/[\u0590-\u05ff]/g)||[]).length;
    if(hebrewCount<3 || transcript.split(/\s+/).filter(Boolean).length<2){
      throw new Error('הזיהוי הסתיים, אך לא הופק תמלול עברי אמין. נסה שוב או תקן ידנית.');
    }
    send(id,'done',{transcript,chunks,model:MODEL_ID,language:'hebrew'});
  }catch(error){
    const details=String(error?.message||error||'Unknown error').slice(0,360);
    const lower=details.toLowerCase();
    const category=/fetch|network|cors|404|403|failed to load|download|cdn/i.test(lower)?'NETWORK_OR_MODEL':
      /memory|alloc|oom|out of memory/i.test(lower)?'MEMORY':
      /wasm|webassembly|unsupported|operator/i.test(lower)?'RUNTIME':'TRANSCRIPTION';
    send(id,'error',{code:category,message:'לא ניתן לתמלל את ההקלטה: '+details});
  }
};
