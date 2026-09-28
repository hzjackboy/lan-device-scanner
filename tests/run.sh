#!/bin/bash
# 跑全部前端 / 接口测试
#   离线测试（不需要服务）：ui_*.test.js
#   联调测试（需要服务在跑）：integration_*.js
set -u
cd "$(dirname "$0")/.." || exit 1

pass=0; fail=0
for f in tests/ui_*.test.js; do
    printf '%-28s ' "$(basename "$f")"
    if node "$f" >/tmp/.t.log 2>&1; then
        n=$(grep -c '✅' /tmp/.t.log)
        echo "✅ 通过（$n 项）"; pass=$((pass+1))
    else
        echo "❌ 失败"; sed 's/^/    /' /tmp/.t.log | grep -E '❌|Error' | head -5; fail=$((fail+1))
    fi
done

if curl -fsS -m 3 http://127.0.0.1:8765/api/status >/dev/null 2>&1; then
    echo "--- 服务在跑，附带联调测试 ---"
    for f in tests/integration_*.js; do
        printf '%-28s ' "$(basename "$f")"
        if node "$f" >/tmp/.t.log 2>&1; then echo "✅ 通过"; pass=$((pass+1))
        else echo "❌ 失败"; sed 's/^/    /' /tmp/.t.log | tail -5; fail=$((fail+1)); fi
    done
else
    echo "（服务没在跑，跳过联调测试；先执行 ./run.sh 或桌面脚本）"
fi

echo
echo "合计：通过 $pass 套，失败 $fail 套"
[ "$fail" -eq 0 ]
