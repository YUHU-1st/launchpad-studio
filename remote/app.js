const $ = (id) => document.getElementById(id);
const rates = ["0.50×","0.75×","1.00×","1.25×","1.50×","2.00×","3.00×"];
const loops = ["不循环","单曲循环","列表循环"];
const videoEffects = ["原色视频","亮度热图","边缘轮廓","单色辉光","镜像万花筒","像素故障"];
const visualStyles = ["频谱","对称频谱","波形","脉冲","涟漪","星云","雨幕","火焰","隧道","棋盘"];
const macroActions = ["热键","输入文字","打开文件/程序","打开网址","执行命令","PowerShell","媒体控制","按键序列","鼠标操作","系统操作","设置音量","组合动作"];
let token = new URLSearchParams(location.search).get("token") || localStorage.getItem("launchpadPin") || "";
let ws = null, state = null, reconnectTimer = null, selectedMacro = null, lyricsKey = "";
const dragging = new Set();

function options(el, values, selected, labelKey=null, valueKey=null) {
  const signature = JSON.stringify(values);
  if (el.dataset.signature !== signature) {
    el.innerHTML = "";
    values.forEach((item, index) => {
      const opt = document.createElement("option");
      opt.value = valueKey ? item[valueKey] : (typeof item === "object" ? index : item);
      opt.textContent = labelKey ? item[labelKey] : item;
      el.appendChild(opt);
    });
    el.dataset.signature = signature;
  }
  if (selected !== undefined && selected !== null && document.activeElement !== el) el.value = String(selected);
}

function formatTime(seconds) {
  const s = Math.max(0, Math.floor(Number(seconds) || 0));
  return `${String(Math.floor(s/60)).padStart(2,"0")}:${String(s%60).padStart(2,"0")}`;
}

function command(action, value=null) {
  if (ws && ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify({type:"command", action, value}));
}

function connect() {
  if (!token) { $("pair").classList.remove("hidden"); return; }
  clearTimeout(reconnectTimer);
  const scheme = location.protocol === "https:" ? "wss" : "ws";
  ws = new WebSocket(`${scheme}://${location.host}/ws?token=${encodeURIComponent(token)}`);
  ws.onopen = () => {
    $("connection").textContent = "已连接"; $("connection").className = "status online";
    $("pair").classList.add("hidden"); localStorage.setItem("launchpadPin", token);
  };
  ws.onmessage = (event) => {
    const message = JSON.parse(event.data);
    if (message.state) { state = message.state; render(); }
  };
  ws.onclose = () => {
    $("connection").textContent = "重连中"; $("connection").className = "status offline";
    reconnectTimer = setTimeout(connect, 1500);
  };
  ws.onerror = () => ws.close();
}

function bindRange(id, action, transform=Number, delay=70) {
  let timer = null; const el = $(id);
  el.addEventListener("pointerdown", () => dragging.add(id));
  el.addEventListener("pointerup", () => dragging.delete(id));
  el.addEventListener("input", () => { clearTimeout(timer); timer = setTimeout(() => command(action, transform(el.value)), delay); });
  el.addEventListener("change", () => { dragging.delete(id); command(action, transform(el.value)); });
}

function setRange(id, value, max=null) {
  const el=$(id); if (max !== null) el.max = Math.max(.1, Number(max) || .1);
  if (!dragging.has(id)) el.value = Number(value) || 0;
}

function fillParams(hostId, mode, detail, specs) {
  const host=$(hostId);
  if (!host.dataset.ready) {
    specs.forEach(([key,label,min,max,step]) => {
      const row=document.createElement("label"); row.textContent=label;
      const value=document.createElement("b"); value.id=`${hostId}-${key}-value`; row.appendChild(value);
      const input=document.createElement("input"); input.type="range"; input.min=min; input.max=max; input.step=step; input.id=`${hostId}-${key}`;
      input.addEventListener("input",()=>{ value.textContent=input.value; command(`${mode}.param`,{[key]:Number(input.value)}); });
      row.appendChild(input); host.appendChild(row);
    });
    host.dataset.ready="1";
  }
  specs.forEach(([key]) => {
    const input=$(`${hostId}-${key}`); const value=$(`${hostId}-${key}-value`);
    if (input && document.activeElement!==input && detail[key]!==undefined) input.value=detail[key];
    if (input && value) value.textContent=input.value;
  });
}

function renderPreset(hostId, mode, names) {
  const host=$(hostId);
  if (!host.dataset.ready) {
    host.innerHTML=`<select class="preset-select"></select><input class="preset-name" placeholder="新预设名"><button class="preset-load">加载</button><button class="preset-save">保存</button>`;
    host.querySelector(".preset-load").onclick=()=>command("preset.load",{mode,name:host.querySelector(".preset-select").value});
    host.querySelector(".preset-save").onclick=()=>{const name=host.querySelector(".preset-name").value.trim();if(name)command("preset.save",{mode,name});};
    host.dataset.ready="1";
  }
  options(host.querySelector(".preset-select"), names, host.querySelector(".preset-select").value, null, null);
}

function renderStudio() {
  const g=state.global||{}, lp=state.launchpad||{}, perf=state.performance||{};
  $("active-mode").textContent=state.active_mode || state.mode || "空闲"; $("app-status").textContent=state.status||"";
  $("device-chip").textContent=lp.connected?`${lp.model} 已连接`:"Launchpad 未连接";
  options($("palette"),g.palettes||[],g.palette,null,null); setRange("brightness",g.brightness||85); $("brightness-label").textContent=`${Math.round(g.brightness||0)}%`;
  if(document.activeElement!==$("custom-color"))$("custom-color").value=g.custom_color||"#7c5cff"; $("macro-control").checked=!!g.macro_control;
  const metrics=["CPU","RAM","GPU","磁盘","网络 MB/s","磁盘 MB/s"];
  $("perf-grid").innerHTML=metrics.map(k=>`<div class="metric"><small>${k}</small><strong>${perf[k]==null?"--":Number(perf[k]).toFixed(1)+(k.includes("MB/s")?"":"%")}</strong></div>`).join("");
  renderVideo(); renderMusic(); renderLive(); renderUtility();
}

function renderVideo() {
  const v=state.video||{}, d=v.detail||{};
  options($("video-playlist"),(v.playlist||[]).map((name,index)=>({name,index})),v.index,"name","index"); setRange("video-progress",v.position,v.duration);
  $("video-time").textContent=formatTime(v.position); $("video-duration").textContent=formatTime(v.duration); $("video-state").textContent=v.running?(v.paused?"暂停":"播放中"):"停止";
  $("video-play").textContent=v.running?(v.paused?"继续":"暂停"):"播放";
  options($("video-rate"),rates,d.rate??"1.00×",null,null); options($("video-loop"),loops,d.loop??"列表循环",null,null); options($("video-effect"),videoEffects,d.effect??"原色视频",null,null);
  if(document.activeElement!==$("video-fps"))$("video-fps").value=d.fps??20; $("video-fps-label").textContent=`${Math.round(d.fps??20)}`;
  fillParams("video-params","video",d,[["saturation","饱和度",0,2,.05],["contrast","对比度",.2,2.5,.05],["gamma","伽马",.25,2.5,.05],["edge_threshold","边缘阈值",10,180,1]]);
  renderPreset("video-presets","video",state.presets?.video||[]);
}

function renderMusic() {
  const m=state.music||{}, d=m.detail||{}, a=m.analysis||{};
  options($("music-playlist"),(m.playlist||[]).map((name,index)=>({name,index})),m.index,"name","index"); setRange("music-progress",m.position,m.duration);
  $("music-time").textContent=formatTime(m.position); $("music-duration").textContent=formatTime(m.duration); $("music-state").textContent=m.running?(m.paused?"暂停":"播放中"):"停止"; $("music-play").textContent=m.running?(m.paused?"继续":"暂停"):"播放";
  $("music-analysis").textContent=a.bpm?`BPM ${a.bpm} · ${a.mood||"--"} · ${a.genre||"--"} · 能量 ${Math.round((a.energy||0)*100)}%`:"BPM -- · 情绪 -- · 能量 --";
  options($("music-style"),visualStyles,d.style??"频谱",null,null); options($("music-rate"),rates,d.rate??"1.00×",null,null); options($("music-loop"),loops,d.loop??"列表循环",null,null);
  setRange("music-volume",d.volume??85); $("music-volume-label").textContent=`${Math.round(d.volume??85)}%`;
  fillParams("music-params","music",d,visualParamSpecs()); renderPreset("music-presets","music",state.presets?.music||[]);
}

function visualParamSpecs(){return [["freq_min","频谱下限 Hz",20,1000,10],["freq_max","频谱上限 Hz",1000,22000,100],["loud_min","响度下限 dB",-80,-20,1],["loud_max","响度上限 dB",-30,0,1],["sensitivity","灵敏度",.1,4,.05],["threshold","噪声阈值",0,.2,.002],["speed","动画速度",.2,3,.05],["spread","扩散强度",.3,2.5,.05]];}

function renderLive() {
  const l=state.live||{}, d=l.detail||{}; $("live-state").textContent=l.running?"运行中":"停止";
  options($("live-device"),l.devices||[],l.devices?.findIndex(x=>x.name===l.selected),"name",null); options($("live-style"),visualStyles,d.style??"星云",null,null);
  fillParams("live-params","live",d,visualParamSpecs()); renderPreset("live-presets","live",state.presets?.live||[]);
}

function renderUtility() {
  const u=state.utilities||{}; options($("utility-choice"),u.allowed||[],u.selected,null,null); $("utility-state").textContent=u.running?"运行中":"停止";
  if(document.activeElement!==$("weather-city"))$("weather-city").value=u.weather_city||""; if(document.activeElement!==$("focus-minutes"))$("focus-minutes").value=u.focus_minutes||25;
  $("focus-remaining").textContent=formatTime(u.focus_remaining||u.focus_minutes*60||0); $("weather-options").classList.toggle("hidden",u.selected!=="天气"); $("focus-options").classList.toggle("hidden",u.selected!=="专注计时器");
}

function renderMedia() {
  const m=state.system_media||{}, audio=m.audio||{}, controls=m.controls||{};
  $("media-app").textContent=m.app||"Windows 媒体"; $("media-title").textContent=m.title||"没有正在播放的媒体";
  $("media-artist").textContent=m.artist||"打开网易云音乐、PotPlayer、AIMP 等播放器"; $("media-album").textContent=m.album||m.subtitle||"";
  $("lyric-current").textContent=m.lyric_line||"—"; $("lyric-next").textContent=m.lyric_next||"";
  $("cover").src=m.cover_id?`/api/cover/${encodeURIComponent(m.cover_id)}?token=${encodeURIComponent(token)}`:"";
  setRange("system-progress",m.position,m.duration); $("system-progress").disabled=!m.can_seek; $("system-time").textContent=formatTime(m.position); $("system-duration").textContent=formatTime(m.duration);
  $("media-play").textContent=m.playing?"⏸":"▶"; $("media-repeat").textContent=`循环：${({none:"关",track:"单曲",list:"列表"})[m.repeat]||"关"}`; $("media-shuffle").textContent=`随机：${m.shuffle?"开":"关"}`;
  $("media-play").disabled=!m.available||!(m.playing?(controls.pause||controls.toggle):(controls.play||controls.toggle)); $("media-prev").disabled=!controls.previous; $("media-next").disabled=!controls.next; $("media-stop").disabled=!controls.stop; $("media-repeat").disabled=!controls.repeat; $("media-shuffle").disabled=!controls.shuffle;
  setRange("system-volume",audio.volume??0); $("system-volume-label").textContent=audio.available?`${Math.round(audio.volume||0)}%`:"不可用"; $("system-mute").checked=!!audio.mute;
  options($("audio-output"),audio.outputs||[],audio.active_output,"name","id");
  if (m.lyrics_key && m.lyrics_key!==lyricsKey) { lyricsKey=m.lyrics_key; loadLyrics(); }
}

async function loadLyrics() {
  try {
    const response=await fetch(`/api/lyrics?token=${encodeURIComponent(token)}`); if(!response.ok)return;
    const data=await response.json(); if(data.key!==lyricsKey)return;
    $("full-lyrics").textContent=data.lines?.length?data.lines.map(x=>x.text).join("\n"):(data.plain||"暂无歌词");
  } catch (_) {}
}

function selectMacro(item) {
  selectedMacro=item; $("macro-key").textContent=item?`${item.label} · ${item.x},${item.y}`:"未选择";
  if (!item) return;
  if(document.activeElement!==$("macro-action"))$("macro-action").value=item.action||"热键";
  if(document.activeElement!==$("macro-value"))$("macro-value").value=item.value||"";
  if(document.activeElement!==$("macro-color"))$("macro-color").value=item.color||"#7c5cff";
}

function renderMacros() {
  const macros=state.macros||[], host=$("macro-grid");
  const signature=macros.map(x=>`${x.x}:${x.y}`).join("|");
  if(host.dataset.signature!==signature){host.innerHTML="";macros.forEach((item,index)=>{const b=document.createElement("button");b.className="macro-pad";b.dataset.index=index;b.onclick=()=>{const current=state.macros[Number(b.dataset.index)];selectMacro(current);command("macro.trigger",{x:current.x,y:current.y});renderMacros();};host.appendChild(b);});host.dataset.signature=signature;}
  [...host.children].forEach((b,index)=>{const item=macros[index];if(!item)return;b.textContent=item.label;b.style.background=item.configured?item.color:"#202633";b.classList.toggle("empty",!item.configured);b.classList.toggle("selected",!!selectedMacro&&selectedMacro.x===item.x&&selectedMacro.y===item.y);});
  if(selectedMacro){const fresh=macros.find(x=>x.x===selectedMacro.x&&x.y===selectedMacro.y);if(fresh)selectMacro(fresh);}
}

function renderSettings() {
  const lp=state.launchpad||{}; options($("device-model"),lp.models||[],lp.model_key||"auto","name","key");
  options($("device-input"),lp.inputs||[],$("device-input").value,null,null); options($("device-output"),lp.outputs||[],$("device-output").value,null,null);
  $("server-address").textContent=`${location.protocol}//${location.host}/`;
}

function render() {
  if(!state)return; renderStudio(); renderMedia(); renderMacros(); renderSettings();
}

$("pair-form").addEventListener("submit",event=>{event.preventDefault();token=$("pair-pin").value.trim();if(token.length===6){localStorage.setItem("launchpadPin",token);connect();}});
document.querySelectorAll(".nav").forEach(button=>button.onclick=()=>{document.querySelectorAll(".nav").forEach(x=>x.classList.toggle("active",x===button));document.querySelectorAll(".tab").forEach(x=>x.classList.remove("active"));$(`tab-${button.dataset.tab}`).classList.add("active");});
$("stop-all").onclick=()=>command("app.stop"); $("blackout").onclick=()=>command("app.blackout"); $("perf-start").onclick=()=>command("performance.start");
$("palette").onchange=event=>command("global.palette",event.target.value); bindRange("brightness","global.brightness",Number,90); $("custom-color").onchange=event=>command("global.custom_color",event.target.value); $("macro-control").onchange=event=>command("macro_control",event.target.checked);

$("video-playlist").onchange=event=>command("video.select",Number(event.target.value)); $("video-play").onclick=()=>command(`video.${!state?.video?.running?"play":state.video.paused?"resume":"pause"}`);
document.querySelectorAll("[data-video]").forEach(button=>button.onclick=()=>command(`video.${button.dataset.video}`)); bindRange("video-progress","video.seek",Number,60);
$("video-rate").onchange=event=>command("video.rate",event.target.value); $("video-loop").onchange=event=>command("video.loop",event.target.value); $("video-effect").onchange=event=>command("video.effect",event.target.value);
$("video-fps").oninput=event=>{ $("video-fps-label").textContent=event.target.value; command("video.param",{fps:Number(event.target.value)}); };

$("music-playlist").onchange=event=>command("music.select",Number(event.target.value)); $("music-play").onclick=()=>command(`music.${!state?.music?.running?"play":state.music.paused?"resume":"pause"}`);
document.querySelectorAll("[data-music]").forEach(button=>button.onclick=()=>command(`music.${button.dataset.music}`)); bindRange("music-progress","music.seek",Number,60);
$("music-style").onchange=event=>command("music.style",event.target.value); $("music-rate").onchange=event=>command("music.rate",event.target.value); $("music-loop").onchange=event=>command("music.loop",event.target.value); bindRange("music-volume","music.volume",Number,80);

$("live-device").onchange=event=>{const item=state?.live?.devices?.[Number(event.target.value)];if(item)command("live.device",item.id);}; $("live-style").onchange=event=>command("live.style",event.target.value); $("live-start").onclick=()=>command("live.start");
$("utility-choice").onchange=event=>command("utility.select",event.target.value); $("utility-start").onclick=()=>command("utility.start"); $("utility-pause").onclick=()=>command("utility.focus_pause"); $("utility-reset").onclick=()=>command("utility.focus_reset");
$("weather-city").onchange=event=>command("utility.weather_city",event.target.value); $("focus-minutes").onchange=event=>command("utility.focus_minutes",Number(event.target.value));

$("media-prev").onclick=()=>command("system_media.previous"); $("media-play").onclick=()=>command(state?.system_media?.playing?"system_media.pause":"system_media.play"); $("media-next").onclick=()=>command("system_media.next"); $("media-stop").onclick=()=>command("system_media.stop"); bindRange("system-progress","system_media.seek",Number,45);
$("media-repeat").onclick=()=>{const current=state?.system_media?.repeat||"none";const next={none:"track",track:"list",list:"none"}[current];command("system_media.repeat",next);}; $("media-shuffle").onclick=()=>command("system_media.shuffle",!state?.system_media?.shuffle);
bindRange("system-volume","system_media.volume",Number,55); $("system-mute").onchange=event=>command("system_media.mute",event.target.checked); $("audio-output").onchange=event=>command("system_media.output",event.target.value);

options($("macro-action"),macroActions,"热键",null,null); $("macro-mode").onclick=()=>command("macro.start");
$("macro-save").onclick=()=>{if(selectedMacro)command("macro.save",{x:selectedMacro.x,y:selectedMacro.y,action:$("macro-action").value,value:$("macro-value").value,color:$("macro-color").value});}; $("macro-test").onclick=()=>{if(selectedMacro)command("macro.trigger",{x:selectedMacro.x,y:selectedMacro.y});}; $("macro-clear").onclick=()=>{if(selectedMacro)command("macro.clear",{x:selectedMacro.x,y:selectedMacro.y});};

$("device-refresh").onclick=()=>command("device.refresh"); $("device-connect").onclick=()=>command("device.connect",{model:$("device-model").value,input:$("device-input").value,output:$("device-output").value}); $("device-test").onclick=()=>command("app.test_lights");
$("forget-pin").onclick=()=>{localStorage.removeItem("launchpadPin");token="";if(ws)ws.close();$("pair").classList.remove("hidden");};
connect();
