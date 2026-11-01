self.addEventListener('fetch',function(event){
var url=new URL(event.request.url);
if(url.pathname!=='/studio/share'||event.request.method!=='POST')return;
event.respondWith((async function(){
try{
var data=await event.request.formData();
var blob=data.get('audio');
var filename=String(blob&&blob.name||'').toLowerCase();
var video=!!blob&&(String(blob.type||'').indexOf('video/')===0||/\.(mp4|webm|mov|3gp|3gpp)$/.test(filename));
var limit=video?45*1024*1024:15*1024*1024;
if(!blob||!blob.size||blob.size>limit)return Response.redirect('/studio?error=upload',303);
var name=encodeURIComponent(blob.name||'WhatsApp-voice.opus');
var cache=await caches.open('kolbo-studio-share-v1');
await cache.put('/studio/shared-audio',new Response(blob,{headers:{'content-type':blob.type||(video?'video/mp4':'audio/ogg'),'x-filename':name}}));
return Response.redirect('/studio?shared=1',303);
}catch(e){return Response.redirect('/studio?error=share',303)}
})());
});