import test from 'node:test';
import assert from 'node:assert/strict';
import worker, {parsePlan} from '../src/index.js';

const limits={
  USER_RATE:{async limit(){return {success:true}}},
  GLOBAL_RATE:{async limit(){return {success:true}}}
};
const sample={
  action:"The person physically fights exactly two lions and defeats them.",
  camera:"Medium wide view with all three figures in the frame.",
  avoid:"Licking and friendly encounters.",
  steps:["The lions attack.","The human pushes both lions back.","The lions retreat and the human wins."],
  cleanup:true,requires_audio:false
};
test('validate dynamic output schema',()=> {
  assert.deepEqual(parsePlan(JSON.stringify(sample)),sample);
  assert.throws(()=>parsePlan(JSON.stringify({...sample,steps:[]})));
  assert.throws(()=>parsePlan('not JSON'));
});
test('no AI calls without valid consented input',async()=> {
  let calls=0;
  const env={...limits,AI:{async run(){calls++;return {response:JSON.stringify(sample)}}}};
  const req=new Request('https://sample.example/v1/plan',{method:'POST',body:JSON.stringify({
    hebrew_story:'תנקה את התמונה ואז תלחם בשני אריות',
    english_translation:'The person fights two lions and defeats both',
    schema_version:1
  })});
  const resp=await worker.fetch(req,env);
  assert.equal(resp.status,200);
  const value=await resp.json();
  assert.equal(value.plan.steps.length,3);
  assert.equal(calls,1);
  const fake=new Request('https://sample.example/v1/plan',{method:'POST',body:'{"evil":true}'});
  assert.equal((await worker.fetch(fake,env)).status,400);
  assert.equal(calls,1);
});
test('quota/provider failure never sends a second request',async()=>{
  let calls=0;
  const env={...limits,AI:{async run(){calls++;throw Error('daily limit')}}};
  const req=new Request('https://sample.example/v1/plan',{method:'POST',body:JSON.stringify({
    hebrew_story:'דמות נלחמת באריה',english_translation:'Human fights a lion',schema_version:1
  })});
  assert.equal((await worker.fetch(req,env)).status,503);
  assert.equal(calls,1);
});
test('disabled AI binding fails closed',async()=>{
 const req=new Request('https://sample.example/v1/plan',{method:'POST'});
 assert.equal((await worker.fetch(req,{})).status,503);
});

test('without limiter binding, no inference occurs',async()=>{
 let calls=0;
 const env={AI:{async run(){calls++;return {response:JSON.stringify(sample)}}}};
 const req=new Request('https://sample.example/v1/plan',{method:'POST',body:JSON.stringify({
  hebrew_story:'דמות נלחמת באריה',english_translation:'Person fights a lion',schema_version:1
 })});
 assert.equal((await worker.fetch(req,env)).status,503);
 assert.equal(calls,0);
});
test('rate limit applies before model and forbids spending free compute',async()=>{
 let calls=0;
 const env={
  USER_RATE:{async limit(){return {success:false}}},
  GLOBAL_RATE:{async limit(){return {success:true}}},
  AI:{async run(){calls++;return {response:JSON.stringify(sample)}}}
 };
 const req=new Request('https://sample.example/v1/plan',{method:'POST',body:JSON.stringify({
  hebrew_story:'דמות נלחמת באריה',english_translation:'Person fights a lion',schema_version:1
 })});
 assert.equal((await worker.fetch(req,env)).status,429);
 assert.equal(calls,0);
});
