#!/usr/bin/env python3
"""TinyML RAG Pipeline - Streamlit UI

Web-based replacement for the old Tkinter desktop app. Runs headless,
which makes it a natural fit for Docker (no X11 / Xvfb required) while
still working as a local dev UI (`streamlit run app.py`).
"""

import base64
import os
import platform
import subprocess
import sys
import time
from pathlib import Path

import streamlit as st


def _monogram_avatar(letters: str, bg: str) -> str:
    """A flat, monochrome monogram avatar (data URI) instead of Streamlit's default emoji icons."""
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="64" height="64">'
        f'<rect width="64" height="64" rx="14" fill="{bg}"/>'
        f'<text x="32" y="34" font-family="Helvetica, Arial, sans-serif" font-size="22" '
        f'font-weight="600" fill="#F2F3F5" text-anchor="middle" dominant-baseline="middle">{letters}</text>'
        f"</svg>"
    )
    return "data:image/svg+xml;base64," + base64.b64encode(svg.encode()).decode()


ASSISTANT_AVATAR = _monogram_avatar("AI", "#5B7CFA")
USER_AVATAR = _monogram_avatar("Y", "#3A3F4B")

# ── Project paths ────────────────────────────────────────────────────────────
BASE_DIR      = Path(__file__).parent
MODELS_DIR    = BASE_DIR / "models"
RAG_DIR       = BASE_DIR / "rag"
SPLITTER_DIR  = BASE_DIR / "scripts" / "rag-document-splitter"
RAG_BUILD_DIR = RAG_DIR / "build" / "Release"
RAG_DEMO_BIN  = RAG_BUILD_DIR / "apps" / "rag_demo" / "rag_demo"
TEMPLATES_DIR = RAG_DIR / "assets" / "prompt_templates"
MODEL_CONFIG  = MODELS_DIR / "model_config.json"

DEFAULT_EMBED_MODEL = MODELS_DIR / "nomic-embed-text-v1.f32.gguf"

# Smaller/faster model + template defaults on ARM (Raspberry Pi) targets.
IS_ARM = platform.machine().startswith(("aarch64", "armv"))
DEFAULT_LLM = MODELS_DIR / (
    "tinyllama-1.1b-chat-v1.0.Q4_K_M.gguf" if IS_ARM else "qwen2.5-1.5b-instruct-q4_k_m.gguf"
)
DEFAULT_TEMPLATE = TEMPLATES_DIR / ("tiny_llama1.1B.mustache" if IS_ARM else "qwen2.5.mustache")
if not DEFAULT_TEMPLATE.exists():
    DEFAULT_TEMPLATE = TEMPLATES_DIR / "qwen2.5.mustache"

# Each chat model ships with a prompt template matched to its chat format
# (ChatML for Qwen, Zephyr-style for TinyLlama, etc.) - picking a model in the
# UI should switch the template with it, not leave a stale mismatch behind.
TEMPLATE_FOR_MODEL = {
    "qwen2.5-1.5b-instruct-q4_k_m.gguf": TEMPLATES_DIR / "qwen2.5.mustache",
    "tinyllama-1.1b-chat-v1.0.Q4_K_M.gguf": TEMPLATES_DIR / "tiny_llama1.1B.mustache",
}


def template_for_model(model_path: str) -> Path:
    return TEMPLATE_FOR_MODEL.get(Path(model_path).name, DEFAULT_TEMPLATE)


def discover_llm_models() -> list[Path]:
    """.gguf files in MODELS_DIR usable as chat models (i.e. not the embedding model)."""
    if not MODELS_DIR.is_dir():
        return []
    return sorted(p for p in MODELS_DIR.glob("*.gguf") if p.name != DEFAULT_EMBED_MODEL.name)


def discover_files(directory: Path, glob: str = "*") -> list[Path]:
    """Return sorted list of files matching glob inside directory."""
    if not directory.is_dir():
        return []
    return sorted(directory.glob(glob))


AVAILABLE_LLM_MODELS = discover_llm_models()

# ── Make Qwen the default (put it first in the list) ─────────────────────────
QWEN_NAME = "qwen2.5-1.5b-instruct-q4_k_m.gguf"
if AVAILABLE_LLM_MODELS:
    qwen_match = [p for p in AVAILABLE_LLM_MODELS if QWEN_NAME in p.name.lower()]
    others = [p for p in AVAILABLE_LLM_MODELS if QWEN_NAME not in p.name.lower()]
    AVAILABLE_LLM_MODELS = qwen_match + others
    DEFAULT_LLM = AVAILABLE_LLM_MODELS[0]
elif not DEFAULT_LLM.exists():
    pass  # keep DEFAULT_LLM as-is (path hint for the user)

# Markers that precede the model's actual answer in rag_demo's CHAT stdout,
# one per prompt template style shipped in rag/assets/prompt_templates/:
# ChatML (qwen2.5), Zephyr-style (tiny_llama1.1B), and Phi-2's "Output:".
ASSISTANT_MARKERS = ("<|im_start|>assistant", "<|assistant|>", "Output:")

st.set_page_config(page_title="TinyML · RAG Pipeline", page_icon="◆", layout="wide")

st.markdown(
    """
    <style>
    /* Tighter, more deliberate vertical rhythm in the sidebar */
    section[data-testid="stSidebar"] .stButton button { margin-top: 0.15rem; }
    section[data-testid="stSidebar"] h3 {
        font-size: 0.78rem;
        letter-spacing: 0.06em;
        text-transform: uppercase;
        color: var(--text-color, #9AA3B2);
        opacity: 0.75;
        margin-top: 1.4rem;
        margin-bottom: 0.4rem;
    }
    /* Quiet, monospace status line under the wordmark */
    .tinyml-status { font-family: monospace; font-size: 0.8rem; opacity: 0.7; }
    </style>
    """,
    unsafe_allow_html=True,
)

# ── Session state ────────────────────────────────────────────────────────────
_DEFAULTS = {
    "logs": [],           # list[(level, str)]
    "chat_history": [],   # list[{"role": ..., "content": ...}]
    "chat_proc": None,    # persistent llama.cpp CHAT subprocess
}
for _k, _v in _DEFAULTS.items():
    st.session_state.setdefault(_k, _v)


def log(msg: str, level: str = "info") -> None:
    st.session_state.logs.append((level, msg))


def render_logs(placeholder) -> None:
    text = "\n".join(m for _, m in st.session_state.logs[-1000:])
    placeholder.code(text or "No logs yet.", language="bash")


def rag_env() -> dict:
    """llama.cpp / RAG shared libs live next to the binary, not on the default loader path."""
    env = os.environ.copy()
    lib_path = str(RAG_BUILD_DIR)
    if sys.platform == "darwin":
        env["DYLD_LIBRARY_PATH"] = lib_path
    else:
        env["LD_LIBRARY_PATH"] = lib_path + ":" + env.get("LD_LIBRARY_PATH", "")
    return env


def stream_process(cmd, placeholder, cwd=None, env=None) -> bool:
    """Run a subprocess to completion, streaming its output into the log placeholder."""
    log("$ " + " ".join(cmd), "info")
    render_logs(placeholder)
    try:
        proc = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, cwd=cwd, env=env, bufsize=1,
        )
    except FileNotFoundError:
        log(f"✗ Executable not found: {cmd[0]}", "err")
        render_logs(placeholder)
        return False

    for line in proc.stdout:
        stripped = line.rstrip()
        if stripped:
            log(stripped)
            render_logs(placeholder)
    proc.wait()

    if proc.returncode == 0:
        log("✔ Done (exit 0)", "ok")
    else:
        log(f"✗ Exited with code {proc.returncode}", "err")
    render_logs(placeholder)
    return proc.returncode == 0


# ── Pipeline steps ───────────────────────────────────────────────────────────

def run_splitter_step(placeholder) -> bool:
    log("\n━━━━  STEP 1 · Document Splitter  ━━━━", "header")
    venv_py = SPLITTER_DIR / ".venv" / "bin" / "python"
    py_exec = str(venv_py) if venv_py.exists() else sys.executable
    cmd = [
        py_exec, str(SPLITTER_DIR / "document_splitter.py"),
        st.session_state.knowledge_file,
        "--output", st.session_state.chunks_file,
        "--chunk_size", str(st.session_state.chunk_size),
        "--chunk_overlap", str(st.session_state.chunk_overlap),
    ]
    return stream_process(cmd, placeholder, cwd=str(SPLITTER_DIR))


def run_embeddings_step(placeholder) -> bool:
    log("\n━━━━  STEP 2 · Embedding Generation  ━━━━", "header")
    if not RAG_DEMO_BIN.exists():
        log(f"✗ Binary not found: {RAG_DEMO_BIN}", "err")
        log("  Build the project first: cd rag && conan build . --build=missing", "warn")
        render_logs(placeholder)
        return False
    cmd = [
        str(RAG_DEMO_BIN), "--mode", "RETRIEVAL",
        "-m", st.session_state.embed_model_file,
        "--database_input", st.session_state.chunks_file,
        "--database_output", st.session_state.embedded_file,
        "-t", str(st.session_state.embed_threads),
        "--top_k", str(st.session_state.top_k),
    ]
    return stream_process(cmd, placeholder, cwd=str(RAG_BUILD_DIR), env=rag_env())


def start_chat_session(placeholder) -> None:
    proc = st.session_state.chat_proc
    if proc and proc.poll() is None:
        st.toast("Chat session already running.")
        return
    log("\n━━━━  STEP 3 · Chat Session  ━━━━", "header")
    if not RAG_DEMO_BIN.exists():
        log(f"✗ Binary not found: {RAG_DEMO_BIN}", "err")
        render_logs(placeholder)
        return
    cmd = [
        str(RAG_DEMO_BIN), "--mode", "CHAT",
        "-m", st.session_state.embed_model_file,
        "--database_input", st.session_state.embedded_file,
        "--model_path", st.session_state.llm_model_file,
        "--model_config_path", st.session_state.model_config,
        "--prompt_template_path", st.session_state.prompt_template,
        "-t", str(st.session_state.embed_threads),
        "--top_k", str(st.session_state.top_k),
    ]
    log("$ " + " ".join(cmd), "info")
    try:
        proc = subprocess.Popen(
            cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, text=True,
            cwd=str(RAG_BUILD_DIR), env=rag_env(), bufsize=1,
        )
    except Exception as exc:  # noqa: BLE001 - surface any launch failure to the log panel
        log(f"✗ {exc}", "err")
        render_logs(placeholder)
        return

    # Model loading can legitimately take a while, but a bad model/template path
    # (or a crash on load) fails almost instantly - catch that instead of blindly
    # reporting "started" and leaving the user staring at a chat box that never replies.
    for _ in range(20):  # ~4s
        if proc.poll() is not None:
            break
        time.sleep(0.2)

    if proc.poll() is not None:
        output = proc.stdout.read().strip()
        if output:
            log(output, "err")
        log(f"✗ Chat process exited immediately (code {proc.returncode}) - check the model/template paths above.", "err")
        render_logs(placeholder)
        return

    st.session_state.chat_proc = proc
    st.session_state.chat_history.append(
        {"role": "assistant", "content": "Chat session started. Ask a question below."}
    )
    render_logs(placeholder)


def stop_all(placeholder) -> None:
    proc = st.session_state.chat_proc
    if proc and proc.poll() is None:
        proc.terminate()
    st.session_state.chat_proc = None
    log("Stopped by user.", "warn")
    render_logs(placeholder)


def handle_chat(prompt: str, log_placeholder) -> None:
    proc = st.session_state.chat_proc
    if proc is None or proc.poll() is not None:
        st.session_state.chat_history.append(
            {"role": "assistant", "content": "Start a chat session first (sidebar, step 3)."}
        )
        return

    st.session_state.chat_history.append({"role": "user", "content": prompt})
    with st.chat_message("user", avatar=USER_AVATAR):
        st.markdown(prompt)

    try:
        proc.stdin.write(prompt + "\n")
        proc.stdin.flush()
    except Exception as exc:  # noqa: BLE001
        st.session_state.chat_history.append({"role": "assistant", "content": f"Error: {exc}"})
        return

    # Mirrors the old Tkinter line-routing logic: everything between the
    # assistant marker (template-dependent, see ASSISTANT_MARKERS) and the
    # answer-summary block is the real answer; everything else is
    # prompt/context noise → logs only.
    after_assistant = False
    in_summary = False
    answer_lines: list[str] = []
    summary_lines: list[str] = []

    with st.chat_message("assistant", avatar=ASSISTANT_AVATAR):
        placeholder = st.empty()
        placeholder.markdown("_Thinking…_")
        for line in proc.stdout:
            stripped = line.rstrip()
            if not stripped:
                continue
            log(stripped)

            if "=====ANSWER SUMMARY=====" in stripped:
                in_summary = True
                continue
            if "=====END OF SUMMARY=====" in stripped:
                break
            if in_summary:
                summary_lines.append(stripped)
                continue
            if any(marker in stripped for marker in ASSISTANT_MARKERS):
                after_assistant = True
                continue
            if not after_assistant:
                continue
            if stripped.startswith("[") or stripped.startswith("<|"):
                continue

            answer_lines.append(stripped)
            placeholder.markdown("\n".join(answer_lines))

        final_answer = "\n".join(answer_lines) if answer_lines else "_(no answer captured — check Pipeline Logs)_"
        placeholder.markdown(final_answer)
        if summary_lines:
            with st.expander("Response timing / summary"):
                st.code("\n".join(summary_lines))

    render_logs(log_placeholder)
    st.session_state.chat_history.append({"role": "assistant", "content": final_answer})


# ── Sidebar (pipeline configuration + controls) ─────────────────────────────
with st.sidebar:
    st.markdown("## TinyML")
    st.caption("RAG pipeline for small language models")
    runtime_status = "runtime ready" if RAG_DEMO_BIN.exists() else "binary not built"
    profile = "ARM · Raspberry Pi" if IS_ARM else "Desktop"
    st.markdown(f'<div class="tinyml-status">{runtime_status} &nbsp;·&nbsp; {profile}</div>', unsafe_allow_html=True)

    # ── § 1 · Document chunking ──────────────────────────────────────────────
    st.markdown("### 1 · Document chunking")

    # Knowledge file picker: show .txt / .pdf files found in MODELS_DIR
    _txt_files = discover_files(MODELS_DIR, "*.txt") + discover_files(MODELS_DIR, "*.pdf")
    _txt_options = [str(p) for p in _txt_files] or [str(MODELS_DIR / "sample_knowledge.txt")]
    _txt_default = str(MODELS_DIR / "sample_knowledge.txt")
    _txt_idx = _txt_options.index(_txt_default) if _txt_default in _txt_options else 0
    st.selectbox(
        "Knowledge file (.txt / .pdf)",
        _txt_options,
        index=_txt_idx,
        format_func=lambda p: Path(p).name,
        key="knowledge_file",
    )
    # Manual override
    st.caption("Or type a custom path:")
    _kf_custom = st.text_input(
        "Custom knowledge file path", value="", key="knowledge_file_custom",
        placeholder="/absolute/path/to/file.txt",
        label_visibility="collapsed",
    )
    if _kf_custom.strip():
        st.session_state.knowledge_file = _kf_custom.strip()

    # Chunks output picker: show existing .json files in MODELS_DIR
    _json_files = discover_files(MODELS_DIR, "*.json")
    _chunks_options = [str(p) for p in _json_files] + [str(MODELS_DIR / "document_chunks.json")]
    _chunks_options = list(dict.fromkeys(_chunks_options))  # deduplicate
    _chunks_default = str(MODELS_DIR / "document_chunks.json")
    _chunks_idx = _chunks_options.index(_chunks_default) if _chunks_default in _chunks_options else 0
    st.selectbox(
        "Chunks output (.json)",
        _chunks_options,
        index=_chunks_idx,
        format_func=lambda p: Path(p).name,
        key="chunks_file",
    )
    st.number_input("Chunk size (chars)", min_value=64, max_value=4096, value=512, step=64, key="chunk_size")
    st.number_input("Chunk overlap", min_value=0, max_value=512, value=0, step=16, key="chunk_overlap")
    run_splitter_clicked = st.button("Run document splitter", use_container_width=True)

    # ── § 2 · Embedding generation ───────────────────────────────────────────
    st.markdown("### 2 · Embedding generation")

    # Embedding model picker: show all .gguf files in MODELS_DIR
    _all_gguf = discover_files(MODELS_DIR, "*.gguf")
    _embed_options = [str(p) for p in _all_gguf] or [str(DEFAULT_EMBED_MODEL)]
    _embed_default = str(DEFAULT_EMBED_MODEL)
    _embed_idx = _embed_options.index(_embed_default) if _embed_default in _embed_options else 0
    st.selectbox(
        "Embedding model (.gguf)",
        _embed_options,
        index=_embed_idx,
        format_func=lambda p: Path(p).name,
        key="embed_model_file",
    )

    # Embedded DB output picker
    _emb_db_options = [str(p) for p in _json_files] + [str(MODELS_DIR / "embedded_chunks.json")]
    _emb_db_options = list(dict.fromkeys(_emb_db_options))
    _emb_db_default = str(MODELS_DIR / "embedded_chunks.json")
    _emb_db_idx = _emb_db_options.index(_emb_db_default) if _emb_db_default in _emb_db_options else 0
    st.selectbox(
        "Embedded DB output (.json)",
        _emb_db_options,
        index=_emb_db_idx,
        format_func=lambda p: Path(p).name,
        key="embedded_file",
    )
    st.number_input("Embedding threads", min_value=1, max_value=32, value=4, key="embed_threads")
    st.number_input("Top-K retrieval", min_value=1, max_value=20, value=3, key="top_k")
    run_embed_clicked = st.button("Generate embeddings", use_container_width=True)

    # ── § 3 · Chat ───────────────────────────────────────────────────────────
    st.markdown("### 3 · Chat")

    # LLM model picker — Qwen is first (default)
    _llm_options = [str(p) for p in AVAILABLE_LLM_MODELS] or [str(DEFAULT_LLM)]
    # Ensure session state is initialised to Qwen before the widget renders
    if "llm_model_file" not in st.session_state:
        st.session_state["llm_model_file"] = _llm_options[0]
    if "prompt_template" not in st.session_state:
        st.session_state["prompt_template"] = str(template_for_model(st.session_state["llm_model_file"]))

    def _sync_template_to_model() -> None:
        st.session_state.prompt_template = str(template_for_model(st.session_state.llm_model_file))

    _llm_current = st.session_state.get("llm_model_file", _llm_options[0])
    _llm_idx = _llm_options.index(_llm_current) if _llm_current in _llm_options else 0
    st.selectbox(
        "LLM model (.gguf)",
        _llm_options,
        index=_llm_idx,
        format_func=lambda p: Path(p).name,
        key="llm_model_file",
        on_change=_sync_template_to_model,
        help="Qwen 2.5 1.5B is selected by default. Add more .gguf files to the models/ directory to see them here.",
    )

    # Model config picker
    _cfg_files = discover_files(MODELS_DIR, "*.json")
    _cfg_options = [str(p) for p in _cfg_files] or [str(MODEL_CONFIG)]
    _cfg_default = str(MODEL_CONFIG)
    _cfg_idx = _cfg_options.index(_cfg_default) if _cfg_default in _cfg_options else 0
    st.selectbox(
        "Model config (.json)",
        _cfg_options,
        index=_cfg_idx,
        format_func=lambda p: Path(p).name,
        key="model_config",
    )

    # Prompt template picker
    _tmpl_files = discover_files(TEMPLATES_DIR, "*.mustache")
    _tmpl_options = [str(p) for p in _tmpl_files] or [str(DEFAULT_TEMPLATE)]
    _tmpl_current = st.session_state.get("prompt_template", str(DEFAULT_TEMPLATE))
    _tmpl_idx = _tmpl_options.index(_tmpl_current) if _tmpl_current in _tmpl_options else 0
    st.selectbox(
        "Prompt template (.mustache)",
        _tmpl_options,
        index=_tmpl_idx,
        format_func=lambda p: Path(p).name,
        key="prompt_template",
        help="Template is auto-selected when you change the LLM model above.",
    )
    start_chat_clicked = st.button("Start chat session", use_container_width=True)

    st.divider()
    run_all_clicked = st.button("Run full pipeline", use_container_width=True, type="primary")
    stop_clicked = st.button("Stop", use_container_width=True)

# ── Main area ────────────────────────────────────────────────────────────────
st.title("TinyML")
st.caption("RAG pipeline · local inference")

tab_logs, tab_chat = st.tabs(["Logs", "Chat"])
log_placeholder = tab_logs.empty()
render_logs(log_placeholder)

if stop_clicked:
    stop_all(log_placeholder)

if run_splitter_clicked:
    run_splitter_step(log_placeholder)

if run_embed_clicked:
    run_embeddings_step(log_placeholder)

if start_chat_clicked:
    start_chat_session(log_placeholder)

if run_all_clicked:
    if run_splitter_step(log_placeholder) and run_embeddings_step(log_placeholder):
        start_chat_session(log_placeholder)

with tab_chat:
    for msg in st.session_state.chat_history:
        avatar = ASSISTANT_AVATAR if msg["role"] == "assistant" else USER_AVATAR
        with st.chat_message(msg["role"], avatar=avatar):
            st.markdown(msg["content"])
    prompt = st.chat_input("Ask a question about your knowledge base…")
    if prompt:
        handle_chat(prompt, log_placeholder)
