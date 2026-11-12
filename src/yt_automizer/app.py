"""Desktop app: connect the channel, check status, and update from GitHub Releases."""

from __future__ import annotations

import os
import queue
import subprocess
import sys
import threading
import time
import tkinter as tk
import webbrowser
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from . import __version__, config, setup_wizard as sw, updater

GREEN, RED, GREY, ACCENT = "#1e8e3e", "#d93025", "#80868b", "#c4302b"


class App:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.jobs: queue.Queue = queue.Queue()
        self.update_info: updater.UpdateInfo | None = None
        root.title("YouTube AI-utomizer")
        root.geometry("620x560")
        root.minsize(560, 520)
        self._style()
        self._build()
        root.after(100, self._pump)
        self.refresh()
        self.check_updates(silent=True)

    # ------------------------------------------------------------- plumbing
    def _style(self) -> None:
        style = ttk.Style(self.root)
        if "vista" in style.theme_names():
            style.theme_use("vista")
        elif "clam" in style.theme_names():
            style.theme_use("clam")
        style.configure("Title.TLabel", font=("Segoe UI", 18, "bold"))
        style.configure("Sub.TLabel", foreground=GREY)
        style.configure("Row.TLabel", font=("Segoe UI", 11, "bold"))
        style.configure("Big.TButton", font=("Segoe UI", 11, "bold"), padding=(16, 8))

    def bg(self, fn, done=None, fail=None) -> None:
        """Run ``fn`` in a thread; call ``done(result)`` or ``fail(exc)`` back on the UI thread."""
        def worker():
            try:
                self.jobs.put((done, fn()))
            except Exception as exc:  # noqa: BLE001 - shown to the user
                self.jobs.put((fail or self._error, exc))
        threading.Thread(target=worker, daemon=True).start()

    def _pump(self) -> None:
        while not self.jobs.empty():
            cb, value = self.jobs.get()
            if cb:
                cb(value)
        self.root.after(100, self._pump)

    def _error(self, exc: Exception) -> None:
        messagebox.showerror("Algo ha fallado", str(exc), parent=self.root)

    # ----------------------------------------------------------------- layout
    def _build(self) -> None:
        outer = ttk.Frame(self.root, padding=20)
        outer.pack(fill="both", expand=True)

        head = ttk.Frame(outer)
        head.pack(fill="x")
        ttk.Label(head, text="YouTube AI-utomizer", style="Title.TLabel").pack(anchor="w")
        ttk.Label(head, text="Conecta Claude Code con tu canal de YouTube", style="Sub.TLabel").pack(anchor="w")

        box = ttk.LabelFrame(outer, text=" Estado ", padding=12)
        box.pack(fill="x", pady=(16, 10))
        self.rows = {}
        for key, name in [("google", "Clave de Google"), ("channel", "Canal de YouTube"), ("claude", "Claude Code")]:
            self.rows[key] = self._row(box, name)

        self.main_btn = ttk.Button(outer, text="Configurar todo", style="Big.TButton", command=self.setup_all)
        self.main_btn.pack(fill="x", pady=(6, 4))
        self.hint = ttk.Label(outer, text="", style="Sub.TLabel", wraplength=560, justify="left")
        self.hint.pack(fill="x", pady=(2, 10))

        shortcuts = ttk.LabelFrame(outer, text=" Atajos ", padding=10)
        shortcuts.pack(fill="x")
        for text, cmd in [("YouTube Studio", lambda: webbrowser.open("https://studio.youtube.com")),
                          ("Carpeta de datos", lambda: open_folder(config.home_dir())),
                          ("Comprobar de nuevo", self.refresh)]:
            ttk.Button(shortcuts, text=text, command=cmd).pack(side="left", padx=(0, 8))

        foot = ttk.Frame(outer)
        foot.pack(fill="x", side="bottom")
        ttk.Separator(outer).pack(fill="x", side="bottom", pady=8)
        ttk.Label(foot, text=f"Versión {__version__}", style="Sub.TLabel").pack(side="left")
        self.update_btn = ttk.Button(foot, text="Buscar actualizaciones", command=self.check_updates)
        self.update_btn.pack(side="right")
        self.update_lbl = ttk.Label(foot, text="", style="Sub.TLabel")
        self.update_lbl.pack(side="right", padx=8)

    def _row(self, parent, name: str) -> dict:
        f = ttk.Frame(parent)
        f.pack(fill="x", pady=4)
        dot = tk.Label(f, text="●", fg=GREY, font=("Segoe UI", 14))
        dot.pack(side="left")
        txt = ttk.Frame(f)
        txt.pack(side="left", fill="x", expand=True, padx=8)
        ttk.Label(txt, text=name, style="Row.TLabel").pack(anchor="w")
        detail = ttk.Label(txt, text="Comprobando…", style="Sub.TLabel")
        detail.pack(anchor="w")
        btn = ttk.Button(f, text="")
        return {"dot": dot, "detail": detail, "btn": btn}

    def _set(self, key: str, ok: bool | None, detail: str, action: str | None = None, cmd=None) -> None:
        r = self.rows[key]
        r["dot"].config(fg=GREY if ok is None else GREEN if ok else RED)
        r["detail"].config(text=detail)
        if action:
            r["btn"].config(text=action, command=cmd)
            r["btn"].pack(side="right")
        else:
            r["btn"].pack_forget()

    # ------------------------------------------------------------------ status
    def refresh(self) -> None:
        for key in self.rows:
            self._set(key, None, "Comprobando…")
        self.bg(self._collect_status, self._show_status)

    @staticmethod
    def _collect_status() -> dict:
        st = {"google": sw.has_secret(), "channel": None, "channel_error": None, "claude": sw.is_registered(),
              "claude_installed": sw.find_claude() is not None}
        if st["google"] and config.token_path().exists():
            try:
                st["channel"] = sw.channel_info(allow_browser_login=False)
            except Exception as exc:  # noqa: BLE001
                st["channel_error"] = str(exc)
        return st

    def _show_status(self, st: dict) -> None:
        self.status = st
        if st["google"]:
            self._set("google", True, "Guardada en este PC", "Cambiar", lambda: self.open_wizard(start=0))
        else:
            self._set("google", False, "Falta crear la clave (5 minutos, solo una vez)", "Configurar",
                      lambda: self.open_wizard(start=0))

        ch = st["channel"]
        if ch:
            self._set("channel", True, f"{ch['title']} · {ch['subscribers']:,} suscriptores".replace(",", "."),
                      "Desconectar", self.disconnect)
        elif not st["google"]:
            self._set("channel", False, "Primero configura la clave de Google")
        else:
            self._set("channel", False, "Sin conectar" if not st["channel_error"] else "La sesión ha caducado",
                      "Conectar", self.connect_channel)

        if st["claude"]:
            self._set("claude", True, "Servidor «youtube» activo en Claude Code", "Volver a conectar", self.connect_claude)
        elif not st["claude_installed"]:
            self._set("claude", False, "Claude Code no está instalado en este PC", "Descargar",
                      lambda: webbrowser.open("https://claude.com/claude-code"))
        else:
            self._set("claude", False, "Sin conectar", "Conectar", self.connect_claude)

        ready = st["google"] and ch and st["claude"]
        if ready:
            self.main_btn.config(text="✓ Todo listo · Abrir guía rápida", command=self.show_quick_guide)
            self.hint.config(text="Abre Claude Code y escribe, por ejemplo: «Haz la revisión semanal de mi canal» "
                                  "o «Encuéntrame un nicho: F1, aerodinámica, coches deportivos».")
        else:
            self.main_btn.config(text="Configurar todo", command=self.setup_all)
            self.hint.config(text="Te guío paso a paso. Solo hay que hacerlo una vez.")

    # ----------------------------------------------------------------- actions
    def setup_all(self) -> None:
        st = getattr(self, "status", None) or {}
        if not st.get("google"):
            self.open_wizard(start=0)
        elif not st.get("channel"):
            self.connect_channel()
        elif not st.get("claude"):
            self.connect_claude()

    def connect_channel(self, then=None) -> None:
        if not messagebox.askokcancel("Conectar tu canal", sw.LOGIN_HINT, parent=self.root):
            return
        self._set("channel", None, "Esperando a que inicies sesión en el navegador…")

        def done(info):
            self.refresh()
            if then:
                then()
            elif not self.status.get("claude"):
                self.connect_claude()
        self.bg(sw.connect_channel, done, lambda e: (self._error(e), self.refresh()))

    def connect_claude(self) -> None:
        def done(res):
            ok, msg = res
            (messagebox.showinfo if ok else messagebox.showwarning)("Claude Code", msg, parent=self.root)
            self.refresh()
        self.bg(sw.register_with_claude_code, done)

    def disconnect(self) -> None:
        if messagebox.askyesno("Desconectar", "¿Desconectar tu canal de este PC? Podrás volver a conectarlo cuando quieras.",
                               parent=self.root):
            sw.disconnect()
            self.refresh()

    def show_quick_guide(self) -> None:
        messagebox.showinfo("Cómo usarlo", (
            "Abre Claude Code y pídele cosas como:\n\n"
            "• «Haz la revisión semanal de mi canal»\n"
            "• «Encuéntrame un nicho: F1, aerodinámica, coches deportivos»\n"
            "• «Sube este vídeo: C:\\Videos\\short1.mp4» (se sube en privado)\n"
            "• «Publica el vídeo que revisé» (solo con tu aprobación)\n\n"
            "Claude respeta las normas de YouTube sobre IA: declara el contenido sintético, "
            "evita vídeos repetidos y nunca publica sin tu permiso."), parent=self.root)

    def open_wizard(self, start: int = 0) -> None:
        Wizard(self, start)

    # ----------------------------------------------------------------- updates
    def check_updates(self, silent: bool = False) -> None:
        self.update_btn.config(state="disabled")
        self.update_lbl.config(text="Buscando…")

        def done(info: updater.UpdateInfo):
            self.update_btn.config(state="normal")
            self.update_info = info
            if info.available:
                self.update_lbl.config(text=f"Nueva versión {info.latest}", foreground=ACCENT)
                self.update_btn.config(text="Actualizar ahora", command=self.ask_update)
                if not silent:
                    self.ask_update()
            else:
                self.update_lbl.config(text="Tienes la última versión", foreground=GREY)
                if not silent:
                    extra = f"\n{info.notes}" if info.notes.startswith("Todavía") else ""
                    messagebox.showinfo("Actualizaciones", f"Tienes la última versión ({info.current}).{extra}",
                                        parent=self.root)

        def fail(exc):
            self.update_btn.config(state="normal")
            self.update_lbl.config(text="Sin conexión con GitHub", foreground=GREY)
            if not silent:
                self._error(RuntimeError(f"No he podido comprobar las actualizaciones: {exc}"))
        self.bg(updater.check, done, fail)

    def ask_update(self) -> None:
        info = self.update_info
        notes = info.notes[:800] or "Sin notas."
        msg = (f"Versión {info.latest} disponible (tienes {info.current}).\n\nNovedades:\n{notes}\n\n"
               "Cierra Claude Code antes de actualizar. ¿Actualizar ahora?")
        if not messagebox.askyesno("Actualización disponible", msg, parent=self.root):
            return
        self.update_btn.config(state="disabled")
        self.update_lbl.config(text="Descargando…")

        def done(result):
            messagebox.showinfo("Actualización", "Actualización lista. La app se reiniciará.", parent=self.root)
            updater.relaunch()
            self.root.destroy()

        def fail(exc):
            self.update_btn.config(state="normal")
            self.update_lbl.config(text="")
            if messagebox.askyesno("No se pudo actualizar", f"{exc}\n\n¿Abrir la página de descargas?", parent=self.root):
                webbrowser.open(info.page_url)
        self.bg(lambda: updater.install(info), done, fail)


class Wizard:
    """Step-by-step Google Cloud setup in its own window."""

    def __init__(self, app: App, start: int = 0):
        self.app = app
        self.i = start
        self.started = time.time()
        self.win = tk.Toplevel(app.root)
        self.win.title("Configurar la clave de Google")
        self.win.geometry("560x340")
        self.win.transient(app.root)
        self.win.grab_set()
        f = ttk.Frame(self.win, padding=20)
        f.pack(fill="both", expand=True)
        self.counter = ttk.Label(f, style="Sub.TLabel")
        self.counter.pack(anchor="w")
        self.title = ttk.Label(f, style="Title.TLabel")
        self.title.pack(anchor="w", pady=(2, 10))
        self.text = ttk.Label(f, wraplength=510, justify="left", font=("Segoe UI", 11))
        self.text.pack(anchor="w", fill="x")
        self.extra = ttk.Label(f, style="Sub.TLabel", wraplength=510, justify="left")
        self.extra.pack(anchor="w", pady=(12, 0))
        btns = ttk.Frame(f)
        btns.pack(fill="x", side="bottom")
        self.back = ttk.Button(btns, text="← Atrás", command=lambda: self.go(-1))
        self.back.pack(side="left")
        self.next = ttk.Button(btns, text="Siguiente →", style="Big.TButton", command=lambda: self.go(1))
        self.next.pack(side="right")
        self.open_btn = ttk.Button(btns, text="Abrir página otra vez", command=self.open_page)
        self.open_btn.pack(side="right", padx=8)
        self.pick = ttk.Button(btns, text="Elegir archivo…", command=self.pick_file)
        self.polling = False
        self.show()

    def show(self) -> None:
        step = sw.GOOGLE_STEPS[self.i]
        n = len(sw.GOOGLE_STEPS)
        self.counter.config(text=f"Paso {self.i + 1} de {n}")
        self.title.config(text=step.title)
        self.text.config(text=step.text)
        self.back.config(state="normal" if self.i else "disabled")
        last = self.i == n - 1
        self.extra.config(text="Buscando el archivo en Descargas…" if last else "")
        if last:
            self.next.pack_forget()
            self.pick.pack(side="right")
            self.polling = True
            self._poll()
        else:
            self.pick.pack_forget()
            self.next.pack(side="right")
            self.polling = False
        self.open_page()

    def open_page(self) -> None:
        webbrowser.open(sw.GOOGLE_STEPS[self.i].url)

    def go(self, delta: int) -> None:
        self.i = max(0, min(self.i + delta, len(sw.GOOGLE_STEPS) - 1))
        self.show()

    def _poll(self) -> None:
        if not self.polling or not self.win.winfo_exists():
            return
        found = sw.find_downloaded_secret(sw.downloads_folders(), self.started - 600)
        if found:
            self.finish(found)
        else:
            self.win.after(2000, self._poll)

    def pick_file(self) -> None:
        path = filedialog.askopenfilename(parent=self.win, title="Elige el archivo client_secret….json",
                                          filetypes=[("Clave de Google", "*.json")])
        if path:
            self.finish(Path(path))

    def finish(self, path: Path) -> None:
        self.polling = False
        try:
            sw.install_secret(path)
        except ValueError as exc:
            self.extra.config(text=str(exc), foreground=RED)
            self.polling = True
            self.win.after(2000, self._poll)
            return
        self.win.destroy()
        self.app.refresh()
        self.app.connect_channel()


def open_folder(path: Path) -> None:
    if os.name == "nt":
        os.startfile(path)  # type: ignore[attr-defined]
    elif sys.platform == "darwin":
        subprocess.Popen(["open", str(path)])
    else:
        subprocess.Popen(["xdg-open", str(path)])


def main() -> None:
    config.save_default_settings()
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
