self.addEventListener('fetch',function(event){
var url=new URL(event.request.url);
if(url.pathname!=='/studio/share'||event.request.method!=='POST')return;
event.respondWith((async function(){
try{
var data=await event.request.formData();
var blob=data.get('audio');
if(!blob||!blob.size||blob.size>15*1024*1024)return Response.redirect('/studio?error=upload',303);
var name=encodeURIComponent(blob.name||'WhatsApp-voice.opus');
var cache=await caches.open('kolbo-studio-share-v1');
await cache.put('/studio/shared-audio',new Response(blob,{headers:{'content-type':blob.type||'audio/ogg','x-filename':name}}));
return Response.redirect('/studio?shared=1',303);
}catch(e){return Response.redirect('/studio?error=share',303)}
})());
});