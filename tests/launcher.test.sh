#!/bin/bash
# ============================================
# 桌面启动脚本（desktop/局域网扫描服务.command）回归测试
#
#   在项目根目录跑： ./tests/launcher.test.sh
#
# 盯住两件事（都是用户明确提过的需求）：
#   1. 终端里**时刻**显示服务状态 —— 状态面板要出现，空闲时要自动刷新
#   2. **所有**菜单动作执行完都要回到菜单 —— 不能执行完就退出
#
# 只测不会打扰服务的选项（5 看状态 / 6 看日志 / 输错序号），
# 不碰 1/2/3/4 —— 那些会启停服务、还会弹浏览器。
# ============================================
set -u
cd "$(dirname "$0")/.." || exit 1

SCRIPT="./desktop/局域网扫描服务.command"
ESC=$(printf '\033')
strip_ansi() { sed "s/${ESC}\[[0-9;]*[A-Za-z]//g"; }

GREEN=$'\033[32m'; RED=$'\033[31m'; RESET=$'\033[0m'
pass=0; fail=0
ok()  { printf '%s✔%s %s\n' "${GREEN}" "${RESET}" "$*"; pass=$((pass+1)); }
bad() { printf '%s✘%s %s\n' "${RED}" "${RESET}" "$*"; fail=$((fail+1)); }

if [ ! -x "${SCRIPT}" ]; then
    bad "找不到可执行脚本：${SCRIPT}"
    exit 1
fi

# ---------- 1. 语法 ----------
if /bin/bash -n "${SCRIPT}" 2>/dev/null; then
    ok "语法检查通过"
else
    bad "语法检查失败"; /bin/bash -n "${SCRIPT}"; exit 1
fi

# ---------- 2. 状态面板：服务状态必须显示出来 ----------
out="$(printf '0\n' | "${SCRIPT}" 2>&1 | strip_ansi)"
case "${out}" in
    *"服务状态"*)           ok "状态面板含「服务状态」" ;;
    *)                      bad "状态面板没有服务状态行" ;;
esac
case "${out}" in
    *"运行中"*|*"未运行"*)  ok "服务状态有明确取值（运行中 / 未运行）" ;;
    *)                      bad "服务状态取值不明确" ;;
esac
case "${out}" in
    *"本机访问"*)           ok "状态面板含本机访问地址" ;;
    *)                      bad "状态面板缺本机访问地址" ;;
esac

# ---------- 3. 每个动作后都要回到菜单 ----------
# 喂入：选项5 → 回车 → 选项6 → 回车 → 乱输 → 回车 → 0 退出
# 每次动作后必须重新出现一次「请输入序号」，共 4 次（含最后的 0）。
out="$(printf '5\n\n6\n\nx\n\n0\n' | "${SCRIPT}" 2>&1 | strip_ansi)"
n_prompt=$(printf '%s\n' "${out}" | grep -c "请输入序号")
if [ "${n_prompt}" -ge 4 ]; then
    ok "3 个动作后都回到了菜单（提示行出现 ${n_prompt} 次）"
else
    bad "动作后没有回到菜单（提示行只出现 ${n_prompt} 次，期望 >= 4）"
fi

case "${out}" in
    *"服务运行中"*|*"服务未运行"*) ok "选项 5（看状态）输出了状态详情" ;;
    *)                             bad "选项 5 没有输出状态详情" ;;
esac
case "${out}" in
    *"行日志"*) ok "选项 6（看日志）执行了" ;;
    *)          bad "选项 6 没输出日志" ;;
esac
case "${out}" in
    *"没这个选项"*) ok "乱输序号会告警而不是退出" ;;
    *)              bad "乱输序号没有告警" ;;
esac
case "${out}" in
    *"再见"*) ok "选项 0 正常退出" ;;
    *)        bad "选项 0 没有退出" ;;
esac

# ---------- 4. 空闲时自动刷新状态（每人手按 5 就看不到最新的）----------
# 不输入任何内容，等 7 秒：默认 3 秒刷一次，应该至少刷 2 次。
out="$( (sleep 7; echo 0) | "${SCRIPT}" 2>&1 | strip_ansi)"
n_refresh=$(printf '%s\n' "${out}" | grep -c "状态刷新")
if [ "${n_refresh}" -ge 2 ]; then
    ok "空闲 ${n_refresh} 次自动刷新（约每 3 秒一次）"
else
    bad "空闲时不刷新（只刷了 ${n_refresh} 次）
      常见原因：bash 3.2 的 read -t 超时返回 1（不是 128+14=142），
      若用退出码判断超时，会把超时误当成 EOF 直接退出菜单。"
fi

# ---------- 5. 输入结束不能死循环 ----------
printf '' | "${SCRIPT}" >/dev/null 2>&1
rc=$?
if [ "${rc}" -eq 0 ]; then
    ok "无输入（EOF）时安静退出，退出码 0"
else
    bad "无输入时退出码异常：${rc}"
fi

# ---------- 6. 命令行模式仍然可用 ----------
if "${SCRIPT}" help 2>&1 | grep -q "start"; then
    ok "命令行 help 模式正常"
else
    bad "命令行 help 模式异常"
fi

echo
echo "启动脚本测试：通过 ${pass} 项，失败 ${fail} 项"
[ "${fail}" -eq 0 ]
