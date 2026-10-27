const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const nodes = new Map();
function node(selector) {
  if (!nodes.has(selector)) nodes.set(selector, {
    dataset: {}, textContent: '', innerHTML: '', disabled: false,
    addEventListener() {}, classList: { toggle() {}, add() {}, remove() {} },
  });
  return nodes.get(selector);
}
const context = vm.createContext({
  document: {querySelector: node, querySelectorAll: () => []},
  window: {setInterval() {}, setTimeout() {}, clearTimeout() {}, matchMedia: () => ({matches: false})},
  fetch: () => new Promise(() => {}),
  setTimeout() {}, clearTimeout() {}, console, Intl, Date,
});
vm.runInContext(fs.readFileSync('dashboard/app.js', 'utf8'), context);
for (const [scheduler, expected] of [
  [{running:true, interval_seconds:60}, '后台每 1 分钟采样'],
  [{running:false, interval_seconds:60}, '后台采样未启动'],
  [{}, '后台采样状态未知'],
  [{running:true, last_error:'error'}, '后台调度异常'],
]) {
  context.payload = {automation: {scheduler}};
  vm.runInContext('renderAutomation(payload)', context);
  assert.equal(node('#monitor-interval').textContent, expected);
}
// Config fetch can finish after status: it must not overwrite the scheduler state.
context.config = {monitor_interval_seconds: 30};
vm.runInContext('renderConfig(config)', context);
assert.equal(node('#monitor-interval').textContent, '后台调度异常');

const offlineNodes = new Map();
function offlineNode(selector) {
  if (!offlineNodes.has(selector)) offlineNodes.set(selector, {
    dataset: {}, textContent: 'stale', innerHTML: '', disabled: false,
    addEventListener() {}, classList: { toggle() {}, add() {}, remove() {} },
  });
  return offlineNodes.get(selector);
}
const offline = vm.createContext({
  document: {querySelector: offlineNode, querySelectorAll: () => []},
  window: {setInterval() {}, setTimeout() {}, clearTimeout() {}, matchMedia: () => ({matches: false})},
  fetch: async () => { throw new Error('offline'); },
  setTimeout() {}, clearTimeout() {}, console, Intl, Date,
});
vm.runInContext(fs.readFileSync('dashboard/app.js', 'utf8'), offline);
setImmediate(() => {
  assert.equal(offlineNode('#monitor-interval').textContent, '后台采样状态不可用');
  assert.equal(offlineNode('#scheduler-next').textContent, '--');
});
