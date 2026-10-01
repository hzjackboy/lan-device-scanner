#!/usr/bin/env python3
"""auth.py 的单元测试（纯逻辑，不需要起服务，也不碰真实 data/）。

跑法：python3 tests/auth_unit.py
"""

import json
import os
import shutil
import stat
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import auth  # noqa: E402

checks = []


def check(name, ok):
    checks.append((name, bool(ok)))


def new_store(tmp, name="u"):
    return auth.AuthStore(
        os.path.join(tmp, f"{name}.json"),
        os.path.join(tmp, f"{name}-sessions.json"),
        os.path.join(tmp, f"{name}-token"),
    )


def main():
    tmp = tempfile.mkdtemp(prefix="lanscan-auth-")
    try:
        # ---------------- 密码哈希 ----------------
        h1, h2 = auth.hash_password("correct horse battery"), auth.hash_password("correct horse battery")
        check("同一密码两次哈希不同（随机 salt）", h1 != h2)
        check("哈希带算法标识 scrypt", h1.startswith("scrypt$"))
        check("正确密码校验通过", auth.verify_password("correct horse battery", h1))
        check("错误密码被拒", not auth.verify_password("wrong", h1))
        check("垃圾串不抛异常", auth.verify_password("x", "garbage") is False)
        check("空哈希安全返回 False", auth.verify_password("x", "") is False)
        check("篡改哈希段被拒", not auth.verify_password("correct horse battery", h1[:-4] + "AAAA"))

        # ---------------- 强度校验 ----------------
        check("短密码被拒", auth.check_password_strength("abc", "admin") is not None)
        check("常见弱密码被拒", auth.check_password_strength("password", "admin") is not None)
        check("密码等于用户名被拒", auth.check_password_strength("alexandra", "alexandra") is not None)
        check("重复单字符被拒", auth.check_password_strength("aaaaaaaa", "admin") is not None)
        check("合格密码通过", auth.check_password_strength("Str0ng-Pass!", "admin") is None)

        # ---------------- 首次启动引导 ----------------
        st = new_store(tmp)
        admin = st.get_user("admin")
        check("首次启动自动建 admin", admin is not None)
        check("默认 admin 是管理员", admin and admin["role"] == "admin")
        check("默认账号被标记必须改密", admin and admin["must_change_password"] is True)
        users_raw = open(os.path.join(tmp, "u.json"), encoding="utf-8").read()
        check("用户库里没有明文密码", '"admin"' not in users_raw.split('"password"')[1][:60])
        mode = stat.S_IMODE(os.stat(os.path.join(tmp, "u.json")).st_mode)
        check("用户库权限是 0600", mode == 0o600)
        check("对外表示里没有裸 password 键", "password" not in admin)
        check("对外表示里不含密码哈希",
              "scrypt" not in json.dumps(admin) and "$" not in json.dumps(admin))
        check("对外表示里有 last_login_ip 字段", "last_login_ip" in admin)

        # ---------------- 登录 ----------------
        rec, why = st.authenticate("admin", "admin", "10.0.0.1")
        check("admin/admin 能登录", rec is not None and why is None)
        check("登录后记录 last_login", bool(rec and rec.get("last_login")))
        check("登录后记录来源 IP", rec and rec.get("last_login_ip") == "10.0.0.1")
        # 换个来源再登一次，应当被刷新（否则界面永远显示第一次那个地址）
        rec2, _ = st.authenticate("admin", "admin", "10.0.0.42")
        check("再登录会刷新来源 IP", rec2 and rec2.get("last_login_ip") == "10.0.0.42")
        check("最近登录 IP 对外可见", st.get_user("admin").get("last_login_ip") == "10.0.0.42")
        bad, why2 = st.authenticate("admin", "nope", "10.0.0.1")
        check("错误密码登录失败", bad is None)
        ghost, why3 = st.authenticate("nosuch", "whatever", "10.0.0.1")
        check("不存在的用户登录失败", ghost is None)
        check("两种失败对外原因一致（不泄漏用户是否存在）", why2 == why3)

        # ---------------- 会话 ----------------
        tok = st.create_session("admin", "10.0.0.1")
        check("令牌能解析出用户", (st.resolve(tok) or {}).get("username") == "admin")
        check("伪造令牌解析为 None", st.resolve("forged") is None)
        check("空令牌解析为 None", st.resolve("") is None)
        sess_raw = open(os.path.join(tmp, "u-sessions.json"), encoding="utf-8").read()
        check("盘上不存明文令牌（只存摘要）", tok not in sess_raw)
        st.destroy(tok)
        check("销毁后令牌失效", st.resolve(tok) is None)

        # ---------------- 登录限速（含「不能被人恶意锁死」） ----------------
        st2 = new_store(tmp, "rl")
        for _ in range(auth.MAX_FAILS_PER_USER):
            st2.authenticate("admin", "wrong", "10.0.0.5")
        check("同一 IP 连错后该 IP 被限速", st2.retry_after("admin", "10.0.0.5") > 0)
        check("被限速期间正确密码也拒绝", st2.authenticate("admin", "admin", "10.0.0.5")[0] is None)
        check("换一个 IP 仍能登录（不会被人锁死账号）",
              st2.authenticate("admin", "admin", "10.0.0.6")[0] is not None)

        st3 = new_store(tmp, "rl2")
        for i in range(auth.MAX_FAILS_PER_IP):
            st3.authenticate(f"user{i}", "wrong", "10.0.0.7")
        check("同一 IP 换用户名狂试也会被总量限速", st3.retry_after("admin", "10.0.0.7") > 0)
        check("成功登录会清掉该 IP 的失败计数",
              st2.retry_after("admin", "10.0.0.6") == 0)

        # ---------------- 改密码 ----------------
        st4 = new_store(tmp, "pw")
        ok, reason = st4.change_password("admin", "wrongold", "Brand-New-Pass1")
        check("旧密码不对时拒绝改密", not ok and "不对" in (reason or ""))
        ok, reason = st4.change_password("admin", "admin", "short")
        check("新密码太弱时拒绝改密", not ok)
        ok, reason = st4.change_password("admin", "admin", "admin")
        check("新密码等于旧密码时拒绝", not ok or reason is None)
        ok, reason = st4.change_password("admin", "admin", "Brand-New-Pass1")
        check("合格的新密码改密成功", ok)
        check("改密后解除强制改密标记", st4.get_user("admin")["must_change_password"] is False)
        check("旧密码从此失效", st4.authenticate("admin", "admin", "10.0.0.9")[0] is None)
        check("新密码可以登录", st4.authenticate("admin", "Brand-New-Pass1", "10.0.0.9")[0] is not None)
        ok, _ = st4.change_password("admin", "Brand-New-Pass1", "Brand-New-Pass1")
        check("新旧密码相同时拒绝", not ok)

        # ---------------- 用户管理 ----------------
        st5 = new_store(tmp, "mg")
        u, reason = st5.create_user("alice", "Alice-Pass1", "viewer")
        check("能创建 viewer", u is not None and u["role"] == "viewer")
        check("新用户默认要求改初始密码", u and u["must_change_password"] is True)
        check("新账号的最近登录 IP 初始为空", u and u.get("last_login_ip") is None)
        check("重复用户名被拒", st5.create_user("alice", "Alice-Pass1", "viewer")[1] is not None)
        check("非法用户名被拒", st5.create_user("a b/c", "GoodPass-1", "viewer")[1] is not None)
        check("非法角色被拒", st5.create_user("bob", "GoodPass-1", "root")[1] is not None)
        check("弱密码建号被拒", st5.create_user("bob", "123", "viewer")[1] is not None)

        ok, reason = st5.delete_user("alice", actor="admin")
        check("能删除其他账号", ok)
        ok, reason = st5.delete_user("admin", actor="admin")
        check("不能删除自己", not ok and "当前登录" in (reason or ""))
        ok, reason = st5.set_role("admin", "viewer", actor="admin")
        check("不能把最后一个管理员降级", not ok and "管理员" in (reason or ""))

        st5.create_user("carol", "Carol-Pass1", "admin")
        ok, reason = st5.set_role("carol", "viewer", actor="admin")
        check("有第二个管理员时可以降级", ok)
        # 降完只剩一个管理员了，此时删 admin 应该被拦（保护最后一个管理员）
        ok, reason = st5.delete_user("admin", actor="carol")
        check("降到只剩一个管理员后不能删他", not ok and "管理员" in (reason or ""))
        # 重新凑够两个管理员，再删就该放行
        st5.set_role("carol", "admin", actor="admin")
        ok, reason = st5.delete_user("admin", actor="carol")
        check("有两个管理员时可以删掉其中一个", ok)

        # ---------------- 重置密码 ----------------
        st6 = new_store(tmp, "rs")
        st6.create_user("dave", "Dave-Pass12", "viewer")
        dave_token = st6.create_session("dave", "10.0.0.3")
        st6.change_password("dave", "Dave-Pass12", "Dave-Pass34")
        ok, _ = st6.reset_password("dave", "Reset-Pass99")
        check("管理员能重置他人密码", ok)
        check("重置后旧会话立即失效", st6.resolve(dave_token) is None)
        check("重置后要求再次改密", st6.get_user("dave")["must_change_password"] is True)
        check("重置后新密码可登录", st6.authenticate("dave", "Reset-Pass99", "10.0.0.3")[0] is not None)
        check("不存在的用户重置返回失败", st6.reset_password("nobody", "Whatever-12")[0] is False)

        # ---------------- 会话清理 ----------------
        st7 = new_store(tmp, "gc")
        t_keep = st7.create_session("admin", "10.0.0.1")
        with auth._lock:
            st7._sessions[auth._hash_token("expired-token")] = {
                "username": "admin", "created_at": 0, "expires_at": 1, "ip": "-"}
        removed = st7.purge_expired()
        check("purge_expired 清掉过期会话", removed == 1)
        check("未过期的会话留着", st7.resolve(t_keep) is not None)

        # 重启后会话仍在（落盘 + 重新载入）
        st8 = auth.AuthStore(os.path.join(tmp, "gc.json"),
                             os.path.join(tmp, "gc-sessions.json"),
                             os.path.join(tmp, "gc-token"))
        check("重启后未过期会话仍有效（会话落盘）", st8.resolve(t_keep) is not None)

        # ---------------- 本地令牌 ----------------
        check("本地令牌长度足够", len(st8.local_token) >= 32)
        on_disk = json.load(open(os.path.join(tmp, "gc-token"), encoding="utf-8"))["token"]
        # 关键：内存里的令牌必须就是文件里那个值。
        # 只比「两次是否相同」是不够的——之前那次 bug 里两边都是整段 JSON，
        # 照样相等，但跟实际写进文件的令牌对不上，重启后命令行全 401。
        check("内存令牌等于文件里的令牌值", st8.local_token == on_disk)
        check("令牌里不含 JSON 花括号", "{" not in st8.local_token and "}" not in st8.local_token)
        st9 = auth.AuthStore(os.path.join(tmp, "gc.json"),
                             os.path.join(tmp, "gc-sessions.json"),
                             os.path.join(tmp, "gc-token"))
        check("本地令牌重启后保持不变", st9.local_token == st8.local_token)
        check("重启后令牌仍等于文件里的值", st9.local_token == on_disk)

        # ---------------- 结果 ----------------
        failed = 0
        for name, ok in checks:
            print(("✅ " if ok else "❌ ") + name)
            if not ok:
                failed += 1
        print()
        print(f"auth_unit.py：{len(checks) - failed}/{len(checks)} 项通过")
        return 1 if failed else 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
