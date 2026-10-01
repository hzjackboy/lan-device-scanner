#!/usr/bin/env bash
# 构建 amd64 + arm64 多架构镜像并推送到 Docker Hub
#
# 用法：
#   ./docker-push.sh <dockerhub用户名> [标签...]
#
#   ./docker-push.sh hzjackboy                # 默认推 1.4.0 和 latest
#   ./docker-push.sh hzjackboy 1.4.0          # 只推 1.4.0
#   ./docker-push.sh hzjackboy 1.4.0 latest   # 显式指定多个标签
#
# 前置：已 docker login（见下面「代理」一节）、docker/colima 正在运行。
#
# ── 为什么非得配代理 ──────────────────────────────────────────────
# 国内直连 Docker Hub 不通。踩过的坑：
#   1. BuildKit **自己的** registry 解析器不认 HTTP(S)_PROXY 环境变量，
#      给构建器加 --driver-opt env.HTTPS_PROXY=... 也没用，照样
#      dial tcp x.x.x.x:443: i/o timeout。
#   2. 真正会走代理的，是 **docker CLI 自己**发起的那次 auth.docker.io token 请求。
#      所以命令必须在带 HTTPS_PROXY 的本机 shell 里跑。
#   3. 因此不能用 docker-container 驱动（推镜像的是 VM 里的 buildkitd，它不走代理），
#      要用 docker 驱动：CLI 走代理做鉴权，daemon 走它自己的代理传层，两边都通。
# 脚本会自动探测常见本地代理端口，探测不到就报错提示你手动设置。
set -euo pipefail

USER_NAME="${1:-}"
[ "$#" -gt 0 ] && shift

if [ -z "${USER_NAME}" ]; then
  echo "用法：./docker-push.sh <dockerhub用户名> [标签...]" >&2
  echo "例如：./docker-push.sh hzjackboy 1.4.0 latest" >&2
  exit 1
fi

REPO="${USER_NAME}/lan-device-scanner"
if [ "$#" -gt 0 ]; then
  TAGS=("$@")
else
  TAGS=("1.4.0" "latest")
fi

# 以脚本所在目录为项目根目录（构建上下文、DOCKERHUB.md 都按它找），
# 这样从任何地方调用都行
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [ ! -d "${PROJECT_DIR}" ]; then
  echo "进不去项目目录：${PROJECT_DIR}" >&2
  exit 1
fi
cd "${PROJECT_DIR}"

# buildx 默认把状态写在 ~/.docker/buildx，受限环境（沙箱/CI）下不可写，放到工作区里
export BUILDX_CONFIG="${BUILDX_CONFIG:-${PROJECT_DIR}/.buildx}"

say()  { printf '\033[36m▸\033[0m %s\n' "$1"; }
ok()   { printf '\033[32m✔\033[0m %s\n' "$1"; }
warn() { printf '\033[33m!\033[0m %s\n' "$1"; }
die()  { printf '\033[31m✘\033[0m %s\n' "$1" >&2; exit 1; }

# ── 1. docker 在不在 ────────────────────────────────────────────
docker info >/dev/null 2>&1 || die "docker 连不上，先启动 colima（colima start）或 Docker Desktop"

# 用当前 docker context 对应的 docker 驱动构建器（见文件头第 3 条）
CTX="$(docker context show 2>/dev/null || echo default)"
if docker buildx inspect "${CTX}" >/dev/null 2>&1; then
  BUILDER="${CTX}"
else
  BUILDER="default"
fi
VER="$(docker info --format '{{.ServerVersion}}' 2>/dev/null || echo '?')"
ok "docker ${VER}｜context=${CTX}｜builder=${BUILDER}"

# ── 2. 代理 ────────────────────────────────────────────────────
if curl -s -m 6 -o /dev/null https://registry-1.docker.io/v2/ 2>/dev/null; then
  ok "Docker Hub 可直连，不需要代理"
else
  found=""
  for p in "${HTTPS_PROXY:-}" "http://127.0.0.1:7897" "http://127.0.0.1:7890" \
           "http://127.0.0.1:1087" "http://127.0.0.1:8080"; do
    [ -n "${p}" ] || continue
    if curl -s -m 6 -o /dev/null -x "${p}" https://auth.docker.io/token 2>/dev/null; then
      found="${p}"; break
    fi
  done
  [ -n "${found}" ] || die "直连不通，也没探测到可用代理。请先开代理，或手动 export HTTPS_PROXY=http://127.0.0.1:端口"
  export HTTPS_PROXY="${found}" HTTP_PROXY="${found}"
  ok "经代理访问 Docker Hub：${found}"
fi

# ── 3. 登录状态 ────────────────────────────────────────────────
# 凭据可能在三处，要挨个问：
#   ① credsStore（我们推荐的 macOS 钥匙串）—— 问 docker-credential-<store>
#   ② config.json 的 auths（老式的 base64 明文）
#   ③ docker info 的 Username 行（只在 ② 存在时才会出现）
# 只查 ②③ 会漏掉钥匙串的情况，导致明明登录了却报「还没登录」。
DOCKER_SERVER="https://index.docker.io/v1/"

creds_store() {  # 打印 config.json 里配的 credsStore，没有则空
  python3 -c 'import json,os
try:
    print(json.load(open(os.path.expanduser("~/.docker/config.json"))).get("credsStore",""))
except Exception:
    pass' 2>/dev/null
}

STORE="$(creds_store)"
LOGGED_USER=""
if [ -n "${STORE}" ] && command -v "docker-credential-${STORE}" >/dev/null 2>&1; then
  LOGGED_USER="$(printf '%s' "${DOCKER_SERVER}" | "docker-credential-${STORE}" get 2>/dev/null \
    | python3 -c 'import sys,json;print(json.load(sys.stdin).get("Username",""))' 2>/dev/null)"
fi
if [ -z "${LOGGED_USER}" ]; then
  LOGGED_USER="$(docker info 2>/dev/null | grep -i '^ *Username:' | head -1 | sed 's/.*: *//')"
fi

if [ -n "${LOGGED_USER}" ]; then
  if [ -n "${STORE}" ]; then
    ok "已登录：${LOGGED_USER}（凭据在 ${STORE} 钥匙串里，config.json 里没有明文）"
  else
    ok "已登录：${LOGGED_USER}"
  fi
elif grep -q "index.docker.io" "${HOME}/.docker/config.json" 2>/dev/null; then
  ok "~/.docker/config.json 里有 Docker Hub 凭据"
else
  die "还没 docker login。注意登录也要带代理（写成一行，别分行粘贴）：

    HTTPS_PROXY=http://127.0.0.1:7897 HTTP_PROXY=http://127.0.0.1:7897 docker login -u ${USER_NAME}

    密码处填 Access Token（https://hub.docker.com/settings/security 生成），不是登录密码。
    想避免令牌明文落盘，装个 credential helper：

    brew install docker-credential-helper
    # 然后在 ~/.docker/config.json 里加 \"credsStore\": \"osxkeychain\""
fi

# ── 4. 构建并推送 ──────────────────────────────────────────────
TAG_ARGS=()
for t in "${TAGS[@]}"; do TAG_ARGS+=("-t" "${REPO}:${t}"); done

say "构建 linux/amd64 + linux/arm64 并推送 → ${REPO}"
say "标签：${TAGS[*]}"
docker buildx build \
  --builder "${BUILDER}" \
  --platform linux/amd64,linux/arm64 \
  --push \
  "${TAG_ARGS[@]}" \
  .

ok "推送完成"

# ── 5. 同步 Docker Hub 仓库页的说明 ────────────────────────────
# docker push 只推镜像层，**不带仓库元数据**。不主动设置的话，Hub 页面上
# 既没有副标题也没有 Overview，只会显示 "No overview available"。
# 这里用 Hub 的 REST API 把 DOCKERHUB.md 设成 Overview 正文。
# 这一步失败不影响镜像（镜像已经推上去了），所以只告警不中断。
# Docker Hub 的副标题上限是 **100 字节**（不是 100 字）。
# 中文一个字 3 字节，所以这里最多 33 个汉字 —— 写长了 API 会报
# "Exceeded max number of bytes 100"。下面 python 里还有一层按字节截断兜底。
SHORT_DESC="零依赖的局域网设备扫描器：认出设备、记住它"

hub_credential() {
  [ -n "${STORE}" ] && command -v "docker-credential-${STORE}" >/dev/null 2>&1 || return 1
  printf '%s' "${DOCKER_SERVER}" | "docker-credential-${STORE}" get 2>/dev/null \
    | python3 -c 'import sys,json;print(json.load(sys.stdin).get("Secret",""))' 2>/dev/null
}

sync_hub_meta() {
  local overview="${PROJECT_DIR:-.}/DOCKERHUB.md"
  [ -f "${overview}" ] || overview="DOCKERHUB.md"
  if [ ! -f "${overview}" ]; then
    warn "没找到 DOCKERHUB.md，跳过仓库说明同步"
    return 0
  fi

  local secret
  secret="$(hub_credential)" || true
  if [ -z "${secret}" ]; then
    warn "读不到 Docker Hub 令牌，跳过仓库说明同步"
    return 0
  fi

  # 登录换 JWT。令牌走环境变量传给 python，避免出现在命令行参数里（ps 能看到）
  local login_body jwt
  login_body="$(HUB_USER="${USER_NAME}" HUB_TOKEN="${secret}" python3 -c \
    'import json,os;print(json.dumps({"username":os.environ["HUB_USER"],"password":os.environ["HUB_TOKEN"]}))' 2>/dev/null)"
  jwt="$(curl -s -m 25 -X POST "https://hub.docker.com/v2/users/login/" \
      -H 'Content-Type: application/json' --data-binary "${login_body}" 2>/dev/null \
    | python3 -c 'import sys,json
try: print(json.load(sys.stdin).get("token",""))
except Exception: print("")' 2>/dev/null)"
  if [ -z "${jwt}" ]; then
    warn "拿不到 Docker Hub JWT，跳过仓库说明同步（镜像已推送成功）"
    return 0
  fi

  local body
  body="$(HUB_DESC="${SHORT_DESC}" HUB_FILE="${overview}" python3 -c '
import json, os

full = open(os.environ["HUB_FILE"], encoding="utf-8").read()

# 副标题硬上限 100 字节；按字节截断且不能截断多字节字符
desc = os.environ["HUB_DESC"]
raw = desc.encode("utf-8")
if len(raw) > 100:
    raw = raw[:100]
    while raw:
        try:
            desc = raw.decode("utf-8")
            break
        except UnicodeDecodeError:
            raw = raw[:-1]

print(json.dumps({"description": desc, "full_description": full}))' 2>/dev/null)"

  if curl -s -m 30 -o /dev/null -w '%{http_code}' -X PATCH \
      "https://hub.docker.com/v2/repositories/${REPO}/" \
      -H "Authorization: JWT ${jwt}" -H 'Content-Type: application/json' \
      --data-binary "${body}" 2>/dev/null | grep -q '^200$'; then
    ok "已同步仓库说明（副标题 + Overview 来自 DOCKERHUB.md）"
  else
    warn "仓库说明同步失败（镜像已推送成功，不影响拉取）"
  fi
}

say "同步 Docker Hub 仓库页说明"
sync_hub_meta

echo
echo "  拉取：docker pull ${REPO}:${TAGS[0]}"
echo "  运行：docker run -d --name lan-scan --network host -v lan-scan-data:/app/data ${REPO}:${TAGS[0]}"
echo "  页面：http://127.0.0.1:8765"
echo
echo "  ⚠️  --network host 是必须的，否则 ARP 扫不到局域网。"
echo "      macOS 上即使是 host 网络，容器也只看到虚拟机内网，"
echo "      要扫真实局域网请部署到 Linux 主机 / 软路由 / NAS。"
