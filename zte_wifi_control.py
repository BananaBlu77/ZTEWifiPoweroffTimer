#!/usr/bin/env python3
"""Disable both Wi-Fi bands through the ZTE web console."""

from __future__ import annotations

import argparse
import os
import re
import sys
import time
from pathlib import Path

from playwright.sync_api import Browser, Frame, Locator, Page, TimeoutError as PlaywrightTimeoutError, sync_playwright


def _first_visible(page: Page, selectors: tuple[str, ...], timeout: int = 10) -> Locator:
    deadline = time.time() + timeout
    while time.time() < deadline:
        contexts: list[Page | Frame] = [page] + page.frames
        for ctx in contexts:
            for selector in selectors:
                try:
                    loc = ctx.locator(selector)
                    for i in range(loc.count()):
                        item = loc.nth(i)
                        if item.is_visible():
                            return item
                except Exception:
                    continue
        page.wait_for_timeout(200)
    raise RuntimeError(f"Controllo non trovato nella pagina {page.url} tra i selettori: {selectors}")


def _click_text(page: Page, text: str, timeout: int) -> None:
    locator = page.get_by_text(text, exact=True).first
    locator.wait_for(state="visible", timeout=timeout * 1000)
    locator.click()


def _open_accordion(page: Page, text: str, timeout: int) -> None:
    heading = page.get_by_text(text, exact=True).first
    heading.wait_for(state="visible", timeout=timeout * 1000)
    container = heading.locator("xpath=..").first
    container.click()


def _find_warning_context(page: Page) -> tuple[Page | Frame, Locator | None] | None:
    patterns = [
        re.compile(r"Another\s+user\s+is\s+configuring\s+the\s+device", re.IGNORECASE),
        re.compile(r"force\s+the\s+user\s+to\s+logout", re.IGNORECASE),
        re.compile(r"configuring\s+the\s+device", re.IGNORECASE),
        re.compile(r"select\s+a\s+user\s+and\s+click\s+on", re.IGNORECASE),
        re.compile(r"Another\s+user", re.IGNORECASE),
    ]

    contexts: list[Page | Frame] = [page] + page.frames
    for ctx in contexts:
        # Controllo 1: Playwright text locator
        for pat in patterns:
            try:
                loc = ctx.get_by_text(pat).first
                if loc.is_visible():
                    return ctx, loc
            except Exception:
                pass

        # Controllo 2: JavaScript su innerText, textContent e innerHTML con normalizzazione whitespace
        try:
            matched = ctx.evaluate("""() => {
                const text = ((document.body ? document.body.innerText : '') + ' ' +
                              (document.body ? document.body.textContent : '')).replace(/\\s+/g, ' ');
                const html = document.body ? document.body.innerHTML : '';
                const re = /configuring\\s+the\\s+device|force\\s+the\\s+user\\s+to\\s+logout|Another\\s+user/i;
                return re.test(text) || re.test(html);
            }""")
            if matched:
                return ctx, None
        except Exception:
            pass

        # Controllo 3: Presenza combinata nel DOM di radio button utente e pulsanti Apply / Cancel
        try:
            matched_controls = ctx.evaluate("""() => {
                const all = Array.from(document.querySelectorAll("input, button, a, div, span"));
                const texts = all.map(el => (el.value || el.innerText || '').trim().toLowerCase());
                const hasApply = texts.some(t => t === 'apply');
                const hasCancel = texts.some(t => t === 'cancel');
                const hasRadio = !!document.querySelector("input[type='radio']");
                return (hasApply && hasCancel) || (hasRadio && hasApply);
            }""")
            if matched_controls:
                return ctx, None
        except Exception:
            pass

    return None


def _click_apply_in_context(ctx: Page | Frame, timeout: int) -> bool:
    # 1. Seleziona il radio button dell'utente attivo se non già selezionato
    try:
        ctx.evaluate("""() => {
            const radio = document.querySelector("input[type='radio']");
            if (radio && !radio.checked) {
                radio.checked = true;
                radio.dispatchEvent(new Event('change', { bubbles: true }));
                radio.dispatchEvent(new Event('click', { bubbles: true }));
            }
        }""")
    except Exception:
        pass

    # 2. Prova il click con selettori Playwright
    apply_candidates = [
        "input[type='button'][value='Apply' i]",
        "input[type='submit'][value='Apply' i]",
        "input[value='Apply' i]",
        "button:has-text('Apply')",
        "#Apply",
        "#btnApply",
        "#apply",
        "#btn_apply",
        "#Btn_apply",
        "[role='button']:has-text('Apply')",
        "a:has-text('Apply')",
        "div:has-text('Apply')",
        "span:has-text('Apply')",
    ]

    for sel in apply_candidates:
        try:
            btn = ctx.locator(sel).first
            if btn.is_visible():
                btn.click()
                return True
        except Exception:
            continue

    # 3. Fallback JavaScript: click diretto con scroll ed eventi mousedown/mouseup/click
    try:
        clicked = ctx.evaluate("""() => {
            const elements = Array.from(document.querySelectorAll("input, button, a, div, span"));
            for (const el of elements) {
                const val = (el.value || el.innerText || '').trim();
                if (/^apply$/i.test(val)) {
                    el.scrollIntoView();
                    el.dispatchEvent(new MouseEvent('mousedown', { bubbles: true, cancelable: true }));
                    el.dispatchEvent(new MouseEvent('mouseup', { bubbles: true, cancelable: true }));
                    el.click();
                    return true;
                }
            }
            return false;
        }""")
        if clicked:
            return True
    except Exception:
        pass

    return False


def _is_logged_in(page: Page) -> bool:
    """Verifica se l'utente è già autenticato e si trova nella home del router."""
    # 1. Se il campo password è visibile, siamo ancora nella schermata di login
    for ctx in [page] + page.frames:
        try:
            if ctx.locator("input[type='password']").first.is_visible():
                return False
        except Exception:
            pass

    # 2. Se l'avviso 'configuring the device' è visibile, non siamo loggati
    if _find_warning_context(page) is not None:
        return False

    # 3. Controlla se compare il pulsante Logout / Esci
    for ctx in [page] + page.frames:
        try:
            logout_btn = ctx.locator("a, button, span, [role='button'], div").filter(
                has_text=re.compile(r"^\s*(Logout|Esci|Log out)\s*$", re.IGNORECASE)
            ).first
            if logout_btn.is_visible():
                return True
        except Exception:
            pass

    # 4. Se la finestra di benvenuto iniziale non c'è più ed è presente la navigazione (es. Local Network)
    welcome_visible = False
    for ctx in [page] + page.frames:
        try:
            if ctx.locator("text=/Welcome to/i").first.is_visible():
                welcome_visible = True
                break
        except Exception:
            pass

    if not welcome_visible:
        for ctx in [page] + page.frames:
            try:
                if ctx.get_by_text("Local Network", exact=True).first.is_visible():
                    return True
            except Exception:
                pass

    return False


def _release_existing_session(page: Page, timeout: int) -> bool:
    page.on("dialog", lambda dialog: dialog.accept())

    # Se siamo già nella home, non c'è alcun avviso da gestire
    if _is_logged_in(page):
        return False

    # Attendi fino a 4 secondi per dare tempo al controllo asincrono del router
    deadline = time.time() + min(timeout, 4)
    warning_ctx: Page | Frame | None = None
    warning_loc: Locator | None = None

    while time.time() < deadline:
        if _is_logged_in(page):
            return False
        res = _find_warning_context(page)
        if res:
            warning_ctx, warning_loc = res
            break
        page.wait_for_timeout(250)

    if not warning_ctx:
        return False

    print("[!] Rilevata finestra di avviso: un altro utente sta configurando il dispositivo.")
    print("[*] Selezione dell'utente e click su 'Apply' per forzare il logout...")
    _click_apply_in_context(warning_ctx, timeout)
    page.wait_for_timeout(1000)

    # Attendi che l'avviso scompaia
    if warning_loc:
        try:
            warning_loc.wait_for(state="hidden", timeout=timeout * 1000)
        except Exception:
            pass

    # Attendi la transizione: o compare la home (accesso diretto) o ricompare il login
    print("[*] Attesa transizione post-Apply (home o schermata di login)...")
    deadline_transition = time.time() + timeout
    while time.time() < deadline_transition:
        # Se la home si è già caricata, non serve alcun login aggiuntivo
        if _is_logged_in(page):
            print("[*] Home del router caricata con successo (accesso automatico dopo Apply).")
            page.wait_for_timeout(500)
            return True

        # Se compaiono i campi di login per reinserire credenziali
        for ctx in [page] + page.frames:
            try:
                if ctx.locator("input[type='password']").first.is_visible():
                    print("[*] Schermata di login pronta.")
                    page.wait_for_timeout(300)
                    return True
            except Exception:
                pass
        page.wait_for_timeout(250)

    return True


def _login(page: Page, username: str, password: str, timeout: int) -> None:
    # Se siamo già autenticati (es. dopo Apply l'accesso è stato automatico), non fare nulla
    if _is_logged_in(page):
        print("[*] Già autenticati, passaggio diretto alla configurazione Wi-Fi.")
        return

    # Se invece la schermata di avviso è presente prima di iniziare il login, rilasciamola
    res = _find_warning_context(page)
    if res:
        _release_existing_session(page, timeout)
        if _is_logged_in(page):
            return

    username_field = _first_visible(
        page,
        ("input[name*='user' i]", "input[id*='user' i]", "input[type='text']"),
        timeout=timeout,
    )
    password_field = _first_visible(
        page,
        ("input[type='password']", "input[name*='pass' i]"),
        timeout=timeout,
    )
    username_field.fill(username)
    password_field.fill(password)
    login_button = _first_visible(
        page,
        ("button:has-text('Login')", "button:has-text('Accedi')", "input[type='submit']"),
        timeout=timeout,
    )
    login_button.click()

    # Controlla se il login va a buon fine o se l'avviso di sessione compare dopo il submit
    deadline = time.time() + timeout
    while time.time() < deadline:
        if _find_warning_context(page):
            print("[!] Avviso di sessione attiva comparso dopo il login.")
            _release_existing_session(page, timeout)
            if not _is_logged_in(page):
                _login(page, username, password, timeout)
            return

        # Se la home è già caricata oppure la password si è nascosta, login completato
        if _is_logged_in(page):
            return

        pw_visible = False
        for ctx in [page] + page.frames:
            try:
                if ctx.locator("input[type='password']").first.is_visible():
                    pw_visible = True
                    break
            except Exception:
                pass
        if not pw_visible:
            return

        page.wait_for_timeout(300)

    raise RuntimeError("Login fallito: controlla username e password (timeout attesa completamento login)")


def _click_band_toggle(page: Page, band_pattern: str, enabled: bool) -> None:
    row = page.locator(
        "tr, li, .form-group, .form-item, .row"
    ).filter(
        has_text=re.compile(band_pattern, re.IGNORECASE)
    ).first

    radios = row.locator("input[type='radio']")
    if radios.count() < 2:
        raise RuntimeError(f"Radio On/Off della banda {band_pattern} non trovati")

    # Primo radio = On, secondo radio = Off
    target = radios.nth(0 if enabled else 1)
    target.check(force=True)


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


def _logout(page: Page) -> None:
    try:
        logout_btn = page.locator("a, button, span, [role='button']").filter(
            has_text=re.compile(r"^\s*(Logout|Esci|Log out)\s*$", re.IGNORECASE)
        ).first
        if logout_btn.is_visible():
            logout_btn.click()
            page.wait_for_timeout(500)
    except Exception:
        pass


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
            page.goto(f"http://{args.host}/", wait_until="load", timeout=args.timeout * 1000)
            try:
                page.wait_for_load_state("networkidle", timeout=3000)
            except Exception:
                pass
            _release_existing_session(page, args.timeout)
            if not _is_logged_in(page):
                print("[*] Esecuzione login...")
                _login(page, args.username, args.password, args.timeout)
            else:
                print("[*] Accesso già effettuato alla home, login saltato.")
            enabled = args.action == "on"
            _set_wifi(page, enabled, args.timeout)
            state = "abilitato" if enabled else "disabilitato"
            print(f"Wi-Fi 2.4 GHz e 5 GHz {state} con successo")
            _logout(page)
            browser.close()
        return 0
    except (PlaywrightTimeoutError, RuntimeError) as exc:
        if page and args.screenshot_dir:
            args.screenshot_dir.mkdir(parents=True, exist_ok=True)
            try:
                page.screenshot(path=str(args.screenshot_dir / "zte-wifi-error.png"), full_page=True)
            except Exception:
                pass
            try:
                (args.screenshot_dir / "zte-page-source.html").write_text(page.content(), encoding="utf-8")
            except Exception:
                pass
        print(f"Errore nella console web: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
