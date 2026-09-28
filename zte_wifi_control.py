#!/usr/bin/env python3
"""Disable both Wi-Fi bands through the ZTE web console."""

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

from playwright.sync_api import Browser, Locator, Page, TimeoutError as PlaywrightTimeoutError, sync_playwright


def _first_visible(page: Page, selectors: tuple[str, ...]) -> Locator:
    for selector in selectors:
        locator = page.locator(selector).first
        if locator.is_visible():
            return locator
    raise RuntimeError(f"Controllo non trovato nella pagina {page.url}")


def _click_text(page: Page, text: str, timeout: int) -> None:
    locator = page.get_by_text(text, exact=True).first
    locator.wait_for(state="visible", timeout=timeout * 1000)
    locator.click()


def _open_accordion(page: Page, text: str, timeout: int) -> None:
    heading = page.get_by_text(text, exact=True).first
    heading.wait_for(state="visible", timeout=timeout * 1000)
    container = heading.locator("xpath=..").first
    container.click()


def _login(page: Page, username: str, password: str, timeout: int) -> None:
    username_field = _first_visible(
        page,
        ("input[name*='user' i]", "input[id*='user' i]", "input[type='text']"),
    )
    password_field = _first_visible(page, ("input[type='password']", "input[name*='pass' i]"))
    username_field.fill(username)
    password_field.fill(password)
    login_button = _first_visible(
        page,
        ("button:has-text('Login')", "button:has-text('Accedi')", "input[type='submit']"),
    )
    login_button.click()
    try:
        page.locator("input[type='password']").first.wait_for(state="hidden", timeout=timeout * 1000)
    except PlaywrightTimeoutError as exc:
        raise RuntimeError("Login fallito: controlla username e password") from exc


def _click_band_toggle(page: Page, band_pattern: str, enabled: bool) -> None:
    labels = page.locator("label").filter(has_text=re.compile(band_pattern, re.IGNORECASE))
    for index in range(labels.count()):
        control = labels.nth(index).locator("input[type='checkbox'], input[type='radio']").first
        if control.count():
            if control.is_checked() != enabled:
                control.check(force=True)
            return

    row = page.locator("tr, li, .form-group, .form-item, .row").filter(
        has_text=re.compile(band_pattern, re.IGNORECASE)
    ).first
    control = row.locator("input[type='checkbox'], input[type='radio']").first
    if not control.count():
        raise RuntimeError(f"Interruttore della banda {band_pattern} non trovato")
    if control.is_checked() != enabled:
        control.check(force=True)


def _set_wifi(page: Page, enabled: bool, timeout: int) -> None:
    _click_text(page, "Local Network", timeout)
    _click_text(page, "WLAN", timeout)
    _open_accordion(page, "WLAN On/Off Configuration", timeout)
    band_text = page.get_by_text(re.compile(r"2[.,]?4\s*(GHz|G)|5\s*(GHz|G)", re.IGNORECASE)).first
    band_text.wait_for(state="visible", timeout=timeout * 1000)
    _click_band_toggle(page, r"2[.,]?4\s*(GHz|G)", enabled)
    _click_band_toggle(page, r"5\s*(GHz|G)", enabled)

    save = page.get_by_role("button", name=re.compile(r"Save|Apply|Salva", re.IGNORECASE)).last
    save.wait_for(state="visible", timeout=timeout * 1000)
    save.click()
    page.wait_for_timeout(500)


def _launch_browser(browser: Browser, executable_path: str | None, headless: bool):
    if executable_path:
        return browser.chromium.launch(headless=headless, executable_path=executable_path)
    return browser.chromium.launch(headless=headless)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Abilita/disabilita il Wi-Fi su router ZTE")
    parser.add_argument("action", choices=("on", "off"), help="on = abilita Wi-Fi, off = disabilita")
    parser.add_argument("--host", default=os.environ.get("ZTE_HOST", "192.168.1.1"))
    parser.add_argument("--username", default=os.environ.get("ZTE_USERNAME", "admin"))
    parser.add_argument("--password", default=os.environ.get("ZTE_PASSWORD"))
    parser.add_argument("--timeout", type=int, default=10)
    parser.add_argument("--headed", action="store_true", help="mostra la finestra del browser")
    parser.add_argument("--screenshot-dir", type=Path, help="salva screenshot in caso di errore")
    parser.add_argument("--browser", default=os.environ.get("ZTE_BROWSER", "/usr/bin/google-chrome"))
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    if not args.password:
        print("Errore: imposta la password con --password o variabile ZTE_PASSWORD", file=sys.stderr)
        return 2

    page = None
    try:
        with sync_playwright() as playwright:
            browser = _launch_browser(playwright, args.browser, not args.headed)
            page = browser.new_page()
            page.goto(f"http://{args.host}/", wait_until="domcontentloaded", timeout=args.timeout * 1000)
            _login(page, args.username, args.password, args.timeout)
            enabled = args.action == "on"
            _set_wifi(page, enabled, args.timeout)
            state = "abilitato" if enabled else "disabilitato"
            print(f"Wi-Fi 2.4 GHz e 5 GHz {state} con successo")
            browser.close()
        return 0
    except (PlaywrightTimeoutError, RuntimeError) as exc:
        if args.screenshot_dir and page:
            args.screenshot_dir.mkdir(parents=True, exist_ok=True)
            page.screenshot(path=str(args.screenshot_dir / "zte-wifi-error.png"), full_page=True)
        print(f"Errore nella console web: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
