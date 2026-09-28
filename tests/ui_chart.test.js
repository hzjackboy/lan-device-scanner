// 首页饼图：分段、百分比、空态、点击跳转筛选
const fs = require('fs'), vm = require('vm');
function makeEl(id) {
  const el = { id, innerHTML: '', textContent: '', value: '', checked: false, title: '', hidden: false,
    scrollTop: 0, scrollHeight: 100, dataset: {}, style: {}, options: [],
    _handlers: {}, addEventListener(t, f) { (this._handlers[t] = this._handlers[t] || []).push(f); },
    appendChild() {}, showModal() {}, close() {}, querySelectorAll() { return []; }, querySelector() { return null; },
    classList: { _s: new Set(), add(...c){c.forEach(x=>this._s.add(x));}, remove(...c){c.forEach(x=>this._s.delete(x));},
      toggle(c,on){ if(on===undefined){this._s.has(c)?this._s.delete(c):this._s.add(c); return this._s.has(c);} on?this._s.add(c):this._s.delete(c); return !!on;},
      contains(c){return this._s.has(c);} } };
  return el;
}
const views = ['view-home','view-scan','view-history','view-devices','view-about'].map(makeEl);
const navItems = ['home','scan','history','devices','about'].map((v)=>{const e=makeEl('nav-'+v); e.dataset.view=v; return e;});
const els = {};
const document = { hidden: false, getElementById:(id)=>(els[id]=els[id]||makeEl(id)), createElement:()=>makeEl('n'),
  createDocumentFragment:()=>({appendChild(){}}), querySelectorAll:(s)=>s==='.view'?views:s==='.nav-item'?navItems:[], addEventListener(){} };
const fetched = [];
const ctx = { document, console, setTimeout, clearTimeout, setInterval, clearInterval,
  localStorage:{ getItem:()=>null, setItem(){} }, location:{ hash:'' }, Date, Map, Set, JSON, Math, String, Number, Object, Array, parseInt, isNaN,
  confirm: () => true,
  fetch: (url) => { fetched.push(String(url)); return Promise.resolve({ ok:true, json: async () => ({ ok:true, devices: [], stats: {}, categories: [] }) }); },
  window:{ addEventListener(){}, location:{}, confirm: () => true } };
ctx.globalThis = ctx;
vm.createContext(ctx);
vm.runInContext(fs.readFileSync('static/app.js','utf8'), ctx, { filename:'app.js' });
const run = (code) => vm.runInContext(code, ctx);
const checks = []; const check = (n, ok) => checks.push([n, ok]);

// 1) 典型数据
ctx.renderChart({ total: 59, online: 57, offline: 2, starred: 3, ignored: 1, updated_at: Date.now()/1000 - 120 });
let svg = els['donut'].innerHTML;
check('渲染 SVG', svg.startsWith('<svg') && svg.includes('</svg>'));
check('两段弧 + 底环', (svg.match(/donut-seg/g) || []).length === 2 && svg.includes('donut-ring'));
check('在线段用绿色', svg.includes('#34d399'));
check('离线段用红色', svg.includes('#f87171'));
check('圆心显示总数', String(els['donut-total'].textContent) === '59');
const legend = els['chart-legend'].innerHTML;
check('图例两行', (legend.match(/legend-row/g) || []).length === 2);
check('图例显示台数', legend.includes('>57<') && legend.includes('>2<'));
check('百分比计算正确', legend.includes('96.6%') && legend.includes('3.4%'));
check('脚注含关注/忽略/归档时间', /已关注 3/.test(els['chart-foot'].textContent) && /已忽略 1/.test(els['chart-foot'].textContent) && /分钟前/.test(els['chart-foot'].textContent));

// 弧长比例：周长 = 2πr, r = (168-20)/2 = 74 → 464.96
const dash = svg.match(/stroke-dasharray="([\d.]+)/g).map(x => parseFloat(x.split('"')[1]));
const circumference = 2 * Math.PI * 74;
check('在线弧长占比 ≈ 96.6%', Math.abs(dash[0] / circumference - 57 / 59) < 0.001);
check('离线弧长占比 ≈ 3.4%', Math.abs(dash[1] / circumference - 2 / 59) < 0.001);

// 2) 全部在线
ctx.renderChart({ total: 10, online: 10, offline: 0 });
svg = els['donut'].innerHTML;
check('全在线时只有一段', (svg.match(/donut-seg/g) || []).length === 1);
check('全在线 100%', els['chart-legend'].innerHTML.includes('100.0%'));

// 3) 空台账
ctx.renderChart({ total: 0, online: 0, offline: 0 });
check('空台账只画底环', !els['donut'].innerHTML.includes('donut-seg'));
check('空台账中心为 0', String(els['donut-total'].textContent) === '0');
check('空台账给出提示', els['chart-legend'].innerHTML.includes('还没有设备') && els['chart-foot'].textContent.includes('跑一次扫描'));

// 4) 点图例跳转到设备管理并带上筛选
ctx.renderChart({ total: 5, online: 4, offline: 1 });
const handler = els['chart-legend']._handlers.click[0];
const row = { dataset: { state: 'offline' }, closest: () => row };
handler({ target: row });
check('点图例切到设备管理页', run('state.view') === 'devices' && els['page-title'].textContent === '设备管理');
check('带上对应筛选状态', run('state.devState') === 'offline');

// 5) 「去设备管理」按钮
els['chart-manage']._handlers.click[0]();
check('按钮也能跳到设备管理', run('state.view') === 'devices');

// 6) /api/status 驱动
ctx.chartFromStatus({ devices: { total: 8, online: 6, offline: 2, starred: 0, ignored: 0 } });
check('从 status 更新饼图', String(els['donut-total'].textContent) === '8');

let failed = 0;
for (const [n, ok] of checks) { console.log((ok ? '✅' : '❌') + ' ' + n); if (!ok) failed++; }
console.log(failed ? `\n${failed} 项失败` : '\n全部通过');
process.exit(failed ? 1 : 0);
