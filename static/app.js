/* 局域网设备扫描 —— 前端逻辑（无依赖） */
'use strict';

const PORT_NAMES = {
  9: '丢弃', 21: 'FTP', 22: 'SSH', 23: 'Telnet', 25: 'SMTP', 53: 'DNS',
  80: 'HTTP', 111: 'rpcbind', 135: 'MSRPC', 139: 'NetBIOS', 161: 'SNMP',
  443: 'HTTPS', 445: 'SMB', 515: 'LPD 打印', 548: 'AFP', 554: 'RTSP 视频',
  587: 'SMTP', 631: 'IPP 打印', 873: 'rsync', 902: 'VMware', 993: 'IMAPS',
  1080: 'SOCKS', 1194: 'OpenVPN', 1433: 'SQL Server', 1723: 'PPTP',
  1883: 'MQTT', 2049: 'NFS', 2375: 'Docker', 3000: 'Grafana/Node',
  3128: 'Squid', 3306: 'MySQL', 3389: '远程桌面', 5000: 'UPnP / Web',
  5001: 'Synology', 5060: 'SIP', 5357: 'WSD', 5432: 'PostgreSQL',
  5555: 'ADB', 5672: 'RabbitMQ', 5683: 'CoAP', 5900: 'VNC', 5984: 'CouchDB',
  6379: 'Redis', 6443: 'K8s API', 7000: 'AirPlay', 8000: 'HTTP-Alt',
  8008: 'Chromecast', 8009: 'Chromecast', 8060: 'Roku', 8080: 'HTTP-Alt',
  8081: 'HTTP-Alt', 8123: 'Home Assistant', 8443: 'HTTPS-Alt', 8883: 'MQTTS',
  8888: 'HTTP-Alt', 9000: 'Portainer', 9090: 'Prometheus', 9100: '打印',
  9200: 'Elasticsearch', 10000: 'Webmin', 11211: 'Memcached',
  27017: 'MongoDB', 32400: 'Plex', 37777: '大华私有', 49152: 'UPnP',
  49153: 'UPnP', 62078: 'iPhone 同步', 9999: 'TP-Link Kasa', 54321: '小米私有',
  6053: 'ESPHome API',
};

const SRC_NAMES = {
  'arp-cache': 'ARP缓存', arp: 'ARP', icmp: 'Ping', tcp: '端口',
  mdns: 'mDNS', dns: 'DNS', netbios: 'NetBIOS', demo: '演示',
};

const state = {
  scanId: null,
  snapshot: null,
  sortKey: 'ip',
  sortDesc: false,
  search: '',
  onlyOnline: true,
  knownIps: new Set(),
  es: null,
  pollTimer: null,
  tickTimer: null,
  profile: 'fast',
  subnetMapKey: '',
  view: 'scan',
  homeSearch: '',
  homeOnlyOnline: true,
  homeGroup: '',
  homeMode: 's',        // 首页展示方式：list / l / m / s
  homeSeen: new Set(),
  auto: null,
  autoDeadline: null,
  watchTimer: null,
  managed: [],          // 设备台账
  managedStats: null,
  categories: [],
  editingKey: null,
  devSearch: '',
  devState: 'all',
  devCategory: 'all',
  devGroup: 'category',
  devSort: 'ip',
  devSelected: new Set(),
};

/* 侧边栏导航：加新页面就在 VIEWS 里加一项 + 一个 section.view 即可 */
const VIEWS = {
  home: { title: '首页' },
  scan: { title: '设备扫描' },
  history: { title: '历史记录' },
  devices: { title: '设备管理' },
  users: { title: '用户管理', admin: true },
  about: { title: '关于与说明' },
};

/* ==================================================================
 *  认证
 *  服务端才是权威：未登录 401、必须先改密 403（code=password_change_required）。
 *  前端这里做的只是「把界面切到登录页」和「按角色藏掉按钮」，
 *  就算有人绕过这些，服务端一样会拦。
 * ================================================================== */
const AUTH = { user: null, ready: false };

function authRole() { return (AUTH.user && AUTH.user.role) || 'guest'; }
function isAdmin() { return authRole() === 'admin'; }

function showAuthGate(mode) {
  const gate = $('auth-gate');
  if (!mode) { gate.hidden = true; $('app').classList.remove('locked'); return; }
  gate.hidden = false;
  $('login-form').hidden = mode !== 'login';
  $('force-form').hidden = mode !== 'force';
  if (mode === 'login') {
    authError('login-error', null);
    setTimeout(() => { try { $('login-user').focus(); } catch (_) {} }, 30);
  } else {
    authError('force-error', null);
    setTimeout(() => { try { $('force-old').focus(); } catch (_) {} }, 30);
  }
}

function applyUser(user) {
  AUTH.user = user || null;
  AUTH.ready = true;
  const app = $('app');
  const name = (user && user.username) || '';
  const role = (user && user.role) || 'guest';

  $('sidebar-user').hidden = !name;
  $('user-name').textContent = name || '—';
  $('user-role').textContent = role === 'admin' ? '管理员'
    : (role === 'viewer' ? '只读账号' : role);
  $('user-avatar').textContent = (name || '?').slice(0, 1).toUpperCase();

  // 只读账号：藏掉所有会改数据的控件（服务端同样会拒）
  app.classList.toggle('readonly', !!name && role !== 'admin');
  // 「用户管理」只给管理员看
  $('nav-users').hidden = !(name && role === 'admin');
  if (name && role !== 'admin' && state.view === 'users') switchView('home');
}

async function refreshAuthState() {
  try {
    const res = await fetch('/api/auth/state');
    const data = await res.json();
    applyUser(data.user || null);
    if (data.version) $('auth-version').textContent = 'v' + data.version;
    if (!data.authenticated) return 'login';
    if (data.user && data.user.must_change_password) return 'force';
    return null;
  } catch (_) {
    return null;   // 服务不可达时别卡在登录页，走正常的报错路径
  }
}

/** 重跑当前视图的数据加载。
 *
 *  为什么需要它：init() 里 switchView() 跑在认证之前，那时 AUTH.user 还是空的，
 *  loadUsers() 会因为 isAdmin() 为 false 直接返回。认证完成后不补这一次，
 *  直接用 #/users 打开就会看到一张空表（而且只有管理员会踩到）。 */
function reloadCurrentView() {
  switch (state.view) {
    case 'users': loadUsers(); break;
    case 'devices': loadDevices(); break;
    case 'history': loadHistory(); break;
    case 'home': renderHome(); if (state.chartStats) renderChart(state.chartStats); break;
    case 'about': loadAbout(); break;
    default: break;
  }
}

/** 启动时决定：直接进应用，还是先过登录/改密闸门。 */
async function bootAuth() {
  const need = await refreshAuthState();
  showAuthGate(need);
  if (need === null) reloadCurrentView();
  return need === null;
}

function authError(elId, message) {
  const el = $(elId);
  if (!el) return;
  if (!message) { el.hidden = true; el.textContent = ''; return; }
  el.hidden = false;
  el.textContent = message;
}

async function doLogin(username, password) {
  const res = await fetch('/api/auth/login', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, password }),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    // 服务端只说「用户名或密码不对」，这里也别自作聪明地区分用户不存在
    authError('login-error', data.error || `登录失败（HTTP ${res.status}）`);
    return false;
  }
  applyUser(data.user || null);
  authError('login-error', null);
  $('login-pass').value = '';
  if (data.must_change_password) {
    showAuthGate('force');
  } else {
    showAuthGate(null);
    await afterLogin();
  }
  return true;
}

async function doLogout() {
  try {
    await fetch('/api/auth/logout', { method: 'POST' });
  } catch (_) { /* 网络断了也要把界面切回登录页 */ }
  applyUser(null);
  showAuthGate('login');
}

async function changePassword(oldPw, newPw, { errorId, onSuccess } = {}) {
  const res = await fetch('/api/auth/password', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ old: oldPw, new: newPw }),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    if (errorId) authError(errorId, data.error || `修改失败（HTTP ${res.status}）`);
    return { ok: false, error: data.error };
  }
  if (errorId) authError(errorId, null);
  await refreshAuthState();          // 服务端会发新令牌，同步一下角色/状态
  if (onSuccess) await onSuccess();
  return { ok: true };
}

/** 登录成功之后：拉一次状态、恢复轮询。 */
async function afterLogin() {
  try {
    const info = await (await fetch('/api/status')).json();
    $('version-badge').textContent = 'v' + info.version;
    $('foot-sub').textContent = 'v' + info.version;
    if (info.auto) renderAuto(info.auto);
    chartFromStatus(info);
  } catch (_) { /* 忽略：常规加载还会再试 */ }
  loadHistory();
  loadLatestResult();
  startServerWatch();
  reloadCurrentView();
}

function initAuthEvents() {
  $('login-form').addEventListener('submit', async (event) => {
    event.preventDefault();
    const btn = $('login-submit');
    btn.disabled = true;
    try {
      await doLogin($('login-user').value.trim(), $('login-pass').value);
    } finally {
      btn.disabled = false;
    }
  });

  $('force-form').addEventListener('submit', async (event) => {
    event.preventDefault();
    const next = $('force-new').value;
    if (next !== $('force-new2').value) {
      authError('force-error', '两次输入的新密码不一致');
      return;
    }
    const btn = $('force-submit');
    btn.disabled = true;
    try {
      const res = await changePassword($('force-old').value, next, { errorId: 'force-error' });
      if (res.ok) {
        $('force-old').value = $('force-new').value = $('force-new2').value = '';
        showAuthGate(null);
        toast('密码已更新');
        await afterLogin();
      }
    } finally {
      btn.disabled = false;
    }
  });

  $('force-logout').addEventListener('click', doLogout);
  $('logout-btn').addEventListener('click', () => {
    if (confirm('确定退出登录？')) doLogout();
  });

  // 任何接口返回 401/403 时统一切到登录页：包装 fetch，省得改二十个调用点
  const native = (typeof fetch === 'function') ? fetch.bind(globalThis) : null;
  if (native) {
    globalThis.fetch = async (input, init) => {
      const res = await native(input, init);
      try {
        const url = String((input && input.url) || input || '');
        if (!url.includes('/api/auth/') && typeof res.clone === 'function') {
          if (res.status === 401) {
            const body = await res.clone().json();
            if (body && body.code === 'unauthenticated') {
              applyUser(null);
              showAuthGate('login');
            }
          } else if (res.status === 403) {
            const body = await res.clone().json();
            if (body && body.code === 'password_change_required') showAuthGate('force');
          }
        }
      } catch (_) { /* 不是 JSON，忽略 */ }
      return res;
    };
  }
}

/* ------------------------- 用户管理 ------------------------- */

/** 台账/用户列表用的时间戳格式（带日期）。
 *
 *  名字不能叫 fmtTime：那份是历史表格用的「HH:MM:SS」版本，同名的顶层函数
 *  会被后声明的那个覆盖掉，用户表就会拿错格式化器——空值没兜住会显示成
 *  1970 年的 08:00:00。 */
function fmtStamp(ts) {
  if (!ts) return '—';
  const d = new Date(ts * 1000);
  const pad = (n) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} `
    + `${pad(d.getHours())}:${pad(d.getMinutes())}`;
}
function labelRole(role) { return role === 'admin' ? '管理员' : '只读'; }

let USERS = [];

async function loadUsers() {
  if (!isAdmin()) return;
  try {
    const data = await (await fetch('/api/users')).json();
    USERS = data.users || [];
    $('users-hint').textContent =
      `共 ${USERS.length} 个账号 · 管理员可以创建账号、重置密码、调整角色。`;
    renderUsers();
  } catch (err) {
    toast('读取用户列表失败：' + err.message);
  }
}

function renderUsers() {
  const tbody = $('user-rows');
  tbody.innerHTML = '';
  $('users-empty').hidden = USERS.length > 1;
  USERS.forEach((user) => {
    const tr = document.createElement('tr');
    const me = !!(AUTH.user && AUTH.user.username === user.username);
    const mustChange = user.must_change_password;
    tr.innerHTML = `
      <td>${esc(user.username)}${me ? ' <span class="muted">(我)</span>' : ''}</td>
      <td><span class="role-tag ${esc(user.role)}">${labelRole(user.role)}</span></td>
      <td><span class="state-tag ${mustChange ? 'warn' : ''}">${mustChange ? '待改初始密码' : '正常'}</span></td>
      <td class="muted">${fmtStamp(user.last_login)}</td>
      <td class="muted">${fmtStamp(user.created_at)}</td>
      <td class="col-actions">
        <div class="row-actions">
          <button data-act="reset" data-user="${esc(user.username)}">重置密码</button>
          <button data-act="role" data-user="${esc(user.username)}"
                  data-role="${user.role === 'admin' ? 'viewer' : 'admin'}">
            ${user.role === 'admin' ? '降为只读' : '设为管理员'}
          </button>
          <button data-act="delete" data-user="${esc(user.username)}" ${me ? 'disabled' : ''}>删除</button>
        </div>
      </td>`;
    tbody.appendChild(tr);
  });
  tbody.querySelectorAll('button[data-act]').forEach((btn) => {
    btn.addEventListener('click', () => onUserAction(btn.dataset.act, btn.dataset.user, btn.dataset.role));
  });
}

async function onUserAction(act, username, role) {
  if (act === 'delete') {
    if (!confirm(`确定删除账号「${username}」？该账号会立即被踢下线。`)) return;
    const res = await fetch('/api/users/' + encodeURIComponent(username), { method: 'DELETE' });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) { toast(data.error || '删除失败'); return; }
    USERS = data.users || [];
    renderUsers();
    toast(`已删除 ${username}`);
    return;
  }
  if (act === 'role') {
    const res = await fetch('/api/users/' + encodeURIComponent(username), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ action: 'set-role', role }),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) { toast(data.error || '修改角色失败'); return; }
    await loadUsers();
    toast(`${username} 现在是 ${labelRole(role)}`);
    return;
  }
  if (act === 'reset') openUserDialog('reset', username);
}

let userDialogMode = 'create';
let userDialogTarget = '';

function openUserDialog(mode, username = '') {
  userDialogMode = mode;
  userDialogTarget = username;
  const creating = mode === 'create';
  $('user-dialog-title').textContent = creating ? '新建用户' : `重置「${username}」的密码`;
  $('user-name-field').hidden = !creating;
  $('user-role-field').hidden = !creating;
  $('user-pass-label').textContent = creating ? '初始密码' : '新的初始密码';
  $('user-dialog-note').textContent = creating
    ? '新账号首次登录时会被要求修改这个初始密码。'
    : '重置后该账号的现有登录会立即失效，并需要再改一次密码。';
  $('user-name-input').value = '';
  $('user-role-input').value = 'viewer';
  $('user-pass-input').value = '';
  authError('user-dialog-error', null);
  $('user-dialog').showModal();
}

async function saveUserDialog() {
  const password = $('user-pass-input').value;
  if (userDialogMode === 'create') {
    const res = await fetch('/api/users', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        username: $('user-name-input').value.trim(),
        password,
        role: $('user-role-input').value,
      }),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) { authError('user-dialog-error', data.error || '创建失败'); return; }
    $('user-dialog').close();
    await loadUsers();
    toast(`已创建 ${data.user.username}`);
    return;
  }
  const res = await fetch('/api/users/' + encodeURIComponent(userDialogTarget), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ action: 'reset-password', password }),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) { authError('user-dialog-error', data.error || '重置失败'); return; }
  $('user-dialog').close();
  await loadUsers();
  toast(`已重置 ${userDialogTarget} 的密码`);
}

async function saveSelfPassword() {
  const msg = $('self-password-msg');
  const next = $('self-new').value;
  if (next !== $('self-new2').value) {
    msg.textContent = '两次输入的新密码不一致';
    return;
  }
  const res = await changePassword($('self-old').value, next, {});
  if (!res.ok) { msg.textContent = res.error || '修改失败'; return; }
  $('self-old').value = $('self-new').value = $('self-new2').value = '';
  msg.textContent = '密码已更新。';
  toast('密码已更新');
}

function initUsersView() {
  $('user-add-btn').addEventListener('click', () => openUserDialog('create'));
  $('user-dialog-close').addEventListener('click', () => $('user-dialog').close());
  $('user-dialog-cancel').addEventListener('click', () => $('user-dialog').close());
  $('user-dialog-save').addEventListener('click', saveUserDialog);
  $('self-save').addEventListener('click', saveSelfPassword);
}

/* 设备类型/名称/厂商 关键词 → 方块图标 */
const DEVICE_ICONS = [
  [['灯带', '智能灯', '灯', 'light', 'lamp', 'bulb'], '💡'],
  [['插座', 'plug', 'socket'], '🔌'],
  [['开关', 'switch'], '🎚'],
  [['摄像头', 'camera', 'cam', 'nvr', '监控'], '📷'],
  [['门铃', 'doorbell'], '🔔'],
  [['打印机', 'print'], '🖨'],
  [['扫描仪', 'scanner'], '🖨'],
  [['音箱', 'speaker', 'sonos', 'echo', 'soundbar'], '🔊'],
  [['投屏', 'chromecast'], '📺'],
  [['电视', 'tv', 'appletv', 'airplay'], '📺'],
  [['平板', 'ipad', 'tablet'], '📱'],
  [['手机', 'phone', 'iphone', 'android'], '📱'],
  [['手表', 'watch'], '⌚'],
  [['电脑', 'macbook', 'desktop', 'laptop', 'windows'], '💻'],
  [['服务器', 'server', 'linux'], '🖥'],
  [['nas', '文件服务器', '存储', 'storage'], '🗄'],
  [['树莓派', 'raspberry'], '🍓'],
  [['路由器', 'router', '网关', 'gateway', '无线'], '📡'],
  [['游戏机', 'xbox', 'playstation', 'nintendo'], '🎮'],
  [['虚拟机', 'qemu', 'vmware'], '📦'],
  [['中枢', 'home assistant', 'homeassistant'], '🏠'],
  [['门锁', 'lock'], '🔐'],
  [['传感器', 'sensor', '温控', 'thermo'], '🌡'],
  [['物联网', 'mqtt', 'iot', 'esp', '模块', '智能家居', 'homekit'], '🧩'],
];

// 手动选图标时的候选。用自动识别那套图标打底（保证风格一致），再补一些常用的。
const ICON_CHOICES = [
  ...new Set(DEVICE_ICONS.map(([, ico]) => ico)),
  '❔', '🖥', '📻', '🎵', '🎧', '☎️', '🗃', '💾', '🔋', '🌐',
  '🤖', '📊', '⌨️', '🖱', '🧊', '🚗', '👤', '🏢', '🔦', '🧯',
];

const API_DOCS = [
  ['POST', '/api/auth/login', '登录（JSON：username / password），成功下发 HttpOnly 会话 Cookie'],
  ['POST', '/api/auth/logout', '退出登录并作废当前会话'],
  ['GET', '/api/auth/state', '当前登录状态（<b>不需要登录也能调</b>，登录页靠它判断）'],
  ['POST', '/api/auth/password', '改自己的密码（JSON：old / new），成功后换发新会话'],
  ['GET', '/api/users', '用户列表（仅管理员）'],
  ['POST', '/api/users', '新建用户（仅管理员，JSON：username / password / role）'],
  ['POST', '/api/users/&lt;name&gt;', '改他人：action=reset-password | set-role（仅管理员）'],
  ['DELETE', '/api/users/&lt;name&gt;', '删除用户（仅管理员；不能删自己、不能删最后一个管理员）'],
  ['GET', '/api/status', '服务信息、本机网段、ping 是否可用'],
  ['GET', '/api/interfaces', '可扫描网段列表'],
  ['POST', '/api/scan', '启动扫描（subnet / profile / demo / ping / mdns / netbios / resolve_names）'],
  ['GET', '/api/scan/&lt;id&gt;', '当前快照：进度 + 设备列表 + 日志'],
  ['GET', '/api/scan/&lt;id&gt;/events', 'SSE 实时推送，每次变化推一个 event: scan'],
  ['DELETE', '/api/scan/&lt;id&gt;', '取消扫描'],
  ['GET', '/api/scan/&lt;id&gt;/export', '导出结果，format=csv 或 json'],
  ['GET', '/api/history', '最近 20 次扫描记录'],
  ['GET', '/api/oui', '按 MAC 查厂商'],
];

const $ = (id) => document.getElementById(id);

/* ------------------------- 工具 ------------------------- */
function toast(msg, ms = 2600) {
  const el = $('toast');
  el.textContent = msg;
  el.classList.add('show');
  clearTimeout(el._t);
  el._t = setTimeout(() => el.classList.remove('show'), ms);
}

function ipToInt(ip) {
  return ip.split('.').reduce((acc, part) => acc * 256 + (parseInt(part, 10) || 0), 0);
}

function fmtTime(ts) {
  const d = new Date(ts * 1000);
  const p = (n) => String(n).padStart(2, '0');
  return `${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`;
}

function fmtDate(ts) {
  const d = new Date(ts * 1000);
  const p = (n) => String(n).padStart(2, '0');
  return `${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`;
}

function fmtDuration(sec) {
  if (sec < 60) return sec.toFixed(1) + 's';
  const m = Math.floor(sec / 60);
  return `${m}m${Math.round(sec - m * 60)}s`;
}

function esc(text) {
  return String(text ?? '').replace(/[&<>"']/g, (c) => (
    { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]
  ));
}

/* ------------------------- 初始化 ------------------------- */
async function init() {
  bindEvents();
  initSidebar();
  initHomeMode();
  initAuthEvents();
  initUsersView();
  switchView(viewFromHash(), { push: false });

  // 没登录/没改初始密码就先停在闸门上：这时候去拉数据只会拿到 401
  if (!(await bootAuth())) return;

  try {
    const info = await (await fetch('/api/status')).json();
    $('version-badge').textContent = 'v' + info.version;
    $('foot-sub').textContent = 'v' + info.version;
    const ifaces = info.interfaces || [];
    const select = $('subnet-select');
    select.innerHTML = '';
    ifaces.forEach((iface) => {
      const opt = document.createElement('option');
      opt.value = iface.cidr;
      opt.textContent = `${iface.cidr}  ·  ${iface.name}${iface.is_default ? ' (默认)' : ''}`;
      select.appendChild(opt);
    });
    if (!ifaces.length) {
      const opt = document.createElement('option');
      opt.value = '';
      opt.textContent = '未检测到局域网网段';
      select.appendChild(opt);
    }
    $('subnet-input').value = ifaces.length ? ifaces[0].cidr : '';
    const own = ifaces.map((i) => i.ip).join(', ');
    $('host-info').textContent =
      `本机 ${own || '未知'} · ping ${info.has_ping ? '可用' : '不可用'} · 端口档位 快速 ${info.port_profiles.fast} / 完整 ${info.port_profiles.full}`;
    if (info.active_scan) attach(info.active_scan);
    if (info.auto) renderAuto(info.auto);
    chartFromStatus(info);
  } catch (err) {
    toast('无法连接扫描服务：' + err.message);
  }
  loadHistory();
  loadLatestResult();
  startServerWatch();
}

/* ------------------------- 首页：在线/离线饼图 ------------------------- */
const CHART_COLORS = { online: '#34d399', offline: '#f87171' };

function donutSvg(segments, size = 168, thickness = 20) {
  const total = segments.reduce((sum, s) => sum + s.value, 0);
  const radius = (size - thickness) / 2;
  const circumference = 2 * Math.PI * radius;
  const center = size / 2;
  let offset = 0;
  let arcs = `<circle class="donut-ring" cx="${center}" cy="${center}" r="${radius}" stroke-width="${thickness}"></circle>`;
  if (total > 0) {
    arcs += segments.filter((s) => s.value > 0).map((s) => {
      const length = (s.value / total) * circumference;
      const gap = Math.max(0, circumference - length);
      const el = `<circle class="donut-seg" cx="${center}" cy="${center}" r="${radius}" fill="none"
        stroke="${s.color}" stroke-width="${thickness}" stroke-linecap="butt"
        stroke-dasharray="${length.toFixed(2)} ${gap.toFixed(2)}"
        stroke-dashoffset="${(-offset).toFixed(2)}"
        transform="rotate(-90 ${center} ${center})"><title>${s.label}：${s.value} 台</title></circle>`;
      offset += length;
      return el;
    }).join('');
  }
  return `<svg viewBox="0 0 ${size} ${size}" role="img" aria-label="设备在线离线分布">${arcs}</svg>`;
}

function renderChart(stats) {
  const online = (stats && stats.online) || 0;
  const offline = (stats && stats.offline) || 0;
  const total = online + offline;
  const segments = [
    { key: 'online', label: '在线', value: online, color: CHART_COLORS.online },
    { key: 'offline', label: '已掉线', value: offline, color: CHART_COLORS.offline },
  ];
  $('donut').innerHTML = donutSvg(segments);
  $('donut-total').textContent = total;

  $('chart-legend').innerHTML = total === 0
    ? '<div class="legend-row" style="cursor:default"><span class="legend-name muted">台账里还没有设备</span></div>'
    : segments.map((s) => `
        <button class="legend-row" data-state="${s.key}" title="在设备管理里筛选${s.label}设备">
          <span class="legend-dot" style="background:${s.color}"></span>
          <span class="legend-name">${s.label}</span>
          <span class="legend-value">${s.value}</span>
          <span class="legend-pct">${total ? ((s.value / total) * 100).toFixed(1) : '0.0'}%</span>
        </button>`).join('');

  const bits = [];
  if (stats && stats.starred) bits.push(`已关注 ${stats.starred}`);
  if (stats && stats.ignored) bits.push(`已忽略 ${stats.ignored}`);
  if (stats && stats.updated_at) bits.push(`最近归档 ${fmtAgo(stats.updated_at)}`);
  $('chart-foot').textContent = total === 0
    ? '跑一次扫描后，扫到的设备会自动归档成台账'
    : bits.join(' · ') || '数据来自设备台账';

  state.chartStats = stats || null;
  state.chartTotal = total;
}

function chartFromStatus(info) {
  if (info && info.devices) renderChart(info.devices);
}

/* ------------------------- 定时重扫（服务端调度） ------------------------- */
function fmtInterval(seconds) {
  if (!seconds) return '—';
  if (seconds % 3600 === 0) return `${seconds / 3600} 小时`;
  return `${Math.round(seconds / 60)} 分钟`;
}

function fmtCountdown(seconds) {
  const s = Math.max(0, Math.round(seconds));
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = s % 60;
  if (h) return `${h} 小时 ${String(m).padStart(2, '0')} 分`;
  if (m) return `${m} 分 ${String(sec).padStart(2, '0')} 秒`;
  return `${sec} 秒`;
}

function renderAuto(auto) {
  state.auto = auto;
  $('auto-toggle').checked = !!auto.enabled;
  if (auto.interval) $('auto-interval').value = String(auto.interval);
  state.autoDeadline = (auto.enabled && auto.next_run_in !== null && auto.next_run_in !== undefined)
    ? Date.now() + auto.next_run_in * 1000
    : null;
  updateAutoText();
}

function updateAutoText() {
  const auto = state.auto;
  if (!auto) return;
  if (!auto.enabled) {
    $('auto-status').textContent = '未开启 — 打开后由服务端按时重扫，关掉本页也会继续';
    return;
  }
  const parts = [`每 ${fmtInterval(auto.interval)}扫一次`];
  if (state.autoDeadline) {
    parts.push(`下次 ${fmtCountdown((state.autoDeadline - Date.now()) / 1000)} 后`);
  }
  if (auto.last_run_at) parts.push(`上次 ${fmtTime(auto.last_run_at)}`);
  if (auto.run_count) parts.push(`已自动扫描 ${auto.run_count} 次`);
  $('auto-status').textContent = parts.join(' · ');
}

async function saveAuto(patch) {
  const payload = {
    interval: parseInt($('auto-interval').value, 10),
    subnet: $('subnet-input').value.trim(),
    options: {
      profile: state.profile,
      ping: $('opt-ping').checked,
      mdns: $('opt-mdns').checked,
      netbios: $('opt-netbios').checked,
      resolve_names: $('opt-dns').checked,
    },
    ...patch,
  };
  try {
    const res = await fetch('/api/auto', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    const data = await res.json();
    if (!res.ok || !data.ok) throw new Error(data.error || `HTTP ${res.status}`);
    renderAuto(data.auto);
    if (data.auto.enabled) {
      toast(`已开启：每 ${fmtInterval(data.auto.interval)}自动重扫 ${data.auto.subnet || ''}`);
    } else {
      toast('已关闭定时重扫');
    }
  } catch (err) {
    toast('设置失败：' + err.message);
    await refreshAuto();
  }
}

async function refreshAuto() {
  try {
    const data = await (await fetch('/api/auto')).json();
    if (data.auto) renderAuto(data.auto);
  } catch (_) { /* 忽略 */ }
}

/* 页面开着的时候盯着服务端：定时扫描一旦开始就自动接上实时推送，
   跑完了如果有更新的结果就自动换上。 */
function startServerWatch() {
  if (state.watchTimer) clearInterval(state.watchTimer);
  state.watchTimer = setInterval(watchServer, 10000);
}

async function watchServer() {
  if (document.hidden) return;
  let info;
  try {
    info = await (await fetch('/api/status')).json();
  } catch (_) {
    return;
  }
  if (info.auto) renderAuto(info.auto);
  chartFromStatus(info);

  if (info.active_scan && info.active_scan !== state.scanId) {
    state.subnetMapKey = '';
    attach(info.active_scan);
    toast('检测到后台定时扫描，已接上实时进度');
    return;
  }
  if (info.active_scan) return;

  // 没有在跑的任务：看看是不是有比当前更新的一次扫描结果
  try {
    const data = await (await fetch('/api/history')).json();
    const latest = (data.scans || []).find((s) => s.state === 'done' && s.stats.online > 0);
    if (!latest) return;
    const current = state.snapshot;
    if (current && latest.started_at <= current.started_at) return;
    const res = await fetch('/api/scan/' + latest.id);
    if (!res.ok) return;
    const snap = (await res.json()).scan;
    if (state.snapshot && state.snapshot.started_at >= snap.started_at) return;
    state.subnetMapKey = '';
    applySnapshot(snap);
    toast(`已刷新设备（${fmtTime(snap.started_at)} 的扫描结果）`);
  } catch (_) { /* 忽略 */ }
}

/* 首次打开时，如果服务端还留着上次的扫描结果，就直接铺到首页，
   省得一进来是一片空白（任务过期就静默跳过）。 */
async function loadLatestResult() {
  if (state.snapshot) return;
  try {
    const data = await (await fetch('/api/history')).json();
    const latest = (data.scans || []).find((s) => s.state === 'done' && s.stats.online > 0);
    if (!latest) return;
    const res = await fetch('/api/scan/' + latest.id);
    if (!res.ok) return;
    const snap = (await res.json()).scan;
    if (state.snapshot) return;            // 期间已经有别的结果了，不覆盖
    state.subnetMapKey = '';
    applySnapshot(snap);
    $('subnet-input').value = snap.subnet;
    $('home-meta').textContent += ' · 上次结果';
  } catch (_) { /* 忽略 */ }
}

/* ------------------------- 侧边栏与视图切换 ------------------------- */
function viewFromHash() {
  const name = (location.hash || '').replace(/^#\/?/, '').split('/')[0];
  return VIEWS[name] ? name : 'home';
}

function switchView(name, { push = true } = {}) {
  if (!VIEWS[name]) name = 'home';
  state.view = name;
  document.querySelectorAll('.view').forEach((view) => {
    view.hidden = view.id !== `view-${name}`;
  });
  document.querySelectorAll('.nav-item').forEach((item) => {
    item.classList.toggle('active', item.dataset.view === name);
  });
  $('page-title').textContent = VIEWS[name].title;
  document.title = `${VIEWS[name].title} · 局域网设备扫描`;
  if (push && location.hash !== `#/${name}`) location.hash = `#/${name}`;
  $('app').classList.remove('sidebar-open');   // 手机上选完就收起抽屉
  if (name === 'home') { renderHome(); if (state.chartStats) renderChart(state.chartStats); }
  if (name === 'history') loadHistory();
  if (name === 'devices') loadDevices();
  if (name === 'users') loadUsers();
  if (name === 'about') loadAbout();
}

function initSidebar() {
  const app = $('app');
  let collapsed = false;
  try {
    collapsed = localStorage.getItem('sidebar-collapsed') === '1';
  } catch (_) { /* 隐私模式下 localStorage 不可用 */ }
  app.classList.toggle('collapsed', collapsed);
  $('collapse-btn').title = collapsed ? '展开侧边栏（Ctrl+B）' : '收起侧边栏（Ctrl+B）';
}

/* ---------- 首页展示方式：列表 / 大 / 中 / 小 图标 ----------
   只改 #home-grid 的 data-mode，具体布局交给 CSS，
   所以切换是瞬时的，不需要重新渲染（也不会打断正在看的滚动位置）。 */
const HOME_MODES = ['list', 'l', 'm', 's'];

function applyHomeMode() {
  const mode = HOME_MODES.includes(state.homeMode) ? state.homeMode : 's';
  const grid = $('home-grid');
  if (grid && grid.dataset) grid.dataset.mode = mode;
  const sw = $('home-view-switch');
  if (!sw || !sw.querySelectorAll) return;
  sw.querySelectorAll('button[data-mode]').forEach((b) => {
    b.classList.toggle('on', b.dataset.mode === mode);
  });
}

function setHomeMode(mode) {
  state.homeMode = HOME_MODES.includes(mode) ? mode : 's';
  try {
    localStorage.setItem('home-mode', state.homeMode);
  } catch (_) { /* 忽略 */ }
  applyHomeMode();
}

function initHomeMode() {
  let saved = '';
  try {
    saved = localStorage.getItem('home-mode') || '';
  } catch (_) { /* 忽略 */ }
  if (HOME_MODES.includes(saved)) state.homeMode = saved;
  applyHomeMode();
}

function toggleSidebar() {
  const app = $('app');
  const collapsed = app.classList.toggle('collapsed');
  $('collapse-btn').title = collapsed ? '展开侧边栏（Ctrl+B）' : '收起侧边栏（Ctrl+B）';
  try {
    localStorage.setItem('sidebar-collapsed', collapsed ? '1' : '0');
  } catch (_) { /* 忽略 */ }
}

function bindEvents() {
  $('collapse-btn').addEventListener('click', toggleSidebar);
  $('menu-btn').addEventListener('click', () => $('app').classList.toggle('sidebar-open'));
  $('backdrop').addEventListener('click', () => $('app').classList.remove('sidebar-open'));
  document.querySelectorAll('.nav-item').forEach((item) => {
    item.addEventListener('click', (e) => {
      e.preventDefault();
      switchView(item.dataset.view);
    });
  });
  window.addEventListener('hashchange', () => switchView(viewFromHash(), { push: false }));
  document.addEventListener('keydown', (e) => {
    if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'b') {
      e.preventDefault();
      toggleSidebar();
    }
    if (e.key === 'Escape') $('app').classList.remove('sidebar-open');
  });

  $('history-refresh').addEventListener('click', loadHistory);
  $('history-body').addEventListener('click', onHistoryAction);

  $('dev-refresh').addEventListener('click', loadDevices);
  $('dev-search').addEventListener('input', (e) => {
    state.devSearch = e.target.value.trim().toLowerCase();
    renderDevices();
  });
  $('dev-state').addEventListener('change', (e) => {
    state.devState = e.target.value;
    renderDevices();
  });
  $('dev-category').addEventListener('change', (e) => {
    state.devCategory = e.target.value;
    renderDevices();
  });
  $('dev-group').addEventListener('change', (e) => {
    state.devGroup = e.target.value;
    renderDevices();
  });
  $('dev-sort').addEventListener('change', (e) => {
    state.devSort = e.target.value;
    renderDevices();
  });
  $('dev-export-csv').addEventListener('click', () => {
    window.location = '/api/devices/export?format=csv';
  });
  $('dev-export-json').addEventListener('click', () => {
    window.location = '/api/devices/export?format=json';
  });
  $('dev-body').addEventListener('click', onDeviceRowClick);
  $('dev-check-all').addEventListener('change', (e) => {
    const visible = sortManaged(filteredManaged());
    if (e.target.checked) visible.forEach((d) => state.devSelected.add(d.key));
    else visible.forEach((d) => state.devSelected.delete(d.key));
    renderDevices();
  });
  $('dev-delete-selected').addEventListener('click', () => {
    const keys = [...state.devSelected];
    if (!keys.length) return;
    deleteDevices(keys);
  });
  $('dev-delete-offline').addEventListener('click', deleteOfflineDevices);

  $('edit-close').addEventListener('click', () => $('edit-dialog').close());
  $('edit-save').addEventListener('click', saveDeviceEdit);
  $('edit-reset').addEventListener('click', () => saveDeviceEdit({ reset: true }));
  $('edit-delete').addEventListener('click', deleteDeviceRecord);
  $('edit-dialog').addEventListener('click', (e) => {
    if (e.target === $('edit-dialog')) $('edit-dialog').close();
  });

  // 图标选择器：点图标即选中；手输/粘贴 emoji 也跟着高亮
  $('icon-pick').addEventListener('click', (e) => {
    const btn = e.target && e.target.closest ? e.target.closest('.icon-chip') : null;
    if (!btn) return;
    $('edit-icon').value = btn.dataset.icon || '';
    renderIconPicker();
  });
  $('edit-icon').addEventListener('input', renderIconPicker);
  $('edit-icon-auto').addEventListener('click', () => {
    $('edit-icon').value = '';
    renderIconPicker();
    $('edit-icon').focus();
  });

  $('home-search').addEventListener('input', (e) => {
    state.homeSearch = e.target.value.trim().toLowerCase();
    renderHome();
  });
  $('home-only-online').addEventListener('change', (e) => {
    state.homeOnlyOnline = e.target.checked;
    renderHome();
  });
  // 展示方式：列表 / 大 / 中 / 小 图标
  $('home-view-switch').addEventListener('click', (e) => {
    const btn = e.target && e.target.closest ? e.target.closest('button[data-mode]') : null;
    if (!btn) return;
    setHomeMode(btn.dataset.mode);
  });
  $('home-group').addEventListener('change', (e) => {
    state.homeGroup = e.target.value;
    renderHome();
  });
  $('home-go-scan').addEventListener('click', () => switchView('scan'));
  $('chart-manage').addEventListener('click', () => switchView('devices'));
  $('chart-legend').addEventListener('click', (e) => {
    const row = e.target.closest('.legend-row[data-state]');
    if (!row) return;
    state.devState = row.dataset.state;
    state.devCategory = 'all';
    state.devSearch = '';
    switchView('devices');
  });
  $('home-grid').addEventListener('click', (e) => {
    const card = e.target.closest('.dev-card');
    if (!card) return;
    const dev = (state.snapshot?.devices || []).find((d) => d.ip === card.dataset.ip);
    if (dev) showDetail(dev);
  });

  $('auto-toggle').addEventListener('change', (e) => saveAuto({ enabled: e.target.checked }));
  $('auto-interval').addEventListener('change', () => {
    if ($('auto-toggle').checked) saveAuto({ enabled: true });
  });
  $('auto-run-now').addEventListener('click', async () => {
    try {
      const res = await fetch('/api/auto/run', { method: 'POST' });
      const data = await res.json();
      if (!res.ok || !data.ok) throw new Error(data.error || `HTTP ${res.status}`);
      state.knownIps = new Set();
      state.homeSeen = new Set();
      attach(data.scan_id);
      toast('已开始扫描');
    } catch (err) {
      toast('启动失败：' + err.message);
    }
  });
  document.addEventListener('visibilitychange', () => {
    if (!document.hidden) watchServer();
  });

  $('subnet-select').addEventListener('change', (e) => {
    if (e.target.value) $('subnet-input').value = e.target.value;
  });

  document.querySelectorAll('#profile-switch button').forEach((btn) => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('#profile-switch button').forEach((b) => b.classList.remove('active'));
      btn.classList.add('active');
      state.profile = btn.dataset.profile;
    });
  });

  $('start-btn').addEventListener('click', startScan);
  $('cancel-btn').addEventListener('click', cancelScan);

  $('search').addEventListener('input', (e) => {
    state.search = e.target.value.trim().toLowerCase();
    renderTable();
  });
  $('only-online').addEventListener('change', (e) => {
    state.onlyOnline = e.target.checked;
    renderTable();
  });

  document.querySelectorAll('th.sortable').forEach((th) => {
    th.addEventListener('click', () => {
      const key = th.dataset.key;
      if (state.sortKey === key) {
        state.sortDesc = !state.sortDesc;
      } else {
        state.sortKey = key;
        state.sortDesc = false;
      }
      renderTable();
    });
  });

  $('export-csv').addEventListener('click', () => exportAs('csv'));
  $('export-json').addEventListener('click', () => exportAs('json'));

  $('results-body').addEventListener('click', (e) => {
    const row = e.target.closest('tr');
    if (!row) return;
    const dev = (state.snapshot?.devices || []).find((d) => d.ip === row.dataset.ip);
    if (dev) showDetail(dev);
  });

  $('detail-close').addEventListener('click', () => $('detail-dialog').close());
  $('detail-dialog').addEventListener('click', (e) => {
    if (e.target === $('detail-dialog')) $('detail-dialog').close();
  });
}

/* ------------------------- 扫描控制 ------------------------- */
async function startScan() {
  const subnet = $('subnet-input').value.trim();
  const payload = {
    subnet,
    profile: state.profile,
    demo: $('opt-demo').checked,
    ping: $('opt-ping').checked,
    mdns: $('opt-mdns').checked,
    netbios: $('opt-netbios').checked,
    resolve_names: $('opt-dns').checked,
  };
  $('start-btn').disabled = true;
  $('error-text').textContent = '';
  $('foot-state').textContent = '启动中…';
  $('live-dot').classList.add('live');
  try {
    const res = await fetch('/api/scan', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    const data = await res.json();
    if (!res.ok || !data.ok) throw new Error(data.error || `HTTP ${res.status}`);
    state.knownIps = new Set();
    attach(data.scan_id);
    if (payload.demo) toast('演示模式：使用内置示例设备');
    loadHistory();
  } catch (err) {
    $('start-btn').disabled = false;
    $('foot-state').textContent = '空闲';
    $('live-dot').classList.remove('live');
    toast('启动失败：' + err.message);
  }
}

async function cancelScan() {
  if (!state.scanId) return;
  try {
    await fetch('/api/scan/' + state.scanId, { method: 'DELETE' });
  } catch (_) { /* 忽略 */ }
}

function attach(scanId) {
  closeStream();
  state.scanId = scanId;
  state.snapshot = null;
  state.knownIps = new Set();
  state.homeSeen = new Set();
  $('cancel-btn').disabled = false;
  $('start-btn').disabled = true;
  $('live-dot').classList.add('live');
  startTicker();

  if (window.EventSource) {
    const es = new EventSource(`/api/scan/${scanId}/events`);
    state.es = es;
    es.addEventListener('scan', (ev) => {
      try {
        applySnapshot(JSON.parse(ev.data));
      } catch (err) {
        console.warn('解析推送失败', err);
      }
    });
    es.addEventListener('end', () => closeStream());
    es.onerror = () => {
      if (state.es === es) {
        closeStream();
        startPolling(scanId);
      }
    };
  } else {
    startPolling(scanId);
  }
}

function startPolling(scanId) {
  stopPolling();
  state.pollTimer = setInterval(async () => {
    try {
      const res = await fetch('/api/scan/' + scanId);
      if (!res.ok) throw new Error('gone');
      const data = await res.json();
      applySnapshot(data.scan);
      if (['done', 'cancelled', 'error'].includes(data.scan.state)) stopPolling();
    } catch (_) {
      stopPolling();
    }
  }, 1200);
}

function stopPolling() {
  if (state.pollTimer) clearInterval(state.pollTimer);
  state.pollTimer = null;
}

function closeStream() {
  if (state.es) {
    state.es.close();
    state.es = null;
  }
}

function startTicker() {
  if (state.tickTimer) clearInterval(state.tickTimer);
  state.tickTimer = setInterval(() => {
    if (state.auto) updateAutoText();
    if (!state.snapshot) return;
    const running = !['done', 'cancelled', 'error'].includes(state.snapshot.state);
    if (running) {
      const elapsed = Date.now() / 1000 - state.snapshot.started_at;
      $('stat-time').textContent = fmtDuration(elapsed);
    }
  }, 500);
}

/* ------------------------- 渲染 ------------------------- */
function applySnapshot(snap) {
  // 记住当前展示的是哪一次扫描：导出、编辑后同步别名都靠它。
  // （从首页自动载入或在历史页载入记录时也要跟着变，否则会指向上一份结果）
  if (snap && snap.id) state.scanId = snap.id;
  state.snapshot = snap;
  const running = !['done', 'cancelled', 'error'].includes(snap.state);

  $('phase-text').textContent = snap.phase + (snap.state === 'error' ? '（出错）' : '');
  $('phase-sub').textContent = running
    ? `${snap.subnet} 扫描中…`
    : `${snap.subnet} · ${snap.state === 'done' ? '已完成' : snap.state === 'cancelled' ? '已取消' : '异常'}`;
  $('progress-bar').style.width = Math.max(2, snap.progress.percent) + '%';
  $('progress-detail').textContent = snap.progress.total
    ? `${snap.progress.percent}%  ·  ${snap.progress.done}/${snap.progress.total}`
    : `${snap.progress.percent}%`;

  $('stat-found').textContent = snap.stats.online;
  $('stat-named').textContent = snap.stats.named;
  $('stat-scanned').textContent = snap.progress.done || 0;
  $('stat-time').textContent = fmtDuration(snap.duration);
  if (snap.error) $('error-text').textContent = snap.error;

  $('live-dot').classList.toggle('live', running);
  $('start-btn').disabled = running;
  $('cancel-btn').disabled = !running;

  // 侧边栏底部的状态摘要
  $('foot-state').textContent = running
    ? '扫描中'
    : { done: '已完成', cancelled: '已取消', error: '出错' }[snap.state] || '空闲';
  $('foot-sub').textContent = running
    ? `${snap.subnet} · ${snap.stats.online} 台`
    : `${snap.stats.online} 台在线 · ${fmtDuration(snap.duration)}`;

  renderTable();
  renderMap();
  renderHome();
  renderLogs(snap.logs || []);

  if (!running) {
    closeStream();
    stopPolling();
    loadHistory();
    refreshDevicesBadge();
  }
}

/* ------------------------- 首页：设备方块墙 ------------------------- */
function deviceIcon(dev) {
  // 人工指定的图标优先，其次才按设备类型/主机名/厂商猜
  const manual = (dev && dev.icon ? String(dev.icon) : '').trim();
  if (manual) return manual;
  const text = `${dev.kind || ''} ${dev.hostname || ''} ${dev.vendor || ''}`.toLowerCase();
  for (const [keywords, icon] of DEVICE_ICONS) {
    if (keywords.some((word) => text.includes(word))) return icon;
  }
  return '❔';
}

function deviceCard(dev) {
  const isNew = !state.homeSeen.has(dev.ip);
  const statusClass = dev.only_arp ? 'arp' : 'online';
  const alias = (dev.alias || '').trim();
  const name = alias || dev.hostname || dev.vendor || '未知设备';
  // 名称已经用了厂商/别名时，第二行换成更有信息量的那个
  const vendor = dev.vendor && dev.vendor !== '未知厂商' ? dev.vendor : '';
  const vendor2 = alias
    ? (dev.hostname || vendor || dev.mac || '')
    : (dev.hostname ? (vendor || dev.mac || '') : (dev.mac || ''));
  const ports = (dev.ports || []).slice(0, 6).join(' ');
  const tip = [
    `${dev.ip}${dev.hostname ? ' · ' + dev.hostname : ''}${alias && dev.hostname ? '（别名 ' + alias + '）' : ''}`,
    [dev.vendor, dev.kind].filter(Boolean).join(' · '),
    dev.category && dev.category !== '未分类' ? `分类 ${dev.category}` : '',
    dev.location ? `位置 ${dev.location}` : '',
    dev.mac ? `MAC ${dev.mac}` : '',
    ports ? `端口 ${ports}` : '',
    dev.only_arp ? '仅 ARP 缓存记录，未确认在线' : '',
  ].filter(Boolean).join('\n');
  return `<button class="dev-card${dev.only_arp ? ' arp-only' : ''}${isNew ? ' new-card' : ''}"
      data-ip="${esc(dev.ip)}" title="${esc(tip)}">
    <span class="dev-card-top">
      <span class="dev-ico">${deviceIcon(dev)}</span>
      <span class="dev-status ${statusClass}"></span>
    </span>
    <span class="dev-name">${esc(name)}</span>
    <span class="dev-ip">${esc(dev.ip)}</span>
    <span class="dev-kind">${esc(dev.kind || '未知设备')}</span>
    ${ports ? `<span class="dev-ports">${esc(ports)}</span>` : ''}
    <span class="dev-vendor">${esc(vendor2)}</span>
  </button>`;
}

const byIp = (a, b) => ipToInt(a.ip) - ipToInt(b.ip);

function renderHome() {
  const snap = state.snapshot;
  const devices = snap?.devices || [];
  const stats = snap?.stats || { online: 0, named: 0, kinds: {}, vendors: {} };

  $('home-online').textContent = stats.online || 0;
  $('home-named').textContent = stats.named || 0;
  $('home-kinds').textContent = Object.keys(stats.kinds || {}).length;
  $('home-vendors').textContent = Object.keys(stats.vendors || {}).length;

  const running = snap && !['done', 'cancelled', 'error'].includes(snap.state);
  $('home-meta').textContent = snap
    ? `${snap.subnet} · ${fmtDate(snap.started_at)} · ${fmtDuration(snap.duration)}${running ? ' · 扫描中' : ''}`
    : '还没有扫描结果';

  const q = state.homeSearch;
  const list = devices.filter((dev) => {
    if (dev.ignored) return false;                 // 台账里标记忽略的不上方块墙
    if (state.homeOnlyOnline && !dev.online) return false;
    if (!q) return true;
    return [dev.ip, dev.mac, dev.vendor, dev.hostname, dev.kind, (dev.services || []).join(' '),
      (dev.ports || []).join(' ')].join(' ').toLowerCase().includes(q);
  });

  $('home-count').textContent = list.length === devices.length
    ? String(list.length)
    : `${list.length} / ${devices.length}`;
  $('home-empty').classList.toggle('hidden', list.length > 0);

  let html = '';
  if (state.homeGroup) {
    const isKind = state.homeGroup === 'kind';
    const groups = new Map();
    list.forEach((dev) => {
      const key = (isKind ? dev.kind : dev.vendor) || (isKind ? '未知设备' : '未知厂商');
      if (!groups.has(key)) groups.set(key, []);
      groups.get(key).push(dev);
    });
    [...groups.entries()]
      .sort((a, b) => b[1].length - a[1].length || a[0].localeCompare(b[0], 'zh-Hans-CN'))
      .forEach(([name, items]) => {
        html += `<div class="group-title">${esc(name)}<span class="count">${items.length}</span></div>`;
        html += items.slice().sort(byIp).map(deviceCard).join('');
      });
  } else {
    html = list.slice().sort(byIp).map(deviceCard).join('');
  }
  $('home-grid').innerHTML = html;
  list.forEach((dev) => state.homeSeen.add(dev.ip));
}

function filteredDevices() {
  const devices = state.snapshot?.devices || [];
  const q = state.search;
  return devices.filter((dev) => {
    if (state.onlyOnline && !dev.online) return false;
    if (!q) return true;
    const haystack = [
      dev.ip, dev.mac, dev.vendor, dev.hostname, dev.kind, dev.note,
      (dev.ports || []).join(' '), (dev.services || []).join(' '),
    ].join(' ').toLowerCase();
    return haystack.includes(q);
  });
}

function sortDevices(list) {
  const key = state.sortKey;
  const dir = state.sortDesc ? -1 : 1;
  return list.slice().sort((a, b) => {
    let va = a[key];
    let vb = b[key];
    if (key === 'ip') return (ipToInt(a.ip) - ipToInt(b.ip)) * dir;
    if (key === 'rtt_ms') {
      va = va === null || va === undefined ? Infinity : va;
      vb = vb === null || vb === undefined ? Infinity : vb;
      return (va - vb) * dir;
    }
    return String(va || '').localeCompare(String(vb || ''), 'zh-Hans-CN') * dir;
  });
}

function renderTable() {
  const body = $('results-body');
  const all = state.snapshot?.devices || [];
  const list = sortDevices(filteredDevices());

  document.querySelectorAll('th.sortable').forEach((th) => {
    th.classList.toggle('sorted', th.dataset.key === state.sortKey);
    th.classList.toggle('desc', th.dataset.key === state.sortKey && state.sortDesc);
  });

  $('result-count').textContent = `${list.length}${list.length !== all.length ? ' / ' + all.length : ''}`;
  $('empty-state').classList.toggle('hidden', list.length > 0);

  const rows = list.map((dev) => {
    const isNew = !state.knownIps.has(dev.ip);
    const rtt = dev.rtt_ms;
    const rttClass = rtt === null || rtt === undefined ? 'dim' : rtt < 10 ? 'good' : rtt < 60 ? 'mid' : 'slow';
    const rttText = rtt === null || rtt === undefined ? '—' : rtt.toFixed(1) + ' ms';
    const ports = (dev.ports || []).slice(0, 8).map((p) =>
      `<span class="port" title="${esc(PORT_NAMES[p] || '未知服务')}">${p}</span>`).join('')
      + ((dev.ports || []).length > 8 ? `<span class="dim"> +${dev.ports.length - 8}</span>` : '');
    const mac = dev.mac || '<span class="dim">未知</span>';
    const alias = (dev.alias || '').trim();
    const host = alias
      ? `<span class="alias">${esc(alias)}</span>${dev.hostname ? `<div class="host-sub">${esc(dev.hostname)}</div>` : ''}`
      : (dev.hostname || '<span class="dim">—</span>');
    const vendor = dev.vendor && dev.vendor !== '未知厂商'
      ? esc(dev.vendor) : '<span class="dim">未知厂商</span>';
    const kind = dev.kind ? `<span class="tag kind">${esc(dev.kind)}</span>` : '<span class="dim">—</span>';
    const src = (dev.sources || []).map((s) => SRC_NAMES[s] || s).join('·');
    const title = dev.note ? ` title="${esc(dev.note)}"` : '';
    return `<tr data-ip="${esc(dev.ip)}" class="${dev.only_arp ? 'arp-only' : ''}${isNew ? ' new-row' : ''}"${title}>
      <td class="mono ip">${esc(dev.ip)}</td>
      <td class="host">${host}</td>
      <td class="mono">${mac}</td>
      <td>${vendor}</td>
      <td>${kind}</td>
      <td>${ports || '<span class="dim">—</span>'}</td>
      <td class="num rtt ${rttClass}">${rttText}</td>
      <td class="src">${esc(src)}</td>
    </tr>`;
  });
  body.innerHTML = rows.join('');
  list.forEach((dev) => state.knownIps.add(dev.ip));
}

function renderMap() {
  const snap = state.snapshot;
  if (!snap) return;
  const key = `${snap.subnet}|${snap.id}`;
  const map = $('subnet-map');
  const devices = snap.devices || [];

  if (state.subnetMapKey !== key) {
    state.subnetMapKey = key;
    map.innerHTML = '';
    const base = snap.subnet.split('/')[0].split('.').slice(0, 3).join('.');
    const size = Math.min(1024, Math.max(2, snap.total_hosts || 254));
    const frag = document.createDocumentFragment();
    for (let i = 1; i <= size; i++) {
      const cell = document.createElement('div');
      cell.className = 'cell';
      cell.dataset.ip = `${base}.${i}`;
      frag.appendChild(cell);
    }
    map.appendChild(frag);
  }

  const byIp = new Map(devices.map((d) => [d.ip, d]));
  const arpDone = (snap.progress.percent || 0) >= 30 || !['pending', 'running'].includes(snap.state);
  map.querySelectorAll('.cell').forEach((cell) => {
    const dev = byIp.get(cell.dataset.ip);
    cell.className = 'cell' + (dev ? (dev.only_arp ? ' arp' : ' online') : (arpDone ? ' dead' : ''));
    cell.title = dev
      ? `${dev.ip}\n${dev.hostname || '未知主机名'}\n${dev.vendor || ''} ${dev.kind || ''}`
      : `${cell.dataset.ip}\n${arpDone ? '无响应' : '尚未扫描'}`;
  });
}

function renderLogs(logs) {
  const box = $('logs');
  box.innerHTML = logs.map((l) =>
    `<div class="l-${esc(l.level)}"><span class="t">${fmtTime(l.ts)}</span>${esc(l.msg)}</div>`).join('');
  box.scrollTop = box.scrollHeight;
}

function showDetail(dev) {
  $('detail-title').textContent = `${dev.ip}${dev.hostname ? ' · ' + dev.hostname : ''}`;
  const rows = [
    ['IP 地址', `<span class="mono">${esc(dev.ip)}</span>`],
    ['MAC 地址', `<span class="mono">${esc(dev.mac || '未知')}</span>`],
    ['厂商', esc(dev.vendor || '未知厂商')],
    ['主机名', esc(dev.hostname || '未知')],
    ['设备类型', esc(dev.kind || '未知设备')],
    ['延迟', dev.rtt_ms === null || dev.rtt_ms === undefined ? '—' : dev.rtt_ms.toFixed(2) + ' ms'],
    ['网卡', esc(dev.iface || '未知')],
    ['状态', dev.only_arp ? '仅 ARP 缓存（未确认）' : dev.online ? '在线' : '离线'],
    ['发现方式', (dev.sources || []).map((s) => SRC_NAMES[s] || s).join('、') || '—'],
    ['最后更新', fmtTime(dev.last_seen)],
  ];
  if (dev.note) rows.push(['备注', esc(dev.note)]);
  if (dev.alias) rows.push(['台账别名', esc(dev.alias)]);
  if (dev.icon) rows.push(['图标', `<span class="dev-ico">${esc(dev.icon)}</span> <span class="dim">人工指定</span>`]);
  if (dev.category && dev.category !== '未分类') rows.push(['分类', esc(dev.category)]);
  if (dev.location) rows.push(['位置', esc(dev.location)]);
  if ((dev.tags || []).length) rows.push(['标签', (dev.tags || []).map((t) => `<span class="tag-mini">${esc(t)}</span>`).join(' ')]);
  if (dev.starred) rows.push(['标记', '★ 已关注']);
  if (dev.ignored) rows.push(['标记', '已忽略（首页不显示）']);

  let html = `<dl class="kv">${rows.map(([k, v]) => `<dt>${k}</dt><dd>${v}</dd>`).join('')}</dl>`;

  if ((dev.ports || []).length) {
    html += `<div class="detail-section"><h4>开放端口</h4>${dev.ports.map((p) =>
      `<span class="port" title="${esc(PORT_NAMES[p] || '未知服务')}">${p} · ${esc(PORT_NAMES[p] || '未知')}</span>`).join('')}</div>`;
  }
  if ((dev.services || []).length) {
    html += `<div class="detail-section"><h4>mDNS 服务</h4>${dev.services.map((s) =>
      `<span class="tag">${esc(s)}</span>`).join(' ')}</div>`;
  }
  if (dev.extra && Object.keys(dev.extra).length) {
    html += `<div class="detail-section"><h4>附加信息</h4><div class="txt-list">${
      Object.entries(dev.extra).map(([k, v]) => `<b>${esc(k)}</b><span>${esc(v)}</span>`).join('')}</div></div>`;
  }
  $('detail-body').innerHTML = html;
  $('detail-dialog').showModal();
}

/* ------------------------- 导出 / 历史 ------------------------- */
function exportAs(format) {
  if (!state.scanId) {
    toast('还没有扫描结果');
    return;
  }
  window.location = `/api/scan/${state.scanId}/export?format=${format}`;
}

const STATE_TEXT = {
  done: '完成', running: '进行中', cancelled: '已取消', error: '出错', pending: '排队',
};

async function loadHistory() {
  let scans = [];
  try {
    const data = await (await fetch('/api/history')).json();
    scans = data.scans || [];
  } catch (_) {
    return;
  }
  $('nav-history-badge').textContent = scans.length;
  $('history-count').textContent = scans.length;
  $('history-empty').classList.toggle('hidden', scans.length > 0);
  $('history-body').innerHTML = scans.map((s) => `
    <tr class="${s.state === 'running' ? 'is-running' : ''}">
      <td class="mono">${fmtDate(s.started_at)}</td>
      <td class="mono">${esc(s.subnet)}</td>
      <td class="state-${esc(s.state)}">${STATE_TEXT[s.state] || esc(s.state)}</td>
      <td class="num">${s.stats.online}</td>
      <td class="num">${fmtDuration(s.duration)}</td>
      <td>${s.demo ? '<span class="tag">演示</span>' : '真实扫描'}${s.auto ? ' <span class="tag">定时</span>' : ''}</td>
      <td>
        <div class="history-actions">
          <button class="mini" data-action="load" data-id="${s.id}">载入</button>
          <button class="mini" data-action="csv" data-id="${s.id}">CSV</button>
          <button class="mini" data-action="json" data-id="${s.id}">JSON</button>
        </div>
      </td>
    </tr>`).join('');
}

async function onHistoryAction(e) {
  const btn = e.target.closest('button[data-action]');
  if (!btn) return;
  const { action, id } = btn.dataset;
  if (action === 'csv' || action === 'json') {
    window.location = `/api/scan/${id}/export?format=${action}`;
    return;
  }
  try {
    const res = await fetch('/api/scan/' + id);
    if (!res.ok) {
      toast('该记录已过期，重新扫描一次吧');
      loadHistory();
      return;
    }
    const data = await res.json();
    state.subnetMapKey = '';
    applySnapshot(data.scan);
    closeStream();
    $('subnet-input').value = data.scan.subnet;
    switchView('scan');
    toast(`已载入 ${data.scan.subnet} 的扫描结果`);
  } catch (err) {
    toast('载入失败：' + err.message);
  }
}

/* ------------------------- 设备管理（台账） ------------------------- */
function fmtAgo(ts) {
  if (!ts) return '—';
  const diff = Date.now() / 1000 - ts;
  if (diff < 90) return '刚刚';
  if (diff < 3600) return `${Math.round(diff / 60)} 分钟前`;
  if (diff < 86400) return `${Math.round(diff / 3600)} 小时前`;
  if (diff < 86400 * 30) return `${Math.round(diff / 86400)} 天前`;
  return fmtDate(ts).slice(0, 5);
}

async function loadDevices() {
  try {
    const data = await (await fetch('/api/devices')).json();
    applyDevices(data);
  } catch (err) {
    toast('读取设备台账失败：' + err.message);
  }
}

function applyDevices(data) {
  state.managed = data.devices || [];
  // 已删除的设备要从选中集合里清掉
  const alive = new Set(state.managed.map((d) => d.key));
  [...state.devSelected].forEach((k) => { if (!alive.has(k)) state.devSelected.delete(k); });
  state.managedStats = data.stats || null;
  state.categories = data.categories || [];
  $('nav-devices-badge').textContent = state.managed.length;

  const stats = state.managedStats || {};
  $('dev-total').textContent = stats.total || 0;
  $('dev-online').textContent = stats.online || 0;
  $('dev-offline').textContent = stats.offline || 0;
  $('dev-edited').textContent = stats.edited || 0;
  $('dev-starred').textContent = stats.starred || 0;

  // 分类下拉 + 编辑弹窗的数据源
  const catSelect = $('dev-category');
  const keep = state.devCategory || 'all';
  catSelect.innerHTML = '<option value="all">全部分类</option>'
    + state.categories.map((c) => {
      const n = (stats.categories || {})[c] || 0;
      return `<option value="${esc(c)}">${esc(c)}${n ? ` (${n})` : ''}</option>`;
    }).join('');
  catSelect.value = [...catSelect.options].some((o) => o.value === keep) ? keep : 'all';
  state.devCategory = catSelect.value;
  $('category-list').innerHTML = state.categories.map((c) => `<option value="${esc(c)}"></option>`).join('');

  const kinds = [...new Set(state.managed.map((d) => d.kind).filter(Boolean))].sort();
  $('kind-list').innerHTML = kinds.map((k) => `<option value="${esc(k)}"></option>`).join('');

  $('dev-state').value = state.devState;
  $('dev-search').value = state.devSearch;
  $('dev-group').value = state.devGroup;
  $('dev-sort').value = state.devSort;
  $('dev-meta').textContent = stats.updated_at
    ? `共 ${stats.total} 台（在线 ${stats.online} / 已掉线 ${stats.offline}） · 最近归档 ${fmtAgo(stats.updated_at)}`
    : '每次扫描后自动归档，掉线的设备也留在这里';
  renderDevices();
}

function filteredManaged() {
  const q = state.devSearch || '';
  const mode = state.devState || 'all';
  const cat = state.devCategory || 'all';
  return state.managed.filter((dev) => {
    if (cat !== 'all' && dev.category !== cat) return false;
    if (mode === 'online' && !dev.online) return false;
    if (mode === 'offline' && dev.online) return false;
    if (mode === 'starred' && !dev.starred) return false;
    if (mode === 'edited' && !dev.edited) return false;
    if (mode === 'ignored' && !dev.ignored) return false;
    if (!q) return true;
    return [dev.name, dev.custom_name, dev.hostname, dev.ip, dev.mac, dev.vendor,
      dev.kind, dev.category, dev.location, (dev.tags || []).join(' '), dev.note,
      (dev.ports || []).join(' ')].join(' ').toLowerCase().includes(q);
  });
}

function sortManaged(list) {
  const key = state.devSort || 'ip';
  const cmpIp = (a, b) => (a.ip && b.ip ? ipToInt(a.ip) - ipToInt(b.ip) : (a.ip ? -1 : 1));
  return list.slice().sort((a, b) => {
    if (key === 'last_seen') return (b.last_seen || 0) - (a.last_seen || 0);
    if (key === 'first_seen') return (b.first_seen || 0) - (a.first_seen || 0);
    if (key === 'seen') return (b.seen_count || 0) - (a.seen_count || 0);
    if (key === 'name') return String(a.name).localeCompare(String(b.name), 'zh-Hans-CN');
    return cmpIp(a, b);
  });
}

function deviceRow(dev) {
  const offline = !dev.online;
  const catCls = dev.category && dev.category !== '未分类' ? 'cat-chip' : 'cat-chip none';
  const hostSub = dev.custom_name && dev.hostname ? `<div class="host-sub">${esc(dev.hostname)}</div>` : '';
  const tags = (dev.tags || []).map((t) => `<span class="tag-mini">${esc(t)}</span>`).join('');
  const ports = (dev.ports || []).slice(0, 4).join(' ');
  const kind = dev.kind && dev.kind !== '未知设备'
    ? esc(dev.kind) + (dev.kind !== dev.auto_kind && dev.auto_kind ? '<div class="host-sub">自动识别为 ' + esc(dev.auto_kind) + '</div>' : '')
    : '<span class="dim">未知设备</span>';
  const picked = state.devSelected.has(dev.key);
  return `<tr class="dev-row${offline ? ' offline' : ''}${dev.ignored ? ' ignored' : ''}${picked ? ' picked' : ''}" data-key="${esc(dev.key)}">
    <td class="check-cell">
      <input type="checkbox" class="row-check" data-key="${esc(dev.key)}"${picked ? ' checked' : ''}
        title="勾选后可批量删除">
    </td>
    <td class="star-cell">
      <button class="star-btn${dev.starred ? ' on' : ''}" data-action="star" data-key="${esc(dev.key)}"
        title="${dev.starred ? '取消关注' : '标记为关注'}">${dev.starred ? '★' : '☆'}</button>
    </td>
    <td>
      <div class="alias"><span class="dev-ico">${deviceIcon(dev)}</span>${esc(dev.name)}</div>${hostSub}
      ${dev.location ? `<div class="loc-text">📍 ${esc(dev.location)}</div>` : ''}
      ${tags}
    </td>
    <td><span class="${catCls}">${esc(dev.category)}</span></td>
    <td class="mono">${esc(dev.ip || '—')}${(dev.ips || []).length > 1 ? `<div class="host-sub">曾用 ${esc(dev.ips.slice(0, -1).join(', '))}</div>` : ''}</td>
    <td class="mono">${esc(dev.mac || '—')}</td>
    <td>${dev.vendor && dev.vendor !== '未知厂商' ? esc(dev.vendor) : '<span class="dim">未知厂商</span>'}</td>
    <td>${kind}${ports ? `<div class="host-sub mono">${esc(ports)}</div>` : ''}</td>
    <td>${offline
      ? `<span class="tag" style="border-color:rgba(248,113,113,.35);color:#fca5a5">已掉线</span>`
      : '<span class="tag" style="border-color:rgba(52,211,153,.35);color:#6ee7b7">在线</span>'}
      ${dev.ignored ? ' <span class="tag">已忽略</span>' : ''}</td>
    <td class="num">${offline ? `<span title="${fmtDate(dev.last_seen)}">${fmtAgo(dev.last_seen)}</span>` : '现在'}</td>
    <td class="num">${dev.seen_count || 0}</td>
    <td class="ops-cell">
      <div class="history-actions">
        <button class="mini" data-action="edit" data-key="${esc(dev.key)}">编辑</button>
        <button class="mini" data-action="detail" data-key="${esc(dev.key)}">详情</button>
        <button class="mini danger" data-action="delete" data-key="${esc(dev.key)}"
          title="从台账删除这条记录">删除</button>
      </div>
    </td>
  </tr>`;
}

function renderDevices() {
  const all = state.managed;
  const list = sortManaged(filteredManaged());
  $('dev-count').textContent = list.length === all.length ? String(list.length) : `${list.length} / ${all.length}`;
  $('dev-empty').classList.toggle('hidden', list.length > 0);

  const group = state.devGroup === undefined ? 'category' : state.devGroup;
  let html = '';
  if (group) {
    const pick = group === 'category'
      ? (d) => d.category || '未分类'
      : group === 'kind'
        ? (d) => d.kind || '未知设备'
        : (d) => (d.online ? '在线' : '已掉线');
    const buckets = new Map();
    list.forEach((d) => {
      const key = pick(d);
      if (!buckets.has(key)) buckets.set(key, []);
      buckets.get(key).push(d);
    });
    [...buckets.entries()]
      .sort((a, b) => b[1].length - a[1].length || a[0].localeCompare(b[0], 'zh-Hans-CN'))
      .forEach(([name, items]) => {
        html += `<tr class="group-row"><td colspan="12">${esc(name)}<span class="count"> · ${items.length} 台</span></td></tr>`;
        html += items.map(deviceRow).join('');
      });
  } else {
    html = list.map(deviceRow).join('');
  }
  $('dev-body').innerHTML = html;
  syncSelectionUi(list);
}

/* 同步「全选」框和「删除选中」按钮的状态 */
function syncSelectionUi(visibleList) {
  const visible = visibleList || sortManaged(filteredManaged());
  const picked = visible.filter((d) => state.devSelected.has(d.key)).length;
  const all = $('dev-check-all');
  all.checked = visible.length > 0 && picked === visible.length;
  all.indeterminate = picked > 0 && picked < visible.length;
  const btn = $('dev-delete-selected');
  btn.disabled = state.devSelected.size === 0;
  btn.textContent = state.devSelected.size ? `删除选中 (${state.devSelected.size})` : '删除选中';
}

function findManaged(key) {
  return state.managed.find((d) => d.key === key) || null;
}

function onDeviceRowClick(e) {
  const row = e.target.closest('tr.dev-row');
  if (!row) return;
  const key = row.dataset.key;
  const dev = findManaged(key);

  // 勾选框：只切换选中，不打开编辑
  const box = e.target.closest('input.row-check');
  if (box) {
    if (box.checked) state.devSelected.add(key);
    else state.devSelected.delete(key);
    row.classList.toggle('picked', box.checked);
    syncSelectionUi();
    return;
  }
  if (!dev) return;

  const btn = e.target.closest('button[data-action]');
  // 只读账号的默认动作是「看详情」——否则点一下就直接进编辑弹窗了
  const action = btn ? btn.dataset.action : (isAdmin() ? 'edit' : 'detail');
  if (action === 'star') toggleStar(dev);
  else if (action === 'detail') showDetail(dev);
  else if (action === 'delete') deleteDevices([dev.key], dev.name);
  else openDeviceEditor(dev);
}

/* 删除：单条走这一个入口，批量也走它 */
async function deleteDevices(keys, label) {
  const list = (keys || []).filter(Boolean);
  if (!list.length) return;
  const name = label || (list.length === 1 ? list[0] : `${list.length} 台设备`);
  const extra = list.length > 1 ? `\n共 ${list.length} 台。` : '';
  if (!window.confirm(`从台账中删除「${name}」？${extra}\n\n注意：如果它还在线，下次扫描会作为新设备重新出现（人工填的别名/分类等会丢）。`)) {
    return 0;
  }
  try {
    const res = await fetch('/api/devices/bulk-delete', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ keys: list }),
    });
    const data = await res.json();
    if (!res.ok || !data.ok) throw new Error(data.error || `HTTP ${res.status}`);
    list.forEach((k) => state.devSelected.delete(k));
    if (data.stats) renderChart(data.stats);
    await refreshManaged();
    toast(`已删除 ${data.deleted} 条设备记录`);
    return data.deleted;
  } catch (err) {
    toast('删除失败：' + err.message);
    return 0;
  }
}

/* 一键清除全部已掉线设备 */
async function deleteOfflineDevices() {
  const stats = state.managedStats || {};
  const n = stats.offline || 0;
  if (!n) {
    toast('没有已掉线的设备');
    return;
  }
  if (!window.confirm(`清除 ${n} 台「已掉线」设备的记录？\n\n它们已经不在网上了，删除只是清理台账；以后重新上线会作为新设备出现。`)) {
    return;
  }
  try {
    const res = await fetch('/api/devices/bulk-delete', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ scope: 'offline' }),
    });
    const data = await res.json();
    if (!res.ok || !data.ok) throw new Error(data.error || `HTTP ${res.status}`);
    state.devSelected.clear();
    if (data.stats) renderChart(data.stats);
    await refreshManaged();
    toast(`已清除 ${data.deleted} 台离线设备`);
  } catch (err) {
    toast('清除失败：' + err.message);
  }
}

async function toggleStar(dev) {
  try {
    const res = await fetch('/api/devices/' + encodeURIComponent(dev.key), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ starred: !dev.starred }),
    });
    const data = await res.json();
    if (!res.ok || !data.ok) throw new Error(data.error || `HTTP ${res.status}`);
    await refreshManaged();
  } catch (err) {
    toast('操作失败：' + err.message);
  }
}

async function refreshManaged() {
  try {
    const data = await (await fetch('/api/devices')).json();
    applyDevices(data);
  } catch (_) { /* 忽略 */ }
  await refreshSnapshot();
}

/* 台账改过之后，当前这份扫描结果里贴的别名/分类也是旧的，
   重新取一次快照，首页方块墙、结果表、详情弹窗才会跟着变。 */
async function refreshSnapshot() {
  if (!state.scanId) return false;
  try {
    const res = await fetch('/api/scan/' + state.scanId);
    if (!res.ok) return false;
    const snap = (await res.json()).scan;
    if (!snap) return false;
    applySnapshot(snap);
    return true;
  } catch (_) {
    return false;
  }
}

/* 扫描结束后台账会变，顺手刷新一下角标（正在看设备管理页就整页刷新） */
async function refreshDevicesBadge() {
  try {
    const data = await (await fetch('/api/devices')).json();
    if (state.view === 'devices') {
      applyDevices(data);
    } else {
      state.managed = data.devices || [];
      state.managedStats = data.stats || null;
      state.categories = data.categories || [];
      $('nav-devices-badge').textContent = state.managed.length;
      if (data.stats) renderChart(data.stats);
    }
  } catch (_) { /* 忽略 */ }
}

// 图标选择器：把 ICON_CHOICES 画成一片可点的按钮，当前选中的高亮
function renderIconPicker() {
  const cur = ($('edit-icon').value || '').trim();
  $('icon-pick').innerHTML = ICON_CHOICES.map((ico) =>
    `<button type="button" class="icon-chip${ico === cur ? ' sel' : ''}"`
    + ` data-icon="${esc(ico)}" title="用这个图标">${ico}</button>`).join('');
}

function openDeviceEditor(dev) {
  state.editingKey = dev.key;
  $('edit-title').textContent = `编辑设备 · ${dev.name}`;
  const fmt = (ts) => (ts ? fmtDate(ts) : '—');
  $('edit-meta').innerHTML = `
    <span>IP <b class="mono">${esc(dev.ip || '—')}</b></span>
    <span>MAC <b class="mono">${esc(dev.mac || '—')}</b></span>
    <span>厂商 <b>${esc(dev.vendor || '未知厂商')}</b></span>
    <span>自动识别 <b>${esc(dev.auto_kind || '未知设备')}</b></span>
    <span>首次发现 <b>${fmt(dev.first_seen)}</b></span>
    <span>最近在线 <b>${fmt(dev.last_seen)}</b></span>
    <span>出现次数 <b>${dev.seen_count || 0}</b></span>
    <span>状态 <b>${dev.online ? '在线' : '已掉线'}</b></span>
    ${dev.hostname ? `<span>主机名 <b class="mono">${esc(dev.hostname)}</b></span>` : ''}`;
  $('edit-name').value = dev.custom_name || '';
  $('edit-category').value = dev.category === '未分类' ? '' : dev.category;
  $('edit-location').value = dev.location || '';
  $('edit-tags').value = (dev.tags || []).join(', ');
  $('edit-kind').value = dev.kind !== dev.auto_kind ? dev.kind : '';
  $('edit-icon').value = dev.icon || '';
  renderIconPicker();
  $('edit-note').value = dev.note || '';
  $('edit-starred').checked = !!dev.starred;
  $('edit-ignored').checked = !!dev.ignored;
  $('edit-dialog').showModal();
  setTimeout(() => $('edit-name').focus(), 50);
}

async function saveDeviceEdit(extra = {}) {
  const key = state.editingKey;
  if (!key) return;
  const payload = extra.reset ? { reset: true } : {
    name: $('edit-name').value.trim(),
    category: $('edit-category').value.trim() || '未分类',
    location: $('edit-location').value.trim(),
    tags: $('edit-tags').value,
    note: $('edit-note').value.trim(),
    kind: $('edit-kind').value.trim(),
    icon: $('edit-icon').value.trim(),
    starred: $('edit-starred').checked,
    ignored: $('edit-ignored').checked,
  };
  try {
    const res = await fetch('/api/devices/' + encodeURIComponent(key), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    const data = await res.json();
    if (!res.ok || !data.ok) throw new Error(data.error || `HTTP ${res.status}`);
    $('edit-dialog').close();
    await refreshManaged();
    toast(extra.reset ? '已恢复自动识别' : `已保存「${data.device.name}」`);
  } catch (err) {
    toast('保存失败：' + err.message);
  }
}

async function deleteDeviceRecord() {
  const key = state.editingKey;
  if (!key) return;
  const dev = findManaged(key);
  const deleted = await deleteDevices([key], dev ? dev.name : key);
  if (deleted) $('edit-dialog').close();
}

/* ------------------------- 关于页 ------------------------- */async function loadAbout() {
  $('about-api').innerHTML = API_DOCS.map(([method, path, desc]) => `
    <span class="method ${method === 'POST' ? 'post' : method === 'DELETE' ? 'del' : ''}">${method}</span>
    <span class="path">${path}</span>
    <span class="desc">${desc}</span>`).join('');

  try {
    const info = await (await fetch('/api/status')).json();
    $('about-env').innerHTML = `<div class="kv-inline">
      <div><span>服务版本</span><b>v${esc(info.version)}</b></div>
      <div><span>运行平台</span><b>${esc(info.platform)}</b></div>
      <div><span>ICMP ping</span><b>${info.has_ping ? '可用' : '不可用（仅 ARP + 端口探测）'}</b></div>
      <div><span>运行权限</span><b>${info.is_root ? 'root' : '普通用户（无需 root）'}</b></div>
      <div><span>端口档位</span><b>快速 ${info.port_profiles.fast} 个 / 完整 ${info.port_profiles.full} 个</b></div>
      <div><span>当前任务</span><b>${info.active_scan ? '有扫描正在运行' : '空闲'}</b></div>
    </div>`;

    const ifaces = info.interfaces || [];
    $('about-ifaces').innerHTML = ifaces.length
      ? `<div class="kv-inline">${ifaces.map((i) => `
          <div>
            <span>${esc(i.name)}${i.is_default ? ' · 默认路由' : ''}</span>
            <b>${esc(i.cidr)}</b>
            <span>本机 ${esc(i.ip)} · ${i.hosts} 个可用地址</span>
          </div>`).join('')}</div>`
      : '<span class="muted">未检测到可用的局域网网段</span>';
  } catch (err) {
    $('about-env').innerHTML = `<span class="muted">读取失败：${esc(err.message)}</span>`;
  }
}

init();
