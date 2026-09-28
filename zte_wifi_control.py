#!/usr/bin/env python3
"""Enable or disable Wi-Fi on a ZTE router web console."""

from __future__ import annotations

import argparse
import base64
import json
import os
import sys
from typing import Any

import requests

SUCCESS_RESULTS = {"success", "sucess", "0", "3", "ok"}


def _parse_json(response: requests.Response) -> dict[str, Any]:
    try:
        data = response.json()
        if isinstance(data, dict):
            return data
    except json.JSONDecodeError:
        pass
    return {}


def _is_success(response: requests.Response) -> bool:
    if response.ok:
        payload = _parse_json(response)
        if not payload:
            return True

        for key in ("result", "Result", "ret", "status"):
            if key in payload:
                return str(payload[key]).strip().lower() in SUCCESS_RESULTS
    return False


def login(session: requests.Session, host: str, username: str, password: str, timeout: int) -> None:
    url = f"http://{host}/goform/goform_set_cmd_process"
    encoded_password = base64.b64encode(password.encode("utf-8")).decode("ascii")

    payloads: list[dict[str, str]] = [
        {"isTest": "false", "goformId": "LOGIN", "password": encoded_password},
        {
            "isTest": "false",
            "goformId": "LOGIN",
            "username": username,
            "password": encoded_password,
        },
        {
            "isTest": "false",
            "goformId": "LOGIN",
            "Username": username,
            "Password": encoded_password,
        },
    ]

    for payload in payloads:
        response = session.post(url, data=payload, timeout=timeout)
        if _is_success(response):
            return

    raise RuntimeError("Login al router fallito: verifica credenziali o payload di login")


def set_wifi(session: requests.Session, host: str, enabled: bool, timeout: int) -> None:
    url = f"http://{host}/goform/goform_set_cmd_process"
    value = "1" if enabled else "0"
    payload = {
        "goformId": "SET_WIFI_INFO",
        "isTest": "false",
        "m_ssid_enable": value,
        "wifiEnabled": value,
    }

    response = session.post(url, data=payload, timeout=timeout)
    if not _is_success(response):
        raise RuntimeError(f"Cambio stato Wi-Fi fallito (enabled={enabled})")


def logout(session: requests.Session, host: str, timeout: int) -> None:
    url = f"http://{host}/goform/goform_set_cmd_process"
    for goform_id in ("LOGOUT", "LOGOFF"):
        session.post(url, data={"isTest": "false", "goformId": goform_id}, timeout=timeout)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Abilita/disabilita il Wi-Fi su router ZTE")
    parser.add_argument("action", choices=("on", "off"), help="on = abilita Wi-Fi, off = disabilita")
    parser.add_argument("--host", default=os.environ.get("ZTE_HOST", "192.168.1.1"))
    parser.add_argument("--username", default=os.environ.get("ZTE_USERNAME", "admin"))
    parser.add_argument("--password", default=os.environ.get("ZTE_PASSWORD"))
    parser.add_argument("--timeout", type=int, default=10)
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    if not args.password:
        print("Errore: imposta la password con --password o variabile ZTE_PASSWORD", file=sys.stderr)
        return 2

    desired_enabled = args.action == "on"

    session = requests.Session()
    session.headers.update({"Referer": f"http://{args.host}/index.html"})

    try:
        login(session, args.host, args.username, args.password, args.timeout)
        set_wifi(session, args.host, desired_enabled, args.timeout)
        state = "abilitato" if desired_enabled else "disabilitato"
        print(f"Wi-Fi {state} con successo")
        return 0
    except requests.RequestException as exc:
        print(f"Errore di rete: {exc}", file=sys.stderr)
        return 1
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    finally:
        try:
            logout(session, args.host, args.timeout)
        except requests.RequestException:
            pass


if __name__ == "__main__":
    raise SystemExit(main())
