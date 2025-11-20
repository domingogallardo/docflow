#!/usr/bin/env python3
"""Gestiona sesiones de X con Playwright: login manual persistente y modo storage_state."""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError, sync_playwright

from utils.x_likes_fetcher import (
    DEFAULT_LIKES_URL,
    DEFAULT_MAX_TWEETS,
    STEALTH_SNIPPET,
    collect_likes_from_page,
    fetch_likes_with_state,
)

LOGIN_URL = "https://x.com/i/flow/login"


def log(message: str) -> None:
    print(message)
    sys.stdout.flush()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Inicia un Chrome real con perfil persistente para loguearte manualmente "
            "O reutiliza un storage_state existente (permite --headless)."
        )
    )
    parser.add_argument(
        "--profile-dir",
        type=Path,
        default=Path(".playwright") / "x-profile",
        help="Directorio donde se guardará el perfil de Chrome. Puedes borrarlo para reiniciar la sesión.",
    )
    parser.add_argument(
        "--likes-url",
        default=DEFAULT_LIKES_URL,
        help="URL privada que se abrirá tras el login para comprobar la sesión.",
    )
    parser.add_argument(
        "--export-state",
        type=Path,
        help="Guarda el storage_state tras un login manual exitoso en la ruta indicada.",
    )
    parser.add_argument(
        "--state",
        type=Path,
        help="Usa este storage_state existente (JSON) para abrir los likes directamente.",
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        default=False,
        help="Solo válido con --state: ejecuta Chromium sin UI al reutilizar el storage_state.",
    )
    parser.add_argument(
        "--stop-at-url",
        help="URL de un tweet ya procesado; se detiene cuando aparezca en los likes.",
    )
    parser.add_argument(
        "--max-tweets",
        type=int,
        default=DEFAULT_MAX_TWEETS,
        help=(
            "Límite duro de tweets a inspeccionar en la página de likes "
            f"(por defecto: {DEFAULT_MAX_TWEETS})."
        ),
    )
    return parser.parse_args()


def manual_login_with_persistent_profile(
    profile_dir: Path,
    likes_url: str,
    max_tweets: int,
    stop_at_url: str | None,
    export_state: Path | None = None,
) -> None:
    profile_dir = profile_dir.expanduser()
    profile_dir.mkdir(parents=True, exist_ok=True)
    log(f"📁 Perfil persistente: {profile_dir}")

    with sync_playwright() as playwright:
        try:
            context = playwright.chromium.launch_persistent_context(
                user_data_dir=str(profile_dir),
                headless=False,
                channel="chrome",
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--disable-infobars",
                ],
            )
        except Exception as exc:  # pragma: no cover - dependiente del entorno local
            raise SystemExit(
                f"❌ No se pudo lanzar Chrome. Asegúrate de tener Google Chrome instalado y accesible: {exc}"
            ) from exc

        try:
            context.add_init_script(STEALTH_SNIPPET)
            page = context.pages[0] if context.pages else context.new_page()

            success, count, _, stop_found, _ = collect_likes_from_page(
                page, likes_url, max_tweets, stop_at_url
            )
            if success:
                log(
                    f"🙌 Ya estabas autenticado. Tweets likeados visibles: {count}. "
                    f"Stop URL {'encontrada' if stop_found else 'no encontrada'}."
                )
            else:
                log(f"1️⃣  No hay sesión activa. Abriendo {LOGIN_URL}…")
                page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=60000)
                log("   ℹ️  Completa el login manualmente en la ventana de Chrome (usa teclado/ratón).")
                input("   ⏸️  Pulsa Enter aquí cuando veas tu timeline o X confirme la sesión.\n")

                success, count, _, stop_found, _ = collect_likes_from_page(
                    page, likes_url, max_tweets, stop_at_url
                )
                if success:
                    log(
                        f"   📊 Likes accesibles tras login. Artículos visibles: {count}. "
                        f"Stop URL {'encontrada' if stop_found else 'no encontrada'}."
                    )
                else:
                    log("   ❌ Tras el login manual, sigue sin verse la página de likes.")
                    log("      Revisa la ventana por si X pide pasos adicionales (2FA, captcha, etc.).")

            if export_state and success:
                export_path = export_state.expanduser()
                export_path.parent.mkdir(parents=True, exist_ok=True)
                context.storage_state(path=str(export_path))
                log(f"   💾 storage_state guardado en {export_path}")
            elif export_state:
                log("   ⚠️  No se guardó storage_state porque la sesión no está activa.")

            input("3️⃣  Pulsa Enter cuando quieras cerrar la ventana y conservar el perfil.\n")
        finally:
            context.close()
            log("🏁 Chrome cerrado. El perfil se mantiene en disco para reutilizarlo.")


def visit_with_storage_state(
    state_path: Path,
    likes_url: str,
    headless: bool,
    max_tweets: int,
    stop_at_url: str | None,
) -> None:
    try:
        urls, stop_found, total = fetch_likes_with_state(
            state_path,
            likes_url=likes_url,
            max_tweets=max_tweets,
            stop_at_url=stop_at_url,
            headless=headless,
        )
    except Exception as exc:  # pragma: no cover - mensaje amigable
        raise SystemExit(f"❌ Error usando storage_state: {exc}") from exc

    mode = "headless" if headless else "con UI"
    log(
        f"🏁 Sesión válida ({mode}). Tweets visibles: {total}. "
        f"Stop URL {'encontrada' if stop_found else 'no encontrada'}."
    )
    if urls:
        log(f"   📌 URLs nuevas detectadas: {len(urls)}")


def main() -> None:
    args = parse_args()
    if args.max_tweets <= 0:
        raise SystemExit("❌ --max-tweets debe ser mayor que 0.")
    if args.state:
        visit_with_storage_state(
            args.state,
            args.likes_url,
            args.headless,
            args.max_tweets,
            args.stop_at_url,
        )
        return

    if args.headless:
        raise SystemExit("❌ --headless solo es compatible con --state.")

    manual_login_with_persistent_profile(
        args.profile_dir,
        args.likes_url,
        args.max_tweets,
        args.stop_at_url,
        args.export_state,
    )


if __name__ == "__main__":
    main()
