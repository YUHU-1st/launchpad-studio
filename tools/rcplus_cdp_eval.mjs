const expr = process.argv.slice(2).join(' ');
if (!expr) {
  console.error('Usage: node rcplus_cdp_eval.mjs <expression>');
  process.exit(2);
}

const pages = await fetch('http://127.0.0.1:9222/json').then(r => r.json());
if (!pages.length) throw new Error('No debuggable WebView page');
const ws = new WebSocket(pages[0].webSocketDebuggerUrl);
await new Promise((resolve, reject) => {
  ws.addEventListener('open', resolve, { once: true });
  ws.addEventListener('error', reject, { once: true });
});

const id = 1;
ws.send(JSON.stringify({
  id,
  method: 'Runtime.evaluate',
  params: { expression: expr, awaitPromise: true, returnByValue: true }
}));

const response = await new Promise((resolve, reject) => {
  const timer = setTimeout(() => reject(new Error('CDP timeout')), 5000);
  ws.addEventListener('message', event => {
    const msg = JSON.parse(event.data);
    if (msg.id !== id) return;
    clearTimeout(timer);
    resolve(msg);
  });
});
if (response.error) {
  console.error(JSON.stringify(response.error));
  process.exitCode = 1;
} else if (response.result?.exceptionDetails) {
  console.error(JSON.stringify(response.result.exceptionDetails));
  process.exitCode = 1;
} else {
  const result = response.result?.result;
  console.log(JSON.stringify({
    type: result?.type,
    value: result?.value,
    description: result?.description
  }, null, 2));
}
ws.close();
