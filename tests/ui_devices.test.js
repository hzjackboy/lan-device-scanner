// 设备管理页完整测试：分组/筛选/编辑/星标 + 行内删除/多选/批量清除离线
const fs = require('fs'), vm = require('vm');
function makeEl(id) {
  const el = { id, innerHTML:'', textContent:'', value:'', checked:false, indeterminate:false, disabled:false,
    title:'', hidden:false, scrollTop:0, scrollHeight:100, dataset:{}, style:{}, options:[],
    _handlers:{}, addEventListener(t,f){ (this._handlers[t]=this._handlers[t]||[]).push(f); },
    appendChild(){}, showModal(){ this.opened=true; }, close(){ this.opened=false; },
    querySelectorAll(){return[];}, querySelector(){return null;},
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

let RECORDS = [
  { key:'AA:BB:CC:00:00:01', mac:'AA:BB:CC:00:00:01', ip:'10.0.0.1', ips:['10.0.0.1'], vendor:'iKuai', hostname:'gateway',
    name:'主路由', custom_name:'主路由', auto_kind:'路由器 / 网关', kind:'路由器 / 网关', category:'路由器 / 网络',
    location:'弱电箱', tags:['常驻'], note:'', starred:true, ignored:false, edited:true, ports:[80,443], services:[],
    iface:'en0', first_seen:1700000000, last_seen:Date.now()/1000, seen_count:12, online:true, offline_since:null },
  { key:'AA:BB:CC:00:00:02', mac:'AA:BB:CC:00:00:02', ip:'10.0.0.57', ips:['10.0.0.57','10.0.0.58'], vendor:'Espressif', hostname:'led-strip',
    name:'厨房灯', custom_name:'厨房灯', auto_kind:'智能灯', kind:'智能灯', category:'智能家居',
    location:'厨房', tags:['灯','ESPHome'], note:'灯带控制器', starred:false, ignored:false, edited:true, ports:[80], services:['esphomelib'],
    iface:'en0', first_seen:1700000000, last_seen:Date.now()/1000-7200, seen_count:8, online:false, offline_since:Date.now()/1000-7200 },
  { key:'AA:BB:CC:00:00:03', mac:'AA:BB:CC:00:00:03', ip:'10.0.0.99', ips:['10.0.0.99'], vendor:'未知厂商', hostname:'',
    name:'神秘设备', custom_name:'', auto_kind:'未知设备', kind:'未知设备', category:'未分类',
    location:'', tags:[], note:'', starred:false, ignored:true, edited:false, ports:[], services:[],
    iface:'', first_seen:1700000000, last_seen:Date.now()/1000, seen_count:1, online:true, offline_since:null },
];
const bulkCalls = [];
const calls = [];
const CATS = ['未分类','电脑','手机 / 平板','路由器 / 网络','智能家居','摄像头 / 安防','打印机','存储 / NAS','影音设备','其他'];
const stats = () => ({ total:RECORDS.length, online:RECORDS.filter(r=>r.online).length,
  offline:RECORDS.filter(r=>!r.online).length, edited:RECORDS.filter(r=>r.edited).length,
  starred:RECORDS.filter(r=>r.starred).length, ignored:RECORDS.filter(r=>r.ignored).length,
  categories:{}, updated_at: Date.now()/1000 });
const okJson = (o) => Promise.resolve({ ok:true, json: async () => o });

const ctx = { document, console, setTimeout, clearTimeout, setInterval, clearInterval,
  localStorage:{ getItem:()=>null, setItem(){} }, location:{ hash:'' }, Date, Map, Set, JSON, Math, String,
  Number, Object, Array, parseInt, isNaN,
  fetch: (url, opts) => {
    const u = String(url);
    calls.push({ url:u, method:(opts&&opts.method)||'GET', body:opts&&opts.body });
    if (u.includes('/api/devices/bulk-delete')) {
      const body = JSON.parse(opts.body);
      bulkCalls.push(body);
      let n = 0;
      if (body.keys) { const before = RECORDS.length; RECORDS = RECORDS.filter(r=>!body.keys.includes(r.key)); n = before - RECORDS.length; }
      else if (body.scope === 'offline') { const before = RECORDS.length; RECORDS = RECORDS.filter(r=>r.online); n = before - RECORDS.length; }
      return okJson({ ok:true, deleted:n, stats:stats() });
    }
    if (u.startsWith('/api/devices/')) {
      const key = decodeURIComponent(u.split('/api/devices/')[1]);
      if ((opts && opts.method) === 'POST') {
        const patch = JSON.parse(opts.body);
        const rec = RECORDS.find(r=>r.key===key);
        if (rec) {
          if (patch.name !== undefined) { rec.custom_name = patch.name; rec.name = patch.name || rec.hostname || rec.vendor; }
          if (patch.category !== undefined) rec.category = patch.category;
          if (patch.location !== undefined) rec.location = patch.location;
          if (patch.ignored !== undefined) rec.ignored = patch.ignored;
          if (patch.kind !== undefined) rec.kind = patch.kind || rec.auto_kind;
          if (patch.icon !== undefined) rec.icon = patch.icon;
        }
        return okJson({ ok:true, device: rec });
      }
      return okJson({ ok:true, device: RECORDS.find(r=>r.key===key) });
    }
    // 模拟服务端 apply_to_snapshot：把台账里的人工信息贴到扫描结果上
    if (u.startsWith('/api/scan/')) {
      return okJson({ ok:true, scan: {
        id: u.split('/api/scan/')[1], subnet:'10.0.0.0/24', state:'done', phase:'完成', error:'',
        progress:{done:254,total:254,percent:100}, started_at:1700000000, finished_at:1700000010,
        duration:9, total_hosts:254, options:{}, version:9, logs:[],
        stats:{ total:RECORDS.length, online:RECORDS.filter(r=>r.online).length, arp_only:0,
                with_mac:RECORDS.length, named:RECORDS.length, kinds:{}, vendors:{} },
        devices: RECORDS.map(r => ({
          ip:r.ip, mac:r.mac, vendor:r.vendor, hostname:r.hostname,
          alias:r.custom_name || '', category:r.category,
          kind:(r.kind && r.kind !== r.auto_kind) ? r.kind : r.auto_kind,
          starred:!!r.starred, ignored:!!r.ignored, managed:true, icon:r.icon||'',
          ports:r.ports||[], services:r.services||[], rtt_ms:1, iface:r.iface||'en0',
          online:r.online, confirmed:true, only_arp:false, sources:['arp'], note:'',
          last_seen:r.last_seen, extra:{},
        })),
      }});
    }
    return okJson({ ok:true, devices:RECORDS, stats:stats(), categories:CATS });
  },
  window:{ addEventListener(){}, location:{}, confirm:()=>true } };
ctx.globalThis = ctx;
vm.createContext(ctx);
vm.runInContext(fs.readFileSync('static/app.js','utf8'), ctx, { filename:'app.js' });
const run = (c) => vm.runInContext(c, ctx);
const checks = []; const check = (n, ok) => checks.push([n, ok]);

(async () => {
  await ctx.loadDevices();
  // ---- 基础 ----
  check('统计卡正确', els['dev-total'].textContent===3 && els['dev-offline'].textContent===1);
  check('侧边栏角标', String(els['nav-devices-badge'].textContent)==='3');
  let rows = els['dev-body'].innerHTML;
  check('默认按分类分组', (rows.match(/class="group-row"/g)||[]).length===3);
  check('分组行跨 12 列', rows.includes('colspan="12"'));
  check('掉线设备仍在列表', rows.includes('厨房灯') && rows.includes('已掉线'));
  check('忽略设备有标记', rows.includes('已忽略'));

  // ---- 新增：每行都有勾选框和删除按钮 ----
  check('每行都有勾选框', (rows.match(/class="row-check"/g)||[]).length===3);
  check('每行都有删除按钮', (rows.match(/data-action="delete"/g)||[]).length===3);
  check('每行都有编辑/详情', (rows.match(/data-action="edit"/g)||[]).length===3 && (rows.match(/data-action="detail"/g)||[]).length===3);
  check('删除按钮是危险色', rows.includes('mini danger'));
  check('初始「删除选中」不可点', els['dev-delete-selected'].disabled===true);

  // ---- 新增：勾选不打开编辑弹窗 ----
  const rowEl = { dataset:{ key:'AA:BB:CC:00:00:01' }, classList:{ _s:new Set(), toggle(c,on){ on?this._s.add(c):this._s.delete(c); } } };
  const box = { checked:true, closest:(sel)=> sel==='input.row-check' ? box : null };
  ctx.onDeviceRowClick({ target:{ closest:(sel)=> sel==='tr.dev-row' ? rowEl : (sel==='input.row-check' ? box : null) } });
  check('勾选写入选中集合', run("state.devSelected.has('AA:BB:CC:00:00:01')")===true);
  check('勾选不会打开编辑弹窗', !els['edit-dialog'].opened);
  check('选中行有高亮类', rowEl.classList._s.has('picked'));
  check('「删除选中」变为可用并显示数量', els['dev-delete-selected'].disabled===false && els['dev-delete-selected'].textContent.includes('1'));

  // ---- 新增：全选（只作用于当前筛选）----
  els['dev-check-all']._handlers.change[0]({ target:{ checked:true } });
  check('全选选中所有可见设备', run('state.devSelected.size')===3);
  check('全选后勾选框为选中态', els['dev-check-all'].checked===true && els['dev-check-all'].indeterminate===false);
  run("state.devState='offline'"); ctx.renderDevices();
  check('筛选后全选框跟随可见行（都选中=选中）', els['dev-check-all'].checked===true && els['dev-check-all'].indeterminate===false);
  run("state.devState='all'; state.devSelected.delete('AA:BB:CC:00:00:02')"); ctx.renderDevices();
  check('部分选中时显示半选态', els['dev-check-all'].indeterminate===true && els['dev-check-all'].checked===false);
  els['dev-check-all']._handlers.change[0]({ target:{ checked:false } });
  check('取消全选清空选中', run('state.devSelected.size')===0 && els['dev-delete-selected'].disabled===true);

  // ---- 新增：单行删除 ----
  bulkCalls.length = 0;
  els['edit-dialog'].opened = false;
  await ctx.deleteDevices(['AA:BB:CC:00:00:03'], '神秘设备');
  check('单行删除走 bulk-delete 接口', bulkCalls.length===1 && bulkCalls[0].keys.length===1);
  check('删除后从台账消失', !RECORDS.some(r=>r.key==='AA:BB:CC:00:00:03'));
  check('删除后表格刷新为 2 行', (els['dev-body'].innerHTML.match(/class="dev-card/g)||[]).length===0
        && (els['dev-body'].innerHTML.match(/class="row-check"/g)||[]).length===2);

  // ---- 新增：批量删除选中 ----
  await ctx.loadDevices();
  run("state.devSelected.add('AA:BB:CC:00:00:01'); state.devSelected.add('AA:BB:CC:00:00:02')");
  ctx.renderDevices();
  bulkCalls.length = 0;
  els['dev-delete-selected']._handlers.click[0]();
  await new Promise(r=>setTimeout(r,60));
  check('批量删除提交全部选中 key', bulkCalls.length===1 && bulkCalls[0].keys.length===2);
  check('批量删除后台账清空', RECORDS.length===0);
  check('删除后选中集合被清空', run('state.devSelected.size')===0);

  // ---- 新增：一键清除离线 ----
  RECORDS = [
    { key:'K1', mac:'K1', ip:'10.0.0.1', ips:['10.0.0.1'], vendor:'V', hostname:'', name:'在线设备', custom_name:'',
      auto_kind:'智能灯', kind:'智能灯', category:'智能家居', location:'', tags:[], note:'', starred:false, ignored:false,
      edited:false, ports:[], services:[], iface:'', first_seen:1, last_seen:Date.now()/1000, seen_count:1, online:true, offline_since:null },
    { key:'K2', mac:'K2', ip:'10.0.0.2', ips:['10.0.0.2'], vendor:'V', hostname:'', name:'掉线设备', custom_name:'',
      auto_kind:'智能灯', kind:'智能灯', category:'智能家居', location:'', tags:[], note:'', starred:false, ignored:false,
      edited:false, ports:[], services:[], iface:'', first_seen:1, last_seen:Date.now()/1000-90000, seen_count:1, online:false, offline_since:Date.now()/1000-90000 },
  ];
  await ctx.loadDevices();
  bulkCalls.length = 0;
  els['dev-delete-offline']._handlers.click[0]();
  await new Promise(r=>setTimeout(r,60));
  check('清除离线提交 scope=offline', bulkCalls.length===1 && bulkCalls[0].scope==='offline');
  check('只删掉离线的，在线设备保留', RECORDS.length===1 && RECORDS[0].key==='K1');
  check('没有离线设备时给出提示', typeof (await ctx.deleteOfflineDevices()) === 'undefined');

  // ---- 编辑弹窗里的删除也走同一入口 ----
  await ctx.loadDevices();
  ctx.openDeviceEditor(RECORDS[0]);
  bulkCalls.length = 0;
  await ctx.deleteDeviceRecord();
  check('弹窗删除走 bulk-delete', bulkCalls.length===1 && bulkCalls[0].keys[0]==='K1');
  check('弹窗删除后关闭弹窗', els['edit-dialog'].opened===false);

  // ---- 回归：改名后首页方块墙要跟着变（曾经不同步的 bug）----
  RECORDS = [
    { key:'AA:BB:CC:00:00:01', mac:'AA:BB:CC:00:00:01', ip:'10.0.0.1', ips:['10.0.0.1'], vendor:'iKuai', hostname:'gateway',
      name:'主路由', custom_name:'主路由', auto_kind:'路由器 / 网关', kind:'路由器 / 网关', category:'路由器 / 网络',
      location:'', tags:[], note:'', starred:false, ignored:false, edited:true, ports:[80], services:[],
      iface:'en0', first_seen:1, last_seen:Date.now()/1000, seen_count:1, online:true, offline_since:null },
  ];
  await ctx.loadDevices();
  const snap1 = await (await ctx.fetch('/api/scan/scan-1')).json();
  ctx.applySnapshot(snap1.scan);
  check('首页先显示旧别名', els['home-grid'].innerHTML.includes('主路由'));
  check('applySnapshot 记录了 scanId', run('state.scanId') === 'scan-1');

  ctx.openDeviceEditor(RECORDS[0]);
  els['edit-name'].value = '客厅主路由';
  await ctx.saveDeviceEdit();
  check('首页方块墙同步显示新别名', els['home-grid'].innerHTML.includes('客厅主路由'));
  check('首页不再显示旧别名', !els['home-grid'].innerHTML.includes('>主路由<'));
  check('结果表也同步了', els['results-body'].innerHTML.includes('客厅主路由'));

  // 忽略开关也要同步到首页（被忽略的设备不上方块墙）
  RECORDS[0].ignored = true;
  await ctx.refreshManaged();
  check('标记忽略后首页不再显示该设备', !els['home-grid'].innerHTML.includes('客厅主路由'));

  // ---------- 图标编辑 ----------
  RECORDS[0].ignored = false;
  delete RECORDS[0].icon;
  await ctx.loadDevices();

  // 打开弹窗时应把已有图标填进输入框，并把选择器画出来
  ctx.openDeviceEditor(RECORDS[0]);
  check('没设图标时输入框为空', els['edit-icon'].value === '');
  check('图标选择器渲染出按钮', els['icon-pick'].innerHTML.includes('class="icon-chip'));
  check('图标选择器含自动识别那套图标', els['icon-pick'].innerHTML.includes('📡'));

  // 点调色板里的图标 → 高亮
  els['edit-icon'].value = '🗄';
  ctx.renderIconPicker();
  check('选中调色板里的图标会高亮', /class="icon-chip sel" data-icon="🗄"/.test(els['icon-pick'].innerHTML));

  // 也允许手输/粘贴调色板里没有的 emoji：不高亮，但要能存下来
  els['edit-icon'].value = '🦊';
  ctx.renderIconPicker();
  check('调色板外的自定义 emoji 不高亮但仍可用', !els['icon-pick'].innerHTML.includes('icon-chip sel'));

  // 保存要把 icon 一起发给后端
  calls.length = 0;
  await ctx.saveDeviceEdit();
  const saveCall = calls.find(c => c.method === 'POST' && c.url.includes('/api/devices/'));
  check('保存请求带上了 icon', !!saveCall && JSON.parse(saveCall.body).icon === '🦊');
  check('后端记录里存下了图标', RECORDS[0].icon === '🦊');

  // 人工图标要盖过自动识别（这台是 iKuai 路由器，自动识别是 📡）
  await ctx.loadDevices();
  check('列表里显示人工图标而不是自动图标',
    els['dev-body'].innerHTML.includes('🦊') && !els['dev-body'].innerHTML.includes('📡'));

  // 重新打开弹窗，应回填已保存的图标
  ctx.openDeviceEditor(RECORDS[0]);
  check('重开弹窗回填人工图标', els['edit-icon'].value === '🦊');

  // 「用自动识别」清空
  els['edit-icon'].value = '';
  ctx.renderIconPicker();
  check('清空后没有高亮项', !els['icon-pick'].innerHTML.includes('icon-chip sel'));

  let failed = 0;
  for (const [n, ok] of checks) { console.log((ok ? '✅' : '❌') + ' ' + n); if (!ok) failed++; }
  console.log(failed ? `\n${failed} 项失败` : '\n全部通过');
  process.exit(failed ? 1 : 0);
})();
