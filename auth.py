#!/usr/bin/env python3
"""认证与用户管理（纯标准库）。

设计要点：
- 密码**只存 scrypt 加盐哈希**，永不落明文、永不回显、永不写日志。
- 会话是服务端令牌；盘上只存令牌的 SHA-256，**文件泄露也不能直接拿来登录**。
- Cookie 一律 `HttpOnly` + `SameSite=Lax`（这是防 CSRF 的第一道防线）。
- 首次启动自动建 `admin` / `admin`，并把 `must_change_password` 置 True；
  服务端会拦住其他所有接口，直到密码被改掉（不是只靠前端挡）。
- 登录失败按「用户名」和「来源 IP」两个维度限速，抗暴力破解。
- 另外维护一个本地管理员令牌 `data/local_token`（0600），给同机的命令行工具用
  （桌面启动脚本、测试）。**不做回环地址免认证**——容器是 host 网络时，
  回环免认证等于把整个局域网敞口。

对外接口：
    AuthStore(path, session_path, token_path)
      .authenticate(username, password)   -> (user | None, reason)
      .create_session(username, ip)       -> token
      .resolve(token)                     -> user | None
      .destroy(token)
      .local_token                        -> str（同机命令行用）
      .change_password(user, old, new)
      .list_users() / .create_user(...) / .delete_user(...) / .set_role(...)
      .reset_password(username, new, must_change=True)
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import threading
import time

# ---------------------------------------------------------------- 常量

ROLES = ("admin", "viewer")
DEFAULT_USER = "admin"
DEFAULT_PASSWORD = "admin"

MIN_PASSWORD_LEN = 8
SESSION_TTL = 7 * 24 * 3600          # 会话有效期：7 天（绝对过期，不滑动）
LOGIN_WINDOW = 15 * 60               # 限速统计窗口：15 分钟
LOCKOUT = 15 * 60                    # 触发后的锁定时长
MAX_FAILS_PER_USER = 5               # 同一用户名
MAX_FAILS_PER_IP = 20                # 同一来源 IP

# scrypt 参数：n=2^14 时约需 16MB 内存，单次约几十毫秒，足够抗离线爆破
SCRYPT_N, SCRYPT_R, SCRYPT_P = 2 ** 14, 8, 1
SCRYPT_DKLEN = 32

# 弱密码黑名单（只挡最离谱的几个，真正的强度靠长度和强制改密）
WEAK = {
    "admin", "password", "12345678", "123456789", "1234567890",
    "qwertyui", "11111111", "00000000", "admin123", "lanscan123",
}

_lock = threading.RLock()


# ---------------------------------------------------------------- 密码哈希

def _b64(raw: bytes) -> str:
    return base64.b64encode(raw).decode("ascii")


def _unb64(text: str) -> bytes:
    return base64.b64decode(text.encode("ascii"))


def hash_password(password: str, *, n: int = SCRYPT_N, r: int = SCRYPT_R,
                  p: int = SCRYPT_P) -> str:
    """返回 `scrypt$n$r$p$salt$hash`。salt 每次随机，同一个密码两次结果不同。"""
    if not isinstance(password, str):
        raise TypeError("password must be str")
    salt = secrets.token_bytes(16)
    dk = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=n, r=r, p=p,
                        dklen=SCRYPT_DKLEN, maxmem=64 * 1024 * 1024)
    return f"scrypt${n}${r}${p}${_b64(salt)}${_b64(dk)}"


def verify_password(password: str, encoded: str) -> bool:
    """常数时间比对。任何格式错误都返回 False，不抛异常（避免把内部状态泄给调用方）。"""
    try:
        scheme, n_s, r_s, p_s, salt_s, hash_s = (encoded or "").split("$")
        if scheme != "scrypt":
            return False
        n, r, p = int(n_s), int(r_s), int(p_s)
        salt, expected = _unb64(salt_s), _unb64(hash_s)
        dk = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=n, r=r, p=p,
                            dklen=len(expected), maxmem=64 * 1024 * 1024)
        return hmac.compare_digest(dk, expected)
    except (ValueError, TypeError, MemoryError):
        return False


def check_password_strength(password: str, username: str = "") -> str | None:
    """返回 None 表示通过，否则返回给用户看的中文原因。"""
    if not isinstance(password, str) or len(password) < MIN_PASSWORD_LEN:
        return f"密码至少 {MIN_PASSWORD_LEN} 位"
    if password.lower() in WEAK:
        return "这个密码太常见了，换一个"
    if username and password.lower() == username.lower():
        return "密码不能和用户名相同"
    if len(set(password)) == 1:
        return "密码不能是同一个字符重复"
    return None


def _hash_token(token: str) -> str:
    """会话令牌在盘上只留摘要。"""
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------- 存储

class AuthStore:
    """用户库 + 会话 + 登录限速。所有写盘都带锁，可被多线程 Handler 并发调用。"""

    def __init__(self, path: str, session_path: str, token_path: str) -> None:
        self.path = path
        self.session_path = session_path
        self.token_path = token_path
        self._users: dict[str, dict] = {}
        self._sessions: dict[str, dict] = {}
        self._fails: dict[str, list[float]] = {}
        with _lock:
            self._load()
            self._load_sessions()
            self._ensure_local_token()

    # ---------------- 落盘 ----------------

    def _read_json(self, path: str) -> dict:
        try:
            with open(path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            return data if isinstance(data, dict) else {}
        except (OSError, ValueError):
            return {}

    def _write_json(self, path: str, payload: dict, mode: int = 0o600) -> None:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        tmp = f"{path}.tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=1)
        os.replace(tmp, path)
        try:
            os.chmod(path, mode)      # 用户库和会话都只给本人读写
        except OSError:
            pass

    def _load(self) -> None:
        data = self._read_json(self.path)
        users = data.get("users")
        if isinstance(users, dict) and users:
            self._users = {str(k): v for k, v in users.items() if isinstance(v, dict)}
            return
        # 首次启动：建默认管理员，并强制改密
        self._users = {}
        self._users[DEFAULT_USER] = {
            "username": DEFAULT_USER,
            "role": "admin",
            "password": hash_password(DEFAULT_PASSWORD),
            "must_change_password": True,
            "created_at": time.time(),
            "updated_at": time.time(),
            "last_login": None,
            "last_login_ip": None,
            "password_changed_at": None,
        }
        self._save()

    def _save(self) -> None:
        self._write_json(self.path, {"version": 1, "users": self._users})

    def _load_sessions(self) -> None:
        data = self._read_json(self.session_path)
        raw = data.get("sessions")
        now = time.time()
        if isinstance(raw, dict):
            self._sessions = {
                k: v for k, v in raw.items()
                if isinstance(v, dict) and float(v.get("expires_at") or 0) > now
            }
        else:
            self._sessions = {}
        if len(self._sessions) != len(raw or {}):
            self._save_sessions()

    def _save_sessions(self) -> None:
        self._write_json(self.session_path,
                         {"version": 1, "sessions": self._sessions})

    def _ensure_local_token(self) -> None:
        """同机命令行工具用的管理员令牌。已存在就复用，不每次重启换。

        ⚠️ 文件里存的是 JSON（`{"token": "..."}`），必须**解析后取值**。
        第一版直接读原文当令牌，首次启动碰巧是对的（刚生成的就是它），
        重启后读到的却是整个 JSON 文本，令牌就对不上了——现象是
        「刚装好能用，重启一次命令行工具全部 401」。
        """
        token = ""
        try:
            with open(self.token_path, "r", encoding="utf-8") as fh:
                raw = fh.read().strip()
        except OSError:
            raw = ""
        if raw:
            try:
                parsed = json.loads(raw)
                if isinstance(parsed, dict):
                    token = str(parsed.get("token") or "").strip()
            except ValueError:
                token = raw          # 兼容「文件里直接放裸令牌」的写法
        if len(token) < 32:
            token = secrets.token_urlsafe(32)
            self._write_json(self.token_path, {"token": token})
        self.local_token = token

    # ---------------- 限速 ----------------

    def _prune(self, key: str, now: float) -> list[float]:
        hits = [t for t in self._fails.get(key, []) if now - t < LOGIN_WINDOW]
        self._fails[key] = hits
        return hits

    def _keys(self, username: str, ip: str) -> tuple[tuple[str, int], ...]:
        """限速的两个维度。

        注意用户名那维必须**带上 IP**（`u:用户名:IP`）。只按用户名计数的话，
        局域网里任何人连错 5 次就能把 admin 锁死 15 分钟——用限速换来一个
        更好用的拒绝服务，得不偿失。按 (用户名, IP) 计数既能挡住单点爆破，
        又不影响其他人正常登录。
        """
        return ((f"u:{username.lower()}:{ip}", MAX_FAILS_PER_USER),
                (f"i:{ip}", MAX_FAILS_PER_IP))

    def retry_after(self, username: str, ip: str) -> int:
        """还要等几秒才能再试；0 表示可以试。"""
        now = time.time()
        with _lock:
            for key, limit in self._keys(username, ip):
                hits = self._prune(key, now)
                if len(hits) >= limit:
                    return max(1, int(LOGIN_WINDOW - (now - hits[0])))
        return 0

    def _note_failure(self, username: str, ip: str) -> None:
        now = time.time()
        with _lock:
            for key, _limit in self._keys(username, ip):
                self._prune(key, now).append(now)

    def _clear_failures(self, username: str, ip: str) -> None:
        with _lock:
            for key, _limit in self._keys(username, ip):
                self._fails.pop(key, None)

    # ---------------- 登录 / 会话 ----------------

    def authenticate(self, username: str, password: str, ip: str = "-"):
        """返回 (user, None) 或 (None, 原因)。原因只用于服务端日志，不回给客户端。"""
        username = (username or "").strip()
        if self.retry_after(username, ip) > 0:
            return None, "locked"
        with _lock:
            rec = self._users.get(username)
            # 用户不存在时也走一次哈希，避免用响应时间枚举用户名
            stored = rec.get("password") if rec else hash_password("__nonexistent__")
            ok = verify_password(password or "", stored)
            if not rec or not ok:
                self._note_failure(username, ip)
                return None, "bad_credentials"
            rec["last_login"] = time.time()
            # 记的是「上次成功登录的来源」，不是每次请求的 IP——
            # 会话能用 7 天，按请求记的话这个值会变成最后一台设备的地址，
            # 跟列名「最近登录 IP」对不上。
            rec["last_login_ip"] = ip or None
            self._save()
            self._clear_failures(username, ip)
            return dict(rec), None

    def create_session(self, username: str, ip: str = "-") -> str:
        token = secrets.token_urlsafe(32)
        now = time.time()
        with _lock:
            self._sessions[_hash_token(token)] = {
                "username": username, "created_at": now,
                "expires_at": now + SESSION_TTL, "ip": ip,
            }
            self._save_sessions()
        return token

    def resolve(self, token: str):
        """令牌 -> 用户记录（dict 副本），无效/过期/用户已删都返回 None。"""
        if not token:
            return None
        now = time.time()
        with _lock:
            sess = self._sessions.get(_hash_token(token))
            if not sess or float(sess.get("expires_at") or 0) <= now:
                return None
            rec = self._users.get(sess.get("username"))
            return dict(rec) if rec else None

    def destroy(self, token: str) -> None:
        if not token:
            return
        with _lock:
            if self._sessions.pop(_hash_token(token), None) is not None:
                self._save_sessions()

    def destroy_user_sessions(self, username: str) -> int:
        """删用户 / 改角色时把它的会话一并作废。"""
        with _lock:
            doomed = [k for k, v in self._sessions.items()
                      if v.get("username") == username]
            for key in doomed:
                self._sessions.pop(key, None)
            if doomed:
                self._save_sessions()
            return len(doomed)

    def purge_expired(self) -> int:
        now = time.time()
        with _lock:
            doomed = [k for k, v in self._sessions.items()
                      if float(v.get("expires_at") or 0) <= now]
            for key in doomed:
                self._sessions.pop(key, None)
            if doomed:
                self._save_sessions()
            return len(doomed)

    # ---------------- 密码 ----------------

    def change_password(self, username: str, old: str, new: str):
        """用户改自己的密码。返回 (ok, 错误信息)。"""
        with _lock:
            rec = self._users.get(username)
            if not rec:
                return False, "用户不存在"
            if not verify_password(old or "", rec.get("password", "")):
                return False, "当前密码不对"
            reason = check_password_strength(new, username)
            if reason:
                return False, reason
            if verify_password(new, rec.get("password", "")):
                return False, "新密码不能和当前密码相同"
            rec["password"] = hash_password(new)
            rec["must_change_password"] = False
            rec["password_changed_at"] = time.time()
            rec["updated_at"] = time.time()
            self._save()
            return True, None

    def reset_password(self, username: str, new: str, *, must_change: bool = True):
        """管理员重置他人密码。"""
        with _lock:
            rec = self._users.get(username)
            if not rec:
                return False, "用户不存在"
            reason = check_password_strength(new, username)
            if reason:
                return False, reason
            rec["password"] = hash_password(new)
            rec["must_change_password"] = bool(must_change)
            rec["password_changed_at"] = time.time()
            rec["updated_at"] = time.time()
            self._save()
        self.destroy_user_sessions(username)      # 改了密码就让旧会话失效
        return True, None

    # ---------------- 用户管理 ----------------

    @staticmethod
    def _public(rec: dict) -> dict:
        """对外表示：**绝不包含 password 字段**。"""
        return {
            "username": rec.get("username"),
            "role": rec.get("role") or "viewer",
            "must_change_password": bool(rec.get("must_change_password")),
            "created_at": rec.get("created_at"),
            "updated_at": rec.get("updated_at"),
            "last_login": rec.get("last_login"),
            "last_login_ip": rec.get("last_login_ip"),
            "password_changed_at": rec.get("password_changed_at"),
        }

    def list_users(self) -> list[dict]:
        with _lock:
            return sorted((self._public(r) for r in self._users.values()),
                          key=lambda u: (u["role"] != "admin", u["username"]))

    def get_user(self, username: str) -> dict | None:
        with _lock:
            rec = self._users.get(username)
            return self._public(rec) if rec else None

    def count_admins(self) -> int:
        with _lock:
            return sum(1 for r in self._users.values() if r.get("role") == "admin")

    def create_user(self, username: str, password: str, role: str = "viewer",
                    *, must_change: bool = True):
        username = (username or "").strip()
        if not username:
            return None, "用户名不能为空"
        if len(username) > 32:
            return None, "用户名太长（最多 32 字符）"
        if not all(ch.isalnum() or ch in "._-" for ch in username):
            return None, "用户名只能用字母、数字和 . _ -"
        if role not in ROLES:
            return None, f"角色只能是 {' / '.join(ROLES)}"
        reason = check_password_strength(password, username)
        if reason:
            return None, reason
        with _lock:
            if username in self._users:
                return None, "这个用户名已经存在了"
            now = time.time()
            self._users[username] = {
                "username": username, "role": role,
                "password": hash_password(password),
                "must_change_password": bool(must_change),
                "created_at": now, "updated_at": now,
                "last_login": None, "last_login_ip": None, "password_changed_at": None,
            }
            self._save()
            return self._public(self._users[username]), None

    def delete_user(self, username: str, *, actor: str = ""):
        with _lock:
            if username not in self._users:
                return False, "用户不存在"
            if username == actor:
                return False, "不能删除当前登录的账号"
            if (self._users[username].get("role") == "admin"
                    and self.count_admins() <= 1):
                return False, "至少要保留一个管理员"
            self._users.pop(username, None)
            self._save()
        self.destroy_user_sessions(username)
        return True, None

    def set_role(self, username: str, role: str, *, actor: str = ""):
        if role not in ROLES:
            return False, f"角色只能是 {' / '.join(ROLES)}"
        with _lock:
            rec = self._users.get(username)
            if not rec:
                return False, "用户不存在"
            if role != "admin" and rec.get("role") == "admin" and self.count_admins() <= 1:
                return False, "至少要保留一个管理员"
            rec["role"] = role
            rec["updated_at"] = time.time()
            self._save()
            return True, None
