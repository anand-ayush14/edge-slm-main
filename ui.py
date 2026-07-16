#!/usr/bin/env python3
"""
Edge SLM RAG Pipeline - Tkinter UI
Provides a graphical interface to run the full Edge SLM RAG pipeline.
"""

import tkinter as tk
from tkinter import ttk, filedialog, scrolledtext, messagebox
import subprocess
import threading
import os
import sys
from pathlib import Path

# ── Project paths ─────────────────────────────────────────────────────────────
BASE_DIR        = Path(__file__).parent
MODELS_DIR      = BASE_DIR / "models"
RAG_DIR         = BASE_DIR / "rag"
SPLITTER_DIR    = BASE_DIR / "scripts" / "rag-document-splitter"
RAG_DEMO_BIN    = RAG_DIR / "build" / "Release" / "apps" / "rag_demo" / "rag_demo"
PROMPT_TEMPLATE = RAG_DIR / "assets" / "prompt_templates" / "qwen2.5.mustache"
MODEL_CONFIG    = MODELS_DIR / "model_config.json"

# ── Colour palette ────────────────────────────────────────────────────────────
BG        = "#0d1117"
PANEL     = "#161b22"
BORDER    = "#30363d"
ACCENT    = "#238636"
ACCENT2   = "#1f6feb"
ACCENT_H  = "#2ea043"
TEXT      = "#e6edf3"
TEXT_DIM  = "#8b949e"
RED       = "#da3633"
YELLOW    = "#d29922"
FONT_MONO = ("Menlo", 11)
FONT_UI   = ("SF Pro Display", 11) if sys.platform == "darwin" else ("Segoe UI", 11)
FONT_H    = ("SF Pro Display", 13, "bold") if sys.platform == "darwin" else ("Segoe UI", 13, "bold")


# ═════════════════════════════════════════════════════════════════════════════
class EdgeSLMApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Edge SLM · RAG Pipeline")
        self.configure(bg=BG)
        self.geometry("1100x780")
        self.minsize(900, 640)

        # Process handles
        self._proc: subprocess.Popen | None = None
        self._chat_proc: subprocess.Popen | None = None
        self._running = False

        # Tkinter vars
        self.knowledge_file   = tk.StringVar(value=str(MODELS_DIR / "sample_knowledge.txt"))
        self.chunks_file      = tk.StringVar(value=str(MODELS_DIR / "document_chunks.json"))
        self.embedded_file    = tk.StringVar(value=str(MODELS_DIR / "embedded_chunks.json"))
        self.embed_model_file = tk.StringVar(value=str(MODELS_DIR / "nomic-embed-text-v1.f32.gguf"))
        self.llm_model_file   = tk.StringVar(value=str(MODELS_DIR / "qwen2.5-1.5b-instruct-q4_k_m.gguf"))
        self.model_config     = tk.StringVar(value=str(MODEL_CONFIG))
        self.prompt_template  = tk.StringVar(value=str(PROMPT_TEMPLATE))
        self.chunk_size       = tk.IntVar(value=512)
        self.chunk_overlap    = tk.IntVar(value=0)
        self.top_k            = tk.IntVar(value=3)
        self.embed_threads    = tk.IntVar(value=4)
        self.status_text      = tk.StringVar(value="Ready")

        self._build_ui()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ── UI BUILD ──────────────────────────────────────────────────────────────

    def _build_ui(self):
        # Header
        hdr = tk.Frame(self, bg=PANEL, height=56)
        hdr.pack(fill="x")
        hdr.pack_propagate(False)
        tk.Label(hdr, text="⚡ Edge SLM",
                 font=("SF Pro Display", 16, "bold") if sys.platform == "darwin" else ("Segoe UI", 16, "bold"),
                 bg=PANEL, fg=TEXT).pack(side="left", padx=20, pady=14)
        tk.Label(hdr, text="RAG Pipeline · Local Inference",
                 font=FONT_UI, bg=PANEL, fg=TEXT_DIM).pack(side="left", pady=14)
        self._status_lbl = tk.Label(hdr, textvariable=self.status_text,
                                    font=FONT_UI, bg=ACCENT, fg="white",
                                    padx=12, pady=4, relief="flat")
        self._status_lbl.pack(side="right", padx=20, pady=14)

        tk.Frame(self, bg=BORDER, height=1).pack(fill="x")

        body = tk.Frame(self, bg=BG)
        body.pack(fill="both", expand=True)

        # Left control panel
        left = tk.Frame(body, bg=PANEL, width=400)
        left.pack(side="left", fill="y")
        left.pack_propagate(False)
        canvas = tk.Canvas(left, bg=PANEL, highlightthickness=0)
        scrollbar = ttk.Scrollbar(left, orient="vertical", command=canvas.yview)
        self._ctrl_frame = tk.Frame(canvas, bg=PANEL)
        self._ctrl_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=self._ctrl_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)
        self._build_controls(self._ctrl_frame)

        tk.Frame(body, bg=BORDER, width=1).pack(side="left", fill="y")

        # Right notebook
        right = tk.Frame(body, bg=BG)
        right.pack(side="left", fill="both", expand=True)
        nb = ttk.Notebook(right)
        nb.pack(fill="both", expand=True)
        self._style_notebook(nb)

        log_frame = tk.Frame(nb, bg=BG)
        nb.add(log_frame, text="  📋 Pipeline Logs  ")
        self._log_box = scrolledtext.ScrolledText(
            log_frame, bg="#010409", fg=TEXT, font=FONT_MONO,
            insertbackground=TEXT, relief="flat", padx=12, pady=10,
            state="disabled", wrap="word")
        self._log_box.pack(fill="both", expand=True)
        self._log_box.tag_config("ok",     foreground="#3fb950")
        self._log_box.tag_config("err",    foreground=RED)
        self._log_box.tag_config("warn",   foreground=YELLOW)
        self._log_box.tag_config("info",   foreground=ACCENT2)
        self._log_box.tag_config("header", foreground=TEXT, font=FONT_H)

        chat_frame = tk.Frame(nb, bg=BG)
        nb.add(chat_frame, text="  💬 Chat  ")
        self._build_chat_tab(chat_frame)

        self.notebook = nb

    def _build_controls(self, parent):
        pad = {"padx": 16, "pady": 4}

        def section(title):
            tk.Frame(parent, bg=BORDER, height=1).pack(fill="x", pady=(16, 0))
            tk.Label(parent, text=title, font=FONT_H, bg=PANEL,
                     fg=ACCENT2, anchor="w").pack(fill="x", **pad)

        def file_row(label, var, filetypes):
            tk.Label(parent, text=label, font=FONT_UI, bg=PANEL, fg=TEXT_DIM, anchor="w").pack(fill="x", **pad)
            row = tk.Frame(parent, bg=PANEL)
            row.pack(fill="x", padx=16, pady=2)
            entry = tk.Entry(row, textvariable=var, bg="#010409", fg=TEXT,
                             font=("Menlo", 10), relief="flat",
                             insertbackground=TEXT, bd=0, highlightthickness=1,
                             highlightbackground=BORDER, highlightcolor=ACCENT2)
            entry.pack(side="left", fill="x", expand=True, ipady=5, padx=(0, 6))
            tk.Button(row, text="…", bg=PANEL, fg=TEXT, font=FONT_UI,
                      relief="flat", cursor="hand2", bd=0,
                      command=lambda v=var, ft=filetypes: self._browse(v, ft)).pack(side="left")

        def spin_row(label, var, lo, hi):
            row = tk.Frame(parent, bg=PANEL)
            row.pack(fill="x", padx=16, pady=3)
            tk.Label(row, text=label, font=FONT_UI, bg=PANEL, fg=TEXT_DIM, width=18, anchor="w").pack(side="left")
            tk.Spinbox(row, from_=lo, to=hi, textvariable=var,
                       bg="#010409", fg=TEXT, font=FONT_MONO,
                       relief="flat", width=8,
                       buttonbackground=PANEL, highlightthickness=1,
                       highlightbackground=BORDER).pack(side="left")

        section("① Document Chunking")
        file_row("Knowledge File (.txt / .pdf)", self.knowledge_file,
                 [("Text/PDF", "*.txt *.pdf"), ("All", "*.*")])
        file_row("Chunks Output (.json)", self.chunks_file,
                 [("JSON", "*.json"), ("All", "*.*")])
        spin_row("Chunk Size (chars)", self.chunk_size, 64, 4096)
        spin_row("Chunk Overlap", self.chunk_overlap, 0, 512)
        self._make_btn(parent, "▶  Run Document Splitter", self._run_splitter, ACCENT).pack(fill="x", padx=16, pady=(8, 4))

        section("② Embedding Generation")
        file_row("Embedding Model (.gguf)", self.embed_model_file,
                 [("GGUF", "*.gguf"), ("All", "*.*")])
        file_row("Chunks Input (.json)", self.chunks_file, [("JSON", "*.json")])
        file_row("Embedded DB Output (.json)", self.embedded_file, [("JSON", "*.json")])
        spin_row("Embedding Threads", self.embed_threads, 1, 32)
        spin_row("Top-K Retrieval", self.top_k, 1, 20)
        self._make_btn(parent, "▶  Generate Embeddings", self._run_embeddings, ACCENT).pack(fill="x", padx=16, pady=(8, 4))

        section("③ Chat / Query")
        file_row("LLM Model (.gguf)", self.llm_model_file,
                 [("GGUF", "*.gguf"), ("All", "*.*")])
        file_row("Model Config (.json)", self.model_config, [("JSON", "*.json")])
        file_row("Prompt Template (.mustache)", self.prompt_template,
                 [("Mustache", "*.mustache"), ("All", "*.*")])
        self._make_btn(parent, "▶  Start Chat Session", self._start_chat, ACCENT2).pack(fill="x", padx=16, pady=(8, 4))

        tk.Frame(parent, bg=BORDER, height=1).pack(fill="x", pady=(16, 0))
        self._make_btn(parent, "🚀  Run Full Pipeline", self._run_all, "#6e40c9").pack(fill="x", padx=16, pady=(10, 4))
        self._make_btn(parent, "⛔  Stop", self._stop, RED).pack(fill="x", padx=16, pady=(4, 16))

    def _build_chat_tab(self, parent):
        # Chat display
        self._chat_display = scrolledtext.ScrolledText(
            parent, bg="#010409", fg=TEXT, font=FONT_MONO,
            relief="flat", padx=12, pady=10, state="disabled", wrap="word")
        self._chat_display.pack(fill="both", expand=True)
        self._chat_display.tag_config("user",    foreground=ACCENT2, font=(FONT_MONO[0], FONT_MONO[1], "bold"))
        self._chat_display.tag_config("bot",     foreground="#3fb950")
        self._chat_display.tag_config("sys",     foreground=TEXT_DIM)
        self._chat_display.tag_config("summary", foreground=YELLOW, font=(FONT_MONO[0], FONT_MONO[1], "italic"))

        # Chat parsing state
        self._in_summary     = False
        self._answer_buf     = []
        self._after_assistant = False   # gate: only show lines AFTER <|im_start|>assistant

        # ── Thinking / spinner bar ────────────────────────────────────────────
        self._thinking_bar = tk.Frame(parent, bg="#0d1117", height=28)
        self._thinking_bar.pack(fill="x")
        self._thinking_bar.pack_propagate(False)
        self._thinking_lbl = tk.Label(
            self._thinking_bar, text="", bg="#0d1117",
            fg="#58a6ff", font=("Menlo", 10), anchor="w", padx=12)
        self._thinking_lbl.pack(fill="x", pady=4)
        self._spinner_frames  = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
        self._spinner_idx     = 0
        self._spinner_job     = None
        self._thinking_active = False

        # ── Input bar ─────────────────────────────────────────────────────────
        bar = tk.Frame(parent, bg=PANEL, height=52)
        bar.pack(fill="x")
        bar.pack_propagate(False)
        self._chat_entry = tk.Entry(bar, bg="#010409", fg=TEXT, font=FONT_MONO,
                                    relief="flat", insertbackground=TEXT,
                                    highlightthickness=1,
                                    highlightbackground=BORDER,
                                    highlightcolor=ACCENT2)
        self._chat_entry.pack(side="left", fill="x", expand=True, padx=12, pady=10, ipady=6)
        self._chat_entry.bind("<Return>", lambda e: self._send_chat())
        self._send_btn = self._make_btn(bar, "Send ↩", self._send_chat, ACCENT)
        self._send_btn.pack(side="right", padx=12, pady=10)

    # ── HELPERS ───────────────────────────────────────────────────────────────

    def _make_btn(self, parent, text, cmd, color):
        btn = tk.Button(parent, text=text, bg=color, fg="#c9d1d9",
                        font=FONT_H, relief="flat", cursor="hand2",
                        activebackground=ACCENT_H, activeforeground="#c9d1d9",
                        pady=9, bd=0, command=cmd)
        btn.bind("<Enter>", lambda e, b=btn, c=color: b.configure(bg=self._lighten(c)))
        btn.bind("<Leave>", lambda e, b=btn, c=color: b.configure(bg=c))
        return btn

    @staticmethod
    def _lighten(hex_color):
        h = hex_color.lstrip("#")
        rgb = [min(int(h[i:i+2], 16) + 24, 255) for i in (0, 2, 4)]
        return "#{:02x}{:02x}{:02x}".format(*rgb)

    def _style_notebook(self, nb):
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("TNotebook",     background=BG,    borderwidth=0)
        style.configure("TNotebook.Tab", background=PANEL, foreground=TEXT_DIM,
                        padding=[14, 8], font=FONT_UI)
        style.map("TNotebook.Tab",
                  background=[("selected", BG)],
                  foreground=[("selected", TEXT)])

    def _browse(self, var, filetypes):
        path = filedialog.askopenfilename(filetypes=filetypes, initialdir=str(BASE_DIR))
        if path:
            var.set(path)

    # ── LOGGING ───────────────────────────────────────────────────────────────

    def _log(self, msg: str, tag: str = ""):
        self._log_box.configure(state="normal")
        self._log_box.insert("end", msg + "\n", tag)
        self._log_box.see("end")
        self._log_box.configure(state="disabled")

    def _chat_append(self, msg: str, tag: str = ""):
        self._chat_display.configure(state="normal")
        self._chat_display.insert("end", msg + "\n", tag)
        self._chat_display.see("end")
        self._chat_display.configure(state="disabled")

    def _set_status(self, text: str, color: str = ACCENT):
        self.status_text.set(text)
        self._status_lbl.configure(bg=color)

    # ── STEP 1: DOCUMENT SPLITTER ─────────────────────────────────────────────

    def _run_splitter(self):
        if self._running:
            messagebox.showwarning("Busy", "A process is already running.")
            return
        threading.Thread(target=self._splitter_thread, daemon=True).start()

    def _splitter_thread(self):
        self._running = True
        self._set_status("Splitting…", YELLOW)
        self._log("\n━━━━  STEP 1 · Document Splitter  ━━━━", "header")
        venv_py = SPLITTER_DIR / ".venv" / "bin" / "python"
        py_exec = str(venv_py) if venv_py.exists() else sys.executable
        cmd = [
            py_exec,
            str(SPLITTER_DIR / "document_splitter.py"),
            str(self.knowledge_file.get()),
            "--output", str(self.chunks_file.get()),
            "--chunk_size", str(self.chunk_size.get()),
            "--chunk_overlap", str(self.chunk_overlap.get()),
        ]
        self._log("$ " + " ".join(cmd), "info")
        self._run_proc(cmd, cwd=str(SPLITTER_DIR))
        self._running = False

    # ── STEP 2: EMBEDDING GENERATION ──────────────────────────────────────────

    def _run_embeddings(self):
        if self._running:
            messagebox.showwarning("Busy", "A process is already running.")
            return
        threading.Thread(target=self._embeddings_thread, daemon=True).start()

    def _embeddings_thread(self):
        self._running = True
        self._set_status("Embedding…", YELLOW)
        self._log("\n━━━━  STEP 2 · Embedding Generation  ━━━━", "header")
        if not RAG_DEMO_BIN.exists():
            self._log(f"✗ Binary not found: {RAG_DEMO_BIN}", "err")
            self._log("  Build the project first: cd rag && conan build . --build=missing", "warn")
            self._set_status("Error", RED)
            self._running = False
            return
        cmd = [
            str(RAG_DEMO_BIN),
            "--mode", "RETRIEVAL",
            "-m", str(self.embed_model_file.get()),
            "--database_input", str(self.chunks_file.get()),
            "--database_output", str(self.embedded_file.get()),
            "-t", str(self.embed_threads.get()),
            "--top_k", str(self.top_k.get()),
        ]
        self._log("$ " + " ".join(cmd), "info")
        env = os.environ.copy()
        env["DYLD_LIBRARY_PATH"] = str(RAG_DIR / "build" / "Release")
        self._run_proc(cmd, cwd=str(RAG_DIR / "build" / "Release"), env=env)
        self._running = False

    # ── STEP 3: CHAT ──────────────────────────────────────────────────────────

    def _start_chat(self):
        if self._chat_proc and self._chat_proc.poll() is None:
            messagebox.showinfo("Chat", "Chat session already running.")
            return
        threading.Thread(target=self._chat_start_thread, daemon=True).start()

    def _chat_start_thread(self):
        self._set_status("Chat active", ACCENT2)
        self._log("\n━━━━  STEP 3 · Chat Session  ━━━━", "header")
        self._chat_append("System: Starting chat session…", "sys")
        if not RAG_DEMO_BIN.exists():
            self._log(f"✗ Binary not found: {RAG_DEMO_BIN}", "err")
            self._set_status("Error", RED)
            return
        cmd = [
            str(RAG_DEMO_BIN),
            "--mode", "CHAT",
            "-m", str(self.embed_model_file.get()),
            "--database_input", str(self.embedded_file.get()),
            "--model_path", str(self.llm_model_file.get()),
            "--model_config_path", str(self.model_config.get()),
            "--prompt_template_path", str(self.prompt_template.get()),
            "-t", str(self.embed_threads.get()),
            "--top_k", str(self.top_k.get()),
        ]
        self._log("$ " + " ".join(cmd), "info")
        env = os.environ.copy()
        env["DYLD_LIBRARY_PATH"] = str(RAG_DIR / "build" / "Release")
        try:
            self._chat_proc = subprocess.Popen(
                cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT, text=True,
                cwd=str(RAG_DIR / "build" / "Release"), env=env, bufsize=1)
            self._chat_append("System: Chat process started. Type your question below.", "sys")
            self._in_summary      = False
            self._answer_buf      = []
            self._after_assistant = False
            for line in self._chat_proc.stdout:
                stripped = line.rstrip()
                if not stripped:
                    continue
                self._log(stripped)            # everything → Pipeline Logs
                self._route_chat_line(stripped)  # filtered   → Chat tab
        except Exception as exc:
            self._log(f"✗ {exc}", "err")
            self._set_status("Error", RED)

    def _route_chat_line(self, line: str):
        """Filter bot output so only the real answer appears in the Chat tab.

        Stream order:
          [debug] timestamps
          <|im_start|>system … context chunks … <|im_end|>
          <|im_start|>user … <|im_end|>
          <|im_start|>assistant        ← gate opens HERE
          The actual LLM answer.
          =====ANSWER SUMMARY=====
          Time to first token / speed
          =====END OF SUMMARY=====
        """
        # Summary block — always shown regardless of gate
        if "=====ANSWER SUMMARY=====" in line:
            self._in_summary = True
            self._stop_thinking()
            self._chat_append("─" * 40, "summary")
            return
        if "=====END OF SUMMARY=====" in line:
            self._in_summary = False
            self._chat_append("─" * 40, "summary")
            return
        if self._in_summary:
            self._chat_append(line, "summary")
            return

        # Open the gate when the assistant turn marker is seen
        if "<|im_start|>assistant" in line:
            self._after_assistant = True
            return

        # Before the gate: everything is context/prompt noise → logs only
        if not self._after_assistant:
            return

        # After the gate: skip any stray template tags
        if line.startswith("[") or line.startswith("<|"):
            return

        # Real answer line → stop spinner, show in chat
        self._stop_thinking()
        self._chat_append(f"Bot: {line}", "bot")

    # ── THINKING SPINNER ──────────────────────────────────────────────────────

    def _start_thinking(self):
        self._thinking_active = True
        self._spinner_idx = 0
        self._chat_entry.configure(state="disabled")
        self._send_btn.configure(state="disabled")
        self._tick_spinner()

    def _tick_spinner(self):
        if not self._thinking_active:
            return
        frame = self._spinner_frames[self._spinner_idx % len(self._spinner_frames)]
        self._thinking_lbl.configure(text=f"{frame}  Thinking…")
        self._spinner_idx += 1
        self._spinner_job = self.after(90, self._tick_spinner)

    def _stop_thinking(self):
        if not self._thinking_active:
            return
        self._thinking_active = False
        if self._spinner_job:
            self.after_cancel(self._spinner_job)
            self._spinner_job = None
        self._thinking_lbl.configure(text="")
        self._chat_entry.configure(state="normal")
        self._send_btn.configure(state="normal")

    # ── SEND CHAT ─────────────────────────────────────────────────────────────

    def _send_chat(self):
        query = self._chat_entry.get().strip()
        if not query:
            return
        if self._chat_proc is None or self._chat_proc.poll() is not None:
            messagebox.showwarning("Chat", "Start a chat session first (Step 3).")
            return
        self._chat_append(f"You: {query}", "user")
        self._chat_entry.delete(0, "end")
        self._after_assistant = False         # reset gate for new query
        self.after(0, self._start_thinking)   # start spinner on UI thread
        try:
            self._chat_proc.stdin.write(query + "\n")
            self._chat_proc.stdin.flush()
        except Exception as exc:
            self._stop_thinking()
            self._chat_append(f"Error: {exc}", "sys")

    # ── RUN ALL ───────────────────────────────────────────────────────────────

    def _run_all(self):
        if self._running:
            messagebox.showwarning("Busy", "A process is already running.")
            return
        threading.Thread(target=self._run_all_thread, daemon=True).start()

    def _run_all_thread(self):
        self._splitter_thread()
        if self._running:
            return
        self._embeddings_thread()
        if self._running:
            return
        self.after(0, self._start_chat)

    # ── PROCESS RUNNER ────────────────────────────────────────────────────────

    def _run_proc(self, cmd, cwd=None, env=None):
        try:
            self._proc = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, cwd=cwd, env=env, bufsize=1)
            for line in self._proc.stdout:
                stripped = line.rstrip()
                if stripped:
                    tag = "err"  if any(w in stripped.lower() for w in ("error", "fatal", "exception")) else \
                          "warn" if "warn" in stripped.lower() else ""
                    self._log(stripped, tag)
            self._proc.wait()
            rc = self._proc.returncode
            if rc == 0:
                self._log("✔ Done (exit 0)", "ok")
                self._set_status("Done ✔", ACCENT)
            else:
                self._log(f"✗ Process exited with code {rc}", "err")
                self._set_status(f"Error ({rc})", RED)
        except FileNotFoundError:
            self._log(f"✗ Executable not found: {cmd[0]}", "err")
            self._set_status("Error", RED)
        except Exception as exc:
            self._log(f"✗ {exc}", "err")
            self._set_status("Error", RED)

    # ── STOP ──────────────────────────────────────────────────────────────────

    def _stop(self):
        for proc in (self._proc, self._chat_proc):
            if proc and proc.poll() is None:
                proc.terminate()
        self._running = False
        self._set_status("Stopped", RED)
        self._log("⛔ Stopped by user.", "warn")

    def _on_close(self):
        self._stop()
        self.destroy()


# ── Entry point ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    app = EdgeSLMApp()
    app.mainloop()
