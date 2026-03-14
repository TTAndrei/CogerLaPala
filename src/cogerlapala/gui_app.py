from __future__ import annotations

import asyncio
import os
import threading
import traceback
from pathlib import Path

import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from cogerlapala.config import get_settings
from cogerlapala.models import PipelineRequest, PipelineResponse
from cogerlapala.services.pipeline import build_default_pipeline


class CogerLaPalaGUI:
    def __init__(self, initial_request_path: str | None = None) -> None:
        self.settings = get_settings()
        self.pipeline = build_default_pipeline(self.settings)

        self.root = tk.Tk()
        self.root.title("CogerLaPala - Control Panel")
        self.root.geometry("1180x840")
        self.root.minsize(980, 720)

        self.running = False
        self.current_request_path = Path(
            initial_request_path
            or os.getenv("DEFAULT_REQUEST_FILE", "examples/linkedin_request.json")
        )

        self._build_variables()
        self._build_layout()
        self._load_request_file(self.current_request_path, show_dialog=False)

    def run(self) -> int:
        self.root.mainloop()
        return 0

    def _build_variables(self) -> None:
        self.profile_vars: dict[str, tk.Variable] = {
            "full_name": tk.StringVar(),
            "email": tk.StringVar(),
            "phone": tk.StringVar(),
            "location": tk.StringVar(),
            "headline": tk.StringVar(),
            "summary": tk.StringVar(),
            "target_roles": tk.StringVar(),
            "sectors": tk.StringVar(),
            "skills": tk.StringVar(),
            "languages": tk.StringVar(),
            "years_experience": tk.StringVar(value="0"),
            "salary_expectation_min": tk.StringVar(),
            "salary_expectation_currency": tk.StringVar(value="EUR"),
            "cv_path": tk.StringVar(),
        }

        self.search_vars: dict[str, tk.Variable] = {
            "keywords": tk.StringVar(),
            "location": tk.StringVar(),
            "remote_only": tk.BooleanVar(value=True),
            "sectors": tk.StringVar(),
            "seniority": tk.StringVar(value="mid"),
            "linkedin_easy_apply_only": tk.BooleanVar(value=True),
            "max_results_per_source": tk.StringVar(value="10"),
            "sources": tk.StringVar(value="linkedin"),
        }

        self.execution_vars: dict[str, tk.Variable] = {
            "dry_run": tk.BooleanVar(value=True),
            "enable_browser_automation": tk.BooleanVar(value=True),
            "require_human_review": tk.BooleanVar(value=True),
            "max_applications": tk.StringVar(value="5"),
            "screenshot_each_step": tk.BooleanVar(value=True),
        }

        self.request_path_var = tk.StringVar(value=str(self.current_request_path))

    def _build_layout(self) -> None:
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(2, weight=1)
        self.root.rowconfigure(3, weight=1)

        header = ttk.Frame(self.root, padding=10)
        header.grid(row=0, column=0, sticky="ew")
        header.columnconfigure(1, weight=1)

        ttk.Label(header, text="Request JSON:").grid(row=0, column=0, sticky="w", padx=(0, 8))
        ttk.Entry(header, textvariable=self.request_path_var).grid(row=0, column=1, sticky="ew")

        header_buttons = ttk.Frame(header)
        header_buttons.grid(row=0, column=2, sticky="e", padx=(8, 0))

        ttk.Button(header_buttons, text="Cargar JSON", command=self._load_request_dialog).grid(
            row=0, column=0, padx=3
        )
        ttk.Button(header_buttons, text="Guardar JSON", command=self._save_current_request).grid(
            row=0, column=1, padx=3
        )
        ttk.Button(header_buttons, text="Guardar Como", command=self._save_request_as_dialog).grid(
            row=0, column=2, padx=3
        )
        ttk.Button(header_buttons, text="Seleccionar CV", command=self._select_cv).grid(
            row=0, column=3, padx=3
        )
        ttk.Button(header_buttons, text="Abrir Capturas", command=self._open_screenshots).grid(
            row=0, column=4, padx=3
        )

        help_bar = ttk.Frame(self.root, padding=(10, 0, 10, 8))
        help_bar.grid(row=1, column=0, sticky="ew")
        help_bar.columnconfigure(0, weight=1)
        ttk.Label(
            help_bar,
            text=(
                "Configura parametros y luego usa Preview (sin aplicar) o Run (ejecucion real segun dry_run)."
            ),
        ).grid(row=0, column=0, sticky="w")

        notebook = ttk.Notebook(self.root)
        notebook.grid(row=2, column=0, sticky="nsew", padx=10)

        profile_tab = ttk.Frame(notebook, padding=12)
        search_tab = ttk.Frame(notebook, padding=12)
        execution_tab = ttk.Frame(notebook, padding=12)
        notebook.add(profile_tab, text="Perfil")
        notebook.add(search_tab, text="Busqueda")
        notebook.add(execution_tab, text="Ejecucion")

        self._build_profile_tab(profile_tab)
        self._build_search_tab(search_tab)
        self._build_execution_tab(execution_tab)

        run_controls = ttk.Frame(self.root, padding=(10, 8))
        run_controls.grid(row=3, column=0, sticky="ew")
        run_controls.columnconfigure(2, weight=1)

        self.preview_button = ttk.Button(run_controls, text="Ejecutar Preview", command=self._run_preview)
        self.preview_button.grid(row=0, column=0, padx=(0, 8))

        self.run_button = ttk.Button(run_controls, text="Ejecutar Run", command=self._run_pipeline)
        self.run_button.grid(row=0, column=1, padx=(0, 8))

        ttk.Label(run_controls, text="Output:").grid(row=0, column=2, sticky="w")

        output_frame = ttk.Frame(self.root, padding=(10, 0, 10, 10))
        output_frame.grid(row=4, column=0, sticky="nsew")
        self.root.rowconfigure(4, weight=1)
        output_frame.columnconfigure(0, weight=1)
        output_frame.rowconfigure(0, weight=1)

        self.output_text = tk.Text(output_frame, height=14, wrap="word")
        self.output_text.grid(row=0, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(output_frame, orient="vertical", command=self.output_text.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        self.output_text.configure(yscrollcommand=scroll.set)

    def _build_profile_tab(self, parent: ttk.Frame) -> None:
        parent.columnconfigure(1, weight=1)

        self._add_entry(parent, 0, "Nombre completo", self.profile_vars["full_name"])
        self._add_entry(parent, 1, "Email", self.profile_vars["email"])
        self._add_entry(parent, 2, "Telefono", self.profile_vars["phone"])
        self._add_entry(parent, 3, "Ubicacion perfil", self.profile_vars["location"])
        self._add_entry(parent, 4, "Titular", self.profile_vars["headline"])
        self._add_entry(parent, 5, "Resumen", self.profile_vars["summary"])
        self._add_entry(parent, 6, "Roles objetivo (CSV)", self.profile_vars["target_roles"])
        self._add_entry(parent, 7, "Sectores perfil (CSV)", self.profile_vars["sectors"])
        self._add_entry(parent, 8, "Skills (CSV)", self.profile_vars["skills"])
        self._add_entry(parent, 9, "Idiomas (CSV)", self.profile_vars["languages"])
        self._add_entry(parent, 10, "Anios experiencia", self.profile_vars["years_experience"])
        self._add_entry(parent, 11, "Salario minimo", self.profile_vars["salary_expectation_min"])
        self._add_entry(parent, 12, "Moneda salario", self.profile_vars["salary_expectation_currency"])
        self._add_entry(parent, 13, "Ruta CV", self.profile_vars["cv_path"])

    def _build_search_tab(self, parent: ttk.Frame) -> None:
        parent.columnconfigure(1, weight=1)

        self._add_entry(parent, 0, "Keywords (CSV)", self.search_vars["keywords"])
        self._add_entry(
            parent,
            1,
            "Ubicaciones (una o CSV)",
            self.search_vars["location"],
        )
        self._add_entry(parent, 2, "Sectores busqueda (CSV)", self.search_vars["sectors"])
        self._add_entry(parent, 3, "Seniority", self.search_vars["seniority"])
        self._add_entry(parent, 4, "Max resultados por fuente", self.search_vars["max_results_per_source"])
        self._add_entry(parent, 5, "Sources (CSV)", self.search_vars["sources"])

        ttk.Checkbutton(
            parent,
            text="Solo remoto",
            variable=self.search_vars["remote_only"],
        ).grid(row=6, column=1, sticky="w", pady=4)

        ttk.Checkbutton(
            parent,
            text="LinkedIn Easy Apply only",
            variable=self.search_vars["linkedin_easy_apply_only"],
        ).grid(row=7, column=1, sticky="w", pady=4)

    def _build_execution_tab(self, parent: ttk.Frame) -> None:
        parent.columnconfigure(1, weight=1)

        self._add_entry(parent, 0, "Max aplicaciones", self.execution_vars["max_applications"])

        ttk.Checkbutton(
            parent,
            text="Dry run",
            variable=self.execution_vars["dry_run"],
        ).grid(row=1, column=1, sticky="w", pady=4)

        ttk.Checkbutton(
            parent,
            text="Habilitar automatizacion navegador",
            variable=self.execution_vars["enable_browser_automation"],
        ).grid(row=2, column=1, sticky="w", pady=4)

        ttk.Checkbutton(
            parent,
            text="Requerir revision humana",
            variable=self.execution_vars["require_human_review"],
        ).grid(row=3, column=1, sticky="w", pady=4)

        ttk.Checkbutton(
            parent,
            text="Captura por paso",
            variable=self.execution_vars["screenshot_each_step"],
        ).grid(row=4, column=1, sticky="w", pady=4)

    def _add_entry(self, parent: ttk.Frame, row: int, label: str, variable: tk.Variable) -> None:
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", padx=(0, 8), pady=4)
        ttk.Entry(parent, textvariable=variable).grid(row=row, column=1, sticky="ew", pady=4)

    def _load_request_dialog(self) -> None:
        selected = filedialog.askopenfilename(
            title="Selecciona request JSON",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
        )
        if not selected:
            return
        self._load_request_file(Path(selected), show_dialog=True)

    def _load_request_file(self, path: Path, show_dialog: bool) -> None:
        if not path.exists():
            self._log(f"Request no encontrado: {path}")
            return

        try:
            payload = path.read_text(encoding="utf-8")
            request = PipelineRequest.model_validate_json(payload)
            self.current_request_path = path
            self.request_path_var.set(str(path))
            self._set_form_from_request(request)
            self._log(f"Request cargado: {path}")
            if show_dialog:
                messagebox.showinfo("Carga", "Request cargado correctamente")
        except Exception as exc:
            messagebox.showerror("Error", f"No se pudo cargar request: {exc}")

    def _set_form_from_request(self, request: PipelineRequest) -> None:
        profile = request.profile
        self.profile_vars["full_name"].set(profile.full_name)
        self.profile_vars["email"].set(profile.email)
        self.profile_vars["phone"].set(profile.phone or "")
        self.profile_vars["location"].set(profile.location)
        self.profile_vars["headline"].set(profile.headline or "")
        self.profile_vars["summary"].set(profile.summary or "")
        self.profile_vars["target_roles"].set(", ".join(profile.target_roles))
        self.profile_vars["sectors"].set(", ".join(profile.sectors))
        self.profile_vars["skills"].set(", ".join(profile.skills))
        self.profile_vars["languages"].set(", ".join(profile.languages))
        self.profile_vars["years_experience"].set(str(profile.years_experience))
        self.profile_vars["salary_expectation_min"].set(
            "" if profile.salary_expectation_min is None else str(profile.salary_expectation_min)
        )
        self.profile_vars["salary_expectation_currency"].set(profile.salary_expectation_currency or "")
        self.profile_vars["cv_path"].set(profile.cv_path or "")

        search = request.search
        self.search_vars["keywords"].set(", ".join(search.keywords))
        location_value = search.location
        if isinstance(location_value, list):
            self.search_vars["location"].set(", ".join(location_value))
        else:
            self.search_vars["location"].set(location_value or "")
        self.search_vars["remote_only"].set(search.remote_only)
        self.search_vars["sectors"].set(", ".join(search.sectors))
        self.search_vars["seniority"].set(search.seniority or "")
        self.search_vars["linkedin_easy_apply_only"].set(search.linkedin_easy_apply_only)
        self.search_vars["max_results_per_source"].set(str(search.max_results_per_source))
        self.search_vars["sources"].set(", ".join(search.sources))

        execution = request.execution
        self.execution_vars["dry_run"].set(execution.dry_run)
        self.execution_vars["enable_browser_automation"].set(execution.enable_browser_automation)
        self.execution_vars["require_human_review"].set(execution.require_human_review)
        self.execution_vars["max_applications"].set(str(execution.max_applications))
        self.execution_vars["screenshot_each_step"].set(execution.screenshot_each_step)

    def _save_current_request(self) -> None:
        if not self.current_request_path:
            self._save_request_as_dialog()
            return

        try:
            request = self._build_request_from_form()
            self.current_request_path.write_text(request.model_dump_json(indent=2), encoding="utf-8")
            self._log(f"Request guardado: {self.current_request_path}")
            messagebox.showinfo("Guardar", "Request guardado correctamente")
        except Exception as exc:
            messagebox.showerror("Error", f"No se pudo guardar request: {exc}")

    def _save_request_as_dialog(self) -> None:
        selected = filedialog.asksaveasfilename(
            title="Guardar request JSON",
            defaultextension=".json",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")],
            initialfile=self.current_request_path.name if self.current_request_path else "request.json",
        )
        if not selected:
            return

        path = Path(selected)
        try:
            request = self._build_request_from_form()
            path.write_text(request.model_dump_json(indent=2), encoding="utf-8")
            self.current_request_path = path
            self.request_path_var.set(str(path))
            self._log(f"Request guardado: {path}")
            messagebox.showinfo("Guardar", "Request guardado correctamente")
        except Exception as exc:
            messagebox.showerror("Error", f"No se pudo guardar request: {exc}")

    def _select_cv(self) -> None:
        selected = filedialog.askopenfilename(
            title="Selecciona CV PDF",
            filetypes=[("PDF files", "*.pdf"), ("All files", "*.*")],
        )
        if not selected:
            return

        cv_path = str(Path(selected).expanduser().resolve())
        self.profile_vars["cv_path"].set(cv_path)
        self._log(f"CV seleccionado: {cv_path}")

        if self.current_request_path:
            try:
                request = self._build_request_from_form()
                self.current_request_path.write_text(request.model_dump_json(indent=2), encoding="utf-8")
                self._log("Ruta CV guardada en request.")
            except Exception as exc:
                self._log(f"No se pudo guardar la ruta de CV automaticamente: {exc}")

    def _open_screenshots(self) -> None:
        folder = Path(self.settings.screenshot_dir)
        folder.mkdir(parents=True, exist_ok=True)

        try:
            os.startfile(folder)
        except Exception as exc:
            messagebox.showerror("Error", f"No se pudo abrir carpeta: {exc}")

    def _run_preview(self) -> None:
        self._start_run(preview=True)

    def _run_pipeline(self) -> None:
        self._start_run(preview=False)

    def _start_run(self, preview: bool) -> None:
        if self.running:
            messagebox.showinfo("En curso", "Ya hay una ejecucion en progreso")
            return

        try:
            request = self._build_request_from_form()
        except Exception as exc:
            messagebox.showerror("Request invalido", str(exc))
            return

        if preview:
            request = request.model_copy(deep=True)
            request.execution.dry_run = True
            request.execution.enable_browser_automation = False

        self.running = True
        self.preview_button.configure(state="disabled")
        self.run_button.configure(state="disabled")

        mode_name = "preview" if preview else "run"
        self._log(f"Iniciando {mode_name}...")

        worker = threading.Thread(
            target=self._run_worker,
            args=(request, mode_name),
            daemon=True,
        )
        worker.start()

    def _run_worker(self, request: PipelineRequest, mode_name: str) -> None:
        try:
            response = asyncio.run(self.pipeline.run(request))
            response_json = response.model_dump_json(indent=2)
            self.root.after(0, lambda: self._on_run_success(mode_name, response, response_json))
        except Exception as exc:
            trace = traceback.format_exc()
            self.root.after(0, lambda: self._on_run_error(mode_name, exc, trace))

    def _on_run_success(self, mode_name: str, response: PipelineResponse, response_json: str) -> None:
        self.running = False
        self.preview_button.configure(state="normal")
        self.run_button.configure(state="normal")

        self._log(f"{mode_name} finalizado.")
        self._log(response_json)

        status_counts: dict[str, int] = {}
        for action in response.action_results:
            status_counts[action.status] = status_counts.get(action.status, 0) + 1

        summary = [
            "Resumen:",
            f"- Vacantes detectadas: {response.discovered_count}",
            f"- Vacantes seleccionadas: {response.selected_count}",
            f"- Acciones ejecutadas: {len(response.action_results)}",
        ]
        if status_counts:
            summary.append("- Estados: " + ", ".join(f"{k}={v}" for k, v in sorted(status_counts.items())))
        if response.warnings:
            summary.append("- Warnings: " + " | ".join(response.warnings))

        self._log("\n" + "\n".join(summary))

    def _on_run_error(self, mode_name: str, exc: Exception, trace: str) -> None:
        self.running = False
        self.preview_button.configure(state="normal")
        self.run_button.configure(state="normal")

        self._log(f"{mode_name} fallo: {exc}")
        self._log(trace)
        messagebox.showerror("Error", f"La ejecucion fallo: {exc}")

    def _build_request_from_form(self) -> PipelineRequest:
        location_values = self._parse_csv(self.search_vars["location"].get())
        if not location_values:
            search_location: str | list[str] | None = None
        elif len(location_values) == 1:
            search_location = location_values[0]
        else:
            search_location = location_values

        salary_min = self._parse_optional_int(self.profile_vars["salary_expectation_min"].get())

        payload = {
            "profile": {
                "full_name": self.profile_vars["full_name"].get().strip(),
                "email": self.profile_vars["email"].get().strip(),
                "phone": self.profile_vars["phone"].get().strip() or None,
                "location": self.profile_vars["location"].get().strip(),
                "headline": self.profile_vars["headline"].get().strip() or None,
                "summary": self.profile_vars["summary"].get().strip() or None,
                "target_roles": self._parse_csv(self.profile_vars["target_roles"].get()),
                "sectors": self._parse_csv(self.profile_vars["sectors"].get()),
                "skills": self._parse_csv(self.profile_vars["skills"].get()),
                "languages": self._parse_csv(self.profile_vars["languages"].get()),
                "years_experience": self._parse_int(self.profile_vars["years_experience"].get(), "years_experience"),
                "salary_expectation_min": salary_min,
                "salary_expectation_currency": self.profile_vars["salary_expectation_currency"].get().strip() or None,
                "cv_path": self.profile_vars["cv_path"].get().strip() or None,
            },
            "search": {
                "keywords": self._parse_csv(self.search_vars["keywords"].get()),
                "location": search_location,
                "remote_only": bool(self.search_vars["remote_only"].get()),
                "sectors": self._parse_csv(self.search_vars["sectors"].get()),
                "seniority": self.search_vars["seniority"].get().strip() or None,
                "linkedin_easy_apply_only": bool(self.search_vars["linkedin_easy_apply_only"].get()),
                "max_results_per_source": self._parse_int(
                    self.search_vars["max_results_per_source"].get(),
                    "max_results_per_source",
                ),
                "sources": self._parse_csv(self.search_vars["sources"].get()) or ["linkedin"],
            },
            "execution": {
                "dry_run": bool(self.execution_vars["dry_run"].get()),
                "enable_browser_automation": bool(self.execution_vars["enable_browser_automation"].get()),
                "require_human_review": bool(self.execution_vars["require_human_review"].get()),
                "max_applications": self._parse_int(
                    self.execution_vars["max_applications"].get(),
                    "max_applications",
                ),
                "screenshot_each_step": bool(self.execution_vars["screenshot_each_step"].get()),
            },
        }

        return PipelineRequest.model_validate(payload)

    def _parse_csv(self, value: str) -> list[str]:
        return [part.strip() for part in value.split(",") if part.strip()]

    def _parse_int(self, value: str, field_name: str) -> int:
        raw = value.strip()
        if not raw:
            raise ValueError(f"El campo {field_name} no puede estar vacio")
        try:
            return int(raw)
        except ValueError as exc:
            raise ValueError(f"El campo {field_name} debe ser entero") from exc

    def _parse_optional_int(self, value: str) -> int | None:
        raw = value.strip()
        if not raw:
            return None
        try:
            return int(raw)
        except ValueError as exc:
            raise ValueError("salary_expectation_min debe ser entero") from exc

    def _log(self, text: str) -> None:
        self.output_text.insert("end", text + "\n")
        self.output_text.see("end")


def run_gui(initial_request_path: str | None = None) -> int:
    app = CogerLaPalaGUI(initial_request_path=initial_request_path)
    return app.run()
