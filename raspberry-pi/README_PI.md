# ⚡ Edge SLM — Raspberry Pi Edition

> **Local AI chat on your Pi — no internet, no cloud, fully private.**
> Uses **TinyLlama 1.1B** (smallest model, ~638 MB) with a RAG pipeline
> for grounded, document-aware answers.

---

## What You Get

| Feature | Details |
|---|---|
| **Model** | TinyLlama 1.1B Q4_K_M — runs on 1 GB+ RAM |
| **UI** | Tkinter desktop app, optimised for Pi touchscreen |
| **RAG** | Chunk docs → embed → chat with context |
| **Launcher** | Double-click icon on Desktop or App Menu |
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
cp -r ~/Desktop/edge-slm-main /Volumes/YOUR_USB/

# On your Pi — paste from USB
cp -r /media/pi/YOUR_USB/edge-slm-main ~/
```

### Option B: SCP over WiFi
```bash
# Run this on your Mac
scp -r ~/Desktop/edge-slm-main pi@raspberrypi.local:~/
```

### Option C: Git
```bash
# On your Pi
git clone https://github.com/YOUR_USERNAME/edge-slm-main ~/edge-slm-main
```

---

## Step 2 — Run the Installer (One Time Only)

Open a terminal on your Pi and run:

```bash
cd ~/edge-slm-main
bash raspberry-pi/install.sh
```

The installer will:
1. ✅ Detect your Pi model and RAM
2. ✅ Install Python, Tkinter, CMake, Conan via `apt`
3. ✅ Create a swap file if RAM < 2 GB
4. ✅ **Build the RAG binary for ARM** (takes 10–20 min, one time)
5. ✅ Set up the Python venv for document splitting
6. ✅ Create a **Desktop shortcut** and **App Menu entry**

> ☕ The build step takes 10–20 minutes. This only happens once.

---

## Step 3 — Launch the App

After installation, you can launch Edge SLM in any of these ways:

| Method | How |
|---|---|
| **Desktop icon** | Double-click `Edge SLM` on your Desktop |
| **App Menu** | Applications → Education (or Science) → Edge SLM |
| **Terminal** | `python3 ~/edge-slm-main/raspberry-pi/edge-slm-pi.py` |
| **Shell** | `bash ~/edge-slm-main/raspberry-pi/launch.sh` |

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
- Type your question and press **Enter** or **Send ↩**
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
# Or run directly
python3 ~/edge-slm-main/raspberry-pi/edge-slm-pi.py
```

### "RAG binary not found" error
```bash
# Rebuild manually
cd ~/edge-slm-main/rag
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
bash ~/edge-slm-main/raspberry-pi/uninstall.sh
```

To remove everything:
```bash
rm -rf ~/edge-slm-main
```

---

## File Structure

```
edge-slm-main/
├── raspberry-pi/
│   ├── install.sh          ← Run this first!
│   ├── uninstall.sh        ← Cleanup shortcuts
│   ├── edge-slm-pi.py      ← Pi-optimised UI
│   ├── edge-slm.desktop    ← App menu template
│   ├── icon.png            ← App icon
│   └── README_PI.md        ← This file
├── models/
│   ├── tinyllama-1.1b-chat-v1.0.Q4_K_M.gguf
│   ├── nomic-embed-text-v1.f32.gguf
│   ├── sample_knowledge.txt
│   └── model_config.json
├── rag/                    ← C++ RAG engine (built by install.sh)
├── scripts/                ← Python document splitter
└── ui.py                   ← Original macOS UI
```
