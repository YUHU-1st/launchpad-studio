// Real Android WebView UI smoke test; credentials never enter command lines/output.
import fs from "node:fs";
const config=JSON.parse(fs.readFileSync("build/vj-ui-test/data/settings.json","utf8"));
const pages=await fetch("http://127.0.0.1:9222/json").then(r=>r.json());
if(pages.length!==1)throw Error("Expected one RC Plus WebView");
const socket=new WebSocket(pages[0].webSocketDebuggerUrl);
await new Promise((resolve,reject)=>{socket.onopen=resolve;socket.onerror=reject;});
let id=0;const pending=new Map();
socket.onmessage=event=>{const message=JSON.parse(event.data);const handler=pending.get(message.id);if(handler){pending.delete(message.id);handler(message);}};
async function call(method,params={}){
  const next=++id;
  const reply=new Promise((resolve,reject)=>{const timer=setTimeout(()=>reject(Error(`${method} timeout`)),25000);pending.set(next,result=>{clearTimeout(timer);resolve(result);});});
  socket.send(JSON.stringify({id:next,method,params}));const response=await reply;
  if(response.error||response.result?.exceptionDetails)throw Error(`${method} failed`);
  return response.result;
}
async function evaluate(expression){return (await call("Runtime.evaluate",{expression,awaitPromise:true,returnByValue:true})).result?.value;}
const originalUrl=pages[0].url,originalPin=await evaluate("localStorage.getItem('launchpadPin')");
try{
  await call("Page.navigate",{url:`http://192.168.10.7:8767/?token=${encodeURIComponent(config.remote.pin)}`});
  await new Promise(resolve=>setTimeout(resolve,1800));
  const result=await evaluate(`(async()=>{
    async function until(predicate){for(let i=0;i<80;i++){if(predicate())return;await new Promise(r=>setTimeout(r,150));}throw Error('Expected VJ state not reached');}
    await until(()=>state?.app_version==='2.2.0'&&state?.vj?.devices?.length>0);
    $('vj-start').closest('.card').scrollIntoView();
    if($('vj-style').options.length!==9)throw Error('Missing VJ styles');
    const check=$('vj-alpha');check.checked=true;check.dispatchEvent(new Event('change'));
    await new Promise(r=>setTimeout(r,650));if(!check.checked)throw Error('Draft reset by live state');
    $('vj-width').value=1280;$('vj-height').value=720;$('vj-preview').checked=true;$('vj-map_launchpad').checked=true;
    const target=$('vj-screens').querySelector('input');if(target){target.checked=true;target.dispatchEvent(new Event('change'));}
    $('vj-apply').click();await until(()=>state.vj.config.alpha&&state.vj.config.map_launchpad);
    $('vj-start').click();await until(()=>state.vj.state.running&&state.vj.state.fps>10);
    const fps=state.vj.state.fps,windows=state.vj.state.windows;
    check.checked=false;check.dispatchEvent(new Event('change'));await new Promise(r=>setTimeout(r,650));
    if(check.checked)throw Error('Alpha draft lost');$('vj-apply').click();await until(()=>!state.vj.config.alpha);
    $('vj-stop').click();await until(()=>!state.vj.state.running);
    ws.close();await until(()=>ws?.readyState===WebSocket.OPEN);
    return {version:state.app_version,styles:$('vj-style').options.length-1,fps,windows,draftPreserved:true,reconnected:true,userAgent:navigator.userAgent};
  })()`);
  if(!result)throw Error("WebView did not return the test result");
  fs.writeFileSync("build/vj-rcplus-result.json",JSON.stringify(result,null,2));console.log(JSON.stringify(result,null,2));
}finally{
  await evaluate(`localStorage.${originalPin===null?"removeItem('launchpadPin')":`setItem('launchpadPin',${JSON.stringify(originalPin)})`}`);
  await call("Page.navigate",{url:originalUrl});socket.close();
}
