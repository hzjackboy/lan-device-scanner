#!/bin/bash
# ============================================
# 容器冒烟测试：构建镜像 → 起容器 → 验证 API / 页面 / 扫描 / 持久化 / 健康检查
#
#   在项目根目录跑： ./tests/docker_smoke.sh
#
# 两个场景：
#   A. bridge + 端口映射（宿主机 8899 → 容器 8765，避开你在本机跑的 8765）
#   B. host 网络（生产用法：ARP 才看得到 docker 宿主机的局域网）
#
# 两个环境细节（macOS + colima 上踩过的）：
#   1. 探测 host 网络的容器必须从容器内部（docker exec）去 curl。
#      不能从 Mac 上 curl 127.0.0.1 —— colima 把虚拟机的 localhost 转发到了
#      Mac 的 localhost，会打到 Mac 自己的服务上，测出假结果。
#   2. 数据卷路径要在 $HOME 下：colima 默认只把 $HOME 挂进虚拟机，
#      用 /tmp 之类的路径，容器会写进虚拟机内部，宿主机看不到文件。
# ============================================
set -u
cd "$(dirname "$0")/.." || exit 1

# buildx 把状态写在 ~/.docker/buildx，受限环境（沙箱 / CI）下不可写，
# 装了 buildx 插件后 `docker build` 会走 BuildKit 并因此报
# "mkdir /Users/xxx/.docker/buildx: operation not permitted"。放到工作区里绕开。
export BUILDX_CONFIG="${BUILDX_CONFIG:-${PWD}/.buildx}"

IMG="lan-device-scanner:test"
NAME="lan-scan-test"
PORT=8899
DATA_DIR="${HOME}/.lan-scan-docker-smoke/data"
mkdir -p "${DATA_DIR}" 2>/dev/null || true     # 沙箱里可能不让建，容器会自己创建
rm -f "${DATA_DIR}/devices.json" 2>/dev/null || true

GREEN=$'\033[32m'; RED=$'\033[31m'; DIM=$'\033[2m'; RESET=$'\033[0m'
pass=0; fail=0
ok()   { printf '%s✔%s %s\n' "${GREEN}" "${RESET}" "$*"; pass=$((pass+1)); }
bad()  { printf '%s✘%s %s\n' "${RED}" "${RESET}" "$*"; fail=$((fail+1)); }
step() { printf '\n%s── %s ──%s\n' "${DIM}" "$*" "${RESET}"; }

cleanup() { docker rm -f "${NAME}" >/dev/null 2>&1; }
trap cleanup EXIT

# 服务需要登录。容器首次启动会在 /app/data/local_token 生成管理员令牌；
# 容器内用 ctoken()，宿主机侧访问映射端口用 htoken()。
ctoken() {
    docker exec "${NAME}" python3 -c \
        'import json;print(json.load(open("/app/data/local_token"))["token"])' 2>/dev/null
}

htoken() {
    sed -n 's/.*"token"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' \
        "${DATA_DIR}/local_token" 2>/dev/null
}

hcurl() {  # 宿主机侧带令牌的 curl
    local tok; tok="$(htoken)"
    if [ -n "${tok}" ]; then curl -fsS -H "X-Local-Token: ${tok}" "$@"
    else curl -fsS "$@"; fi
}

# 从容器内部取数据：镜像里没有 curl，用 python3 标准库
cexec() { # $1=url，$2=可选 POST body
    if [ $# -ge 2 ]; then
        docker exec "${NAME}" python3 -c '
import sys, json, urllib.request
h = {"Content-Type": "application/json"}
try: h["X-Local-Token"] = json.load(open("/app/data/local_token"))["token"]
except Exception: pass
req = urllib.request.Request(sys.argv[1], data=sys.argv[2].encode(), headers=h, method="POST")
print(urllib.request.urlopen(req, timeout=10).read().decode())' "$1" "$2"
    else
        docker exec "${NAME}" python3 -c '
import sys, json, urllib.request
h = {}
try: h["X-Local-Token"] = json.load(open("/app/data/local_token"))["token"]
except Exception: pass
req = urllib.request.Request(sys.argv[1], headers=h)
print(urllib.request.urlopen(req, timeout=10).read().decode())' "$1"
    fi
}

wait_http() {      # 从本机探测（端口映射场景）$1=url $2=最多等几秒
    local url="$1" limit="${2:-60}" i
    for i in $(seq 1 "${limit}"); do
        hcurl -m 2 "${url}/api/status" >/dev/null 2>&1 && return 0
        sleep 1
    done
    return 1
}

wait_container() { # 从容器内部探测（host 网络场景）$1=最多等几秒
    local limit="${1:-60}" i
    for i in $(seq 1 "${limit}"); do
        cexec http://127.0.0.1:8765/api/status >/dev/null 2>&1 && return 0
        sleep 1
    done
    return 1
}

step "1/7 构建镜像"
if docker build -q -t "${IMG}" . > /tmp/.docker-build.log 2>&1; then
    ok "构建成功（docker images 显示 $(docker image inspect "${IMG}" --format '{{.Size}}' | awk '{printf "%.0f MB 层大小", $1/1048576}')）"
else
    bad "构建失败"; tail -25 /tmp/.docker-build.log; exit 1
fi

step "2/7 镜像内容自检（不该带 data/、desktop/、tests/）"
LIST="$(docker run --rm --entrypoint sh "${IMG}" -c 'ls -A /app')"
for want in server.py scanner.py auth.py mdns.py netbios.py oui.py update_oui.py static data; do
    printf '%s' "${LIST}" | grep -qx "${want}" && ok "含 ${want}" || bad "缺 ${want}"
done
for unwanted in desktop tests oui.csv; do
    printf '%s' "${LIST}" | grep -qx "${unwanted}" && bad "不该有 ${unwanted}" || ok "无 ${unwanted}"
done

step "3/7 场景 A：bridge 网络 + 端口映射"
docker rm -f "${NAME}" >/dev/null 2>&1
docker run -d --name "${NAME}" -p "${PORT}:8765" -v "${DATA_DIR}:/app/data" "${IMG}" >/dev/null
if wait_http "http://127.0.0.1:${PORT}" 60; then
    ok "容器起来了，/api/status 有响应"
else
    bad "起不来"; docker logs "${NAME}" 2>&1 | tail -15
fi
for path in "/" "/static/app.js" "/static/style.css"; do
    code="$(curl -s -o /dev/null -w '%{http_code}' "http://127.0.0.1:${PORT}${path}")"
    [ "${code}" = "200" ] && ok "GET ${path} → 200" || bad "GET ${path} → ${code}"
done
hcurl "http://127.0.0.1:${PORT}/api/status" | python3 -c '
import json,sys
d = json.load(sys.stdin)
print("    版本 %s | 网卡 %s | 台账 %s 台" % (
    d["version"], ", ".join(i["cidr"] for i in d["interfaces"]) or "无", d["devices"]["total"]))
' 2>/dev/null && ok "状态接口返回正常" || bad "状态接口异常"
BRIDGE_CIDR="$(hcurl "http://127.0.0.1:${PORT}/api/status" | python3 -c 'import json,sys;print(",".join(i["cidr"] for i in json.load(sys.stdin)["interfaces"]))' 2>/dev/null)"
case "${BRIDGE_CIDR}" in
    172.*) ok "bridge 模式下只能看到容器网络（${BRIDGE_CIDR}）——这就是必须用 host 网络的原因" ;;
    *)     ok "bridge 模式下网段：${BRIDGE_CIDR}" ;;
esac
SID="$(hcurl -X POST "http://127.0.0.1:${PORT}/api/scan" -H 'Content-Type: application/json' \
        -d '{"subnet":"10.0.0.0/24","demo":true}' | python3 -c 'import json,sys;print(json.load(sys.stdin)["scan_id"])' 2>/dev/null)"
if [ -n "${SID}" ]; then
    for i in $(seq 1 30); do
        st="$(hcurl "http://127.0.0.1:${PORT}/api/scan/${SID}" | python3 -c 'import json,sys;print(json.load(sys.stdin)["scan"]["state"])' 2>/dev/null)"
        [ "${st}" = "done" ] && break
        sleep 1
    done
    n="$(hcurl "http://127.0.0.1:${PORT}/api/scan/${SID}" | python3 -c 'import json,sys;print(len(json.load(sys.stdin)["scan"]["devices"]))' 2>/dev/null)"
    [ "${n:-0}" -gt 0 ] && ok "演示扫描跑通，识别 ${n} 台设备（扫描引擎与 SSE 在容器里正常）" || bad "演示扫描没出结果"
else
    bad "启动演示扫描失败"
fi
sleep 3
HEALTH="$(docker inspect "${NAME}" --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}')"
[ "${HEALTH}" = "healthy" ] && ok "HEALTHCHECK = healthy" || bad "HEALTHCHECK = ${HEALTH}"

step "4/7 场景 B：host 网络（生产用法）"
docker rm -f "${NAME}" >/dev/null 2>&1
docker run -d --name "${NAME}" --network host -v "${DATA_DIR}:/app/data" "${IMG}" >/dev/null
if wait_container 60; then
    ok "host 网络下容器正常启动（从容器内部探测）"
    HOST_CIDR="$(cexec http://127.0.0.1:8765/api/status | python3 -c 'import json,sys;print(",".join(i["cidr"] for i in json.load(sys.stdin)["interfaces"]))' 2>/dev/null)"
    echo "    容器看到的网段：${HOST_CIDR}"
    case "${HOST_CIDR}" in
        172.17.*) bad "还是 docker bridge 网段，host 网络没生效" ;;
        "")       bad "没识别到网段" ;;
        *)        ok "host 网络生效（不再是 bridge 网段）" ;;
    esac
else
    bad "host 网络起不来"; docker logs "${NAME}" 2>&1 | tail -15
fi

TARGET_CIDR="$(cexec http://127.0.0.1:8765/api/status | python3 -c '
import json,sys
ifaces = json.load(sys.stdin)["interfaces"]
print(ifaces[0]["cidr"] if ifaces else "")' 2>/dev/null)"
if [ -n "${TARGET_CIDR}" ]; then
    SID="$(cexec "http://127.0.0.1:8765/api/scan" "{\"subnet\":\"${TARGET_CIDR}\",\"profile\":\"fast\"}" | python3 -c 'import json,sys;print(json.load(sys.stdin)["scan_id"])' 2>/dev/null)"
    for i in $(seq 1 45); do
        st="$(cexec "http://127.0.0.1:8765/api/scan/${SID}" | python3 -c 'import json,sys;print(json.load(sys.stdin)["scan"]["state"])' 2>/dev/null)"
        [ "${st}" = "done" ] && break
        sleep 1
    done
    cexec "http://127.0.0.1:8765/api/scan/${SID}" | python3 -c '
import json,sys
s = json.load(sys.stdin)["scan"]
print("    扫描 %s：发现 %d 台，其中 %d 台拿到 MAC" % (
    s["subnet"], s["stats"]["total"], s["stats"]["with_mac"]))
for d in s["devices"][:4]:
    print("      %-14s %-18s %s" % (d["ip"], d["mac"] or "-", d.get("vendor") or ""))
' 2>/dev/null
    WITH_MAC="$(cexec "http://127.0.0.1:8765/api/scan/${SID}" | python3 -c 'import json,sys;print(json.load(sys.stdin)["scan"]["stats"]["with_mac"])' 2>/dev/null)"
    [ "${WITH_MAC:-0}" -gt 0 ] && ok "容器内 ARP + 扫描可用（拿到 ${WITH_MAC} 个 MAC）" || bad "容器内扫描没拿到 MAC，ARP 可能不可用"
    if [ -f "${DATA_DIR}/devices.json" ]; then
        ok "台账已写入挂载卷（$(python3 -c 'import json;print(len(json.load(open("'"${DATA_DIR}"'/devices.json"))["devices"]))' 2>/dev/null) 条）"
    else
        bad "挂载卷里没有 devices.json（卷路径要在 \$HOME 下，colima 才挂得进去）"
    fi
    BEFORE="$(cexec http://127.0.0.1:8765/api/devices | python3 -c 'import json,sys;print(json.load(sys.stdin)["stats"]["total"])' 2>/dev/null)"
    docker restart "${NAME}" >/dev/null && wait_container 60
    AFTER="$(cexec http://127.0.0.1:8765/api/devices | python3 -c 'import json,sys;print(json.load(sys.stdin)["stats"]["total"])' 2>/dev/null)"
    [ "${BEFORE}" = "${AFTER}" ] && ok "容器重启后台账不丢（${BEFORE} 条）" || bad "重启后台账变了：${BEFORE} → ${AFTER}"
else
    bad "拿不到网段，跳过真实扫描"
fi

step "5/7 日志里有没有异常"
if docker logs "${NAME}" 2>&1 | grep -qiE "traceback|error"; then
    bad "日志里有报错"
    docker logs "${NAME}" 2>&1 | grep -iE -A3 "traceback|error" | head -12
else
    ok "日志干净"
fi

step "6/7 清理"
docker rm -f "${NAME}" >/dev/null 2>&1 && ok "已删除测试容器（镜像保留：${IMG}）"
rm -rf "${DATA_DIR%/*}" 2>/dev/null && ok "已清理测试数据目录" || echo "    测试数据留在：${DATA_DIR}"

step "7/7 结果"
printf '通过 %d 项，失败 %d 项\n' "${pass}" "${fail}"
[ "${fail}" -eq 0 ] || exit 1
