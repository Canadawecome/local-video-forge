"""Main entry point for Local Video Forge v2.6.
If run without arguments, launches the Web Dashboard Server.
Otherwise, delegates to cli.py.
"""
from __future__ import annotations

import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

def main():
    if len(sys.argv) == 1:
        # Default: launch server
        import uvicorn
        from config import Config
        print(f"\n=======================================================")
        print(f"  Local Video Forge v2.6 — GPT-5.6 Sol Only")
        print(f"  OpenAI Base URL: {Config.OPENAI_BASE_URL}")
        print(f"  OpenAI Model:    {Config.OPENAI_MODEL}")
        print(f"  ElevenLabs Voice: Adam ({Config.ELEVENLABS_VOICE_ID})")
        print(f"  Web Dashboard:   http://{Config.HOST}:{Config.PORT}")
        print(f"=======================================================\n")
        uvicorn.run("server:app", host=Config.HOST, port=Config.PORT, reload=False)
    else:
        from cli import main as cli_main
        cli_main()

if __name__ == "__main__":
    main()
