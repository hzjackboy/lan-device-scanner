// 用最小 DOM 桩在 node 里跑一遍前端渲染逻辑，捕获拼写/引用错误
const fs = require('fs'), vm = require('vm');

function makeEl(id) {
  return {
    id, innerHTML: '', textContent: '', value: '', title: '', scrollTop: 0, scrollHeight: 100,
    dataset: {}, style: {}, _classes: new Set(),
    classList: {
      add(...c) { c.forEach(x => this._s.add(x)); }, remove(...c) { c.forEach(x => this._s.delete(x)); },
      toggle(c, on) { if (on === undefined) { this._s.has(c) ? this._s.delete(c) : this._s.add(c); } else if (on) this._s.add(c); else this._s.delete(c); },
      contains(c) { return this._s.has(c); }, _s: new Set(),
    },
    addEventListener() {}, appendChild() {}, showModal() {}, close() {}, querySelectorAll() { return []; },
    querySelector() { return null; }, remove() {},
  };
}
const els = {};
const document = {
  getElementById(id) { return (els[id] = els[id] || makeEl(id)); },
  createElement() { return makeEl('new'); },
  createDocumentFragment() { return { appendChild() {} }; },
  querySelectorAll() { return []; },
  addEventListener() {},
};
const ctx = {
  document, console,
  window: {}, setTimeout, clearTimeout, setInterval, clearInterval,
  fetch: () => Promise.reject(new Error('no network in test')),
  Date, Map, Set, JSON, Math, String, Number, Object, Array, parseInt, isNaN,
};
ctx.globalThis = ctx;
vm.createContext(ctx);
vm.runInContext(fs.readFileSync('static/app.js', 'utf8'), ctx, { filename: 'app.js' });

const snap = {
  id: 'test', subnet: '10.0.0.0/24', state: 'running', phase: '端口指纹扫描', error: '',
  progress: { done: 120, total: 254, percent: 62 }, started_at: Date.now() / 1000 - 5,
  finished_at: null, duration: 5, total_hosts: 254, options: {}, version: 3,
  devices: [
    { ip: '10.0.0.1', mac: '02:00:00:00:00:01', vendor: 'iKuai', hostname: 'gateway', kind: '路由器 / 网关',
      ports: [80, 443, 53, 22, 8080, 8443, 9100, 9101, 9102], services: ['http'], rtt_ms: 2.3, iface: 'en0',
      online: true, confirmed: true, only_arp: false, sources: ['arp', 'icmp', 'tcp'], note: '', last_seen: Date.now() / 1000, extra: {} },
    { ip: '10.0.0.139', mac: '', vendor: '', hostname: '', kind: '',
      ports: [], services: [], rtt_ms: null, iface: '', online: true, confirmed: false, only_arp: true,
      sources: ['arp-cache'], note: '仅 ARP 缓存记录', last_seen: Date.now() / 1000, extra: {} },
  ],
  stats: { total: 2, online: 1, arp_only: 1, with_mac: 1, named: 1, kinds: {}, vendors: {} },
  logs: [{ ts: Date.now() / 1000, level: 'info', msg: '测试日志' }, { ts: Date.now() / 1000, level: 'warn', msg: '警告日志' }],
};
ctx.applySnapshot(snap);
const body = els['results-body'].innerHTML;
const checks = [
  ['表格渲染出两行', (body.match(/<tr /g) || []).length === 2],
  ['IP 已渲染', body.includes('10.0.0.1')],
  ['端口 chip 已渲染', body.includes('class="port"') && body.includes('>443<')],
  ['延迟已渲染', body.includes('2.3 ms')],
  ['仅 ARP 行有样式', body.includes('arp-only')],
  ['新行闪烁类', body.includes('new-row')],
  ['统计卡片更新', els['stat-found'].textContent === 1],
  ['进度条更新', els['progress-bar'].style.width === '62%'],
  ['日志渲染', els['logs'].innerHTML.includes('测试日志') && els['logs'].innerHTML.includes('l-warn')],
  ['结果计数', els['result-count'].textContent === '2'],
];
ctx.showDetail(snap.devices[0]);
checks.push(['详情弹窗包含端口名', els['detail-body'].innerHTML.includes('HTTP')]);
ctx.renderTable(); // 二次渲染不应再标记 new-row
checks.push(['二次渲染不再闪烁', !els['results-body'].innerHTML.includes('new-row')]);

let failed = 0;
for (const [name, ok] of checks) { console.log((ok ? '✅' : '❌') + ' ' + name); if (!ok) failed++; }
console.log(failed ? `\n${failed} 项失败` : '\n全部通过');
process.exit(failed ? 1 : 0);
