#!/usr/bin/env python3
"""
Edge SLM RAG Pipeline — Raspberry Pi Edition
Lightweight Tkinter UI optimised for Pi screen sizes (800×480 and up).
Uses TinyLlama 1.1B Q4_K_M by default (smallest, fastest model).
"""

import tkinter as tk
from tkinter import ttk, filedialog, scrolledtext, messagebox
import subprocess
import threading
import os
import sys
import platform
from pathlib import Path

# ── Project paths ──────────────────────────────────────────────────────────────
BASE_DIR        = Path(__file__).parent.parent          # edge-slm-main/
MODELS_DIR      = BASE_DIR / "models"
RAG_DIR         = BASE_DIR / "rag"
SPLITTER_DIR    = BASE_DIR / "scripts" / "rag-document-splitter"

# ARM Linux binary path (built by install.sh via Conan)
RAG_DEMO_BIN  = RAG_DIR / "build" / "Release" / "apps" / "rag_demo" / "rag_demo"
PROMPT_TEMPLATE = RAG_DIR / "assets" / "prompt_templates" / "tinyllama.mustache"
# Fall back to qwen template if tinyllama one doesn't exist
if not PROMPT_TEMPLATE.exists():
    PROMPT_TEMPLATE = RAG_DIR / "assets" / "prompt_templates" / "qwen2.5.mustache"
MODEL_CONFIG    = MODELS_DIR / "model_config.json"

# Default to TinyLlama — smallest & fastest on Pi
DEFAULT_LLM   = MODELS_DIR / "tinyllama-1.1b-chat-v1.0.Q4_K_M.gguf"
DEFAULT_EMBED = MODELS_DIR / "nomic-embed-text-v1.f32.gguf"

# ── Detect screen DPI / size for scaling ──────────────────────────────────────
IS_PI    = platform.machine().startswith(("aarch64", "armv"))
IS_SMALL = False  # set after root creation

# ── Colour palette (same dark theme, Pi-friendly) ─────────────────────────────
BG       = "#0d1117"
PANEL    = "#161b22"
BORDER   = "#30363d"
ACCENT   = "#238636"
ACCENT2  = "#1f6feb"
ACCENT_H = "#2ea043"
TEXT     = "#e6edf3"
TEXT_DIM = "#8b949e"
RED      = "#da3633"
YELLOW   = "#d29922"
PURPLE   = "#6e40c9"

# Fonts — prefer system sans-serif, fall back gracefully
def _font(size, weight="normal"):
    for fam in ("DejaVu Sans", "Liberation Sans", "FreeSans", "Helvetica"):
        return (fam, size, weight)

def _mono(size):
    for fam in ("DejaVu Sans Mono", "Liberation Mono", "FreeMono", "Courier"):
        return (fam, size)

FONT_H    = _font(11, "bold")
FONT_UI   = _font(10)
FONT_MONO = _mono(10)
FONT_SMALL= _font(9)


# ═════════════════════════════════════════════════════════════════════════════
class EdgeSLMPiApp(tk.Tk):
    """Main application window — Pi edition."""

    def __init__(self):
        super().__init__()
        self.title("⚡ Edge SLM · Pi")
        self.configure(bg=BG)

        # Detect small screen (Pi touchscreen is typically 800×480)
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        global IS_SMALL
        IS_SMALL = (sw <= 1024 or sh <= 600)

        if IS_SMALL:
            self.geometry(f"{sw}x{sh}+0+0")
            self.state("zoomed") if sys.platform == "win32" else None
            try:
                self.attributes("-zoomed", True)
            except Exception:
                self.geometry("800x480")
        else:
            self.geometry("1000x700")
            self.minsize(800, 480)

        # Process handles
        self._proc: "subprocess.Popen | None" = None
        self._chat_proc: "subprocess.Popen | None" = None
        self._running = False

        # Tkinter vars
        self.knowledge_file   = tk.StringVar(value=str(MODELS_DIR / "sample_knowledge.txt"))
        self.chunks_file      = tk.StringVar(value=str(MODELS_DIR / "document_chunks.json"))
        self.embedded_file    = tk.StringVar(value=str(MODELS_DIR / "embedded_chunks.json"))
        self.embed_model_file = tk.StringVar(value=str(DEFAULT_EMBED))
        self.llm_model_file   = tk.StringVar(value=str(DEFAULT_LLM))
        self.model_config     = tk.StringVar(value=str(MODEL_CONFIG))
        self.prompt_template  = tk.StringVar(value=str(PROMPT_TEMPLATE))
        self.chunk_size       = tk.IntVar(value=512)
        self.chunk_overlap    = tk.IntVar(value=0)
        self.top_k            = tk.IntVar(value=3)
        # Pi has 4 cores — use 3 for inference, leave 1 for OS
        self.embed_threads    = tk.IntVar(value=3)
        self.status_text      = tk.StringVar(value="Ready")

        # Chat state
        self._in_summary       = False
        self._after_assistant  = False
        self._thinking_active  = False
        self._spinner_job      = None
        self._spinner_frames   = ["⠋","⠙","⠹","⠸","⠼","⠴","⠦","⠧","⠇","⠏"]
        self._spinner_idx      = 0

        self._build_ui()
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self._check_binary_on_start()

    # ── Startup check ─────────────────────────────────────────────────────────

    def _check_binary_on_start(self):
        if not RAG_DEMO_BIN.exists():
            self._log(
                "⚠  RAG binary not built yet.\n"
                "   Run:  bash raspberry-pi/install.sh\n"
                "   or:   cd rag && conan build . --build=missing",
                "warn")
        else:
            self._log(f"✔ RAG binary found: {RAG_DEMO_BIN}", "ok")
        llm = Path(self.llm_model_file.get())
        if llm.exists():
            size_mb = llm.stat().st_size // (1024*1024)
            self._log(f"✔ TinyLlama model: {size_mb} MB", "ok")
        else:
            self._log(f"⚠  LLM model not found: {llm}", "warn")

    # ── UI BUILD ──────────────────────────────────────────────────────────────

    def _build_ui(self):
        # ── Header ────────────────────────────────────────────────────────────
        hdr = tk.Frame(self, bg=PANEL, height=46)
        hdr.pack(fill="x")
        hdr.pack_propagate(False)

        tk.Label(hdr, text="⚡ Edge SLM",
                 font=_font(14, "bold"), bg=PANEL, fg=TEXT).pack(
                     side="left", padx=16, pady=10)
        tk.Label(hdr, text="Raspberry Pi · Local AI",
                 font=FONT_UI, bg=PANEL, fg=TEXT_DIM).pack(side="left", pady=10)

        # RAM info badge
        try:
            ram_kb = int(open("/proc/meminfo").readline().split()[1])
            ram_gb = ram_kb / 1024 / 1024
            ram_lbl = f"RAM {ram_gb:.1f} GB"
        except Exception:
            ram_lbl = "Raspberry Pi"
        tk.Label(hdr, text=ram_lbl, font=FONT_SMALL, bg=BORDER,
                 fg=TEXT_DIM, padx=8, pady=4).pack(side="right", padx=8, pady=10)

        self._status_lbl = tk.Label(hdr, textvariable=self.status_text,
                                    font=FONT_UI, bg=ACCENT, fg="white",
                                    padx=10, pady=4, relief="flat")
        self._status_lbl.pack(side="right", padx=4, pady=10)

        tk.Frame(self, bg=BORDER, height=1).pack(fill="x")

        # ── Body: left panel + right notebook ────────────────────────────────
        body = tk.Frame(self, bg=BG)
        body.pack(fill="both", expand=True)

        # Left panel (controls) — narrower on small screens
        lw = 320 if IS_SMALL else 380
        left = tk.Frame(body, bg=PANEL, width=lw)
        left.pack(side="left", fill="y")
        left.pack_propagate(False)

        canvas = tk.Canvas(left, bg=PANEL, highlightthickness=0)
        scrollbar = ttk.Scrollbar(left, orient="vertical", command=canvas.yview)
        self._ctrl_frame = tk.Frame(canvas, bg=PANEL)
        self._ctrl_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=self._ctrl_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)

        # Mouse wheel scroll on Pi touchscreen
        canvas.bind_all("<Button-4>", lambda e: canvas.yview_scroll(-1, "units"))
        canvas.bind_all("<Button-5>", lambda e: canvas.yview_scroll(1, "units"))

        self._build_controls(self._ctrl_frame)

        tk.Frame(body, bg=BORDER, width=1).pack(side="left", fill="y")

        # Right: notebook tabs
        right = tk.Frame(body, bg=BG)
        right.pack(side="left", fill="both", expand=True)
        nb = ttk.Notebook(right)
        nb.pack(fill="both", expand=True)
        self._style_notebook(nb)

        # Logs tab
        log_frame = tk.Frame(nb, bg=BG)
        nb.add(log_frame, text="  📋 Logs  ")
        self._log_box = scrolledtext.ScrolledText(
            log_frame, bg="#010409", fg=TEXT, font=FONT_MONO,
            insertbackground=TEXT, relief="flat", padx=10, pady=8,
            state="disabled", wrap="word")
        self._log_box.pack(fill="both", expand=True)
        self._log_box.tag_config("ok",     foreground="#3fb950")
        self._log_box.tag_config("err",    foreground=RED)
        self._log_box.tag_config("warn",   foreground=YELLOW)
        self._log_box.tag_config("info",   foreground=ACCENT2)
        self._log_box.tag_config("header", foreground=TEXT, font=_font(11, "bold"))

        # Chat tab
        chat_frame = tk.Frame(nb, bg=BG)
        nb.add(chat_frame, text="  💬 Chat  ")
        self._build_chat_tab(chat_frame)

        self.notebook = nb

    def _build_controls(self, parent):
        p = {"padx": 14, "pady": 3}

        def section(title, icon=""):
            tk.Frame(parent, bg=BORDER, height=1).pack(fill="x", pady=(12, 0))
            tk.Label(parent, text=f"{icon} {title}", font=FONT_H, bg=PANEL,
                     fg=ACCENT2, anchor="w").pack(fill="x", **p)

        def file_row(label, var, filetypes):
            tk.Label(parent, text=label, font=FONT_SMALL, bg=PANEL,
                     fg=TEXT_DIM, anchor="w").pack(fill="x", **p)
            row = tk.Frame(parent, bg=PANEL)
            row.pack(fill="x", padx=14, pady=2)
            e = tk.Entry(row, textvariable=var, bg="#010409", fg=TEXT,
                         font=_mono(9), relief="flat",
                         insertbackground=TEXT, bd=0,
                         highlightthickness=1,
                         highlightbackground=BORDER,
                         highlightcolor=ACCENT2)
            e.pack(side="left", fill="x", expand=True, ipady=4, padx=(0, 4))
            tk.Button(row, text="…", bg=PANEL, fg=TEXT, font=FONT_UI,
                      relief="flat", cursor="hand2", bd=0,
                      command=lambda v=var, ft=filetypes: self._browse(v, ft)
                      ).pack(side="left")

        def spin_row(label, var, lo, hi):
            row = tk.Frame(parent, bg=PANEL)
            row.pack(fill="x", padx=14, pady=2)
            tk.Label(row, text=label, font=FONT_SMALL, bg=PANEL,
                     fg=TEXT_DIM, width=16, anchor="w").pack(side="left")
            tk.Spinbox(row, from_=lo, to=hi, textvariable=var,
                       bg="#010409", fg=TEXT, font=FONT_MONO,
                       relief="flat", width=7,
                       buttonbackground=PANEL,
                       highlightthickness=1,
                       highlightbackground=BORDER).pack(side="left")

        # ① Document Chunking
        section("Document Chunking", "①")
        file_row("Knowledge file (.txt/.pdf)", self.knowledge_file,
                 [("Text/PDF", "*.txt *.pdf"), ("All", "*.*")])
        file_row("Chunks output (.json)", self.chunks_file,
                 [("JSON", "*.json"), ("All", "*.*")])
        spin_row("Chunk size (chars)", self.chunk_size, 64, 4096)
        spin_row("Chunk overlap", self.chunk_overlap, 0, 512)
        self._btn(parent, "▶  Split Document", self._run_splitter, ACCENT
                  ).pack(fill="x", padx=14, pady=(6, 2))

        # ② Embedding
        section("Generate Embeddings", "②")
        file_row("Embedding model (.gguf)", self.embed_model_file,
                 [("GGUF", "*.gguf"), ("All", "*.*")])
        file_row("Embedded DB output (.json)", self.embedded_file,
                 [("JSON", "*.json"), ("All", "*.*")])
        spin_row("Threads", self.embed_threads, 1, 8)
        spin_row("Top-K retrieval", self.top_k, 1, 20)
        self._btn(parent, "▶  Generate Embeddings", self._run_embeddings, ACCENT
                  ).pack(fill="x", padx=14, pady=(6, 2))

        # ③ Chat
        section("Chat / Query", "③")
        file_row("LLM model (.gguf)", self.llm_model_file,
                 [("GGUF", "*.gguf"), ("All", "*.*")])
        file_row("Prompt template (.mustache)", self.prompt_template,
                 [("Mustache", "*.mustache"), ("All", "*.*")])
        self._btn(parent, "▶  Start Chat Session", self._start_chat, ACCENT2
                  ).pack(fill="x", padx=14, pady=(6, 2))

        # Action row
        tk.Frame(parent, bg=BORDER, height=1).pack(fill="x", pady=(12, 0))
        self._btn(parent, "🚀  Run Full Pipeline", self._run_all, PURPLE
                  ).pack(fill="x", padx=14, pady=(8, 2))
        self._btn(parent, "⛔  Stop", self._stop, RED
                  ).pack(fill="x", padx=14, pady=(2, 14))

    def _build_chat_tab(self, parent):
        self._chat_display = scrolledtext.ScrolledText(
            parent, bg="#010409", fg=TEXT, font=FONT_MONO,
            relief="flat", padx=10, pady=8, state="disabled", wrap="word")
        self._chat_display.pack(fill="both", expand=True)
        self._chat_display.tag_config("user",    foreground=ACCENT2,
                                      font=_mono(10) + ("bold",) if False else _font(10, "bold"))
        self._chat_display.tag_config("bot",     foreground="#3fb950")
        self._chat_display.tag_config("sys",     foreground=TEXT_DIM)
        self._chat_display.tag_config("summary", foreground=YELLOW)

        # Thinking bar
        self._thinking_bar = tk.Frame(parent, bg=BG, height=26)
        self._thinking_bar.pack(fill="x")
        self._thinking_bar.pack_propagate(False)
        self._thinking_lbl = tk.Label(
            self._thinking_bar, text="", bg=BG,
            fg="#58a6ff", font=_mono(9), anchor="w", padx=10)
        self._thinking_lbl.pack(fill="x", pady=3)

        # Input bar
        bar = tk.Frame(parent, bg=PANEL, height=48)
        bar.pack(fill="x")
        bar.pack_propagate(False)
        self._chat_entry = tk.Entry(
            bar, bg="#010409", fg=TEXT, font=FONT_MONO,
            relief="flat", insertbackground=TEXT,
            highlightthickness=1,
            highlightbackground=BORDER, highlightcolor=ACCENT2)
        self._chat_entry.pack(side="left", fill="x", expand=True,
                              padx=10, pady=8, ipady=5)
        self._chat_entry.bind("<Return>", lambda e: self._send_chat())
        self._send_btn = self._btn(bar, "Send ↩", self._send_chat, ACCENT)
        self._send_btn.pack(side="right", padx=10, pady=8)

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _btn(self, parent, text, cmd, color):
        b = tk.Button(parent, text=text, bg=color, fg="#c9d1d9",
                      font=FONT_H, relief="flat", cursor="hand2",
                      activebackground=self._lighten(color),
                      activeforeground="#c9d1d9",
                      pady=8, bd=0, command=cmd)
        b.bind("<Enter>", lambda e, btn=b, c=color: btn.configure(bg=self._lighten(c)))
        b.bind("<Leave>", lambda e, btn=b, c=color: btn.configure(bg=c))
        return b

    @staticmethod
    def _lighten(hex_color: str) -> str:
        h = hex_color.lstrip("#")
        rgb = [min(int(h[i:i+2], 16) + 28, 255) for i in (0, 2, 4)]
        return "#{:02x}{:02x}{:02x}".format(*rgb)

    def _style_notebook(self, nb):
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("TNotebook",     background=BG,    borderwidth=0)
        style.configure("TNotebook.Tab", background=PANEL, foreground=TEXT_DIM,
                        padding=[12, 6], font=FONT_UI)
        style.map("TNotebook.Tab",
                  background=[("selected", BG)],
                  foreground=[("selected", TEXT)])

    def _browse(self, var, filetypes):
        path = filedialog.askopenfilename(filetypes=filetypes, initialdir=str(BASE_DIR))
        if path:
            var.set(path)

    # ── Logging ───────────────────────────────────────────────────────────────

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

    # ── Linux env helper ──────────────────────────────────────────────────────

    def _arm_env(self) -> dict:
        """Return env dict with LD_LIBRARY_PATH set for ARM Linux."""
        env = os.environ.copy()
        lib_path = str(RAG_DIR / "build" / "Release")
        env["LD_LIBRARY_PATH"] = lib_path + ":" + env.get("LD_LIBRARY_PATH", "")
        return env

    # ── Step 1: Document Splitter ─────────────────────────────────────────────

    def _run_splitter(self):
        if self._running:
            messagebox.showwarning("Busy", "A process is already running.")
            return
        threading.Thread(target=self._splitter_thread, daemon=True).start()

    def _splitter_thread(self):
        self._running = True
        self._set_status("Splitting…", YELLOW)
        self._log("\n━━━━  ① Document Splitter  ━━━━", "header")
        venv_py = SPLITTER_DIR / ".venv" / "bin" / "python"
        py_exec = str(venv_py) if venv_py.exists() else sys.executable
        cmd = [
            py_exec,
            str(SPLITTER_DIR / "document_splitter.py"),
            str(self.knowledge_file.get()),
            "--output",       str(self.chunks_file.get()),
            "--chunk_size",   str(self.chunk_size.get()),
            "--chunk_overlap", str(self.chunk_overlap.get()),
        ]
        self._log("$ " + " ".join(cmd), "info")
        self._run_proc(cmd, cwd=str(SPLITTER_DIR))
        self._running = False

    # ── Step 2: Embeddings ────────────────────────────────────────────────────

    def _run_embeddings(self):
        if self._running:
            messagebox.showwarning("Busy", "A process is already running.")
            return
        threading.Thread(target=self._embeddings_thread, daemon=True).start()

    def _embeddings_thread(self):
        self._running = True
        self._set_status("Embedding…", YELLOW)
        self._log("\n━━━━  ② Embedding Generation  ━━━━", "header")
        if not RAG_DEMO_BIN.exists():
            self._log(f"✗ Binary not found: {RAG_DEMO_BIN}", "err")
            self._log("  Run install.sh first to build the RAG binary.", "warn")
            self._set_status("Error", RED)
            self._running = False
            return
        cmd = [
            str(RAG_DEMO_BIN),
            "--mode",            "RETRIEVAL",
            "-m",                str(self.embed_model_file.get()),
            "--database_input",  str(self.chunks_file.get()),
            "--database_output", str(self.embedded_file.get()),
            "-t",                str(self.embed_threads.get()),
            "--top_k",           str(self.top_k.get()),
        ]
        self._log("$ " + " ".join(cmd), "info")
        self._run_proc(cmd,
                       cwd=str(RAG_DIR / "build" / "Release"),
                       env=self._arm_env())
        self._running = False

    # ── Step 3: Chat ──────────────────────────────────────────────────────────

    def _start_chat(self):
        if self._chat_proc and self._chat_proc.poll() is None:
            messagebox.showinfo("Chat", "Chat session already running.")
            return
        threading.Thread(target=self._chat_start_thread, daemon=True).start()

    def _chat_start_thread(self):
        self._set_status("Chat active", ACCENT2)
        self._log("\n━━━━  ③ Chat Session  ━━━━", "header")
        self._chat_append("System: Starting TinyLlama chat…", "sys")
        if not RAG_DEMO_BIN.exists():
            self._log(f"✗ Binary not found: {RAG_DEMO_BIN}", "err")
            self._set_status("Error", RED)
            return
        cmd = [
            str(RAG_DEMO_BIN),
            "--mode",                "CHAT",
            "-m",                    str(self.embed_model_file.get()),
            "--database_input",      str(self.embedded_file.get()),
            "--model_path",          str(self.llm_model_file.get()),
            "--model_config_path",   str(self.model_config.get()),
            "--prompt_template_path", str(self.prompt_template.get()),
            "-t",                    str(self.embed_threads.get()),
            "--top_k",               str(self.top_k.get()),
        ]
        self._log("$ " + " ".join(cmd), "info")
        try:
            self._chat_proc = subprocess.Popen(
                cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT, text=True,
                cwd=str(RAG_DIR / "build" / "Release"),
                env=self._arm_env(), bufsize=1)
            self.notebook.select(1)   # jump to Chat tab
            self._chat_append("System: Ready — type a question below.", "sys")
            self._in_summary      = False
            self._after_assistant = False
            for line in self._chat_proc.stdout:
                stripped = line.rstrip()
                if not stripped:
                    continue
                self._log(stripped)
                self._route_chat_line(stripped)
        except Exception as exc:
            self._log(f"✗ {exc}", "err")
            self._set_status("Error", RED)

    def _route_chat_line(self, line: str):
        if "=====ANSWER SUMMARY=====" in line:
            self._in_summary = True
            self._stop_thinking()
            self._chat_append("─" * 36, "summary")
            return
        if "=====END OF SUMMARY=====" in line:
            self._in_summary = False
            self._chat_append("─" * 36, "summary")
            return
        if self._in_summary:
            self._chat_append(line, "summary")
            return
        if "<|im_start|>assistant" in line:
            self._after_assistant = True
            return
        if not self._after_assistant:
            return
        if line.startswith("[") or line.startswith("<|"):
            return
        self._stop_thinking()
        self._chat_append(f"Bot: {line}", "bot")

    # ── Thinking spinner ──────────────────────────────────────────────────────

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
        self._thinking_lbl.configure(
            text=f"{frame}  TinyLlama is thinking… (may take 30–90 s on Pi)")
        self._spinner_idx += 1
        self._spinner_job = self.after(120, self._tick_spinner)

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

    # ── Send chat ─────────────────────────────────────────────────────────────

    def _send_chat(self):
        query = self._chat_entry.get().strip()
        if not query:
            return
        if self._chat_proc is None or self._chat_proc.poll() is not None:
            messagebox.showwarning("Chat", "Start a chat session first (Step ③).")
            return
        self._chat_append(f"You: {query}", "user")
        self._chat_entry.delete(0, "end")
        self._after_assistant = False
        self.after(0, self._start_thinking)
        try:
            self._chat_proc.stdin.write(query + "\n")
            self._chat_proc.stdin.flush()
        except Exception as exc:
            self._stop_thinking()
            self._chat_append(f"Error: {exc}", "sys")

    # ── Run Full Pipeline ─────────────────────────────────────────────────────

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

    # ── Generic process runner ────────────────────────────────────────────────

    def _run_proc(self, cmd, cwd=None, env=None):
        try:
            self._proc = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                text=True, cwd=cwd, env=env, bufsize=1)
            for line in self._proc.stdout:
                stripped = line.rstrip()
                if stripped:
                    kw_lower = stripped.lower()
                    tag = ("err"  if any(w in kw_lower for w in ("error","fatal","exception"))
                           else "warn" if "warn" in kw_lower
                           else "")
                    self._log(stripped, tag)
            self._proc.wait()
            rc = self._proc.returncode
            if rc == 0:
                self._log("✔ Done (exit 0)", "ok")
                self._set_status("Done ✔", ACCENT)
            else:
                self._log(f"✗ Exited with code {rc}", "err")
                self._set_status(f"Error ({rc})", RED)
        except FileNotFoundError:
            self._log(f"✗ Not found: {cmd[0]}", "err")
            self._set_status("Error", RED)
        except Exception as exc:
            self._log(f"✗ {exc}", "err")
            self._set_status("Error", RED)

    # ── Stop ──────────────────────────────────────────────────────────────────

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
    app = EdgeSLMPiApp()
    app.mainloop()
