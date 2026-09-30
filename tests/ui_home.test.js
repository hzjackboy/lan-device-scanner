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
const stored = {};
const ctx = { document, console, setTimeout, clearTimeout, setInterval, clearInterval,
  localStorage:{ getItem:(k)=> (k in stored ? stored[k] : null), setItem:(k,v)=>{ stored[k]=String(v); } },
  location:{ hash:'' }, Date, Map, Set, JSON, Math,
  String, Number, Object, Array, parseInt, isNaN, fetch: () => Promise.reject(new Error('x')),
  window:{ addEventListener(){} } };
ctx.globalThis = ctx;
vm.createContext(ctx);
vm.runInContext(fs.readFileSync('static/app.js','utf8'), ctx, { filename:'app.js' });

// 展示方式切换的四个按钮（真实页面里由 index.html 提供，测试里补上）
const modeButtons = ['list','l','m','s'].map((m) => { const b = makeEl('view-'+m); b.dataset.mode = m; return b; });
const switchEl = document.getElementById('home-view-switch');
switchEl.querySelectorAll = (sel) => (sel === 'button[data-mode]' ? modeButtons : []);

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

// ---------- 人工图标要盖过自动识别 ----------
// 设备管理里给设备选了图标后，服务端会通过 apply_to_snapshot 把 icon 贴到扫描结果上
run("state.homeGroup = ''; state.homeSearch = ''; state.homeOnlyOnline = true;");
ctx.applySnapshot({ ...snap, devices: devices.map((d) =>
  d.ip === '10.0.0.96' ? { ...d, icon: '🦊' } : d) });
grid = els['home-grid'].innerHTML;
check('人工图标盖过自动识别（摄像头不再用 📷）', grid.includes('🦊') && !grid.includes('📷'));
check('没设图标的设备仍用自动识别', grid.includes('💡') && grid.includes('📡'));

// 详情弹窗里也要能看到人工图标
ctx.showDetail({ ...devices[2], icon: '🦊' });
check('详情弹窗显示人工图标', els['detail-body'].innerHTML.includes('🦊') && els['detail-body'].innerHTML.includes('人工指定'));

// ---------- 首页展示方式：列表 / 大 / 中 / 小 ----------
ctx.applyHomeMode();
check('默认是小图标', run('state.homeMode') === 's' && els['home-grid'].dataset.mode === 's');
check('默认时小图标按钮高亮', modeButtons.find(b=>b.dataset.mode==='s').classList.contains('on'));

ctx.setHomeMode('l');
check('切到大图标后 grid 的 data-mode 跟着变', els['home-grid'].dataset.mode === 'l');
check('大图标按钮高亮、小图标取消高亮',
  modeButtons.find(b=>b.dataset.mode==='l').classList.contains('on') &&
  !modeButtons.find(b=>b.dataset.mode==='s').classList.contains('on'));
check('选择写进了 localStorage', stored['home-mode'] === 'l');

ctx.setHomeMode('list');
check('切到列表', els['home-grid'].dataset.mode === 'list');
check('列表按钮高亮', modeButtons.find(b=>b.dataset.mode==='list').classList.contains('on'));

// 非法值要退回默认，不能把 grid 搞成没有样式的状态
ctx.setHomeMode('bogus');
check('非法模式退回小图标', els['home-grid'].dataset.mode === 's');

// 重新进入页面时读回上次的选择
stored['home-mode'] = 'm';
ctx.initHomeMode();
check('重新初始化时读回上次选择', els['home-grid'].dataset.mode === 'm');
check('读回后对应按钮高亮', modeButtons.find(b=>b.dataset.mode==='m').classList.contains('on'));

// 静态结构：按钮和样式缺一个，切换就会「点了没反应」
const htmlSrc = fs.readFileSync('static/index.html', 'utf8');
const cssSrc = fs.readFileSync('static/style.css', 'utf8');
check('index.html 里有展示方式切换器', htmlSrc.includes('id="home-view-switch"'));
for (const m of ['list', 'l', 'm', 's']) {
  check(`切换器有 ${m} 按钮`, htmlSrc.includes(`data-mode="${m}"`));
  check(`样式里定义了 ${m} 模式`, cssSrc.includes(`[data-mode="${m}"]`));
}

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
