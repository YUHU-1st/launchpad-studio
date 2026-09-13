#!/usr/bin/env node

const endpoint = process.env.CDP_HTTP || "http://127.0.0.1:9222";
const expression = process.argv.slice(2).join(" ") || "JSON.stringify({title:document.title,url:location.href})";

const pages = await fetch(`${endpoint}/json`).then(r => {
  if (!r.ok) throw new Error(`CDP /json failed: HTTP ${r.status}`);
  return r.json();
});
const page = pages.find(item => item.type === "page" && item.webSocketDebuggerUrl);
if (!page) throw new Error("No debuggable WebView page found");

const socket = new WebSocket(page.webSocketDebuggerUrl);
const id = 1;
const result = await new Promise((resolve, reject) => {
  const timer = setTimeout(() => reject(new Error("CDP timeout")), 8000);
  socket.addEventListener("open", () => {
    socket.send(JSON.stringify({
      id,
      method: "Runtime.evaluate",
      params: {expression, returnByValue: true, awaitPromise: true},
    }));
  });
  socket.addEventListener("message", event => {
    const message = JSON.parse(event.data);
    if (message.id !== id) return;
    clearTimeout(timer);
    if (message.error) reject(new Error(JSON.stringify(message.error)));
    else resolve(message.result?.result);
  });
  socket.addEventListener("error", () => reject(new Error("CDP WebSocket error")));
});
socket.close();
console.log(JSON.stringify(result, null, 2));
