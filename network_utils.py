import socket
from contextlib import closing

from app_config import PORT


def _is_usable_lan_ip(ip: str) -> bool:
    return bool(ip) and not ip.startswith(("127.", "169.254.", "0."))


def lan_ip_candidates() -> list[str]:
    candidates: list[str] = []

    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(("8.8.8.8", 80))
            candidates.append(sock.getsockname()[0])
    except Exception:
        pass

    try:
        hostname = socket.gethostname()
        for ip in socket.gethostbyname_ex(hostname)[2]:
            candidates.append(ip)
    except Exception:
        pass

    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            candidates.append(info[4][0])
    except Exception:
        pass

    seen = set()
    ordered = []
    for ip in candidates:
        if ip in seen:
            continue
        seen.add(ip)
        if _is_usable_lan_ip(ip):
            ordered.append(ip)

    if not ordered:
        ordered.append("127.0.0.1")
    return ordered


def primary_lan_ip() -> str:
    return lan_ip_candidates()[0]


def local_url(port: int = PORT) -> str:
    return f"http://127.0.0.1:{port}"


def guest_url(ip: str | None = None, port: int = PORT, include_role: bool = True) -> str:
    host = ip or primary_lan_ip()
    url = f"http://{host}:{port}"
    return f"{url}/?role=guest" if include_role else url


def port_accepts_connections(host: str = "127.0.0.1", port: int = PORT, timeout: float = 0.3) -> bool:
    with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as sock:
        sock.settimeout(timeout)
        return sock.connect_ex((host, port)) == 0


def can_bind(host: str = "0.0.0.0", port: int = PORT) -> bool:
    try:
        with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind((host, port))
            return True
    except OSError:
        return False
