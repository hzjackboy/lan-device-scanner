// 联调测试专用：给所有 /api/ 请求自动带上本地管理员令牌。
//
// 服务端现在要求认证。测试跑在服务本机，所以用 data/local_token
// （0600，只给同机进程读）——不用在服务端开「回环免认证」那种后门。
const fs = require('fs');
const path = require('path');

const TOKEN = (() => {
  try {
    return JSON.parse(fs.readFileSync(path.join(__dirname, '..', 'data', 'local_token'), 'utf8')).token;
  } catch (_) {
    return '';
  }
})();

const nativeFetch = globalThis.fetch;
globalThis.fetch = (url, opts = {}) => {
  const target = String((url && url.url) || url || '');
  if (TOKEN && target.includes('/api/')) {
    opts = Object.assign({}, opts, {
      headers: Object.assign({}, opts.headers || {}, { 'X-Local-Token': TOKEN }),
    });
  }
  return nativeFetch(url, opts);
};

module.exports = { TOKEN };
