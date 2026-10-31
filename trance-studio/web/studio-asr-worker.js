/*
 * Kolbo Hebrew ASR (experimental, on-device/browser): reads the ORIGINAL
 * WhatsApp recording. Never transcribes the music remix and never invents
 * scenes when transcription is unavailable. No paid service is required.
 *
 * The Hebrew model is itayinbar/whisper-he-12x2 (Apache 2.0, Hugging Face).
 * First use downloads around 131 MB of weights to the browser cache.
 * Phone/WebView CPU inference may be slow or unsupported: report errors.
 */
let transcriberPromise=null;
async function transcriber() {
  if(!transcriberPromise) {
    transcriberPromise=(async()=>{
      const {pipeline}=await import('https://cdn.jsdelivr.net/npm/@huggingface/transformers@4.2.0');
      return await pipeline('automatic-speech-recognition','itayinbar/whisper-he-12x2',{
        device:'wasm',
        dtype:{encoder_model:'fp16',decoder_model_merged:'fp32'},
        progress_callback:(p)=>{
          if(p&&p.status==='progress'&&typeof p.progress==='number') {
            self.postMessage({type:'model_progress',percent:Math.min(99,Math.round(p.progress))});
          }
        }
      });
    })().catch(e=>{transcriberPromise=null;throw e});
  }
  return transcriberPromise;
}
function normalize(text) {
  return String(text||'').replace(/\s+/g,' ').trim();
}
self.onmessage=async event=>{
  const {id,data}=event.data||{};
  if(!data||!id||!(data.samples instanceof Float32Array))return;
  try {
    const samples=data.samples;
    const sampleRate=data.sampleRate;
    if(sampleRate!==16000||!samples.length||samples.length>16000*125) {
      throw new Error('פורמט ההקלטה אינו נתמך לצורך תמלול');
    }
    self.postMessage({id,type:'stage',label:'מוריד/טוען מודל זיהוי דיבור בעברית'});
    const asr=await transcriber();
    const chunks=[];
    const segmentSamples=24*16000;
    for(let start=0;start<samples.length;start+=segmentSamples) {
      const end=Math.min(samples.length,start+segmentSamples);
      const segment=samples.slice(start,end);
      const position=Math.round(start/samples.length*100);
      self.postMessage({id,type:'stage',label:'מזהה מילים בהקלטה המקורית',percent:position});
      // The distilled Hebrew model is monolingual; never pass language/task
      // flags or fabricate timestamp confidence that it does not provide.
      const answer=await asr(segment,{max_new_tokens:220,return_timestamps:false});
      const spoken=normalize(answer?.text);
      if(spoken)chunks.push({start:start/16000,end:end/16000,text:spoken});
    }
    const transcript=normalize(chunks.map(s=>s.text).join('. '));
    const he=(transcript.match(/[\u0590-\u05ff]/g)||[]).length;
    if(transcript.split(/\s+/).length<2||he<3) {
      throw new Error('לא זוהה דיבור עברי מספיק ברור. יש לתקן את התמלול ידנית.');
    }
    self.postMessage({id,type:'done',transcript,chunks});
  }catch(err){
    self.postMessage({id,type:'error',message:String(err?.message||err).slice(0,500)});
  }
};