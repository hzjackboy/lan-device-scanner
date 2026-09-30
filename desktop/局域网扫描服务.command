#!/bin/bash
# ============================================
# 局域网设备扫描服务 —— 启动 / 停止 / 重启 / 打开页面
# （单文件版，全部功能都在这一个脚本里）
#
# 用法：
#   双击本文件   打开菜单。顶部状态面板常驻，等待输入时每 3 秒原地刷新一次，
#                随时都能看到服务是死是活、台账多少台、下次重扫还有多久。
#   命令行调用   ./局域网扫描服务.command start|stop|restart|open|toggle|status|log|help
#
# 菜单行为：
#   · 顶部状态面板在等待输入期间自动刷新，不需要手动按 5 查状态
#   · 输入序号后按回车执行；直接回车 = 按当前状态执行默认动作
#   · **每个动作执行完都会自动回到菜单**：倒计时结束自动回，按回车立刻回
# ============================================

# ⚠️ 本脚本用 macOS 自带的 bash 3.2 跑（#!/bin/bash），它有两个坑：
#    1. 变量后面紧跟中文/全角字符时，会把该字符的第一个字节当成变量名的一部分，
#       导致"$PORT）"这种写法输出乱码。所以本脚本里变量一律写成 ${VAR}，
#       以后改脚本也请保持这个写法。
#    2. read 的 -t 只认整数秒（`read -t 0.5` 会报 invalid timeout specification），
#       所以刷新/倒计时都用整数秒。
#    3. read -t 超时**返回 1**，和 EOF 一样（不是常见的 128+14=142）。
#       菜单循环靠"耗时是否等满超时秒数"来区分，改这段时务必保留。
#
# Finder 启动的终端 PATH 可能不含 Homebrew，补一下
export PATH="/opt/homebrew/bin:/usr/local/bin:${PATH}"

# 项目目录按这个顺序找：
#   1. 环境变量 LAN_SCAN_PROJECT —— 把脚本复制到桌面时，由那份「指针」脚本设好
#   2. 脚本所在目录的上一级 —— 直接在仓库的 desktop/ 里跑，或者仓库里双击
# 这里不写死任何绝对路径，换台机器 / 换个用户名都不用改代码。
PROJECT_DIR="${LAN_SCAN_PROJECT:-}"
if [ -z "${PROJECT_DIR}" ] || [ ! -f "${PROJECT_DIR}/server.py" ]; then
    PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." 2>/dev/null && pwd)"
fi
PORT=8765
HOST="0.0.0.0"
PID_FILE="${PROJECT_DIR}/data/server.pid"
LOG_FILE="${PROJECT_DIR}/data/server.log"
URL="http://127.0.0.1:${PORT}"
PYTHON="$(command -v python3 || true)"

# 菜单在等待输入时，每隔这么多秒刷新一次状态面板
REFRESH_SECS=3
# 动作执行完后，倒计时多少秒自动回到菜单（按回车可立刻返回）
PAUSE_SECS=6

BOLD=$'\033[1m'; DIM=$'\033[2m'; RED=$'\033[31m'; GREEN=$'\033[32m'
YELLOW=$'\033[33m'; CYAN=$'\033[36m'; RESET=$'\033[0m'

say()  { printf '%s\n' "$*"; }
ok()   { printf '%s✔%s %s\n' "${GREEN}" "${RESET}" "$*"; }
warn() { printf '%s!%s %s\n' "${YELLOW}" "${RESET}" "$*"; }
err()  { printf '%s✘%s %s\n' "${RED}" "${RESET}" "$*"; }

# ---------- 基础检查 ----------
if [ ! -f "${PROJECT_DIR}/server.py" ]; then
    err "找不到项目目录（里面应该有 server.py）：${PROJECT_DIR}"
    say "   这个脚本会先看环境变量 LAN_SCAN_PROJECT，再找自己所在目录的上一级。"
    say "   把脚本复制到别处（比如桌面）时，用一份设好该变量的指针脚本调用它，例如："
    say "       export LAN_SCAN_PROJECT=/你的路径/局域网模拟器"
    say "       exec \"\${LAN_SCAN_PROJECT}/desktop/局域网扫描服务.command\" \"\$@\""
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

# 终端行数（拿不到就按 24 算）
term_lines() {
    local n
    n="$(tput lines 2>/dev/null)"
    case "${n}" in
        ''|*[!0-9]*) n=24 ;;
    esac
    [ "${n}" -lt 10 ] && n=24
    printf '%s' "${n}"
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

# ---------- 查看状态（命令行 do_status 用，一次输出完整信息）----------
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
    # 只显示能塞进当前终端的行数，免得把状态面板顶出屏幕
    local n=$(( $(term_lines) - 14 ))
    [ "${n}" -lt 10 ] && n=10
    say "${BOLD}最近 ${n} 行日志${RESET}  ${LOG_FILE}"
    say "----------------------------------------------"
    tail -n "${n}" "${LOG_FILE}"
    say "----------------------------------------------"
    say "实时跟踪：tail -f \"${LOG_FILE}\""
}

# ---------- 切换（一个动作搞定开关）----------
do_toggle() {
    if is_up; then
        do_stop
    else
        do_start && do_open
    fi
}

# 当前状态下回车应该做什么
default_action() {
    if is_up; then printf '打开页面'; else printf '启动服务并打开页面'; fi
}

usage() {
    say "局域网设备扫描服务 —— 单文件控制脚本"
    say ""
    say "用法： $(basename "$0") [动作]"
    say ""
    say "  不带动作   打开菜单（顶部状态面板自动刷新，直接回车执行默认动作）"
    say "  start      启动服务并打开页面"
    say "  stop       停止服务"
    say "  restart    重启服务"
    say "  open       只打开页面（没跑就先启动）"
    say "  toggle     没跑就启动，在跑就停止"
    say "  status     查看运行状态"
    say "  log        查看最近日志"
    say "  help       显示本帮助"
}

# ============================================================
#  状态面板
# ============================================================

# 把服务状态抓成一组变量，只发一次 HTTP 请求
load_status() {
    S_UP=0; S_PID=""; S_VER="-"; S_PLATFORM="-"; S_PING="-"
    S_IFACE="-"; S_CIDR="-"; S_SRV_IP="-"
    S_AUTO_ON=0; S_AUTO_IV=0; S_AUTO_NEXT=0; S_AUTO_RUNS=0
    S_TOTAL=0; S_ONLINE=0; S_OFFLINE=0; S_ACTIVE=""

    if ! is_up; then
        # 没跑，但端口可能被占着（半死不活）
        S_PID="$(port_pid)"
        return 0
    fi
    S_UP=1
    S_PID="$(server_pid)"

    local json
    json="$(curl -s -m 3 "${URL}/api/status" 2>/dev/null)"
    [ -z "${json}" ] && return 0
    [ -z "${PYTHON}" ] && return 0

    # 用 tab 分隔的 k/v 输出，避免 eval 注入
    local k v
    while IFS=$'\t' read -r k v; do
        case "${k}" in
            version)   S_VER="${v}" ;;
            platform)  S_PLATFORM="${v}" ;;
            ping)      S_PING="${v}" ;;
            iface)     S_IFACE="${v}" ;;
            cidr)      S_CIDR="${v}" ;;
            ip)        S_SRV_IP="${v}" ;;
            auto_on)   S_AUTO_ON="${v}" ;;
            auto_iv)   S_AUTO_IV="${v}" ;;
            auto_next) S_AUTO_NEXT="${v}" ;;
            auto_runs) S_AUTO_RUNS="${v}" ;;
            total)     S_TOTAL="${v}" ;;
            online)    S_ONLINE="${v}" ;;
            offline)   S_OFFLINE="${v}" ;;
            active)    S_ACTIVE="${v}" ;;
        esac
    done < <(printf '%s' "${json}" | "${PYTHON}" -c '
import json, sys
try:
    d = json.load(sys.stdin)
except Exception:
    raise SystemExit
def out(k, v):
    print("%s\t%s" % (k, v))
out("version", d.get("version", "?"))
out("platform", d.get("platform", "?"))
out("ping", "可用" if d.get("has_ping") else "不可用")
ifs = d.get("interfaces") or []
if ifs:
    out("iface", ifs[0].get("name", ""))
    out("cidr", ifs[0].get("cidr", ""))
    out("ip", ifs[0].get("ip", ""))
a = d.get("auto") or {}
out("auto_on", "1" if a.get("enabled") else "0")
out("auto_iv", a.get("interval") or 0)
out("auto_next", int(a.get("next_run_in") or 0))
out("auto_runs", a.get("run_count") or 0)
s = d.get("devices") or {}
out("total", s.get("total", 0))
out("online", s.get("online", 0))
out("offline", s.get("offline", 0))
out("active", d.get("active_scan") or "")
' 2>/dev/null)
}

# 已经运行了多久（用 pid 文件的修改时间当启动时间，避免依赖 ps）
fmt_uptime() {
    local base now
    base="$(stat -f %m "${PID_FILE}" 2>/dev/null || stat -c %Y "${PID_FILE}" 2>/dev/null)"
    case "${base}" in
        ''|*[!0-9]*) printf '刚刚'; return ;;
    esac
    now="$(date +%s)"
    local s=$(( now - base ))
    [ "${s}" -lt 0 ] && s=0
    if [ "${s}" -lt 60 ]; then
        printf '已运行 %d 秒' "${s}"
    elif [ "${s}" -lt 3600 ]; then
        printf '已运行 %d 分 %d 秒' $(( s / 60 )) $(( s % 60 ))
    elif [ "${s}" -lt 86400 ]; then
        printf '已运行 %d 小时 %d 分' $(( s / 3600 )) $(( (s % 3600) / 60 ))
    else
        printf '已运行 %d 天 %d 小时' $(( s / 86400 )) $(( (s % 86400) / 3600 ))
    fi
}

# 定时重扫还有多久
fmt_next() {
    local s="${1:-0}"
    if [ "${s}" -le 0 ]; then
        printf '即将执行'
    elif [ "${s}" -lt 60 ]; then
        printf '不足 1 分钟后'
    else
        printf '约 %d 分钟后' $(( s / 60 ))
    fi
}

# 打印状态面板（这段会被原地重画，见 render_frame）
status_panel() {
    local ip line
    ip="$(lan_ip)"

    say "=============================================="
    say "  ${BOLD}局域网设备扫描服务${RESET}"
    say "=============================================="

    if [ "${S_UP}" = "1" ]; then
        line="${GREEN}● 运行中${RESET}（PID ${S_PID}，$(fmt_uptime)）"
    elif [ -n "${S_PID}" ]; then
        line="${YELLOW}● 端口被占用但无响应${RESET}（PID ${S_PID}）"
    else
        line="${DIM}○ 未运行${RESET}"
    fi
    printf '  %s服务状态%s : %b\n' "${DIM}" "${RESET}" "${line}"
    printf '  %s本机访问%s : %s\n' "${DIM}" "${RESET}" "${URL}"
    if [ -n "${ip}" ]; then
        printf '  %s局域网  %s : http://%s:%s\n' "${DIM}" "${RESET}" "${ip}" "${PORT}"
    fi

    if [ "${S_UP}" = "1" ]; then
        printf '  %s版本信息%s : v%s · %s · 网段 %s · ping %s\n' \
            "${DIM}" "${RESET}" "${S_VER}" "${S_PLATFORM}" "${S_CIDR}" "${S_PING}"
        printf '  %s设备台账%s : 共 %s 台（在线 %s / 掉线 %s）\n' \
            "${DIM}" "${RESET}" "${S_TOTAL}" "${S_ONLINE}" "${S_OFFLINE}"
        if [ "${S_AUTO_ON}" = "1" ]; then
            printf '  %s定时重扫%s : 已开启，每 %d 分钟一次 · 下次%s（已跑 %s 次）\n' \
                "${DIM}" "${RESET}" $(( S_AUTO_IV / 60 )) "$(fmt_next "${S_AUTO_NEXT}")" "${S_AUTO_RUNS}"
        else
            printf '  %s定时重扫%s : 未开启\n' "${DIM}" "${RESET}"
        fi
        if [ -n "${S_ACTIVE}" ]; then
            printf '  %s当前任务%s : %s有扫描正在运行%s\n' "${DIM}" "${RESET}" "${YELLOW}" "${RESET}"
        else
            printf '  %s当前任务%s : 空闲\n' "${DIM}" "${RESET}"
        fi
    else
        say "  ${DIM}版本信息${RESET} : —"
        say "  ${DIM}设备台账${RESET} : —（服务未运行，启动后可查看）"
        say "  ${DIM}定时重扫${RESET} : —"
    fi

    printf '  %s状态刷新%s : %s\n' "${DIM}" "${RESET}" "$(date '+%H:%M:%S')"
}

# 菜单选项
menu_body() {
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

# 原地重画整屏：光标回左上角 → 重画 → 清掉屏幕剩余部分
# 不用 clear 是为了不闪屏；只要整屏内容不超过终端高度，就不会滚动，
# 状态面板就能一直固定在顶部。
render_frame() {
    load_status
    printf '\033[H'
    status_panel
    menu_body
    printf '\033[J'
}

# 动作执行完后回到菜单：倒计时结束自动回，按回车立刻回
pause_return() {
    local wait="${1:-${PAUSE_SECS}}" i
    printf '\n'
    for (( i=wait; i>0; i-- )); do
        printf '\r\033[K  %s%d 秒后自动回到菜单（按回车立即返回）%s ' "${DIM}" "${i}" "${RESET}"
        if read -r -t 1 _pause_key; then
            break
        fi
    done
    printf '\r\033[K'
}

# ---------- 菜单 ----------
menu_loop() {
    local choice rc

    clear 2>/dev/null || printf '\033[H\033[2J'

    while true; do
        render_frame
        printf '  请输入序号（直接回车 = %s）: ' "$(default_action)"

        # 等待输入，同时定期刷新状态面板。
        #
        # ⚠️ 区分"超时"和"输入结束"在 bash 3.2 上是个坑：
        #    网上都说 read -t 超时会返回 128+SIGALRM(14)=142，
        #    但 macOS 自带 bash 3.2 实测**超时也返回 1**，和 EOF 完全一样。
        #    所以只能靠耗时判断：等满 REFRESH_SECS 秒 = 真超时；立刻返回 = EOF。
        local t0 el
        t0=${SECONDS}
        read -r -t "${REFRESH_SECS}" choice
        rc=$?
        el=$(( SECONDS - t0 ))

        if [ "${rc}" -ne 0 ]; then
            if [ "${el}" -lt "${REFRESH_SECS}" ]; then
                # 输入结束（例如被管道调用）→ 安静退出，不要死循环
                printf '\n'
                return 0
            fi
            # 超时：只想刷新状态。但用户可能已经敲了一半，
            # 把已输入的内容当成完整输入执行，避免"打了一半被刷掉"。
            choice="${choice//[[:space:]]/}"
            if [ -z "${choice}" ]; then
                continue
            fi
        fi

        choice="${choice//[[:space:]]/}"
        printf '\n'

        case "${choice}" in
            "")  if is_up; then do_open; else do_start && do_open; fi ;;
            1)   do_start && do_open ;;
            2)   do_stop ;;
            3)   do_stop; do_start && do_open ;;
            4)   do_open ;;
            5)   do_status ;;
            6)   do_log ;;
            0|q|Q)
                 say "再见。"
                 return 0 ;;
            *)   warn "没这个选项：${choice}（有效：0-6，直接回车 = $(default_action)）" ;;
        esac

        # 无论上面走的是哪个分支（包括输错序号），都回到菜单
        pause_return
    done
}

# ---------- 入口 ----------
case "${1:-}" in
    start)   do_start && do_open ;;
    stop)    do_stop ;;
    restart) do_stop; do_start && do_open ;;
    open)    do_open ;;
    toggle)  do_toggle ;;
    status)  do_status ;;
    log)     do_log ;;
    help|-h|--help) usage ;;
    "")      menu_loop ;;
    *)
        err "没有这个动作：${1}"
        say ""
        usage
        exit 2
        ;;
esac
