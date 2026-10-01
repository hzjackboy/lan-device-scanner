// 把 app.js 跑在 node 里，fetch 转发到真实服务，验证首页自动填充
const fs = require('fs'), vm = require('vm');
require('./_auth_shim');   // 服务要登录：给 /api/ 请求带上本地令牌
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
const document = { getElementById:(id)=>(els[id]=els[id]||makeEl(id)), createElement:()=>makeEl('n'), createDocumentFragment:()=>({appendChild(){}}),
  querySelectorAll:(s)=> s==='.view'?views : s==='.nav-item'?navItems : [], addEventListener(){} };
const ctx = { document, console, setTimeout, clearTimeout, setInterval, clearInterval,
  localStorage:{ getItem:()=>null, setItem(){} }, location:{ hash:'' }, Date, Map, Set, JSON, Math, String, Number, Object, Array,
  parseInt, isNaN, fetch: (url, opts) => fetch('http://127.0.0.1:8765' + url, opts), window:{ addEventListener(){} } };
ctx.globalThis = ctx;
vm.createContext(ctx);
vm.runInContext(fs.readFileSync('static/app.js','utf8'), ctx, { filename:'app.js' });

setTimeout(() => {
  const grid = els['home-grid'].innerHTML;
  const cards = (grid.match(/<button class="dev-card/g) || []).length;
  const all = vm.runInContext('state.snapshot ? state.snapshot.devices.length : 0', ctx);
  console.log('后端返回设备总数 :', all);
  console.log('首页方块数       :', cards);
  console.log('统计卡片 在线    :', els['home-online'].textContent, '| 类型', els['home-kinds'].textContent, '| 厂商', els['home-vendors'].textContent);
  console.log('概览计数         :', els['home-count'].textContent);
  console.log('元信息           :', els['home-meta'].textContent);
  console.log('历史角标         :', els['nav-history-badge'].textContent);
  console.log('当前视图         :', vm.runInContext('state.view', ctx), '/ 标题', els['page-title'].textContent);
  console.log('\n前 3 张方块：');
  grid.split('<button').slice(1, 4).forEach((c) => {
    const ico = (c.match(/dev-ico">([^<]+)</) || [])[1];
    const name = (c.match(/dev-name">([^<]+)</) || [])[1];
    const ip = (c.match(/dev-ip">([^<]+)</) || [])[1];
    const kind = (c.match(/dev-kind">([^<]+)</) || [])[1];
    const vendor = (c.match(/dev-vendor">([^<]+)</) || [])[1];
    console.log(`  ${ico}  ${ip.padEnd(14)} ${String(name).padEnd(22)} ${String(kind).padEnd(20)} ${vendor}`);
  });
  process.exit(cards > 0 ? 0 : 1);
}, 2500);
