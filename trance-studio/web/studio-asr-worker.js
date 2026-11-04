/* Kolbo Hebrew recognition — quantized multilingual Whisper.
 * Replaces a non-existent Hebrew-model ID. Work is performed on the SOURCE
 * WhatsApp voice, never the backing track. No fabricated transcripts.
 */
const MODEL_IDS = ['onnx-community/whisper-base','onnx-community/whisper-tiny'];
const RUNTIME_URL = 'https://cdn.jsdelivr.net/npm/@huggingface/transformers@3.8.1';
const CHUNK_SECONDS = 20;
const SAMPLE_RATE = 16000;
let pipelinePromise = null;
let loadedModel = '';
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
async function createRecognizer(id,modelIndex=0){
  const modelID=MODEL_IDS[modelIndex];
  send(id,'stage',{label:modelIndex===0?
    'מאתחל זיהוי דיבור עברי מדויק יותר מתוך ההקלטה המקורית':
    'מנוע הזיהוי הראשי אינו זמין; עובר למודל חינמי קל יותר'});
  const {pipeline,env} = await import(RUNTIME_URL);
  env.allowLocalModels=false;
  if(env.backends?.onnx?.wasm)env.backends.onnx.wasm.numThreads=1;
  const recognizer=await pipeline('automatic-speech-recognition',modelID,{
    device:'wasm',dtype:'q8',
    progress_callback:p=>{
      if(p && p.status==='progress' && Number.isFinite(p.progress)){
        send(id,'model_progress',{percent:Math.min(99,Math.round(p.progress))});
      }
    }
  });
  loadedModel=modelID;
  send(id,'stage',{label:'מודל הזיהוי נטען. מפענח דיבור מהקובץ המקורי...'});
  return recognizer;
}
async function getRecognizer(id) {
  if(!pipelinePromise){
    pipelinePromise=(async()=>{
      try{return await createRecognizer(id,0)}
      catch(firstError){
        send(id,'stage',{label:'עובר למנוע תמלול חלופי, ללא צורך באישור'});
        return await createRecognizer(id,1);
      }
    })().catch(e=>{pipelinePromise=null;throw e});
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
    let recognize=await getRecognizer(id);
    async function recognizeAll(model) {
      const found=[];
      const timed=[];
      const step=CHUNK_SECONDS*SAMPLE_RATE;
      for(let start=0;start<samples.length;start+=step){
        const segment=samples.slice(start,Math.min(samples.length,start+step));
        if(segment.length<SAMPLE_RATE*.4 && found.length)break;
        send(id,'stage',{label:'מזהה דיבור בעברית מתוך קובץ המקור — קטע '+
           (1+Math.floor(start/step)),percent:Math.min(95,Math.round(start/samples.length*100))});
        let result;
        // Transformers.js 3.8 supports per-word Whisper timestamps. They
        // place comic edits at the real utterance instead of assuming the
        // text occupies the entire recording at a constant speed.
        // Fallback to transcription-only on unsupported WASM/runtime paths.
        try{
          result=await model(segment,{
            language:'hebrew',task:'transcribe',
            max_new_tokens:160,return_timestamps:'word'
          });
        }catch(timestampError){
          send(id,'stage',{label:'זיהוי זמני מילים אינו נתמך במכשיר; ממשיך בתמלול רגיל'});
          result=await model(segment,{
            language:'hebrew',task:'transcribe',
            max_new_tokens:160,return_timestamps:false
          });
        }
        const words=normalize(result?.text);
        if(words)found.push({start:start/SAMPLE_RATE,
          end:Math.min(samples.length,start+step)/SAMPLE_RATE,text:words});
        // Only actual model timestamps, never estimated word positions.
        for(const entry of Array.isArray(result?.chunks)?result.chunks:[]){
          const pair=entry?.timestamp;
          const text=normalize(entry?.text).slice(0,80);
          if(!Array.isArray(pair)||pair.length!==2||!text)continue;
          const a=Number(pair[0]),b=Number(pair[1]);
          if(!Number.isFinite(a)||!Number.isFinite(b)||
             a<0||b<=a||b>segment.length/SAMPLE_RATE+.25)continue;
          if(timed.length>=1200)break;
          timed.push({start:Math.round((start/SAMPLE_RATE+a)*1000)/1000,
                      end:Math.round((start/SAMPLE_RATE+b)*1000)/1000,
                      text:text});
        }
      }
      return {chunks:found,word_timeline:timed};
    }
    let recognized;
    try{
      recognized=await recognizeAll(recognize);
    }catch(primaryError){
      if(loadedModel!==MODEL_IDS[0])throw primaryError;
      send(id,'stage',{label:'מנוע התמלול הראשי נכשל במהלך העיבוד; מנסה מנוע חלופי'});
      pipelinePromise=null;
      recognize=await createRecognizer(id,1);
      pipelinePromise=Promise.resolve(recognize);
      recognized=await recognizeAll(recognize);
    }
    let chunks=recognized.chunks;
    let wordTimeline=recognized.word_timeline;
    let transcript=normalize(chunks.map(x=>x.text).join(' '));
    let hebrewCount=(transcript.match(/[\u0590-\u05ff]/g)||[]).length;
    if((hebrewCount<3 || transcript.split(/\s+/).filter(Boolean).length<2)
       && loadedModel===MODEL_IDS[0]){
      send(id,'stage',{label:'לא זוהו מילים בעברית באופן מספק; מנסה תמלול חלופי אוטומטי'});
      pipelinePromise=null;
      recognize=await createRecognizer(id,1);
      pipelinePromise=Promise.resolve(recognize);
      recognized=await recognizeAll(recognize);
      chunks=recognized.chunks;
      wordTimeline=recognized.word_timeline;
      transcript=normalize(chunks.map(x=>x.text).join(' '));
      hebrewCount=(transcript.match(/[\u0590-\u05ff]/g)||[]).length;
    }
    if(hebrewCount<3 || transcript.split(/\s+/).filter(Boolean).length<2){
      throw new Error('שני מנועי התמלול לא זיהו מספיק מילים בעברית מתוך ההקלטה המקורית.');
    }
    send(id,'done',{transcript,chunks,
      word_timeline:wordTimeline,model:loadedModel,language:'hebrew'});
  }catch(error){
    const details=String(error?.message||error||'Unknown error').slice(0,360);
    const lower=details.toLowerCase();
    const category=/fetch|network|cors|404|403|failed to load|download|cdn/i.test(lower)?'NETWORK_OR_MODEL':
      /memory|alloc|oom|out of memory/i.test(lower)?'MEMORY':
      /wasm|webassembly|unsupported|operator/i.test(lower)?'RUNTIME':'TRANSCRIPTION';
    send(id,'error',{code:category,message:'לא ניתן לתמלל את ההקלטה: '+details});
  }
};
