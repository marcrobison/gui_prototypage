"""LAN address discovery and self-signed TLS certificate management."""
import os
import shutil
import socket
import subprocess
from pathlib import Path

from PySide6.QtNetwork import QAbstractSocket, QNetworkInterface

from . import config


def lan_ipv4_addresses() -> list[str]:
    """IPv4 addresses of interfaces that are up and not loopback (no packets sent)."""
    addresses = []
    flags = QNetworkInterface.InterfaceFlag
    for iface in QNetworkInterface.allInterfaces():
        f = iface.flags()
        if not (f & flags.IsUp and f & flags.IsRunning) or f & flags.IsLoopBack:
            continue
        for entry in iface.addressEntries():
            ip = entry.ip()
            if ip.protocol() == QAbstractSocket.NetworkLayerProtocol.IPv4Protocol and not ip.isLoopback():
                addresses.append(ip.toString())
    return addresses


def primary_lan_ip() -> str:
    addresses = lan_ipv4_addresses()
    # Prefer private ranges typical of home / school networks.
    for prefix in ("192.168.", "10.", "172."):
        for ip in addresses:
            if ip.startswith(prefix):
                return ip
    return addresses[0] if addresses else "127.0.0.1"


class CertificateError(RuntimeError):
    pass


def ensure_certificate(cert_path: Path = config.CERT_PATH, key_path: Path = config.KEY_PATH) -> tuple[Path, Path]:
    """Create a self-signed certificate on first run (needs the `openssl` CLI, standard on Pi OS)."""
    if cert_path.exists() and key_path.exists():
        return cert_path, key_path
    openssl = shutil.which("openssl")
    if not openssl:
        raise CertificateError("`openssl` not found: install it (sudo apt install openssl) "
                               "or run with --insecure-http")
    cert_path.parent.mkdir(parents=True, exist_ok=True)
    hostname = socket.gethostname()
    san = {f"DNS:localhost", f"DNS:{hostname}", f"DNS:{hostname}.local", "IP:127.0.0.1"}
    san.update(f"IP:{ip}" for ip in lan_ipv4_addresses())
    cmd = [openssl, "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-sha256", "-days", "825",
           "-keyout", str(key_path), "-out", str(cert_path),
           "-subj", "/CN=Raspberry Pi Security Station",
           "-addext", "subjectAltName=" + ",".join(sorted(san))]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise CertificateError(f"openssl failed: {result.stderr.strip()}")
    os.chmod(key_path, 0o600)
    return cert_path, key_path
