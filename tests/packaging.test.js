// 打包自检：镜像里到底有没有跑起来需要的东西。
//
// 为什么要有这个：加 auth.py 时忘了同步 Dockerfile 的 COPY 行，
// 结果镜像能构建成功、`docker run` 立刻崩在 `import auth`，
// 而且因为构建不报错，很容易一路推到 Docker Hub 才发现。
// 这里用静态检查把它挡在提交之前（不需要 Docker，秒级）。

const fs = require('fs');
const path = require('path');

const ROOT = path.join(__dirname, '..');
const read = (f) => fs.readFileSync(path.join(ROOT, f), 'utf8');

const dockerfile = read('Dockerfile');
const dockerignore = read('.dockerignore');
const compose = read('docker-compose.yml');

const checks = [];
const check = (name, ok) => checks.push([name, !!ok]);

// ---------- 1. 所有本地模块都必须被 COPY 进镜像 ----------
// 扫描**每一个** .py，而不只是 server.py：scanner.py 会 import mdns / netbios / oui，
// 只看入口文件的话会把它们漏掉。
const serverSrc = read('server.py');
const pyFiles = fs.readdirSync(ROOT).filter((f) => f.endsWith('.py'));
const localNames = new Set(pyFiles.map((f) => f.replace(/\.py$/, '')));
const localModules = [];
for (const file of pyFiles) {
  const self = file.replace(/\.py$/, '');
  for (const m of read(file).matchAll(/^\s*(?:import|from)\s+([a-zA-Z_][\w]*)/gm)) {
    if (localNames.has(m[1]) && m[1] !== self && !localModules.includes(m[1])) {
      localModules.push(m[1]);
    }
  }
}

const copied = new Set();
for (const line of dockerfile.split('\n')) {
  if (!line.startsWith('COPY ')) continue;
  const parts = line.replace(/^COPY\s+/, '').trim().split(/\s+/);
  parts.slice(0, -1).forEach((f) => copied.add(f.replace(/^\.\//, '')));
}
// COPY static/ ./static/ 这种目录也要算进去
const copiedDirs = new Set([...copied].map((f) => f.replace(/\/$/, '')));

const missing = localModules.filter((m) => !copied.has(`${m}.py`));
check(`${localModules.length} 个被引用的本地模块都在 Dockerfile COPY 里`
  + (missing.length ? `（漏了：${missing.join(', ')}）` : ''), missing.length === 0);

// ---------- 2. .dockerignore 不能把刚 COPY 的东西又排掉 ----------
const ignored = dockerignore.split('\n')
  .map((l) => l.trim()).filter((l) => l && !l.startsWith('#'));

const wronglyIgnored = [...copied].filter((f) => {
  const base = f.replace(/\/$/, '');
  return ignored.some((ig) => ig === base || ig === `${base}/` || ig === `${base}.py`);
});
check('.dockerignore 没有把要 COPY 的文件排除掉'
  + (wronglyIgnored.length ? `（冲突：${wronglyIgnored.join(', ')}）` : ''), wronglyIgnored.length === 0);

// ---------- 3. 隐私数据必须被 dockerignore 排除 ----------
for (const secret of ['data/', 'oui.csv', '.git']) {
  check(`.dockerignore 排除 ${secret}`, ignored.includes(secret));
}

// ---------- 4. 容器必须用 host 网络 ----------
// ARP 只在本广播域有效，bridge 下 /proc/net/arp 只有 docker 网段。
check('docker-compose.yml 使用 network_mode: host', /network_mode:\s*host/.test(compose));
check('Dockerfile 声明了数据卷挂载点 /app/data', /RUN mkdir -p \/app\/data/.test(dockerfile));

// ---------- 5. 镜像里的版本号要和代码一致 ----------
const version = (read('server.py').match(/VERSION\s*=\s*"([^"]+)"/) || [])[1];
const label = (dockerfile.match(/image\.version="([^"]+)"/) || [])[1];
check(`Dockerfile 的 image.version（${label}）与 server.py VERSION（${version}）一致`,
  !!version && version === label);

// ---------- 6. HEALTHCHECK 打的是真实存在的接口 ----------
const health = (dockerfile.match(/HEALTHCHECK[\s\S]*?(?=\n[A-Z]|\n$)/) || [''])[0];
if (health) {
    // 正则括号从「/」之后开始，抓到的是 "api/status"（不含前导斜杠），比对时补回 "/"。
    const paths = [...health.matchAll(/\/(api\/[a-z/<>\-_]+)/g)].map((m) => m[1]);

    const missing = paths.filter((p) => !serverSrc.includes(`"/${p}"`));
    check(`HEALTHCHECK 打的是真实存在的接口（${paths.join(', ') || '未解析到'}）`, missing.length === 0);

    // 更进一步：健康检查必须打**免登录**接口。
    // 加认证时 HEALTHCHECK 还指着 /api/status，容器就永远是 unhealthy——
    // 而且 docker build 完全不报错，只有跑起来才发现。
    const publicApi = (serverSrc.match(/PUBLIC_API\s*=\s*\{([^}]*)\}/) || [])[1] || '';
    const notPublic = paths.filter((p) => !publicApi.includes(`"/${p}"`));
    check(`HEALTHCHECK 打的接口不需要登录（白名单：${publicApi.trim() || '未解析到'}）`, notPublic.length === 0);
}

let failed = 0;
for (const [name, ok] of checks) {
  console.log((ok ? '✅ ' : '❌ ') + name);
  if (!ok) failed++;
}
console.log(failed ? `\n${failed} 项失败` : `\n全部通过（${checks.length} 项）`);
process.exit(failed ? 1 : 0);
