// 校验首页设备方块墙：分组、过滤、图标、新设备动画、点击详情
const fs = require('fs'), vm = require('vm');
function makeEl(id) {
  const el = { id, innerHTML: '', textContent: '', value: '', title: '', hidden: false, scrollTop: 0, scrollHeight: 100,
    dataset: {}, style: {},
    classList: { _s: new Set(), add(...c){c.forEach(x=>this._s.add(x));}, remove(...c){c.forEach(x=>this._s.delete(x));},
      toggle(c,on){ if(on===undefined){this._s.has(c)?this._s.delete(c):this._s.add(c); return this._s.has(c);} on?this._s.add(c):this._s.delete(c); return !!on;},
      contains(c){return this._s.has(c);} },
    addEventListener(){}, appendChild(){}, showModal(){}, close(){}, querySelectorAll(){return [];}, querySelector(){return null;} };
  return el;
}
const views = ['view-home','view-scan','view-history','view-about'].map(makeEl);
const navItems = ['home','scan','history','about'].map((v)=>{const e=makeEl('nav-'+v); e.dataset.view=v; return e;});
const els = {};
const document = {
  getElementById(id){ return (els[id] = els[id] || makeEl(id)); },
  createElement(){ return makeEl('new'); },
  createDocumentFragment(){ return { appendChild(){} }; },
  querySelectorAll(sel){ if(sel==='.view') return views; if(sel==='.nav-item') return navItems; return []; },
  addEventListener(){},
};
const ctx = { document, console, setTimeout, clearTimeout, setInterval, clearInterval,
  localStorage:{ getItem:()=>null, setItem(){} }, location:{ hash:'' }, Date, Map, Set, JSON, Math,
  String, Number, Object, Array, parseInt, isNaN, fetch: () => Promise.reject(new Error('x')),
  window:{ addEventListener(){} } };
ctx.globalThis = ctx;
vm.createContext(ctx);
vm.runInContext(fs.readFileSync('static/app.js','utf8'), ctx, { filename:'app.js' });

const devices = [
  { ip:'10.0.0.1', mac:'02:00:00:00:00:01', vendor:'iKuai', hostname:'gateway', kind:'路由器 / 网关',
    ports:[80,443], services:[], rtt_ms:2.1, iface:'en0', online:true, confirmed:true, only_arp:false, sources:['arp'], note:'', last_seen:1, extra:{} },
  { ip:'10.0.0.57', mac:'02:00:00:00:00:02', vendor:'Espressif', hostname:'led-strip', kind:'智能灯',
    ports:[80], services:['esphomelib'], rtt_ms:7.7, iface:'en0', online:true, confirmed:true, only_arp:false, sources:['mdns'], note:'', last_seen:1, extra:{} },
  { ip:'10.0.0.96', mac:'02:00:00:00:00:03', vendor:'Hangzhou Hikvision', hostname:'IP-Camera', kind:'网络摄像头',
    ports:[80,554], services:['http'], rtt_ms:6.1, iface:'en0', online:true, confirmed:true, only_arp:false, sources:['tcp'], note:'', last_seen:1, extra:{} },
  { ip:'10.0.0.139', mac:'02:00:00:00:00:04', vendor:'私有/随机 MAC', hostname:'Tablet-A', kind:'iPhone / iPad',
    ports:[62078], services:['companion-link'], rtt_ms:96.9, iface:'en0', online:true, confirmed:true, only_arp:false, sources:['tcp'], note:'', last_seen:1, extra:{} },
  { ip:'10.0.0.200', mac:'', vendor:'未知厂商', hostname:'', kind:'',
    ports:[], services:[], rtt_ms:null, iface:'', online:false, confirmed:false, only_arp:true, sources:['arp-cache'], note:'仅 ARP 缓存记录', last_seen:1, extra:{} },
];
const snap = { id:'t', subnet:'10.0.0.0/24', state:'done', phase:'完成', error:'', progress:{done:254,total:254,percent:100},
  started_at: 1700000000, finished_at: 1700000010, duration: 9.5, total_hosts:254, options:{}, version:9,
  devices, stats:{ total:5, online:4, arp_only:1, with_mac:4, named:4,
    kinds:{ '智能灯':1,'网络摄像头':1,'iPhone / iPad':1,'路由器 / 网关':1 }, vendors:{ iKuai:1, Espressif:1 } }, logs:[] };

const run = (code) => vm.runInContext(code, ctx);
const checks = [];
const check = (n, ok) => checks.push([n, ok]);

ctx.applySnapshot(snap);
let grid = els['home-grid'].innerHTML;
check('方块数量 = 在线设备数（默认仅在线）', (grid.match(/<button class="dev-card/g) || []).length === 4);
check('渲染设备名与 IP', grid.includes('led-strip') && grid.includes('10.0.0.57'));
check('渲染设备类型', grid.includes('智能灯'));
check('灯设备用 💡', grid.includes('💡'));
check('摄像头用 📷', grid.includes('📷'));
check('手机/平板用 📱', grid.includes('📱'));
check('路由器用 📡', grid.includes('📡'));
check('在线状态点', grid.includes('dev-status online'));
check('新设备动画类', grid.includes('new-card'));
check('统计卡片：在线', els['home-online'].textContent === 4);
check('统计卡片：类型数', els['home-kinds'].textContent === 4);
check('概览计数', els['home-count'].textContent === '4 / 5');
check('元信息含网段', String(els['home-meta'].textContent).includes('10.0.0.0/24'));
check('空态隐藏', els['home-empty'].classList.contains('hidden'));

// 二次渲染不应再有 new-card
ctx.renderHome();
check('二次渲染不再闪烁', !els['home-grid'].innerHTML.includes('new-card'));

// 取消"仅在线"→ 出现仅 ARP 的方块（虚线样式）
run('state.homeOnlyOnline = false');
ctx.renderHome();
grid = els['home-grid'].innerHTML;
check('显示仅 ARP 设备', (grid.match(/<button class="dev-card/g) || []).length === 5 && grid.includes('arp-only'));
check('仅 ARP 状态点', grid.includes('dev-status arp'));

// 按类型分组
run("state.homeGroup = 'kind'");
ctx.renderHome();
grid = els['home-grid'].innerHTML;
check('分组标题渲染', (grid.match(/class="group-title"/g) || []).length === 5);
check('分组标题在方块之前', grid.indexOf('group-title') < grid.indexOf('dev-card'));
check('分组数量角标', grid.includes('<span class="count">1</span>'));

// 搜索
run("state.homeGroup = ''; state.homeSearch = 'hikvision';");
ctx.renderHome();
grid = els['home-grid'].innerHTML;
check('搜索过滤生效', (grid.match(/<button class="dev-card/g) || []).length === 1 && grid.includes('网络摄像头'));

run("state.homeSearch = ''; state.homeOnlyOnline = true;");
ctx.renderHome();

// 点击方块 → 详情弹窗
const card = { dataset:{ ip:'10.0.0.57' }, closest: () => card };
ctx.showDetail(devices[1]);
check('详情弹窗有端口/服务信息', els['detail-body'].innerHTML.includes('80') && els['detail-body'].innerHTML.includes('esphomelib'));

// 路由：默认落在首页
check('默认视图是首页', ctx.viewFromHash() === 'home');
ctx.switchView('home');
check('首页导航高亮', navItems[0].classList.contains('active'));
check('首页视图可见', views[0].hidden === false && views[1].hidden === true);

let failed = 0;
for (const [n, ok] of checks) { console.log((ok ? '✅' : '❌') + ' ' + n); if (!ok) failed++; }
if (process.env.DEBUG) {
  console.log('--- debug ---');
  console.log('卡片数:', (els['home-grid'].innerHTML.match(/dev-card/g) || []).length);
  console.log('button 数:', (els['home-grid'].innerHTML.match(/<button/g) || []).length);
  console.log('片段:', els['home-grid'].innerHTML.slice(0, 200));
}
console.log(failed ? `\n${failed} 项失败` : '\n全部通过');
process.exit(failed ? 1 : 0);
