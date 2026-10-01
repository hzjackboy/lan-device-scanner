const fs = require('fs'), vm = require('vm');
require('./_auth_shim');   // 服务要登录：给 /api/ 请求带上本地令牌
function makeEl(id) {
  const el = { id, innerHTML:'', textContent:'', value:'', checked:false, hidden:false, scrollTop:0, scrollHeight:100,
    dataset:{}, style:{}, options:[], _handlers:{},
    addEventListener(t,f){ (this._handlers[t]=this._handlers[t]||[]).push(f); },
    appendChild(){}, showModal(){}, close(){}, querySelectorAll(){return[];}, querySelector(){return null;},
    classList:{ _s:new Set(), add(...c){c.forEach(x=>this._s.add(x));}, remove(...c){c.forEach(x=>this._s.delete(x));},
      toggle(c,on){ if(on===undefined){this._s.has(c)?this._s.delete(c):this._s.add(c); return this._s.has(c);} on?this._s.add(c):this._s.delete(c); return !!on;},
      contains(c){return this._s.has(c);} } };
  return el;
}
const views = ['view-home','view-scan','view-history','view-devices','view-about'].map(makeEl);
const navItems = ['home','scan','history','devices','about'].map(v=>{const e=makeEl('nav-'+v); e.dataset.view=v; return e;});
const els = {};
const document = { hidden:false, getElementById:(id)=>(els[id]=els[id]||makeEl(id)), createElement:()=>makeEl('n'),
  createDocumentFragment:()=>({appendChild(){}}), querySelectorAll:s=>s==='.view'?views:s==='.nav-item'?navItems:[], addEventListener(){} };
const ctx = { document, console, setTimeout, clearTimeout, setInterval, clearInterval,
  localStorage:{getItem:()=>null,setItem(){}}, location:{hash:''}, Date, Map, Set, JSON, Math, String, Number, Object, Array, parseInt, isNaN,
  fetch:(u,o)=>fetch('http://127.0.0.1:8765'+u,o), window:{addEventListener(){},location:{},confirm:()=>true} };
ctx.globalThis = ctx;
vm.createContext(ctx);
vm.runInContext(fs.readFileSync('static/app.js','utf8'), ctx, { filename:'app.js' });

setTimeout(() => {
  const run = (c) => vm.runInContext(c, ctx);
  const stats = run('state.chartStats');
  console.log('后端台账统计 :', JSON.stringify(stats && { total: stats.total, online: stats.online, offline: stats.offline, starred: stats.starred, edited: stats.edited }));
  console.log('圆心总数     :', els['donut-total'].textContent);
  console.log('弧段数量     :', (els['donut'].innerHTML.match(/donut-seg/g)||[]).length);
  console.log('图例         :');
  els['chart-legend'].innerHTML.replace(/<button[\s\S]*?<\/button>/g, (m) => {
    const label = (m.match(/legend-name">([^<]+)</)||[])[1];
    const value = (m.match(/legend-value">([^<]+)</)||[])[1];
    const pct = (m.match(/legend-pct">([^<]+)</)||[])[1];
    const color = (m.match(/background:([^"]+)/)||[])[1];
    console.log(`   ${color}  ${label} ${value} 台  ${pct}`);
    return '';
  });
  console.log('脚注         :', els['chart-foot'].textContent);
  const svg = els['donut'].innerHTML;
  const dashes = (svg.match(/stroke-dasharray="([\d.]+)/g)||[]).map(x=>parseFloat(x.split('"')[1]));
  const C = 2*Math.PI*74;
  console.log('弧长占比     :', dashes.map(d => (d/C*100).toFixed(1)+'%').join(' / '));
  process.exit(0);
}, 2500);
