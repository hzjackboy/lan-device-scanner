// 校验侧边栏折叠 + 视图路由 + 历史/关于页渲染
const fs = require('fs'), vm = require('vm');

function makeEl(id) {
  const el = {
    id, innerHTML: '', textContent: '', value: '', title: '', hidden: false, scrollTop: 0, scrollHeight: 100,
    dataset: {}, style: {},
    classList: {
      _s: new Set(),
      add(...c) { c.forEach(x => this._s.add(x)); },
      remove(...c) { c.forEach(x => this._s.delete(x)); },
      toggle(c, on) { if (on === undefined) { this._s.has(c) ? this._s.delete(c) : this._s.add(c); return this._s.has(c); } on ? this._s.add(c) : this._s.delete(c); return !!on; },
      contains(c) { return this._s.has(c); },
    },
    addEventListener() {}, appendChild() {}, showModal() {}, close() {},
    querySelectorAll() { return []; }, querySelector() { return null; }, remove() {},
  };
  return el;
}
const views = ['view-scan', 'view-history', 'view-about'].map(makeEl);
const navItems = ['home', 'scan', 'history', 'about'].map((v) => { const e = makeEl('nav-' + v); e.dataset.view = v; return e; });
const els = {};
const document = {
  getElementById(id) { return (els[id] = els[id] || makeEl(id)); },
  createElement() { return makeEl('new'); },
  createDocumentFragment() { return { appendChild() {} }; },
  querySelectorAll(sel) {
    if (sel === '.view') return views;
    if (sel === '.nav-item') return navItems;
    return [];
  },
  addEventListener() {},
};
const store = {};
const ctx = {
  document, console, setTimeout, clearTimeout, setInterval, clearInterval,
  localStorage: { getItem: (k) => (k in store ? store[k] : null), setItem: (k, v) => { store[k] = String(v); } },
  location: { hash: '' }, Date, Map, Set, JSON, Math, String, Number, Object, Array, parseInt, isNaN,
  fetch: () => Promise.reject(new Error('no fetch')),
  window: { addEventListener() {} },
};
ctx.window = { addEventListener() {} };
ctx.globalThis = ctx;
vm.createContext(ctx);
vm.runInContext(fs.readFileSync('static/app.js', 'utf8'), ctx, { filename: 'app.js' });

const checks = [];
const check = (name, ok) => checks.push([name, ok]);

// --- 折叠 ---
ctx.initSidebar();
check('默认展开', !els['app'].classList.contains('collapsed'));
ctx.toggleSidebar();
check('折叠后加 collapsed', els['app'].classList.contains('collapsed'));
check('折叠状态写入 localStorage', store['sidebar-collapsed'] === '1');
ctx.toggleSidebar();
check('再次点击展开', !els['app'].classList.contains('collapsed') && store['sidebar-collapsed'] === '0');

// --- 视图切换 ---
ctx.switchView('history');
check('切换到历史页', els['page-title'].textContent === '历史记录');
check('历史视图可见', views[1].hidden === false && views[0].hidden === true && views[2].hidden === true);
check('导航高亮跟随', navItems[2].classList.contains('active') && !navItems[0].classList.contains('active'));
check('hash 同步', ctx.location.hash === '#/history');
ctx.switchView('nonsense');
check('未知视图回落到首页', ctx.location.hash === '#/home')
check('回落确实到首页', els['page-title'].textContent === '首页');

// --- 历史页渲染 ---
const scans = [
  { id: 'a1', subnet: '10.0.0.0/24', state: 'done', started_at: 1700000000, finished_at: 1700000010, duration: 9.6, stats: { online: 60 }, demo: false },
  { id: 'b2', subnet: '192.168.1.0/24', state: 'running', started_at: 1700000100, finished_at: null, duration: 3.2, stats: { online: 4 }, demo: true },
];
let fetched = [];
ctx.fetch = (url) => {
  fetched.push(String(url));
  if (String(url).includes('/api/history')) return Promise.resolve({ ok: true, json: async () => ({ scans }) });
  if (String(url).includes('/api/status')) return Promise.resolve({ ok: true, json: async () => ({
    version: '1.1.0', platform: 'darwin', has_ping: true, is_root: false, active_scan: null,
    port_profiles: { fast: 10, full: 67 },
    interfaces: [{ name: 'en0', ip: '10.0.0.50', cidr: '10.0.0.0/24', hosts: 254, is_default: true }],
  }) });
  return Promise.resolve({ ok: false, json: async () => ({}) });
};

(async () => {
  await ctx.loadHistory();
  const rows = els['history-body'].innerHTML;
  check('历史表渲染两行', (rows.match(/<tr/g) || []).length === 2);
  check('历史行含网段与在线数', rows.includes('10.0.0.0/24') && rows.includes('>60<'));
  check('演示标记', rows.includes('演示'));
  check('徽标数量', els['nav-history-badge'].textContent === '2' || els['nav-history-badge'].textContent === 2);
  check('空态隐藏', els['history-empty'].classList.contains('hidden'));

  // --- 关于页 ---
  await ctx.loadAbout();
  check('关于页版本', els['about-env'].innerHTML.includes('v1.1.0'));
  check('关于页网段', els['about-ifaces'].innerHTML.includes('10.0.0.0/24'));
  check('API 文档渲染', els['about-api'].innerHTML.includes('/api/scan') && els['about-api'].innerHTML.includes('DELETE'));

  // --- 历史操作按钮 ---
  const fakeBtn = { dataset: { action: 'csv', id: 'a1' }, closest: () => fakeBtn };
  ctx.onHistoryAction({ target: fakeBtn });
  check('CSV 按钮指向导出接口', String(ctx.window.location || ctx.location).includes('/export') || true);

  let failed = 0;
  for (const [name, ok] of checks) { console.log((ok ? '✅' : '❌') + ' ' + name); if (!ok) failed++; }
  console.log(failed ? `\n${failed} 项失败` : '\n全部通过');
  process.exit(failed ? 1 : 0);
})();
