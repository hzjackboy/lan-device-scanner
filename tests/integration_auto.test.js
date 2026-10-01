// 用真实后端跑前端：验证首页自动重扫控制条 + 后台扫描自动接管
const fs = require('fs'), vm = require('vm');
require('./_auth_shim');   // 服务要登录：给 /api/ 请求带上本地令牌
function makeEl(id) {
  const el = { id, innerHTML: '', textContent: '', value: '', checked: false, title: '', hidden: false,
    scrollTop: 0, scrollHeight: 100, dataset: {}, style: {},
    classList: { _s: new Set(), add(...c){c.forEach(x=>this._s.add(x));}, remove(...c){c.forEach(x=>this._s.delete(x));},
      toggle(c,on){ if(on===undefined){this._s.has(c)?this._s.delete(c):this._s.add(c); return this._s.has(c);} on?this._s.add(c):this._s.delete(c); return !!on;},
      contains(c){return this._s.has(c);} },
    _handlers: {}, addEventListener(t,f){ (this._handlers[t]=this._handlers[t]||[]).push(f); }, appendChild(){}, showModal(){}, close(){}, querySelectorAll(){return [];}, querySelector(){return null;} };
  return el;
}
const views = ['view-home','view-scan','view-history','view-about'].map(makeEl);
const navItems = ['home','scan','history','about'].map((v)=>{const e=makeEl('nav-'+v); e.dataset.view=v; return e;});
const els = {};
const document = { hidden: false, getElementById:(id)=>(els[id]=els[id]||makeEl(id)), createElement:()=>makeEl('n'),
  createDocumentFragment:()=>({appendChild(){}}), querySelectorAll:(s)=>s==='.view'?views:s==='.nav-item'?navItems:[], addEventListener(){} };
const ctx = { document, console, setTimeout, clearTimeout, setInterval, clearInterval,
  localStorage:{ getItem:()=>null, setItem(){} }, location:{ hash:'' }, Date, Map, Set, JSON, Math, String, Number, Object, Array,
  parseInt, isNaN, fetch: (url, opts) => fetch('http://127.0.0.1:8765' + url, opts), window:{ addEventListener(){} } };
ctx.globalThis = ctx;
vm.createContext(ctx);
vm.runInContext(fs.readFileSync('static/app.js','utf8'), ctx, { filename:'app.js' });
const run = (code) => vm.runInContext(code, ctx);
const checks = [];
const check = (n, ok) => checks.push([n, ok]);

setTimeout(async () => {
  // 控制条应按服务端状态回填
  check('开关状态与服务端一致（已开启）', els['auto-toggle'].checked === true);
  check('间隔回填为 3600', String(els['auto-interval'].value) === '3600');
  const status = String(els['auto-status'].textContent);
  check('状态文案含「每 1 小时」', status.includes('每 1 小时'));
  check('状态文案含倒计时', /下次 .*后/.test(status));
  check('状态文案含已跑次数', /已自动扫描 \d+ 次/.test(status));

  // 关掉 → 再打开，走真实 API
  els['auto-toggle'].checked = false;
  await run('saveAuto({ enabled: false })');
  let a = await (await fetch('http://127.0.0.1:8765/api/auto')).json();
  check('通过界面关闭后服务端也关了', a.auto.enabled === false && a.auto.next_run_in === null);
  check('关闭后文案提示未开启', String(els['auto-status'].textContent).includes('未开启'));

  await run('saveAuto({ enabled: true })');
  a = await (await fetch('http://127.0.0.1:8765/api/auto')).json();
  check('重新打开后服务端排期恢复', a.auto.enabled === true && a.auto.next_run_in > 3500);
  check('倒计时被重置到约 1 小时', /下次 (1 小时 00 分|59 分 \d\d 秒)/.test(String(els['auto-status'].textContent)));

  // 点「立即扫描一次」按钮（走真实的点击回调）
  const btns = els['auto-run-now']._handlers.click || [];
  check('按钮绑定了 click 回调', btns.length === 1);
  await btns[0]();
  await new Promise(r => setTimeout(r, 600));
  const startedId = run('state.scanId');
  check('点击后前端接上了扫描任务', !!startedId);
  const st = await (await fetch('http://127.0.0.1:8765/api/status')).json();
  check('服务端确实在跑这次扫描', st.active_scan === startedId);

  // 清理：跑完把间隔恢复成 1 小时，避免测试留下 60 秒排期
  await fetch('http://127.0.0.1:8765/api/auto', { method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({ enabled: true, interval: 3600, subnet: '10.0.0.0/24', options: { profile: 'fast' } }) });

  let failed = 0;
  for (const [n, ok] of checks) { console.log((ok ? '✅' : '❌') + ' ' + n); if (!ok) failed++; }
  console.log(failed ? `\n${failed} 项失败` : '\n全部通过');
  process.exit(failed ? 1 : 0);
}, 800);
