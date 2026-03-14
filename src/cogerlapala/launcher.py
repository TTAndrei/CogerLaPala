from __future__ import annotations

import argparse
import asyncio
import json
import os
import time
from pathlib import Path

from cogerlapala.config import Settings, get_settings
from cogerlapala.models import PipelineRequest, PipelineResponse
from cogerlapala.services.pipeline import build_default_pipeline


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="CogerLaPala launcher (single entrypoint)",
    )
    parser.add_argument(
        "--request",
        default=None,
        help="Request JSON path. Defaults to DEFAULT_REQUEST_FILE or examples/linkedin_request.json",
    )
    parser.add_argument(
        "--location",
        default=None,
        help="Override search location (example: Madrid or Barcelona)",
    )
    parser.add_argument(
        "--sectors",
        default=None,
        help="Override sectors as CSV (example: SaaS,Fintech,Health)",
    )
    parser.add_argument(
        "--keywords",
        default=None,
        help="Override keywords as CSV (example: python,backend,automation)",
    )
    parser.add_argument(
        "--roles",
        default=None,
        help="Override target roles as CSV (example: Backend Engineer,Automation Engineer)",
    )
    parser.add_argument(
        "--remote-only",
        choices=["true", "false"],
        default=None,
        help="Override remote filter",
    )
    parser.add_argument(
        "--start-mode",
        choices=["command", "signal", "immediate"],
        default=None,
        help="How to start execution: command, signal, or immediate",
    )
    parser.add_argument(
        "--signal-file",
        default=None,
        help="File path used when --start-mode signal",
    )
    parser.add_argument(
        "--signal-timeout",
        type=int,
        default=None,
        help="Seconds to wait in signal mode. 0 means wait forever",
    )
    parser.add_argument(
        "--pick-cv",
        action="store_true",
        help="Open file picker to select CV PDF before execution",
    )
    return parser.parse_args()


def resolve_request_path(cli_request: str | None) -> Path:
    configured_default = os.getenv("DEFAULT_REQUEST_FILE", "examples/linkedin_request.json")
    request_path = Path(cli_request or configured_default)
    return request_path


def load_request(path: Path) -> PipelineRequest:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return PipelineRequest.model_validate(payload)


def _csv_to_list(value: str | None) -> list[str]:
    if not value:
        return []
    return [part.strip() for part in value.split(",") if part.strip()]


def apply_overrides(request: PipelineRequest, args: argparse.Namespace) -> PipelineRequest:
    if args.location:
        request.search.location = args.location.strip()

    sectors = _csv_to_list(args.sectors)
    if sectors:
        request.search.sectors = sectors

    keywords = _csv_to_list(args.keywords)
    if keywords:
        request.search.keywords = keywords

    roles = _csv_to_list(args.roles)
    if roles:
        request.profile.target_roles = roles

    if args.remote_only is not None:
        request.search.remote_only = args.remote_only.lower() == "true"

    return request


async def run_pipeline(settings: Settings, request: PipelineRequest) -> PipelineResponse:
    pipeline = build_default_pipeline(settings)
    return await pipeline.run(request)


def _print_linkedin_login_guidance(settings: Settings, request: PipelineRequest) -> None:
    sources = {source.lower() for source in request.search.sources}
    uses_linkedin = "linkedin" in sources
    if not uses_linkedin:
        return

    storage_state_exists = Path(settings.linkedin_storage_state).exists()
    has_credentials = bool(settings.linkedin_email and settings.linkedin_password)

    if storage_state_exists:
        return

    print("\nAviso de login LinkedIn:")
    print("- Si inicias sesion con Google, puede aparecer 'navegador no seguro'.")
    print("- Recomendado: iniciar sesion con email/password de LinkedIn.")

    if not has_credentials:
        print("- Configura LINKEDIN_EMAIL y LINKEDIN_PASSWORD en .env para login directo.")
        print("- Si tu cuenta solo usa Google, crea una clave en LinkedIn y usa esa clave.")
    else:
        print("- Se usaran las credenciales LINKEDIN_EMAIL/LINKEDIN_PASSWORD de .env.")

    print(f"- Al completar login una vez, se guarda sesion en {settings.linkedin_storage_state}")


def _print_summary(response: PipelineResponse) -> None:
    print("\nResumen:")
    print(f"- Vacantes detectadas: {response.discovered_count}")
    print(f"- Vacantes seleccionadas: {response.selected_count}")
    print(f"- Acciones ejecutadas: {len(response.action_results)}")

    status_counts: dict[str, int] = {}
    for action in response.action_results:
        status_counts[action.status] = status_counts.get(action.status, 0) + 1

    if status_counts:
        print("- Estados:")
        for status, count in sorted(status_counts.items()):
            print(f"  - {status}: {count}")

    if response.warnings:
        print("- Warnings:")
        for warning in response.warnings:
            print(f"  - {warning}")


def _resolve_start_mode(args: argparse.Namespace) -> str:
    if args.start_mode:
        return args.start_mode
    mode = os.getenv("START_MODE", "command").strip().lower()
    if mode not in {"command", "signal", "immediate"}:
        return "command"
    return mode


def _resolve_signal_file(args: argparse.Namespace) -> Path:
    signal_file = args.signal_file or os.getenv("START_SIGNAL_FILE", ".artifacts/start.signal")
    return Path(signal_file)


def _resolve_signal_timeout(args: argparse.Namespace) -> int:
    if args.signal_timeout is not None:
        return max(args.signal_timeout, 0)
    raw = os.getenv("START_SIGNAL_TIMEOUT_SECONDS", "0").strip()
    try:
        return max(int(raw), 0)
    except ValueError:
        return 0


def _save_request(path: Path, request: PipelineRequest) -> None:
    path.write_text(request.model_dump_json(indent=2), encoding="utf-8")


def _pick_cv_file(current_cv_path: str | None) -> str | None:
    try:
        import tkinter as tk
        from tkinter import filedialog
    except Exception as exc:
        print(f"No se pudo cargar selector grafico de archivos: {exc}")
        return None

    try:
        initial_dir = Path.cwd()
        if current_cv_path:
            current = Path(current_cv_path).expanduser()
            if current.exists() and current.parent.exists():
                initial_dir = current.parent

        root = tk.Tk()
        root.withdraw()
        try:
            root.attributes("-topmost", True)
        except Exception:
            pass

        selected = filedialog.askopenfilename(
            title="Selecciona tu CV (PDF)",
            initialdir=str(initial_dir),
            filetypes=[("PDF files", "*.pdf"), ("All files", "*.*")],
        )
        root.destroy()

        if not selected:
            return None

        selected_path = Path(selected).expanduser().resolve()
        return str(selected_path)
    except Exception as exc:
        print(f"No se pudo abrir selector de archivos: {exc}")
        return None


def _update_cv_from_picker(request: PipelineRequest, request_path: Path) -> bool:
    selected = _pick_cv_file(request.profile.cv_path)
    if not selected:
        print("No se selecciono ningun archivo.")
        return False

    if not selected.lower().endswith(".pdf"):
        print("Aviso: el archivo seleccionado no es PDF.")

    request.profile.cv_path = selected
    _save_request(request_path, request)
    print(f"CV guardado en request: {selected}")
    return True


def _await_start_permission(
    mode: str,
    signal_file: Path,
    timeout_seconds: int,
    request: PipelineRequest,
    request_path: Path,
) -> bool:
    if mode == "immediate":
        return True

    if mode == "command":
        print("\nArranque en modo command.")
        print("Comandos: RUN, CV, SHOW, EXIT")
        while True:
            try:
                value = input("> ").strip().lower()
            except (KeyboardInterrupt, EOFError):
                print("\nCancelado por usuario.")
                return False

            if value in {"run", "start", "go", "si", "yes"}:
                return True
            if value in {"cv", "curriculum", "resume"}:
                _update_cv_from_picker(request, request_path)
                continue
            if value in {"show", "status", "cvpath"}:
                print(f"CV actual: {request.profile.cv_path or '(vacio)'}")
                continue
            if value in {"exit", "quit", "cancel", "no"}:
                print("Cancelado por usuario.")
                return False
            print("Comando no valido. Usa RUN, CV, SHOW o EXIT.")

    print("\nArranque en modo signal.")
    print(f"Esperando archivo de senal: {signal_file}")
    if timeout_seconds > 0:
        print(f"Timeout configurado: {timeout_seconds}s")
    print("Crea ese archivo para iniciar.")

    start = time.monotonic()
    while True:
        if signal_file.exists():
            try:
                signal_file.unlink(missing_ok=True)
            except Exception:
                pass
            print("Senal recibida. Iniciando pipeline.")
            return True

        if timeout_seconds > 0 and (time.monotonic() - start) >= timeout_seconds:
            print("Timeout esperando senal. Proceso cancelado.")
            return False

        time.sleep(1)


def main() -> int:
    args = parse_args()
    request_path = resolve_request_path(args.request)

    if not request_path.exists():
        print(f"Request file not found: {request_path}")
        print("Tip: use --request examples/sample_request.json")
        return 1

    settings = get_settings()
    request = load_request(request_path)
    request = apply_overrides(request, args)

    if args.pick_cv:
        _update_cv_from_picker(request, request_path)

    _print_linkedin_login_guidance(settings, request)

    start_mode = _resolve_start_mode(args)
    signal_file = _resolve_signal_file(args)
    signal_timeout = _resolve_signal_timeout(args)
    if not _await_start_permission(
        start_mode,
        signal_file,
        signal_timeout,
        request,
        request_path,
    ):
        return 0

    response = asyncio.run(run_pipeline(settings, request))
    print(response.model_dump_json(indent=2))
    _print_summary(response)
    print("\nCapturas disponibles en .artifacts/screenshots")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
