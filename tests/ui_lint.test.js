// 前端静态自检：不需要起服务，也不跑业务逻辑，
// 专门抓那些「运行时不报错、但结果悄悄不对」的问题。
//
// 两条规则都是踩过坑才加的：
//   1) 同名的顶层函数会被后声明的覆盖。之前给用户表写了个 fmtTime，
//      结果被历史表格那个 fmtTime 顶掉，空值没兜住，页面显示 1970 年的 08:00:00。
//   2) $('xxx') 里的 id 必须在 index.html 里真实存在，
//      否则那一整段 UI 静默不工作（比如只读模式下按 id 隐藏按钮，写错就永远藏不掉）。

const fs = require('fs');
const path = require('path');

const ROOT = path.join(__dirname, '..');
const JS = fs.readFileSync(path.join(ROOT, 'static/app.js'), 'utf8');
const HTML = fs.readFileSync(path.join(ROOT, 'static/index.html'), 'utf8');
const CSS = fs.readFileSync(path.join(ROOT, 'static/style.css'), 'utf8');

const checks = [];
const check = (name, ok) => checks.push([name, !!ok]);

// ---------- 1. 顶层函数 / 常量不能重名 ----------
const seen = new Map();
const dups = [];
for (const m of JS.matchAll(/^(?:async\s+)?function\s+([A-Za-z_$][\w$]*)/gm)) {
  const name = m[1];
  if (seen.has(name)) dups.push(name);
  seen.set(name, true);
}
check('app.js 没有重名的顶层函数' + (dups.length ? `（重复：${[...new Set(dups)].join(', ')}）` : ''), dups.length === 0);

// ---------- 2. $('id') 引用的元素必须存在 ----------
const ids = new Set([...JS.matchAll(/\$\('([a-zA-Z0-9_-]+)'\)/g)].map((m) => m[1]));
const missing = [...ids].filter((id) => !HTML.includes(`id="${id}"`));
check(`app.js 引用的 ${ids.size} 个 id 在 index.html 里都存在`
  + (missing.length ? `（缺失：${missing.join(', ')}）` : ''), missing.length === 0);

// ---------- 3. 只读模式要隐藏的选择器必须命中真实元素 ----------
const readonlySels = [...CSS.matchAll(/\.app\.readonly\s+(#[A-Za-z0-9_-]+)/g)].map((m) => m[1]);
const readonlyMissing = readonlySels.filter((sel) => !HTML.includes(`id="${sel.slice(1)}"`));
check(`只读模式下按 id 隐藏的 ${readonlySels.length} 个控件都真实存在`
  + (readonlyMissing.length ? `（缺失：${readonlyMissing.join(', ')}）` : ''), readonlyMissing.length === 0);

// ---------- 4. 视图与侧边栏入口要配套 ----------
const viewNames = [...HTML.matchAll(/<section class="view" id="view-([a-z]+)"/g)].map((m) => m[1]);
const navNames = [...HTML.matchAll(/class="nav-item"[^>]*data-view="([a-z]+)"/g)].map((m) => m[1]);
const noNav = viewNames.filter((v) => !navNames.includes(v));
const noView = navNames.filter((v) => !viewNames.includes(v));
check(`每个视图都有侧边栏入口（视图 ${viewNames.length} / 入口 ${navNames.length}）`
  + (noNav.length ? `（缺入口：${noNav.join(', ')}）` : ''), noNav.length === 0);
check('每个侧边栏入口都有对应视图'
  + (noView.length ? `（缺视图：${noView.join(', ')}）` : ''), noView.length === 0);

// ---------- 5. 登录页要用的元素齐不齐 ----------
for (const id of ['auth-gate', 'login-form', 'login-user', 'login-pass', 'login-submit',
  'force-form', 'force-old', 'force-new', 'force-new2', 'force-submit',
  'sidebar-user', 'logout-btn', 'nav-users', 'view-users', 'user-rows']) {
  check(`认证/用户管理所需元素存在：#${id}`, HTML.includes(`id="${id}"`));
}

// ---------- 6. 用户表的列要对得上 ----------
// 表头 <th> 数量必须等于 renderUsers 里渲染的 <td> 数量，
// 否则整个表格会错位（而且看起来「只是有点歪」，不容易发现）。
function countMatches(text, re) { return [...text.matchAll(re)].length; }

const userTableHead = HTML.slice(HTML.indexOf('id="user-table"'));
// 注意用 /<th[\s>]/：直接的 /<th/ 会把 <thead> 也算进去
const thCount = countMatches(userTableHead.slice(0, userTableHead.indexOf('</thead>')), /<th[\s>]/g);

const renderFn = JS.slice(JS.indexOf('function renderUsers()'));
const tmpl = renderFn.slice(renderFn.indexOf('tr.innerHTML = `') , renderFn.indexOf('`;', renderFn.indexOf('tr.innerHTML = `')));
const tdCount = countMatches(tmpl, /<td/g);

check(`用户表表头 ${thCount} 列 = 渲染 ${tdCount} 个单元格`, thCount === tdCount && thCount > 0);

// 表格里按类名收起的列，类名必须在表头里真实存在（写错就会永远收不掉）
const colSels = [...CSS.matchAll(/#user-table\s+\.(col-[a-z-]+)/g)].map((m) => m[1]);
const colMissing = colSels.filter((cls) => !userTableHead.includes(`class="${cls}"`) && !userTableHead.includes(cls));
check(`窄屏收起的 ${colSels.length} 个列类名都存在（${colSels.join(', ')}）`, colMissing.length === 0);

// ---------- 7. 前端不能出现明文凭据 ----------
check('前端代码里没有硬编码密码', !/password\s*[:=]\s*['"][^'"]+['"]/i.test(JS));
check('前端只有默认账号的提示文案，没有默认密码逻辑',
  !/localStorage.*password|sessionStorage.*password/i.test(JS));

let failed = 0;
for (const [name, ok] of checks) {
  console.log((ok ? '✅ ' : '❌ ') + name);
  if (!ok) failed++;
}
console.log(failed ? `\n${failed} 项失败` : `\n全部通过（${checks.length} 项）`);
process.exit(failed ? 1 : 0);
