#!/usr/bin/env python3
"""
Stem Splitter — macOS desktop app for splitting audio into stems using Demucs.

Requirements:
    brew install ffmpeg
    pip install demucs torchcodec
"""

import os
import sys
import shutil
import tempfile
import threading
import subprocess
import time
from pathlib import Path
from typing import Optional

import tkinter as tk
from tkinter import ttk, filedialog, messagebox


STEMS = ["vocals", "drums", "bass", "other"]
OUTPUT_BASE = Path.home() / "stems_output"

QUALITY_PRESETS = {
    "Best  — htdemucs_ft, shifts 10  (slow)":     {"model": "htdemucs_ft", "shifts": 10, "overlap": 0.5},
    "Balanced  — htdemucs_ft, shifts 5  (medium)": {"model": "htdemucs_ft", "shifts": 5,  "overlap": 0.25},
    "Preview  — htdemucs, shifts 1  (fast)":        {"model": "htdemucs",    "shifts": 1,  "overlap": 0.25},
}
DEFAULT_QUALITY = next(iter(QUALITY_PRESETS))  # first entry = Best


class App:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Stem Splitter")
        self.root.resizable(False, False)
        self.file: Optional[Path] = None
        self._build()

    # ── UI ────────────────────────────────────────────────────────────────────

    def _build(self):
        f = ttk.Frame(self.root, padding=20)
        f.grid()

        ttk.Label(f, text="Stem Splitter", font=("Helvetica", 18, "bold")).grid(
            row=0, column=0, columnspan=4, pady=(0, 14)
        )

        # File selection
        file_frame = ttk.LabelFrame(f, text="Audio File", padding=(10, 8))
        file_frame.grid(row=1, column=0, columnspan=4, sticky="ew", pady=(0, 10))

        self.btn_file = ttk.Button(file_frame, text="Choose File…", command=self._pick_file)
        self.btn_file.grid(row=0, column=0, padx=(0, 10))

        self.lbl_file = ttk.Label(file_frame, text="No file selected", foreground="gray", width=44)
        self.lbl_file.grid(row=0, column=1, sticky="w")

        # Stem checkboxes
        stem_frame = ttk.LabelFrame(f, text="Stems to Export", padding=(10, 8))
        stem_frame.grid(row=2, column=0, columnspan=4, sticky="ew", pady=(0, 10))

        self.stem_vars = {s: tk.BooleanVar(value=True) for s in STEMS}
        for col, stem in enumerate(STEMS):
            ttk.Checkbutton(
                stem_frame, text=stem.capitalize(),
                variable=self.stem_vars[stem],
                command=self._sync_all_cb,
            ).grid(row=0, column=col, padx=12)

        self.all_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            stem_frame, text="Select All",
            variable=self.all_var, command=self._toggle_all,
        ).grid(row=1, column=0, columnspan=4, pady=(8, 0))

        # Quality preset
        quality_frame = ttk.LabelFrame(f, text="Quality", padding=(10, 8))
        quality_frame.grid(row=3, column=0, columnspan=4, sticky="ew", pady=(0, 10))

        self.quality_var = tk.StringVar(value=DEFAULT_QUALITY)
        quality_box = ttk.Combobox(
            quality_frame, textvariable=self.quality_var,
            values=list(QUALITY_PRESETS.keys()),
            state="readonly", width=52,
        )
        quality_box.grid(sticky="w")

        # Options
        opt_frame = ttk.LabelFrame(f, text="Options", padding=(10, 8))
        opt_frame.grid(row=4, column=0, columnspan=4, sticky="ew", pady=(0, 10))

        self.del_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            opt_frame, text="Delete temporary Demucs files after export",
            variable=self.del_var,
        ).grid(sticky="w")

        # Run button
        self.btn_run = ttk.Button(f, text="▶  Split Stems", command=self._start)
        self.btn_run.grid(row=5, column=0, columnspan=4, pady=10)

        # Status log
        log_frame = ttk.LabelFrame(f, text="Status", padding=(10, 8))
        log_frame.grid(row=6, column=0, columnspan=4, sticky="ew", pady=(0, 6))

        self.log_box = tk.Text(
            log_frame, height=9, width=60, state="disabled",
            wrap="word", font=("Menlo", 11),
            bg="#1c1c1e", fg="#e5e5ea", relief="flat",
        )
        self.log_box.grid()

        # Elapsed time label
        self.lbl_time = ttk.Label(f, text="", foreground="gray")
        self.lbl_time.grid(row=7, column=0, columnspan=4)

    # ── Checkbox helpers ──────────────────────────────────────────────────────

    def _toggle_all(self):
        val = self.all_var.get()
        for v in self.stem_vars.values():
            v.set(val)

    def _sync_all_cb(self):
        self.all_var.set(all(v.get() for v in self.stem_vars.values()))

    # ── File picker ───────────────────────────────────────────────────────────

    def _pick_file(self):
        p = filedialog.askopenfilename(
            title="Select Audio File",
            filetypes=[("Audio", "*.mp3 *.wav *.flac *.m4a"), ("All", "*.*")],
        )
        if p:
            self.file = Path(p)
            name = self.file.name
            self.lbl_file.config(
                text=(name if len(name) <= 44 else f"…{name[-41:]}"),
                foreground="black",
            )

    # ── Processing ────────────────────────────────────────────────────────────

    def _start(self):
        if not self.file:
            messagebox.showwarning("No File", "Please choose an audio file first.")
            return
        want = [s for s, v in self.stem_vars.items() if v.get()]
        if not want:
            messagebox.showwarning("No Stems", "Select at least one stem to export.")
            return
        self._clear_log()
        self.lbl_time.config(text="")
        self._ui_lock(True)
        preset = QUALITY_PRESETS[self.quality_var.get()]
        threading.Thread(target=self._process, args=(want, preset), daemon=True).start()

    def _process(self, want: list, preset: dict):
        t0 = time.time()
        tmp = Path(tempfile.mkdtemp(prefix="demucs_"))
        out_dir = OUTPUT_BASE / self.file.stem

        try:
            self._log("Checking dependencies…")
            self._assert_deps()

            self._log("Loading file…")

            model = preset["model"]
            shifts = preset["shifts"]
            self._log(f"Separating stems — model: {model}, shifts: {shifts}  (this may take a while)…")
            self._run_demucs(tmp, preset)

            self._log("Filtering selected stems…")
            song_dir = self._find_song_dir(tmp, model)

            self._log("Saving output…")
            out_dir.mkdir(parents=True, exist_ok=True)
            for stem in want:
                src = song_dir / f"{stem}.wav"
                if src.exists():
                    shutil.copy2(src, out_dir / f"{stem}.wav")
                    self._log(f"  ✓  {stem}.wav")
                else:
                    self._log(f"  ⚠  {stem}.wav not found in Demucs output")

            if self.del_var.get():
                shutil.rmtree(tmp, ignore_errors=True)
                self._log("Temporary files removed.")

            elapsed = time.time() - t0
            self._log(f"\nDone.  Saved to:\n  {out_dir}")
            self.root.after(0, lambda: self.lbl_time.config(text=f"Completed in {elapsed:.1f}s"))
            subprocess.run(["open", str(out_dir)])

        except EnvironmentError as e:
            self._log(f"\n⛔  {e}")
        except FileNotFoundError as e:
            self._log(f"\n⛔  Output not found: {e}")
        except subprocess.CalledProcessError:
            self._log("\n⛔  Demucs failed. See output above for details.")
        except Exception as e:
            self._log(f"\n⛔  Unexpected error: {e}")
        finally:
            self.root.after(0, lambda: self._ui_lock(False))

    def _subprocess_env(self):
        env = os.environ.copy()
        env["PATH"] = "/opt/homebrew/bin:/usr/local/bin:" + env.get("PATH", "")
        try:
            import certifi
            ca = certifi.where()
            env.setdefault("SSL_CERT_FILE", ca)
            env.setdefault("REQUESTS_CA_BUNDLE", ca)
        except ImportError:
            pass
        return env

    def _assert_deps(self):
        env = self._subprocess_env()
        r = subprocess.run([sys.executable, "-m", "demucs", "--help"], capture_output=True, env=env)
        if r.returncode != 0:
            raise EnvironmentError("Demucs not installed.\n  Fix: pip install demucs")
        r = subprocess.run(["ffmpeg", "-version"], capture_output=True, env=env)
        if r.returncode != 0:
            raise EnvironmentError("ffmpeg not installed.\n  Fix: brew install ffmpeg")

    def _run_demucs(self, tmp: Path, preset: dict):
        cmd = [
            sys.executable, "-m", "demucs",
            "--name",    preset["model"],
            "--shifts",  str(preset["shifts"]),
            "--overlap", str(preset["overlap"]),
            "--out",     str(tmp),
            str(self.file),
        ]
        proc = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, env=self._subprocess_env(),
        )
        all_lines = []
        for line in proc.stdout:
            line = line.strip()
            if not line:
                continue
            all_lines.append(line)
            if any(k in line for k in ("%|", "Separating", "Downloading", "segment", "Model")):
                self._log(f"  {line}")
        proc.wait()
        if proc.returncode != 0:
            self._log("\n  Demucs output:")
            for line in all_lines:
                self._log(f"    {line}")
            raise subprocess.CalledProcessError(proc.returncode, cmd)

    def _find_song_dir(self, tmp: Path, model: str) -> Path:
        """Find the song output folder — searches by model name then falls back to any folder."""
        for search_dir in [tmp / model, tmp]:
            if not search_dir.exists():
                continue
            dirs = [d for d in search_dir.iterdir() if d.is_dir()]
            if dirs:
                return max(dirs, key=lambda d: d.stat().st_mtime)
        raise FileNotFoundError(f"No Demucs output found in {tmp}")

    # ── UI helpers ────────────────────────────────────────────────────────────

    def _log(self, msg: str):
        self.root.after(0, lambda m=msg: self._append_log(m))

    def _append_log(self, msg: str):
        self.log_box.config(state="normal")
        self.log_box.insert("end", msg + "\n")
        self.log_box.see("end")
        self.log_box.config(state="disabled")

    def _clear_log(self):
        self.log_box.config(state="normal")
        self.log_box.delete("1.0", "end")
        self.log_box.config(state="disabled")

    def _ui_lock(self, locked: bool):
        state = "disabled" if locked else "normal"
        self.btn_file.config(state=state)
        self.btn_run.config(state=state)


def main():
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
