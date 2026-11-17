"""Password storage: salted scrypt hash in a JSON config file (never the plain password)."""
import hashlib
import hmac
import json
import os
import secrets
import threading
from pathlib import Path

from . import config

# scrypt cost parameters (~16 MiB of memory per hash: slow to brute force, fine on a Pi)
SCRYPT_N = 2**14
SCRYPT_R = 8
SCRYPT_P = 1
SCRYPT_DKLEN = 32


def hash_password(password: str, salt: bytes | None = None,
                  n: int = SCRYPT_N, r: int = SCRYPT_R, p: int = SCRYPT_P) -> dict:
    salt = salt if salt is not None else secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=n, r=r, p=p, dklen=SCRYPT_DKLEN)
    return {"algo": "scrypt", "n": n, "r": r, "p": p, "salt": salt.hex(), "hash": digest.hex()}


def _matches(password: str, record: dict) -> bool:
    if record.get("algo") != "scrypt":
        return False
    candidate = hash_password(password, bytes.fromhex(record["salt"]),
                              record["n"], record["r"], record["p"])
    return hmac.compare_digest(candidate["hash"], record["hash"])


class PasswordStore:
    """Thread-safe access to the stored hash. Reloads automatically if the file changes."""

    def __init__(self, path: Path = config.CONFIG_PATH):
        self.path = Path(path)
        self._lock = threading.Lock()
        self._record: dict = {}
        self._is_default = False
        self._mtime = None
        self._ensure_exists()
        self._load()

    def _ensure_exists(self):
        if not self.path.exists():
            self._write(hash_password(config.DEFAULT_PASSWORD), is_default=True)

    def _write(self, record: dict, is_default: bool):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as f:
            json.dump({"password": record, "default_password": is_default}, f, indent=2)
        os.replace(tmp, self.path)

    def _load(self):
        data = json.loads(self.path.read_text())
        self._record = data["password"]
        self._is_default = bool(data.get("default_password", False))
        self._mtime = self.path.stat().st_mtime_ns

    def _reload_if_changed(self):
        try:
            if self.path.stat().st_mtime_ns != self._mtime:
                self._load()
        except FileNotFoundError:
            self._ensure_exists()
            self._load()

    @property
    def is_default(self) -> bool:
        with self._lock:
            self._reload_if_changed()
            return self._is_default

    def verify(self, password: str) -> bool:
        if not isinstance(password, str) or not password:
            return False
        with self._lock:
            self._reload_if_changed()
            record = dict(self._record)
        return _matches(password, record)

    def set_password(self, password: str):
        with self._lock:
            self._write(hash_password(password), is_default=False)
            self._load()
