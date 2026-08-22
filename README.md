# 🌈 Gigmo Giggles: Automated Kids Educational YouTube Video Creator

[![Daily Kids YouTube Episode Creator](https://github.com/your-org/gigmo-giggles/actions/workflows/daily_episode.yml/badge.svg)](.github/workflows/daily_episode.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Code Style: Clean](https://img.shields.io/badge/code%20style-modular-green.svg)](src/)

**Gigmo Giggles** is an open-source, automated educational cartoon production pipeline that produces 1 complete, kid-safe, colorful animated episode every day.

The system uses **Google Gemini as Creative Director** (via the official `google-genai` Python SDK), FFmpeg for dynamic Ken Burns-style animated video assembly, open/free TTS and image generation adapters, child-safety filtering, and GitHub Actions for daily scheduled orchestration.

---

## 🌟 Original Characters

Visual descriptors and voice profiles are canonically locked to ensure consistent appearances and personalities across every episode:

| Character | Type | Personality | Canonical Visual Description | Voice Style |
| :--- | :--- | :--- | :--- | :--- |
| **🐻 Bobo** | Cartoon Bear | Curious, funny, enthusiastic | Chubby, smiling honey-brown teddy bear with round fuzzy ears, big friendly sparkling eyes, and a sunny yellow neckerchief. | Warm, playful, friendly |
| **🦊 Luna** | Cartoon Fox | Clever, thoughtful, helpful | Bright orange fox with creamy-white chest fur, inquisitive amber eyes, fluffy white-tipped tail, and a teal explorer vest. | Energetic, clever, cheerful |
| **🤖 Milo** | Cartoon Robot | Energetic, tech-whiz, asks questions | Sky-blue compact robot with rounded corners, glowing lime-green screen eyes, yellow antenna light, and roller wheels. | Robotic but cute, melodic |

---

## ⚙️ Pipeline Architecture

```
┌──────────────┐     ┌────────────────────────┐     ┌──────────────────────┐
│ Daily Topic  │ ──> │ Gemini Creative Dir    │ ──> │ Screenplay Script    │
│  Selection   │     │ (google-genai SDK)     │     │      (script.md)     │
└──────────────┘     └────────────────────────┘     └──────────────────────┘
                                                               │
┌──────────────────────┐     ┌────────────────────────┐        ▼
│ Scene Image Frames   │ <── │ Storyboard Generator   │ <──────┘
│ (PIL Comic / HF SD)  │     │   (storyboard.json)    │
└──────────────────────┘     └────────────────────────┘
          │                               │
          ▼                               ▼
┌──────────────────────┐     ┌────────────────────────┐     ┌──────────────────────┐
│ Character Voice TTS  │     │ Subtitles Generation   │     │ FFmpeg Ken Burns     │
│ (gTTS / Tone / WAV)  │ ──> │   (SRT / WebVTT)       │ ──> │ Video Assembly       │
└──────────────────────┘     └────────────────────────┘     └──────────────────────┘
                                                                       │
┌──────────────────────┐     ┌────────────────────────┐                ▼
│ Quality Gate Pass    │ <── │ YouTube SEO & Chapters │ <── ┌──────────────────────┐
│ & Artifacts Export   │     │ (youtube_metadata.json)│     │ YouTube Thumbnail    │
└──────────────────────┘     └────────────────────────┘     │   (thumbnail.png)    │
                                                            └──────────────────────┘
```

---

## 📁 Repository Structure

```
Gigmo Giggles/
├── .github/
│   └── workflows/
│       └── daily_episode.yml          # Daily 06:00 UTC schedule & manual workflow_dispatch
├── config/
│   ├── characters.json               # Canonical visual descriptions for Bobo, Luna, Milo
│   ├── topics.json                   # Curated educational topics catalog
│   ├── topic_history.json           # Tracks used topics & timestamps
│   └── settings.json                 # Age (6-9), video formats (16:9, 9:16), durations
├── prompts/
│   ├── creative_director.md          # Master Gemini system prompt & JSON schema
│   ├── script.md                     # Screenplay pacing and dialogue rules
│   ├── storyboard.md                 # Storyboard & camera motion directives
│   ├── image.md                      # 2D cartoon cel-shaded image prompting rules
│   ├── video.md                      # FFmpeg Ken Burns zoom/pan/transition rules
│   ├── voice.md                      # Character voice acting guidelines
│   └── youtube.md                    # YouTube SEO, tags, description & chapter format
├── src/
│   ├── __init__.py
│   ├── main.py                       # CLI orchestrator & run status manager
│   ├── gemini_creator.py             # Google GenAI client with auto-repair loop
│   ├── topic_manager.py              # Non-repeating topic selector & auto-replenisher
│   ├── script_generator.py           # Screenplay markdown formatter
│   ├── storyboard_generator.py       # Storyboard builder & timing planner
│   ├── image_generator.py            # Multi-provider (HuggingFace / PIL Comic procedural)
│   ├── voice_generator.py            # Character TTS (gTTS / tone synthesis / manifest)
│   ├── video_generator.py            # FFmpeg video assembler with Ken Burns motion
│   ├── subtitle_generator.py         # Subtitle generator (.srt and .vtt)
│   ├── thumbnail_generator.py        # YouTube high-contrast thumbnail generator
│   ├── youtube_metadata.py           # YouTube metadata, chapters, tags & Shorts ideas
│   ├── youtube_publisher.py          # Future YouTube API upload stub (v1 disabled)
│   ├── validator.py                  # Child safety filter & Quality Gate checks
│   └── utils.py                      # JSON, file helpers, FFmpeg detector & WAV synthesizers
├── assets/
│   ├── characters/                   # Character reference graphics
│   ├── backgrounds/                  # Backdrop textures
│   ├── music/                        # Royalty-free cheerful audio loops
│   └── sounds/                       # Sound effects (pops, chimes, whooshes)
├── episodes/
│   └── YYYY-MM-DD/                   # Daily episode output bundle
│       ├── episode.json              # Full structured Gemini output
│       ├── script.md                 # Screenplay markdown
│       ├── storyboard.json           # Visual and camera storyboard
│       ├── images/                   # Scene image frames (scene_01.png, ...)
│       ├── audio/                    # Voice audio tracks (scene_01_audio.wav, ...)
│       ├── video/                    # Final assembled video (episode.mp4)
│       ├── subtitles/                # Synchronized captions (episode.srt, episode.vtt)
│       ├── thumbnail/                # Eye-catching graphic (thumbnail.png)
│       ├── youtube_metadata.json     # Title, description, tags, chapters, shorts
│       ├── pipeline.log              # Execution log file
│       └── run_status.json           # Step-by-step progress & success tracker
├── tests/                            # 100% passing automated test suite
├── requirements.txt                  # Python dependencies
├── .env.example                      # Environment variables template
├── .gitignore                        # Git ignore rules
├── README.md                         # Project documentation
└── LICENSE                           # MIT License
```

---

## 🚀 Quickstart & Local Setup

### 1. Clone Repository & Setup Virtual Environment
```bash
git clone https://github.com/your-org/gigmo-giggles.git
cd gigmo-giggles

python -m venv venv
# On Windows:
.\venv\Scripts\activate
# On Linux / macOS:
source venv/bin/activate

pip install -r requirements.txt
```

### 2. Configure Environment Variables
Copy `.env.example` to `.env`:
```bash
cp .env.example .env
```
Edit `.env` and set your Google Gemini API key:
```ini
GEMINI_API_KEY=AIzaSy...your_gemini_api_key...
GEMINI_MODEL=gemini-2.5-flash
```

*(Note: You can get a free Gemini API key at [Google AI Studio](https://aistudio.google.com/)).*

---

## 🎬 Running Locally

### Standard Run (Auto-Selects Next Unused Topic)
```bash
python -m src.main
```

### Force a Specific Topic
```bash
python -m src.main --topic "Why Does Rain Happen?"
```

### Offline / Mock Mode (Zero API Usage & Zero Cost)
```bash
python -m src.main --mock
```

### Specify Episode Date Identifier
```bash
python -m src.main --date 2026-08-22 --mock
```

---

## 🧪 Running Automated Tests

Run the complete test suite locally:
```bash
pytest -v
```

The automated test suite verifies:
- ✅ Gemini structured JSON parsing, Pydantic schema validation, and auto-repair
- ✅ Child-safety filter detecting and rejecting violence, gore, weapons, and dangerous actions
- ✅ Non-repeating topic selection and automatic topic catalog replenishment
- ✅ Canonical character visual description persistence (Bobo, Luna, Milo)
- ✅ Image, Voice, Subtitle, Thumbnail, and Video generator executions
- ✅ Quality gate verification of all required output files
- ✅ Graceful failure recovery and `run_status.json` recording

---

## 🤖 GitHub Actions Daily Automation

The workflow `.github/workflows/daily_episode.yml` automatically triggers **every day at 06:00 UTC**.

### Required GitHub Secrets
In your GitHub repository settings under **Settings > Secrets and variables > Actions**, add:

| Secret Name | Required | Description |
| :--- | :--- | :--- |
| `GEMINI_API_KEY` | **Yes** | Your Google Gemini API Key from AI Studio |
| `GEMINI_MODEL` | Optional | Custom Gemini model (defaults to `gemini-2.5-flash`) |
| `HF_TOKEN` | Optional | Hugging Face token for remote AI image generation |

### Triggering the GitHub Action Manually
1. Go to your repository on GitHub.
2. Click the **Actions** tab.
3. Select **Daily Kids YouTube Episode Creator** in the left sidebar.
4. Click **Run workflow**, enter an optional topic or enable mock mode, and click **Run workflow**.
5. When finished, download the **`daily-episode-XXX`** artifact containing the complete video, screenplay, thumbnail, subtitles, and metadata bundle.

---

## 💡 Free-First Design & Service Limitations

This repository was designed with a **free-first philosophy**:
1. **Google Gemini API**: Free tier available on Google AI Studio provides more than enough quota for 1 episode per day.
2. **Video Assembly**: 100% free and open-source using FFmpeg Ken Burns zoom/pan/transitions.
3. **Voice Audio / TTS**: Uses free `gTTS` or offline audio tone synthesis; saves complete dialogue to `voice_manifest.json`.
4. **Image Generation**: Includes a built-in PIL procedural comic cartoon generator for instant free rendering, with an adapter for Hugging Face Inference models.
5. **No Commercial Subscriptions Required**: The pipeline can run entirely on free GitHub Actions runners.

---

## 📤 Pushing to GitHub

To initialize git and push to your new GitHub repository:
```bash
git init
git add .
git commit -m "Initial commit: Gigmo Giggles automated kids YouTube creator"
git branch -M main
git remote add origin https://github.com/your-username/gigmo-giggles.git
git push -u origin main
```

---

## 📄 License
Released under the [MIT License](LICENSE).
