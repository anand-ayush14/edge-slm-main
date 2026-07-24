# ⚡ TinyML — Raspberry Pi Edition

> **Local AI chat on your Pi — no internet, no cloud, fully private.**
> Uses **TinyLlama 1.1B** (smallest model, ~638 MB) with a RAG pipeline
> for grounded, document-aware answers.

---

## What You Get

| Feature | Details |
|---|---|
| **Model** | TinyLlama 1.1B Q4_K_M — runs on 1 GB+ RAM |
| **UI** | Streamlit web app — opens in your browser, no X11 needed |
| **RAG** | Chunk docs → embed → chat with context |
| **Launcher** | Double-click icon on Desktop or App Menu (opens browser automatically) |
| **Offline** | 100% local — no API keys, no internet needed |

---

## Requirements

- Raspberry Pi 4 (2 GB+ recommended) or Pi 5
- Raspberry Pi OS (64-bit Bookworm or Bullseye)
- Internet connection **one time** during install (to download build deps)
- ~3 GB free disk space

> **Pi 3 / 1 GB RAM?** The installer will create a 2 GB swap file automatically.

---

## Step 1 — Copy the Project to Your Pi

### Option A: USB Drive
```bash
# On your Mac — copy to USB
cp -r ~/Desktop/tinyml /Volumes/YOUR_USB/

# On your Pi — paste from USB
cp -r /media/pi/YOUR_USB/tinyml ~/
```

### Option B: SCP over WiFi
```bash
# Run this on your Mac
scp -r ~/Desktop/tinyml pi@raspberrypi.local:~/
```

### Option C: Git
```bash
# On your Pi
git clone https://github.com/YOUR_USERNAME/tinyml ~/tinyml
```

---

## Step 2 — Run the Installer (One Time Only)

Open a terminal on your Pi and run:

```bash
cd ~/tinyml
bash raspberry-pi/install.sh
```

The installer will:
1. ✅ Detect your Pi model and RAM
2. ✅ Install Python, CMake, Conan via `apt`, and Streamlit via `pip`
3. ✅ Create a swap file if RAM < 2 GB
4. ✅ **Build the RAG binary for ARM** (takes 10–20 min, one time)
5. ✅ Set up the Python venv for document splitting
6. ✅ Create a **Desktop shortcut** and **App Menu entry**

> ☕ The build step takes 10–20 minutes. This only happens once.

---

## Step 3 — Launch the App

After installation, you can launch TinyML in any of these ways:

| Method | How |
|---|---|
| **Desktop icon** | Double-click `TinyML` on your Desktop (opens browser automatically) |
| **App Menu** | Applications → Education (or Science) → TinyML |
| **Terminal** | `cd ~/tinyml && python3 -m streamlit run app.py` |
| **Shell** | `bash ~/tinyml/raspberry-pi/launch.sh` |

Then open **http://localhost:8501** in a browser if it doesn't open automatically
(or `http://<pi-ip-address>:8501` from another device on the same network).

---

## Step 4 — Using the App

The app has three steps — run them in order:

### ① Split Document
- Click **Browse** next to "Knowledge file" and pick a `.txt` or `.pdf`
- Click **▶ Split Document**
- Takes a few seconds

### ② Generate Embeddings
- Click **▶ Generate Embeddings**
- This loads the embedding model and processes your document
- Takes 2–5 minutes on Pi 4

### ③ Chat
- Click **▶ Start Chat Session**
- Switch to the **💬 Chat** tab
- Type your question in the chat box and press **Enter**
- Wait 30–90 seconds for TinyLlama to respond

### 🚀 Run Full Pipeline
Click this button to run all three steps automatically in sequence.

---

## Models Included

| Model | File | Size | Role |
|---|---|---|---|
| TinyLlama 1.1B Q4_K_M | `tinyllama-1.1b-chat-v1.0.Q4_K_M.gguf` | 638 MB | LLM (chat) |
| nomic-embed-text-v1 F32 | `nomic-embed-text-v1.f32.gguf` | 523 MB | Embeddings |

Both files must be in the `models/` folder. They are already there if you copied the full project.

---

## Performance on Raspberry Pi

| Task | Pi 4 (4 GB) | Pi 4 (2 GB) | Pi 3 |
|---|---|---|---|
| Embedding (50 chunks) | ~2–3 min | ~3–4 min | ~8–10 min |
| First token (TinyLlama) | ~20–40 s | ~40–60 s | ~90–120 s |
| Full response | ~40–80 s | ~60–90 s | ~2–3 min |

> **Tip:** Reduce `Threads` to 2 if the Pi overheats (install a heatsink/fan).

---

## Troubleshooting

### App won't open (double-click does nothing)
```bash
# Make the launcher executable
chmod +x ~/Desktop/Edge\ SLM.desktop
# Or run directly, then open http://localhost:8501 in a browser
cd ~/tinyml && python3 -m streamlit run app.py
```

### "RAG binary not found" error
```bash
# Rebuild manually
cd ~/tinyml/rag
conan build . --build=missing
```

### Out of memory / system freezes
```bash
# Add more swap
sudo dphys-swapfile swapoff
sudo sed -i 's/CONF_SWAPSIZE=.*/CONF_SWAPSIZE=2048/' /etc/dphys-swapfile
sudo dphys-swapfile setup
sudo dphys-swapfile swapon
```

### TinyLlama gives slow/poor answers
- Ensure the **embedded_chunks.json** is current (re-run embedding after adding docs)
- Lower `max_tokens` in `models/model_config.json` to `200` for faster replies
- Reduce `Top-K` to `2` for less context (faster)

---

## Uninstall

To remove desktop shortcuts (keeps all files):
```bash
bash ~/tinyml/raspberry-pi/uninstall.sh
```

To remove everything:
```bash
rm -rf ~/tinyml
```

---

## File Structure

```
tinyml/
├── raspberry-pi/
│   ├── install.sh          ← Run this first!
│   ├── uninstall.sh        ← Cleanup shortcuts
│   ├── tinyml.desktop    ← App menu template
│   ├── icon.png            ← App icon
│   └── README_PI.md        ← This file
├── models/
│   ├── tinyllama-1.1b-chat-v1.0.Q4_K_M.gguf
│   ├── nomic-embed-text-v1.f32.gguf
│   ├── sample_knowledge.txt
│   └── model_config.json
├── rag/                    ← C++ RAG engine (built by install.sh)
├── scripts/                ← Python document splitter
└── app.py                  ← Streamlit web UI (same app on desktop, Pi, and Docker)
```
