/* Exact asset hashes, finite sizes, no remote CDN and no persistent client data. */
'use strict';
window.DoomXZ=(()=>{
 const pins=__ASSET_PINS__;
 const hex=b=>Array.from(new Uint8Array(b),x=>x.toString(16).padStart(2,'0')).join('');
 async function hash(bytes){return hex(await crypto.subtle.digest('SHA-256',bytes));}
 async function download(name){
  const pin=pins[name];if(!pin)throw Error('Unknown game asset');
  const abort=new AbortController(),timer=setTimeout(()=>abort.abort(),30000);
  let compressed;
  try{
   const response=await fetch('/Doom/'+name+'.xz',{credentials:'omit',cache:'no-store',signal:abort.signal});
   if(!response.ok)throw Error('Game asset request failed');
   const reader=response.body.getReader(),chunks=[];let size=0;
   while(true){const {done,value}=await reader.read();if(done)break;size+=value.byteLength;if(size>pin.compressedBytes){await reader.cancel();throw Error('Game asset exceeds expected size');}chunks.push(value.slice());}
   if(size!==pin.compressedBytes)throw Error('Truncated game asset');
   compressed=new Uint8Array(size);let offset=0;for(const chunk of chunks){compressed.set(chunk,offset);offset+=chunk.byteLength;}
  }finally{clearTimeout(timer);}
  if(await hash(compressed)!==pin.compressedSha256)throw Error('Compressed game asset integrity failed');
  const stream=new xzwasm.XzReadableStream(new Response(compressed).body),reader=stream.getReader();
  const result=new Uint8Array(pin.bytes);let size=0;
  try{
   while(true){const {done,value}=await reader.read();if(done)break;if(size+value.byteLength>pin.bytes)throw Error('Decoded game asset exceeds expected size');result.set(value,size);size+=value.byteLength;}
  }catch(e){await reader.cancel().catch(()=>{});throw e;}
  if(size!==pin.bytes||await hash(result)!==pin.sha256)throw Error('Decoded game asset integrity failed');
  (window.__DOOM_XZ_ASSETS__??=[]).push({name,compressedBytes:compressed.byteLength,decodedBytes:result.byteLength,sha256:pin.sha256});
  return result;
 }
 return {download};
})();
