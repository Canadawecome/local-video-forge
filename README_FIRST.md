# Local Video Forge v3.1 Clean ASMR

Portable source bundle for the Local Video Forge pipeline and web dashboard.
Generated media, local databases, caches, virtual environments, and API secrets are intentionally excluded.

## Requirements

- Python 3.11 or 3.12
- FFmpeg (`ffmpeg` and `ffprobe` must be available on `PATH`)
- OpenAI-compatible, OpusClip, and ElevenLabs API credentials

## Install on a new macOS/Linux machine

```bash
git clone <PRIVATE_REPOSITORY_URL>
cd local-video-forge
chmod +x setup.sh
./setup.sh
```

Open `.env`, add your API keys, then launch the dashboard:

```bash
.venv/bin/python main.py
```

Open <http://127.0.0.1:8000>.

To run the CLI instead:

```bash
.venv/bin/python main.py run "YOUTUBE_URL"
```

## Windows setup

Install Python 3.11/3.12 and FFmpeg, then run:

```powershell
py -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
Copy-Item .env.example .env
.venv\Scripts\python main.py
```

## Configuration

Copy `.env.example` to `.env` and set at least:

- `OPENAI_API_KEY`
- `OPUSCLIP_API_KEY`
- `ELEVENLABS_API_KEY`

Never commit `.env`. Runtime files are created under `data/` automatically.

## Tests

```bash
.venv/bin/python -m pip install -r requirements-dev.txt
.venv/bin/python -m pytest -q
```

The detailed version contracts and migration notes remain in the repository for reference.
