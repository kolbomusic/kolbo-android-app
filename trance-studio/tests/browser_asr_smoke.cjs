const { chromium } = require('playwright');
const fs = require('fs');

async function main(){
  const bytes=fs.readFileSync('/tmp/kolbo-hebrew-asr.f32');
  const floats=new Float32Array(bytes.buffer.slice(bytes.byteOffset,bytes.byteOffset+bytes.byteLength));
  const browser=await chromium.launch({headless:true,args:['--no-sandbox','--disable-dev-shm-usage']});
  try{
    const page=await browser.newPage();
    page.on('console',x=>console.log('BROWSER '+x.type()+': '+x.text().slice(0,240)));
    page.on('pageerror',e=>console.error('BROWSER PAGE ERROR',e.message));
    await page.goto('http://127.0.0.1:8765/studio.html',{waitUntil:'domcontentloaded'});
    const report=await page.evaluate(async sample=>{
      return await new Promise((resolve,reject)=>{
        const worker=new Worker('/studio-asr-worker.js',{type:'module'});
        let modelReady=false,events=[];
        const timer=setTimeout(()=>{worker.terminate();reject(Error('ASR worker timed out after 240s: '+JSON.stringify(events.slice(-8))))},240000);
        worker.onmessage=e=>{
          const m=e.data||{};
          events.push({type:m.type,label:m.label,code:m.code,message:m.message,percent:m.percent});
          if(m.label?.includes('מודל הדיבור נטען')||m.label?.includes('מודל הזיהוי נטען'))modelReady=true;
          if(m.type==='done'||m.type==='error'){
            clearTimeout(timer);worker.terminate();
            resolve({modelReady,outcome:m.type,transcript:m.transcript||'',error:m.message||'',code:m.code||'',events:events.slice(-12)});
          }
        };
        worker.onerror=e=>{clearTimeout(timer);worker.terminate();reject(Error('Module worker crashed: '+e.message))};
        const audio=new Float32Array(sample);
        worker.postMessage({id:'hebrew-sample',data:{samples:audio,sampleRate:16000}},[audio.buffer]);
      });
    },Array.from(floats));
    console.log('ASR_BROWSER_RESULT '+JSON.stringify(report));
    if(!report.modelReady)throw Error('Whisper model did not initialize: '+report.error);
    if(report.outcome==='error' && report.code!=='TRANSCRIPTION')
      throw Error('Model runtime, network or memory failed: '+report.error);
    if(report.outcome==='done' && !/[\u0590-\u05ff]/.test(report.transcript))
      throw Error('ASR result did not include Hebrew characters');
    console.log('ASR_BROWSER_MODEL_READY_WITH_HEBREW_DECODE_PATH');
  }finally{await browser.close()}
}
main().catch(e=>{console.error(e.stack||e);process.exitCode=1});
