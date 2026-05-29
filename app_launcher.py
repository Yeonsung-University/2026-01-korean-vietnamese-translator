"""
Desktop entry point for the Korean-Vietnamese live translator.

It avoids starting a duplicate server: if the local app health endpoint is
already alive, it opens the existing browser UI and exits.
"""
import json
import os
import sys
import threading
import time
import urllib.error
import urllib.request
import webbrowser

import uvicorn

import app_config
from app_config import APP_NAME
from network_utils import can_bind, local_url, port_accepts_connections


FALLBACK_PORT_SCAN_COUNT = 50


def should_open_browser() -> bool:
    value = os.environ.get("KVT_NO_BROWSER", "")
    return value.strip().lower() not in {"1", "true", "yes", "y", "on"}


def open_ui(port: int) -> None:
    if not should_open_browser():
        return
    time.sleep(2)
    webbrowser.open(local_url(port))


def read_existing_health(port: int) -> dict | None:
    url = f"{local_url(port)}/api/health"
    try:
        with urllib.request.urlopen(url, timeout=0.8) as response:
            return json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, OSError):
        return None


def port_is_busy(port: int) -> bool:
    return port_accepts_connections("127.0.0.1", port)


def first_available_fallback_port(start_port: int) -> int | None:
    for port in range(start_port + 1, start_port + FALLBACK_PORT_SCAN_COUNT + 1):
        if not port_is_busy(port) and can_bind("0.0.0.0", port):
            return port
    return None


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    requested_port = app_config.PORT
    health = read_existing_health(requested_port)
    if health and health.get("app") == APP_NAME:
        print(f"Already running: {local_url(requested_port)}")
        if should_open_browser():
            webbrowser.open(local_url(requested_port))
        return 0

    selected_port = requested_port
    if port_is_busy(requested_port):
        if os.environ.get("KVT_PORT"):
            print(f"Port {requested_port} is already in use by another process.")
            print("Close the other program or set KVT_PORT to another port before starting this app.")
            return 2
        fallback_port = first_available_fallback_port(requested_port)
        if fallback_port is None:
            print(f"Port {requested_port} is already in use and no free fallback port was found.")
            print("Close the other program or set KVT_PORT to another port before starting this app.")
            return 2
        selected_port = fallback_port
        print(f"Port {requested_port} is busy; using {selected_port} instead.")

    os.environ["KVT_PORT"] = str(selected_port)
    app_config.PORT = selected_port

    import server

    guest_url = server.network_payload()["guest_url"]
    threading.Thread(target=open_ui, args=(selected_port,), daemon=True).start()
    print(f"App starting: {local_url(selected_port)}")
    print(f"Guest URL: {guest_url}")
    uvicorn.run(server.app, host=app_config.HOST, port=selected_port, log_level="warning")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
