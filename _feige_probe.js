/* Feige in-page send-handle probe — drop-in for ECAN_FEIGE_PROBE_JS_FILE so the
 * send-discovery can iterate WITHOUT an app rebuild. Identical to the default
 * baked into event_monitor.py; edit this + point ECAN_FEIGE_PROBE_JS_FILE at it +
 * restart to try a new variant.
 *
 * READ-mostly: enumerates chatd / pigeon event bus, and installs a DEFENSIVE
 * send-tracer (always calls through to the original; logging is in a swallowed
 * try/catch so it can never block a real send). The +25s probe round installs
 * it; the +70s round returns window.__ecan_send_trace — i.e. exactly which fn
 * fired (and its args) when the bot/human sent a reply. */
(function(){var o={sendCandidates:[],deep:[],sendTrace:[],reactRoot:false,error:null};try{
 var roots=['chatd','__mona_pigeon_event','__WORKBENCH_EVENT_SDK_IN_WINDOW__','pigeon','__pigeon','imSdk','im','PigeonIM'];
 function mem(v){var m=[];try{for(var p in v){try{if(/send|message|emit|dispatch|sdk|conn|socket|reply|post/i.test(p))m.push(p+':'+(typeof v[p]));}catch(e){}}}catch(e){}return m.slice(0,40);}
 for(var i=0;i<roots.length;i++){var k=roots[i];var v;try{v=window[k];}catch(e){continue;}if(!v)continue;
  o.deep.push({root:k,type:(typeof v),members:mem(v)});
  try{for(var p in v){try{var sv=v[p];if(sv&&(typeof sv==='object'||typeof sv==='function')){var mm=mem(sv);if(mm.length)o.sendCandidates.push({path:k+'.'+p,members:mm});}}catch(e){}}}catch(e){}}
 o.reactRoot=!!document.querySelector('#root,[data-reactroot]');
 if(!window.__ecan_send_trace)window.__ecan_send_trace=[];
 function wrap(obj,name,label){try{var orig=obj[name];if(typeof orig!=='function'||orig.__ecanw)return;var w=function(){try{var a=[];for(var i=0;i<Math.min(arguments.length,3);i++){var x=arguments[i];try{a.push(typeof x==='object'?JSON.stringify(x).slice(0,300):String(x).slice(0,200));}catch(e){a.push('['+(typeof x)+']');}}window.__ecan_send_trace.push({fn:label,args:a});}catch(e){}return orig.apply(this,arguments);};w.__ecanw=true;obj[name]=w;}catch(e){}}
 for(var i=0;i<roots.length;i++){var k=roots[i];var v;try{v=window[k];}catch(e){continue;}if(!v)continue;try{for(var p in v){try{if(/^(send|sendMessage|sendMsg|sendText|emit|emitByApp|emitByPlugin|reply|postMessage)$/i.test(p)&&typeof v[p]==='function')wrap(v,p,k+'.'+p);}catch(e){}}}catch(e){}}
 o.sendTrace=(window.__ecan_send_trace||[]).slice(-20);
}catch(e){o.error=String(e);}return JSON.stringify(o);})()
