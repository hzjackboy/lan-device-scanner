// 认证的联调测试：打真实后端，覆盖登录 / 强制改密 / 角色边界 / CSRF / 会话。
//
// 注意：这个文件**故意不用 tests/_auth_shim.js**——它要测的正是「没带令牌会怎样」。
// 需要认证的步骤自己显式带令牌或走会话 Cookie。
//
// 也不能假设服务上的 admin 还是默认密码（真实部署早就改过了），
// 所以这里用本地令牌临时建一个账号来测完整流程，跑完删掉。

const fs = require('fs');
const path = require('path');

const BASE = (process.env.LAN_SCAN_URL || 'http://127.0.0.1:8765').replace(/\/$/, '');
const TOKEN = (() => {
  try {
    return JSON.parse(fs.readFileSync(path.join(__dirname, '..', 'data', 'local_token'), 'utf8')).token;
  } catch (_) { return ''; }
})();

const checks = [];
const check = (name, ok) => checks.push([name, !!ok]);

// ---- 极简 cookie jar：node 的 fetch 不会自动管 Cookie ----
let jar = '';
function absorb(res) {
  const raw = typeof res.headers.getSetCookie === 'function'
    ? res.headers.getSetCookie()
    : [res.headers.get('set-cookie')].filter(Boolean);
  for (const line of raw) {
    const pair = String(line).split(';')[0];
    if (pair.startsWith('lanscan_session=')) {
      jar = pair.endsWith('=') ? '' : pair;
    }
  }
  return res;
}

function req(method, url, { body, token, origin, cookie } = {}) {
  const headers = {};
  if (body !== undefined) headers['Content-Type'] = 'application/json';
  if (token) headers['X-Local-Token'] = token;
  if (origin) headers.Origin = origin;
  const useCookie = cookie !== undefined ? cookie : jar;
  if (useCookie) headers.Cookie = useCookie;
  return fetch(BASE + url, {
    method,
    headers,
    body: body === undefined ? undefined : JSON.stringify(body),
    redirect: 'manual',
  }).then(absorb);
}

const json = async (res) => { try { return await res.json(); } catch (_) { return {}; } };

async function main() {
  const suffix = Math.random().toString(36).slice(2, 8);
  const username = 't_' + suffix;
  const initialPw = 'Init-Pass-' + suffix;
  const finalPw = 'Final-Pass-' + suffix;

  // ---- 1. 未登录时的边界 ----
  jar = '';
  check('未登录访问首页返回 200（否则登录页加载不出来）',
    (await req('GET', '/')).status === 200);
  check('未登录访问 /static/app.js 返回 200',
    (await req('GET', '/static/app.js')).status === 200);
  check('/api/auth/state 未登录也放行', (await req('GET', '/api/auth/state')).status === 200);

  for (const p of ['/api/status', '/api/devices', '/api/history', '/api/users', '/api/auto']) {
    const r = await req('GET', p);
    check(`未登录 GET ${p} → 401`, r.status === 401);
  }
  const unauth = await json(await req('GET', '/api/status'));
  check('401 带 code=unauthenticated', unauth.code === 'unauthenticated');
  check('401 响应不泄漏任何数据', !('interfaces' in unauth) && !('devices' in unauth));

  check('未登录 POST /api/scan → 401', (await req('POST', '/api/scan', { body: {} })).status === 401);

  // ---- 2. 本地令牌（同机命令行用） ----
  check('带正确本地令牌可访问 /api/status', (await req('GET', '/api/status', { token: TOKEN })).status === 200);
  check('带错误本地令牌被拒', (await req('GET', '/api/status', { token: 'not-the-token' })).status === 401);

  // ---- 3. 登录失败路径 ----
  jar = '';
  const wrongLogin = await req('POST', '/api/auth/login',
    { body: { username: username, password: 'definitely-wrong' } });
  check('不存在的用户登录 → 401', wrongLogin.status === 401);
  const wlBody = await json(wrongLogin);
  check('登录失败文案不区分「用户不存在」与「密码错」',
    typeof wlBody.error === 'string' && !/不存在|no such/i.test(wlBody.error));

  // ---- 4. 用本地令牌建一个必须改密的测试账号 ----
  const created = await req('POST', '/api/users',
    { token: TOKEN, body: { username, password: initialPw, role: 'viewer' } });
  const createdBody = await json(created);
  check('用本地令牌能创建账号', created.status === 201 && !!createdBody.user);
  check('接口返回的用户对象不含密码哈希',
    !JSON.stringify(createdBody).includes('scrypt'));

  // ---- 5. 首次登录 → 服务端强制先改密 ----
  jar = '';
  const login = await req('POST', '/api/auth/login', { body: { username, password: initialPw } });
  const loginBody = await json(login);
  check('新账号能登录', login.status === 200);
  check('新账号被标记必须改初始密码', loginBody.must_change_password === true);

  const blocked = await req('GET', '/api/devices');
  const blockedBody = await json(blocked);
  check('没改初始密码前访问业务接口 → 403', blocked.status === 403);
  check('403 带 code=password_change_required', blockedBody.code === 'password_change_required');

  // 弱密码要被拒
  const weak = await req('POST', '/api/auth/password', { body: { old: initialPw, new: 'short' } });
  check('强制改密时弱密码被拒', weak.status === 400);
  // 旧密码不对要被拒
  const wrongOld = await req('POST', '/api/auth/password', { body: { old: 'nope', new: finalPw } });
  check('强制改密时旧密码不对被拒', wrongOld.status === 400);

  // 合格密码：改完应立刻放行
  const changed = await req('POST', '/api/auth/password', { body: { old: initialPw, new: finalPw } });
  check('合格的新密码改密成功', changed.status === 200);
  check('改密后业务接口放行', (await req('GET', '/api/devices')).status === 200);

  // ---- 6. viewer 的角色边界 ----
  check('viewer 可以读台账', (await req('GET', '/api/devices')).status === 200);
  check('viewer 可以读历史', (await req('GET', '/api/history')).status === 200);
  check('viewer 不能看用户列表 → 403', (await req('GET', '/api/users')).status === 403);
  check('viewer 不能起扫描 → 403', (await req('POST', '/api/scan', { body: { subnet: '10.0.0.0/24' } })).status === 403);
  check('viewer 不能改设备 → 403', (await req('POST', '/api/devices/whatever', { body: { name: 'x' } })).status === 403);
  check('viewer 不能删设备 → 403', (await req('DELETE', '/api/devices/whatever')).status === 403);
  check('viewer 不能改定时重扫 → 403', (await req('POST', '/api/auto', { body: { enabled: false } })).status === 403);
  check('viewer 不能建用户 → 403',
    (await req('POST', '/api/users', { body: { username: 'x_' + suffix, password: 'Whatever-123', role: 'viewer' } })).status === 403);

  // ---- 7. CSRF：跨站 Origin 一律拒绝 ----
  const csrf = await req('POST', '/api/auth/logout', { origin: 'http://evil.example' });
  check('跨站 Origin 的改状态请求被拒 → 403', csrf.status === 403);
  check('跨站请求不影响当前会话（同源请求仍可）', (await req('GET', '/api/devices')).status === 200);

  // ---- 8. 登出 ----
  const logout = await req('POST', '/api/auth/logout');
  check('登出返回 200', logout.status === 200);
  check('登出后会话失效 → 401', (await req('GET', '/api/devices')).status === 401);

  // ---- 9. 旧密码失效 ----
  const oldLogin = await req('POST', '/api/auth/login', { body: { username, password: initialPw } });
  check('改密后旧密码不能登录 → 401', oldLogin.status === 401);
  const newLogin = await req('POST', '/api/auth/login', { body: { username, password: finalPw } });
  check('改密后新密码可以登录', newLogin.status === 200);

  // ---- 10. 清理：删掉测试账号 ----
  const del = await req('DELETE', '/api/users/' + encodeURIComponent(username), { token: TOKEN });
  check('测试账号已清理', del.status === 200);
  check('清理后该账号无法登录',
    (await req('POST', '/api/auth/login', { body: { username, password: finalPw } })).status === 401);

  let failed = 0;
  for (const [name, ok] of checks) {
    console.log((ok ? '✅ ' : '❌ ') + name);
    if (!ok) failed++;
  }
  console.log(failed ? `\n${failed} 项失败` : `\n全部通过（${checks.length} 项）`);
  process.exit(failed ? 1 : 0);
}

main().catch((err) => { console.error('测试异常：', err); process.exit(1); });
