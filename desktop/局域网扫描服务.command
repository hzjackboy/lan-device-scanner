#!/bin/bash
# ============================================
# 局域网设备扫描服务 —— 启动 / 停止 / 打开页面
#
# 用法：
#   双击本文件        打开菜单，按序号选择
#   终端带参数调用    ./局域网扫描服务.command start|stop|restart|open|status|log
#
# 桌面上的「启动局域网扫描.command」「关闭局域网扫描.command」
# 是本脚本的快捷方式（分别等价于 start / stop）。
# ============================================

# ⚠️ 本脚本用 macOS 自带的 bash 3.2 跑（#!/bin/bash），它有个坑：
#    变量后面紧跟中文/全角字符时，会把该字符的第一个字节当成变量名的一部分，
#    导致"$PORT）"这种写法输出乱码。所以本脚本里变量一律写成 ${VAR}，
#    以后改脚本也请保持这个写法。
#
# Finder 启动的终端 PATH 可能不含 Homebrew，补一下
export PATH="/opt/homebrew/bin:/usr/local/bin:${PATH}"

# 项目目录：需要改路径时改这里，或者设环境变量 LAN_SCAN_PROJECT
PROJECT_DIR="${LAN_SCAN_PROJECT:-/Users/you/lan-scan}"
# 兜底：从仓库里的 desktop/ 目录直接跑时，用它的上一级
if [ ! -d "${PROJECT_DIR}" ]; then
    PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." 2>/dev/null && pwd)"
fi
PORT=8765
HOST="0.0.0.0"
PID_FILE="${PROJECT_DIR}/data/server.pid"
LOG_FILE="${PROJECT_DIR}/data/server.log"
URL="http://127.0.0.1:${PORT}"
PYTHON="$(command -v python3 || true)"

BOLD=$'\033[1m'; DIM=$'\033[2m'; RED=$'\033[31m'; GREEN=$'\033[32m'
YELLOW=$'\033[33m'; CYAN=$'\033[36m'; RESET=$'\033[0m'

say()  { printf '%s\n' "$*"; }
ok()   { printf '%s✔%s %s\n' "${GREEN}" "${RESET}" "$*"; }
warn() { printf '%s!%s %s\n' "${YELLOW}" "${RESET}" "$*"; }
err()  { printf '%s✘%s %s\n' "${RED}" "${RESET}" "$*"; }

# ---------- 基础检查 ----------
if [ ! -d "${PROJECT_DIR}" ]; then
    err "找不到项目目录：${PROJECT_DIR}"
    say "   请修改本脚本里的 PROJECT_DIR"
    exit 1
fi
cd "${PROJECT_DIR}" || exit 1
mkdir -p "${PROJECT_DIR}/data"

lan_ip() {
    local ip
    ip="$(ipconfig getifaddr en0 2>/dev/null)"
    [ -z "${ip}" ] && ip="$(ipconfig getifaddr en1 2>/dev/null)"
    printf '%s' "${ip}"
}

# 服务在监听端口吗（只要有进程占着端口就算，不要求 HTTP 正常）
port_pid() {
    lsof -ti "tcp:${PORT}" -sTCP:LISTEN 2>/dev/null | head -1
}

# HTTP 真的有响应吗
is_up() {
    curl -fsS -m 3 "${URL}/api/status" >/dev/null 2>&1
}

# 拿服务进程号：先信 pid 文件，再按端口找
server_pid() {
    local p
    if [ -f "${PID_FILE}" ]; then
        p="$(cat "${PID_FILE}" 2>/dev/null)"
        if [ -n "${p}" ] && kill -0 "${p}" 2>/dev/null; then
            printf '%s' "${p}"
            return 0
        fi
    fi
    p="$(port_pid)"
    [ -n "${p}" ] && { printf '%s' "${p}"; return 0; }
    return 1
}

# ---------- 启动 ----------
do_start() {
    if is_up; then
        ok "服务已经在运行了（PID $(server_pid)，端口 ${PORT}）"
        return 0
    fi
    if [ -n "$(port_pid)" ]; then
        warn "端口 ${PORT} 被 PID $(port_pid) 占着但没响应，先清理掉"
        do_stop >/dev/null 2>&1
    fi
    if [ -z "${PYTHON}" ]; then
        err "找不到 python3，请先安装 Python 3.9+"
        return 1
    fi

    say "启动中…（日志：${LOG_FILE}）"
    say "" >> "${LOG_FILE}"
    say "===== $(date '+%Y-%m-%d %H:%M:%S') 启动 =====" >> "${LOG_FILE}"
    nohup "${PYTHON}" "${PROJECT_DIR}/server.py" --host "${HOST}" --port "${PORT}" >> "${LOG_FILE}" 2>&1 &
    local new_pid=$!
    printf '%s' "${new_pid}" > "${PID_FILE}"
    disown 2>/dev/null || true

    local i
    for i in $(seq 1 40); do
        if is_up; then
            ok "服务已启动（PID ${new_pid}）"
            return 0
        fi
        if ! kill -0 "${new_pid}" 2>/dev/null; then
            err "进程已退出，最后几行日志："
            tail -n 15 "${LOG_FILE}"
            return 1
        fi
        sleep 0.4
    done
    err "等了 16 秒还没就绪，看看日志：${LOG_FILE}"
    tail -n 15 "${LOG_FILE}"
    return 1
}

# ---------- 停止 ----------
do_stop() {
    local pid
    pid="$(server_pid)" || {
        warn "服务没在运行"
        rm -f "${PID_FILE}"
        return 0
    }
    say "正在停止 PID ${pid} …"
    kill "${pid}" 2>/dev/null
    local i
    for i in $(seq 1 24); do
        kill -0 "${pid}" 2>/dev/null || break
        sleep 0.25
    done
    if kill -0 "${pid}" 2>/dev/null; then
        warn "优雅退出超时，强制结束"
        kill -9 "${pid}" 2>/dev/null
        sleep 0.5
    fi
    rm -f "${PID_FILE}"
    if [ -n "$(port_pid)" ]; then
        err "端口 ${PORT} 还被 PID $(port_pid) 占用"
        return 1
    fi
    ok "服务已停止"
}

# ---------- 打开页面 ----------
do_open() {
    if ! is_up; then
        warn "服务没在跑，先帮你启动"
        do_start || return 1
    fi
    open "${URL}"
    ok "已在浏览器打开 ${URL}"
    local ip; ip="$(lan_ip)"
    [ -n "${ip}" ] && say "   手机/平板可访问：http://${ip}:${PORT}"
}

# ---------- 查看状态 ----------
do_status() {
    if ! is_up; then
        warn "服务未运行"
        say "   本机地址：${URL}"
        return 1
    fi
    ok "服务运行中（PID $(server_pid)，端口 ${PORT}）"
    local json
    json="$(curl -s -m 3 "${URL}/api/status")"
    printf '%s' "${json}" | "${PYTHON}" -c '
import json, sys
try:
    d = json.load(sys.stdin)
except Exception:
    print("   （状态解析失败）"); raise SystemExit
print("   版本     : v%s   平台 %s   ping %s" % (
    d.get("version", "?"), d.get("platform", "?"),
    "可用" if d.get("has_ping") else "不可用"))
for i in d.get("interfaces", []):
    print("   扫描网段 : %s（%s，本机 %s）" % (i["cidr"], i["name"], i["ip"]))
a = d.get("auto") or {}
if a.get("enabled"):
    left = int(a.get("next_run_in") or 0)
    when = ("即将执行（不足 1 分钟）" if left < 60 else "下次约 %d 分钟后" % (left // 60))
    print("   定时重扫 : 已开启，每 %d 分钟，%s" % (a["interval"] // 60, when))
else:
    print("   定时重扫 : 未开启")
s = d.get("devices") or {}
print("   设备台账 : 共 %s 台（在线 %s / 掉线 %s）" % (
    s.get("total", 0), s.get("online", 0), s.get("offline", 0)))
print("   当前任务 : %s" % ("有扫描正在运行" if d.get("active_scan") else "空闲"))
'
    local ip; ip="$(lan_ip)"
    [ -n "${ip}" ] && say "   局域网   : http://${ip}:${PORT}"
}

# ---------- 看日志 ----------
do_log() {
    if [ ! -f "${LOG_FILE}" ]; then
        warn "还没有日志文件（服务没启动过？）"
        return 1
    fi
    say "${BOLD}最近 40 行日志${RESET}  ${LOG_FILE}"
    say "----------------------------------------------"
    tail -n 40 "${LOG_FILE}"
    say "----------------------------------------------"
    say "实时跟踪：tail -f \"${LOG_FILE}\""
}

# ---------- 菜单 ----------
show_menu() {
    clear 2>/dev/null || true
    say "=============================================="
    say "  ${BOLD}局域网设备扫描服务${RESET}"
    say "=============================================="
    if is_up; then
        printf '  状态：%s● 运行中%s（PID %s）\n' "${GREEN}" "${RESET}" "$(server_pid)"
    elif [ -n "$(port_pid)" ]; then
        printf '  状态：%s● 端口被占但无响应%s（PID %s）\n' "${YELLOW}" "${RESET}" "$(port_pid)"
    else
        printf '  状态：%s○ 未运行%s\n' "${DIM}" "${RESET}"
    fi
    printf '  本机：%s\n' "${URL}"
    local ip; ip="$(lan_ip)"
    [ -n "${ip}" ] && printf '  局域网：http://%s:%s\n' "${ip}" "${PORT}"
    say "----------------------------------------------"
    say "  1) 启动服务并打开页面"
    say "  2) 停止服务"
    say "  3) 重启服务"
    say "  4) 只打开页面"
    say "  5) 查看运行状态"
    say "  6) 查看最近日志"
    say "  0) 退出"
    say "----------------------------------------------"
}

menu_loop() {
    local choice
    while true; do
        show_menu
        printf '  请输入序号: '
        read -r choice || { say ""; exit 0; }   # 没有输入（比如被管道调用）就直接退出
        case "${choice}" in
            1) do_start && do_open ;;
            2) do_stop ;;
            3) do_stop; do_start && do_open ;;
            4) do_open ;;
            5) do_status ;;
            6) do_log ;;
            0|q|Q) say "再见。"; exit 0 ;;
            *) warn "没这个选项：${choice}" ;;
        esac
        say ""
        printf '  按回车回到菜单…'
        read -r _ || exit 0
    done
}

# ---------- 入口 ----------
case "${1:-}" in
    start)   do_start && do_open ;;
    stop)    do_stop ;;
    restart) do_stop; do_start && do_open ;;
    open)    do_open ;;
    status)  do_status ;;
    log)     do_log ;;
    "")      menu_loop ;;
    *)
        say "用法：$(basename "$0") [start|stop|restart|open|status|log]"
        say "   不带参数 = 打开菜单"
        exit 2
        ;;
esac
