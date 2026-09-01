from __future__ import annotations

import os
import queue
import subprocess
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk

from .components import ComponentManager, MODEL_PACKS
from .constants import (
    APP_NAME,
    APP_VERSION,
    QUALITY_PRESETS,
    SOURCE_LANGUAGES,
    TARGET_LANGUAGES,
)
from .pipeline import DubbingPipeline, MissingComponentError
from .project import DubProject, ProjectStore
from .settings import AppSettings, SettingsStore
from .storage import StorageLayout, StorageViolation
from .updater import GitHubUpdater, UpdateInfo, load_update_config


BG = "#0b1020"
PANEL = "#121a2e"
PANEL_2 = "#18223a"
TEXT = "#f4f7ff"
MUTED = "#9aa8c7"
ACCENT = "#7c5cff"
ACCENT_HOVER = "#9279ff"
SUCCESS = "#2fd3a2"
WARNING = "#ffbd59"


class AlviStudioApp(tk.Tk):
    def __init__(self, layout: StorageLayout) -> None:
        super().__init__()
        self.layout = layout
        self.settings_store = SettingsStore(layout)
        self.settings = self.settings_store.load()
        self.project_store = ProjectStore(layout)
        self.pipeline = DubbingPipeline(layout)
        self.components = ComponentManager(layout)
        self.events: queue.Queue[tuple[str, object]] = queue.Queue()
        self.active_thread: threading.Thread | None = None

        self.title(f"{APP_NAME} {APP_VERSION}")
        self.geometry("1120x760")
        self.minsize(960, 680)
        self.configure(bg=BG)
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self._configure_style()
        self._build_variables()
        self._build_ui()
        self._load_recent_projects()
        self._refresh_components()
        self.after(100, self._drain_events)
        if self.github_repo_var.get():
            self.after(2500, lambda: self._check_updates(silent=True))

    def _configure_style(self) -> None:
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("TFrame", background=BG)
        style.configure("Panel.TFrame", background=PANEL)
        style.configure("Subtle.TFrame", background=PANEL_2)
        style.configure("TLabel", background=BG, foreground=TEXT, font=("Segoe UI", 10))
        style.configure("Panel.TLabel", background=PANEL, foreground=TEXT, font=("Segoe UI", 10))
        style.configure("Muted.Panel.TLabel", background=PANEL, foreground=MUTED, font=("Segoe UI", 9))
        style.configure("Title.TLabel", background=BG, foreground=TEXT, font=("Segoe UI Semibold", 22))
        style.configure("Subtitle.TLabel", background=BG, foreground=MUTED, font=("Segoe UI", 10))
        style.configure("Section.Panel.TLabel", background=PANEL, foreground=TEXT, font=("Segoe UI Semibold", 12))
        style.configure("Accent.TButton", background=ACCENT, foreground="white", borderwidth=0, padding=(20, 12), font=("Segoe UI Semibold", 10))
        style.map("Accent.TButton", background=[("active", ACCENT_HOVER), ("disabled", "#4b5067")])
        style.configure("TButton", background=PANEL_2, foreground=TEXT, borderwidth=0, padding=(12, 8), font=("Segoe UI", 9))
        style.map("TButton", background=[("active", "#24314f")])
        style.configure("TCheckbutton", background=PANEL, foreground=TEXT, font=("Segoe UI", 9))
        style.map("TCheckbutton", background=[("active", PANEL)], foreground=[("disabled", MUTED)])
        style.configure("TRadiobutton", background=PANEL, foreground=TEXT, font=("Segoe UI", 9))
        style.map("TRadiobutton", background=[("active", PANEL)])
        style.configure("TCombobox", fieldbackground=PANEL_2, background=PANEL_2, foreground=TEXT, arrowcolor=TEXT, borderwidth=0, padding=8)
        style.map("TCombobox", fieldbackground=[("readonly", PANEL_2)], foreground=[("readonly", TEXT)])
        style.configure("Horizontal.TProgressbar", troughcolor=PANEL_2, background=ACCENT, bordercolor=PANEL_2, lightcolor=ACCENT, darkcolor=ACCENT)
        style.configure("TNotebook", background=BG, borderwidth=0)
        style.configure("TNotebook.Tab", background=BG, foreground=MUTED, borderwidth=0, padding=(18, 10), font=("Segoe UI Semibold", 9))
        style.map("TNotebook.Tab", background=[("selected", PANEL)], foreground=[("selected", TEXT)])
        style.configure("Treeview", background=PANEL, fieldbackground=PANEL, foreground=TEXT, rowheight=34, borderwidth=0, font=("Segoe UI", 9))
        style.configure("Treeview.Heading", background=PANEL_2, foreground=TEXT, borderwidth=0, font=("Segoe UI Semibold", 9))
        style.map("Treeview", background=[("selected", "#28375b")])

    def _build_variables(self) -> None:
        source_label = next((k for k, v in SOURCE_LANGUAGES.items() if v == self.settings.source_language), "Auto detect")
        target_label = next((k for k, v in TARGET_LANGUAGES.items() if v == self.settings.target_language), "Hindi")
        self.media_var = tk.StringVar()
        self.source_var = tk.StringVar(value=source_label)
        self.target_var = tk.StringVar(value=target_label)
        self.quality_var = tk.StringVar(value=self.settings.quality)
        self.keep_music_var = tk.BooleanVar(value=self.settings.keep_music)
        self.keep_sfx_var = tk.BooleanVar(value=self.settings.keep_sfx)
        self.reactions_var = tk.BooleanVar(value=self.settings.preserve_reactions)
        self.voice_volume_var = tk.DoubleVar(value=self.settings.voice_volume)
        self.music_volume_var = tk.DoubleVar(value=self.settings.music_volume)
        self.sfx_volume_var = tk.DoubleVar(value=self.settings.sfx_volume)
        self.original_volume_var = tk.DoubleVar(value=self.settings.original_dialogue_volume)
        self.master_volume_var = tk.DoubleVar(value=self.settings.master_volume)
        packaged_repository = load_update_config().get("repository", "")
        self.github_repo_var = tk.StringVar(value=self.settings.github_repository or packaged_repository)
        self.stage_var = tk.StringVar(value="Ready")
        self.detail_var = tk.StringVar(value="Choose a video or audio file to begin")
        self.progress_var = tk.DoubleVar(value=0.0)

    def _build_ui(self) -> None:
        shell = ttk.Frame(self, padding=(28, 20, 28, 24))
        shell.pack(fill="both", expand=True)

        header = ttk.Frame(shell)
        header.pack(fill="x", pady=(0, 14))
        title_group = ttk.Frame(header)
        title_group.pack(side="left")
        ttk.Label(title_group, text="Alvi Studio", style="Title.TLabel").pack(anchor="w")
        ttk.Label(
            title_group,
            text="Private, local dubbing with accurate timing and emotional Hindi voices",
            style="Subtitle.TLabel",
        ).pack(anchor="w", pady=(2, 0))
        badge = tk.Label(
            header,
            text="LOCAL • NO CLOUD",
            bg="#173d3b",
            fg=SUCCESS,
            font=("Segoe UI Semibold", 9),
            padx=12,
            pady=7,
        )
        badge.pack(side="right", pady=6)

        notebook = ttk.Notebook(shell)
        notebook.pack(fill="both", expand=True)
        self.dub_tab = ttk.Frame(notebook, style="Panel.TFrame", padding=22)
        self.models_tab = ttk.Frame(notebook, style="Panel.TFrame", padding=22)
        self.projects_tab = ttk.Frame(notebook, style="Panel.TFrame", padding=22)
        notebook.add(self.dub_tab, text="New dub")
        notebook.add(self.models_tab, text="Storage & models")
        notebook.add(self.projects_tab, text="Projects")
        self.notebook = notebook

        self._build_dub_tab()
        self._build_models_tab()
        self._build_projects_tab()

    def _build_dub_tab(self) -> None:
        self.dub_tab.columnconfigure(0, weight=3)
        self.dub_tab.columnconfigure(1, weight=2)
        self.dub_tab.rowconfigure(0, weight=1)

        left = ttk.Frame(self.dub_tab, style="Panel.TFrame", padding=(0, 0, 22, 0))
        right = ttk.Frame(self.dub_tab, style="Subtle.TFrame", padding=20)
        left.grid(row=0, column=0, sticky="nsew")
        right.grid(row=0, column=1, sticky="nsew")

        ttk.Label(left, text="1. Choose your media", style="Section.Panel.TLabel").pack(anchor="w")
        media_row = ttk.Frame(left, style="Subtle.TFrame", padding=14)
        media_row.pack(fill="x", pady=(9, 20))
        media_row.columnconfigure(0, weight=1)
        media_entry = tk.Entry(
            media_row,
            textvariable=self.media_var,
            relief="flat",
            bg=PANEL_2,
            fg=TEXT,
            insertbackground=TEXT,
            font=("Segoe UI", 9),
        )
        media_entry.grid(row=0, column=0, sticky="ew", padx=(0, 10), ipady=7)
        ttk.Button(media_row, text="Browse…", command=self._choose_media).grid(row=0, column=1)

        ttk.Label(left, text="2. Languages", style="Section.Panel.TLabel").pack(anchor="w")
        language_row = ttk.Frame(left, style="Panel.TFrame")
        language_row.pack(fill="x", pady=(9, 20))
        language_row.columnconfigure((0, 1), weight=1)
        source_box = ttk.Frame(language_row, style="Subtle.TFrame", padding=12)
        target_box = ttk.Frame(language_row, style="Subtle.TFrame", padding=12)
        source_box.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        target_box.grid(row=0, column=1, sticky="ew", padx=(8, 0))
        ttk.Label(source_box, text="FROM", style="Muted.Panel.TLabel").pack(anchor="w")
        ttk.Combobox(source_box, textvariable=self.source_var, values=list(SOURCE_LANGUAGES), state="readonly").pack(fill="x", pady=(6, 0))
        ttk.Label(target_box, text="TO", style="Muted.Panel.TLabel").pack(anchor="w")
        ttk.Combobox(target_box, textvariable=self.target_var, values=list(TARGET_LANGUAGES), state="readonly").pack(fill="x", pady=(6, 0))

        ttk.Label(left, text="3. Quality", style="Section.Panel.TLabel").pack(anchor="w")
        quality_row = ttk.Frame(left, style="Subtle.TFrame", padding=12)
        quality_row.pack(fill="x", pady=(9, 20))
        for name in QUALITY_PRESETS:
            ttk.Radiobutton(
                quality_row,
                text=name,
                value=name,
                variable=self.quality_var,
                command=self._on_quality_change,
            ).pack(side="left", expand=True)

        ttk.Label(left, text="4. Keep from original", style="Section.Panel.TLabel").pack(anchor="w")
        keep_row = ttk.Frame(left, style="Subtle.TFrame", padding=12)
        keep_row.pack(fill="x", pady=(9, 20))
        ttk.Checkbutton(keep_row, text="Music", variable=self.keep_music_var).pack(side="left", padx=(0, 18))
        ttk.Checkbutton(keep_row, text="SFX & ambience", variable=self.keep_sfx_var).pack(side="left", padx=(0, 18))
        ttk.Checkbutton(keep_row, text="Laughter, crying & reactions", variable=self.reactions_var).pack(side="left")

        ttk.Label(right, text="Mix", style="Section.Panel.TLabel").pack(anchor="w")
        ttk.Label(
            right,
            text="Adjust each stem before rendering. Original dialogue is muted by default.",
            style="Muted.Panel.TLabel",
            wraplength=320,
            justify="left",
        ).pack(anchor="w", pady=(4, 12))
        self._add_slider(right, "Hindi voice", self.voice_volume_var)
        self._add_slider(right, "Music", self.music_volume_var)
        self._add_slider(right, "Sound effects", self.sfx_volume_var)
        self._add_slider(right, "Original dialogue", self.original_volume_var)
        self._add_slider(right, "Master", self.master_volume_var)

        divider = tk.Frame(right, bg="#2a3552", height=1)
        divider.pack(fill="x", pady=(13, 14))
        ttk.Label(right, text="Processing", style="Section.Panel.TLabel").pack(anchor="w")
        ttk.Label(right, textvariable=self.stage_var, style="Panel.TLabel").pack(anchor="w", pady=(7, 0))
        ttk.Label(
            right,
            textvariable=self.detail_var,
            style="Muted.Panel.TLabel",
            wraplength=320,
            justify="left",
        ).pack(anchor="w", pady=(2, 8))
        ttk.Progressbar(right, variable=self.progress_var, maximum=1.0).pack(fill="x", pady=(0, 14), ipady=3)
        self.start_button = ttk.Button(right, text="Start Studio Dub", style="Accent.TButton", command=self._start_dub)
        self.start_button.pack(fill="x", side="bottom")

    def _add_slider(self, parent: ttk.Frame, label: str, variable: tk.DoubleVar) -> None:
        row = ttk.Frame(parent, style="Subtle.TFrame")
        row.pack(fill="x", pady=5)
        ttk.Label(row, text=label, style="Panel.TLabel").pack(side="left")
        value_label = ttk.Label(row, text=f"{round(variable.get() * 100)}%", style="Muted.Panel.TLabel")
        value_label.pack(side="right")
        scale = ttk.Scale(
            parent,
            from_=0.0,
            to=1.5,
            variable=variable,
            command=lambda value, target=value_label: target.configure(text=f"{round(float(value) * 100)}%"),
        )
        scale.pack(fill="x", pady=(0, 4))

    def _build_models_tab(self) -> None:
        storage = ttk.Frame(self.models_tab, style="Subtle.TFrame", padding=18)
        storage.pack(fill="x")
        ttk.Label(storage, text="Selected-drive storage", style="Section.Panel.TLabel").pack(anchor="w")
        path_label = tk.Label(
            storage,
            text=str(self.layout.root),
            bg=PANEL_2,
            fg=SUCCESS,
            font=("Cascadia Mono", 10),
            anchor="w",
            padx=0,
            pady=7,
        )
        path_label.pack(fill="x")
        ttk.Label(
            storage,
            text="Models, caches, temporary audio, projects, exports, logs and updates are locked to this folder.",
            style="Muted.Panel.TLabel",
        ).pack(anchor="w")
        button_row = ttk.Frame(storage, style="Subtle.TFrame")
        button_row.pack(fill="x", pady=(10, 0))
        ttk.Button(button_row, text="Open folder", command=lambda: self._open_folder(self.layout.root)).pack(side="left")
        ttk.Button(button_row, text="Run storage audit", command=self._run_storage_audit).pack(side="left", padx=8)

        updates = ttk.Frame(self.models_tab, style="Subtle.TFrame", padding=18)
        updates.pack(fill="x", pady=(14, 0))
        ttk.Label(updates, text="GitHub automatic updates", style="Section.Panel.TLabel").pack(anchor="w")
        ttk.Label(
            updates,
            text="Use owner/repository format. App updates preserve all models and projects.",
            style="Muted.Panel.TLabel",
        ).pack(anchor="w", pady=(3, 8))
        update_row = ttk.Frame(updates, style="Subtle.TFrame")
        update_row.pack(fill="x")
        repo_entry = tk.Entry(
            update_row,
            textvariable=self.github_repo_var,
            relief="flat",
            bg=PANEL,
            fg=TEXT,
            insertbackground=TEXT,
            font=("Cascadia Mono", 9),
        )
        repo_entry.pack(side="left", fill="x", expand=True, ipady=8, padx=(0, 8))
        ttk.Button(update_row, text="Save", command=self._save_update_repository).pack(side="left")
        ttk.Button(update_row, text="Check now", command=self._check_updates).pack(side="left", padx=(8, 0))

        packs = ttk.Frame(self.models_tab, style="Panel.TFrame")
        packs.pack(fill="both", expand=True, pady=(14, 0))
        ttk.Label(packs, text="Components for selected quality", style="Section.Panel.TLabel").pack(anchor="w")
        self.component_tree = ttk.Treeview(packs, columns=("status", "location", "detail"), show="headings")
        self.component_tree.heading("status", text="Status")
        self.component_tree.heading("location", text="Location")
        self.component_tree.heading("detail", text="Details")
        self.component_tree.column("status", width=95, anchor="center")
        self.component_tree.column("location", width=430)
        self.component_tree.column("detail", width=280)
        self.component_tree.pack(fill="both", expand=True, pady=(9, 10))
        actions = ttk.Frame(packs, style="Panel.TFrame")
        actions.pack(fill="x")
        ttk.Button(actions, text="Refresh", command=self._refresh_components).pack(side="left")
        self.install_button = ttk.Button(actions, text="Install selected model pack", style="Accent.TButton", command=self._install_pack)
        self.install_button.pack(side="right")

    def _build_projects_tab(self) -> None:
        ttk.Label(self.projects_tab, text="Recent projects", style="Section.Panel.TLabel").pack(anchor="w")
        self.projects_tree = ttk.Treeview(
            self.projects_tab,
            columns=("title", "language", "quality", "status", "progress"),
            show="headings",
        )
        for column, title, width in (
            ("title", "Project", 330),
            ("language", "Languages", 160),
            ("quality", "Quality", 110),
            ("status", "Status", 120),
            ("progress", "Progress", 100),
        ):
            self.projects_tree.heading(column, text=title)
            self.projects_tree.column(column, width=width)
        self.projects_tree.pack(fill="both", expand=True, pady=(10, 12))
        row = ttk.Frame(self.projects_tab, style="Panel.TFrame")
        row.pack(fill="x")
        ttk.Button(row, text="Refresh", command=self._load_recent_projects).pack(side="left")
        ttk.Button(row, text="Open projects folder", command=lambda: self._open_folder(self.layout.projects)).pack(side="right")

    def _choose_media(self) -> None:
        path = filedialog.askopenfilename(
            title="Choose video or audio",
            filetypes=[
                ("Video and audio", "*.mp4 *.mkv *.mov *.avi *.webm *.mp3 *.wav *.m4a *.flac"),
                ("All files", "*.*"),
            ],
        )
        if path:
            self.media_var.set(path)
            self.detail_var.set(Path(path).name)

    def _on_quality_change(self) -> None:
        self._refresh_components()

    def _collect_settings(self) -> AppSettings:
        return AppSettings(
            source_language=SOURCE_LANGUAGES[self.source_var.get()],
            target_language=TARGET_LANGUAGES[self.target_var.get()],
            quality=self.quality_var.get(),
            keep_music=self.keep_music_var.get(),
            keep_sfx=self.keep_sfx_var.get(),
            preserve_reactions=self.reactions_var.get(),
            voice_volume=self.voice_volume_var.get(),
            music_volume=self.music_volume_var.get(),
            sfx_volume=self.sfx_volume_var.get(),
            original_dialogue_volume=self.original_volume_var.get(),
            master_volume=self.master_volume_var.get(),
            output_directory=str(self.layout.exports),
            github_repository=self.settings.github_repository,
            update_channel=self.settings.update_channel,
        )

    def _start_dub(self) -> None:
        if self.active_thread and self.active_thread.is_alive():
            return
        media = Path(self.media_var.get().strip())
        if not media.is_file():
            messagebox.showwarning(APP_NAME, "Choose a valid video or audio file first.")
            return
        self.settings = self._collect_settings()
        try:
            self.settings_store.save(self.settings)
        except StorageViolation as exc:
            messagebox.showerror("Storage policy blocked the job", str(exc))
            return
        project = DubProject.new(
            source_media=media,
            source_language=self.settings.source_language,
            target_language=self.settings.target_language,
            quality=self.settings.quality,
            keep_music=self.settings.keep_music,
            keep_sfx=self.settings.keep_sfx,
            preserve_reactions=self.settings.preserve_reactions,
            volumes={
                "voice": self.settings.voice_volume,
                "music": self.settings.music_volume,
                "sfx": self.settings.sfx_volume,
                "original_dialogue": self.settings.original_dialogue_volume,
                "master": self.settings.master_volume,
            },
        )
        self.progress_var.set(0.0)
        self.start_button.configure(state="disabled")
        self.active_thread = threading.Thread(target=self._run_project, args=(project,), daemon=True)
        self.active_thread.start()

    def _run_project(self, project: DubProject) -> None:
        try:
            result = self.pipeline.run(
                project,
                lambda stage, value, detail: self.events.put(("progress", (stage, value, detail))),
            )
            self.events.put(("complete", result))
        except MissingComponentError as exc:
            self.events.put(("missing", str(exc)))
        except Exception as exc:
            self.events.put(("error", str(exc)))

    def _drain_events(self) -> None:
        try:
            while True:
                event, payload = self.events.get_nowait()
                if event == "progress":
                    stage, value, detail = payload  # type: ignore[misc]
                    self.stage_var.set(str(stage))
                    self.progress_var.set(float(value))
                    self.detail_var.set(str(detail))
                elif event == "complete":
                    self.start_button.configure(state="normal")
                    self._load_recent_projects()
                    messagebox.showinfo(APP_NAME, "Dub completed and saved to the selected drive.")
                elif event == "missing":
                    self.start_button.configure(state="normal")
                    self.notebook.select(self.models_tab)
                    self._refresh_components()
                    messagebox.showwarning("Models are not ready", str(payload))
                elif event == "error":
                    self.start_button.configure(state="normal")
                    messagebox.showerror("Dubbing failed", str(payload))
                elif event == "install-complete":
                    self.install_button.configure(state="normal")
                    self.stage_var.set("Models ready")
                    self.detail_var.set(f"{str(payload).title()} model pack installed on the selected drive")
                    self._refresh_components()
                    messagebox.showinfo(APP_NAME, "Model pack installed successfully.")
                elif event == "install-error":
                    self.install_button.configure(state="normal")
                    self._refresh_components()
                    messagebox.showerror("Model installation failed", str(payload))
                elif event == "update-available":
                    updater, update = payload  # type: ignore[misc]
                    if messagebox.askyesno(
                        "Alvi Studio update available",
                        f"Version {update.version} is available. Download and install it now?\n\n{update.notes[:600]}",
                    ):
                        threading.Thread(target=self._download_update, args=(updater, update), daemon=True).start()
                elif event == "update-none":
                    if payload:
                        messagebox.showinfo("Alvi Studio updates", "You already have the latest version.")
                elif event == "update-ready":
                    updater, installer = payload  # type: ignore[misc]
                    updater.install_on_exit(installer)
                    self.destroy()
                elif event == "update-error":
                    if payload:
                        messagebox.showerror("Update failed", str(payload))
        except queue.Empty:
            pass
        self.after(100, self._drain_events)

    def _refresh_components(self) -> None:
        if not hasattr(self, "component_tree"):
            return
        self.component_tree.delete(*self.component_tree.get_children())
        for item in self.components.status(self.quality_var.get()):
            self.component_tree.insert(
                "",
                "end",
                values=("Ready" if item.ready else "Required", str(item.location), item.detail),
            )

    def _install_pack(self) -> None:
        quality = self.quality_var.get().lower()
        pack = MODEL_PACKS[quality]
        if self.active_thread and self.active_thread.is_alive():
            messagebox.showwarning(APP_NAME, "Wait for the current operation to finish.")
            return
        python = self.components.engine_python()
        if not python:
            messagebox.showerror(
                "Runtime is missing",
                "Reinstall Alvi Studio and choose the desired drive. The installer must include the private runtime.",
            )
            return
        free_gb = __import__("shutil").disk_usage(self.layout.root).free / (1024**3)
        if not messagebox.askyesno(
            "Install model pack",
            f"Install {pack['name']} to:\n{self.layout.root}\n\n"
            f"Estimated model space: {pack['approx_gb']} GB\n"
            f"Free space on this drive: {free_gb:.1f} GB\n\n"
            "No model, cache or temporary download will be placed in your user profile.",
        ):
            return
        token = ""
        if quality in {"balanced", "studio"}:
            token = simpledialog.askstring(
                "Hugging Face access token",
                "Indic Parler and pyannote require a Hugging Face token after accepting their model terms.\n"
                "The token is used for this download only and is not saved.",
                show="•",
            ) or ""
        self.install_button.configure(state="disabled")
        self.progress_var.set(0.0)
        self.stage_var.set("Installing models")
        self.detail_var.set(f"Everything is being written to {self.layout.root}")
        self.active_thread = threading.Thread(
            target=self._install_pack_worker,
            args=(python, quality, token),
            daemon=True,
        )
        self.active_thread.start()

    def _install_pack_worker(self, python: Path, quality: str, token: str) -> None:
        command = [
            str(python),
            "-m",
            "dubstudio.model_installer",
            "--root",
            str(self.layout.root),
            "--pack",
            quality,
        ]
        environment = dict(os.environ)
        if token:
            environment["HF_TOKEN"] = token
        process = subprocess.Popen(
            command,
            cwd=str(self.layout.root),
            env=environment,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        assert process.stdout is not None
        error = ""
        current_progress = 0.0
        for line in process.stdout:
            line = line.strip()
            if not line:
                continue
            try:
                event = __import__("json").loads(line)
                if event.get("error"):
                    error = str(event["error"])
                else:
                    current_progress = float(event.get("progress", current_progress))
                    self.events.put(
                        (
                            "progress",
                            ("Installing models", current_progress, str(event.get("message", ""))),
                        )
                    )
            except ValueError:
                self.events.put(("progress", ("Installing models", current_progress, line[-180:])))
        code = process.wait()
        if code:
            self.events.put(("install-error", error or f"Model installer stopped with exit code {code}"))
        else:
            self.events.put(("install-complete", quality))

    def _run_storage_audit(self) -> None:
        try:
            paths = self.layout.audit()
            messagebox.showinfo(
                "Storage audit passed",
                f"Checked {len(paths)} managed paths. Every path is inside:\n{self.layout.root}",
            )
        except StorageViolation as exc:
            messagebox.showerror("Storage audit failed", str(exc))

    def _save_update_repository(self) -> None:
        repository = self.github_repo_var.get().strip().strip("/")
        if repository and repository.count("/") != 1:
            messagebox.showwarning("GitHub repository", "Use owner/repository format.")
            return
        self.settings = self._collect_settings()
        self.settings.github_repository = repository
        self.settings_store.save(self.settings)
        messagebox.showinfo("GitHub updates", "Update repository saved.")

    def _check_updates(self, silent: bool = False) -> None:
        repository = self.github_repo_var.get().strip() or self.settings.github_repository
        if not repository:
            if not silent:
                messagebox.showwarning("GitHub updates", "Enter and save your owner/repository first.")
            return
        config = load_update_config()
        updater = GitHubUpdater(self.layout, repository, config.get("expected_publisher", ""))

        def check() -> None:
            try:
                update = updater.check()
                if update:
                    self.events.put(("update-available", (updater, update)))
                else:
                    self.events.put(("update-none", not silent))
            except Exception as exc:
                self.events.put(("update-error", "" if silent else str(exc)))

        threading.Thread(target=check, daemon=True).start()

    def _download_update(self, updater: GitHubUpdater, update: UpdateInfo) -> None:
        try:
            self.events.put(("progress", ("Downloading update", 0.2, f"Version {update.version}")))
            installer = updater.download(update)
            self.events.put(("update-ready", (updater, installer)))
        except Exception as exc:
            self.events.put(("update-error", str(exc)))

    def _load_recent_projects(self) -> None:
        if not hasattr(self, "projects_tree"):
            return
        self.projects_tree.delete(*self.projects_tree.get_children())
        for project in self.project_store.recent(50):
            self.projects_tree.insert(
                "",
                "end",
                values=(
                    project.title,
                    f"{project.source_language} → {project.target_language}",
                    project.quality,
                    project.status.title(),
                    f"{round(project.progress * 100)}%",
                ),
            )

    def _open_folder(self, path: Path) -> None:
        try:
            os.startfile(str(path))  # type: ignore[attr-defined]
        except OSError as exc:
            messagebox.showerror(APP_NAME, str(exc))

    def _on_close(self) -> None:
        if self.active_thread and self.active_thread.is_alive():
            if not messagebox.askyesno(APP_NAME, "A job is still running. Close the window anyway?"):
                return
        self.destroy()


def main() -> None:
    try:
        layout = StorageLayout.create()
    except Exception as exc:
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror("Alvi Studio could not start", str(exc))
        raise SystemExit(1) from exc
    app = AlviStudioApp(layout)
    app.mainloop()


if __name__ == "__main__":
    main()
