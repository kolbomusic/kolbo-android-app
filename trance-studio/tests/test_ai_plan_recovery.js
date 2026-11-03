'use strict';
const assert=require('node:assert/strict');
const fs=require('node:fs'),vm=require('node:vm');
const src=fs.readFileSync('trance-studio/web/studio-ai-fallback.js','utf8');
const from=src.indexOf('async function getPlan(id,passedPrompt,passedScenes){');
const to=src.indexOf('async function generate(jobId,onStage,passedPrompt,passedScenes){',from);
assert.ok(from>=0&&to>from);
let calls=0;
const scenes=[
  'Photorealistic new moving shot: האיש רץ קדימה בחצר',
  'Photorealistic distinct moving shot: הכלב קופץ ליד הדלת'
];
const env={
  MAX_SHOTS:24,
  HEBREW:/[\u0590-\u05ff]/,
  fail:message=>new Error(message),
  encodeURIComponent,
  fetch:async url=>{
    calls++;
    assert.match(url,/\/api\/jobs\/[a-f0-9]{48}\/ai-plan$/);
    return {ok:true,json:async()=>({prompts:scenes,scene_count:2})};
  },
  Number
};
vm.createContext(env);
vm.runInContext(src.slice(from,to),env);
(async()=>{
  const id='a'.repeat(48);
  const prompt='Old overall cinematic prompt: האיש רץ ואז הכלב קופץ';
  const recovered=await env.getPlan(id,prompt,[]);
  assert.equal(recovered.length,2,'server plan must win over splitting full prompt');
  assert.equal(calls,1);
  const incomplete=await env.getPlan(id,prompt,[scenes[0],'invalid']);
  assert.equal(incomplete.length,2,'partial local plan must trigger exact server recovery');
  assert.equal(calls,2);
  const alreadyValid=await env.getPlan(id,prompt,scenes);
  assert.equal(alreadyValid.length,2);
  assert.equal(calls,2,'valid complete plan needs no extra server round trip');
  env.fetch=async()=>({ok:true,json:async()=>({prompts:scenes,scene_count:3})});
  await assert.rejects(env.getPlan(id,prompt,[]),/תוכנית הסצנות אינה שלמה/);
  console.log('AI_SCENE_PLAN_RECOVERY_NO_ONE_SHOT_REPLAY_PASS');
})().catch(error=>{console.error(error);process.exitCode=1});
