self.addEventListener('fetch',function(event){
var url=new URL(event.request.url);
if(url.pathname!=='/studio/share'||event.request.method!=='POST')return;
event.respondWith((async function(){
try{
var data=await event.request.formData();
var incoming=typeof data.getAll==='function'?data.getAll('audio'):[data.get('audio')];
incoming=incoming.filter(Boolean);
var blob=incoming[0];
var filename=String(blob&&blob.name||'').toLowerCase();
if((!blob||!blob.size)&&data.get('text')){
 var message=String(data.get('text')||'');
 var match=message.match(/https:\/\/[^\s<>]+/i);
 if(match&&match[0].length<=2048){
  var cacheLink=await caches.open('kolbo-studio-share-v1');
  await cacheLink.put('/studio/shared-link',new Response(match[0],{
   headers:{'content-type':'text/plain;charset=UTF-8'}}));
  return Response.redirect('/studio?sharedLink=1',303);
 }
}
if(!incoming.length||incoming.length>4)return Response.redirect('/studio?error=upload',303);
var total=0;
for(var i=0;i<incoming.length;i++){
 var media=incoming[i],fileName=String(media.name||'').toLowerCase();
 var isVideo=String(media.type||'').indexOf('video/')===0||/\.(mp4|webm|mov|3gp|3gpp)$/.test(fileName);
 var isAudio=String(media.type||'').indexOf('audio/')===0||
  String(media.type||'')==='application/ogg'||/\.(opus|ogg|oga|mp3|m4a|wav|flac|aac)$/.test(fileName);
 if(!isVideo&&!isAudio||!media.size||media.size>(isVideo?45:15)*1048576)
  return Response.redirect('/studio?error=upload',303);
 total+=media.size;
 if(total>60*1048576)return Response.redirect('/studio?error=upload',303);
}
var cache=await caches.open('kolbo-studio-share-v1');
await cache.put('/studio/shared-count',new Response(String(incoming.length),{headers:{'content-type':'text/plain'}}));
for(var i=0;i<incoming.length;i++){
 var media=incoming[i],fileName=String(media.name||'').toLowerCase();
 var isVideo=String(media.type||'').indexOf('video/')===0||/\.(mp4|webm|mov|3gp|3gpp)$/.test(fileName);
 var key=i?'/studio/shared-audio/'+i:'/studio/shared-audio';
 await cache.put(key,new Response(media,{headers:{
  'content-type':media.type||(isVideo?'video/mp4':'audio/ogg'),
  'x-filename':encodeURIComponent(media.name||('WhatsApp-'+(i+1)+(isVideo?'.mp4':'.opus')))
 }}));
}
return Response.redirect('/studio?shared=1',303);
}catch(e){return Response.redirect('/studio?error=share',303)}
})());
});