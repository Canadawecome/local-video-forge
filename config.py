"""Configuration manager for Local Video Forge v2.6.
Reads settings from environment variables or .env file.
"""
from __future__ import annotations

import os
from pathlib import Path
from dotenv import load_dotenv

BUNDLE_DIR = Path(__file__).resolve().parent
load_dotenv(BUNDLE_DIR / ".env", override=True)

# Ensure FFmpeg and local venv scripts are discoverable in PATH
extra_paths = [
    str(BUNDLE_DIR / ".venv" / "Scripts"),
    r"C:\Users\ADMIN\AppData\Local\Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-9.0.2-full_build\bin",
]
current_path = os.environ.get("PATH", "")
for ep in extra_paths:
    if os.path.exists(ep) and ep not in current_path:
        current_path = f"{ep};{current_path}"
os.environ["PATH"] = current_path


class Config:
    # Base paths
    BUNDLE_ROOT: Path = BUNDLE_DIR
    DATA_DIR: Path = Path(os.getenv("LVF_DATA_DIR", str(BUNDLE_DIR / "data")))
    
    # OpenAI / Trouter Cloud
    OPENAI_BASE_URL: str = os.getenv("OPENAI_BASE_URL", "https://api.trouter.cloud/v1").rstrip("/")
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")
    OPENAI_MODEL: str = os.getenv("OPENAI_MODEL", "gpt-5.6-sol")
    MAX_OPENAI_CONCURRENCY: int = int(os.getenv("MAX_OPENAI_CONCURRENCY", "2"))
    
    # OpusClip
    OPUSCLIP_API_KEY: str = os.getenv("OPUSCLIP_API_KEY", "")
    OPUSCLIP_BASE_URL: str = os.getenv("OPUSCLIP_BASE_URL", "https://api.opus.pro/api").rstrip("/")
    
    # ElevenLabs
    ELEVENLABS_API_KEY: str = os.getenv("ELEVENLABS_API_KEY", "")
    ELEVENLABS_VOICE_ID: str = os.getenv("ELEVENLABS_VOICE_ID", "QIhD5ivPGEoYZQDocuHI") # Adam - Engineering Professor
    ELEVENLABS_MODEL_ID: str = os.getenv("ELEVENLABS_MODEL_ID", "eleven_multilingual_v2")
    
    # Policies
    SOURCE_INGEST_MODE: str = os.getenv("SOURCE_INGEST_MODE", "METADATA_ONLY")
    ENABLE_AUTHORIZED_ORIGINAL_DOWNLOAD: bool = os.getenv("ENABLE_AUTHORIZED_ORIGINAL_DOWNLOAD", "false").lower() == "true"
    MAX_FRAMES_PER_CLIP: int = int(os.getenv("MAX_FRAMES_PER_CLIP", "45"))
    MAX_PROVIDER_SPEND_USD: float = float(os.getenv("MAX_PROVIDER_SPEND_USD", "10.0"))
    
    # Whisper & Transcript v2.8
    WHISPER_MODEL_SIZE: str = os.getenv("WHISPER_MODEL_SIZE", "base")
    TRANSCRIPT_ENGINE: str = os.getenv("TRANSCRIPT_ENGINE", "opus_first")
    FALLBACK_ASR: str = os.getenv("FALLBACK_ASR", "faster_whisper")
    SOURCE_LANGUAGE: str = os.getenv("SOURCE_LANGUAGE", "de")
    
    # Hybrid Audio & ASMR v2.8
    AUDIO_MODE: str = os.getenv("AUDIO_MODE", "SPEECH_STEM_REPLACEMENT")
    AUDIO_SEPARATOR_PREFERENCE: list[str] = ["sam_audio_local", "audioshake_api_if_allowed"]
    FALLBACK_IF_SEPARATOR_FAILS: str = os.getenv("FALLBACK_IF_SEPARATOR_FAILS", "NEEDS_AUDIO_REVIEW")
    GERMAN_SPEECH_DUCK_DB: float = float(os.getenv("GERMAN_SPEECH_DUCK_DB", "-24.0"))
    COMMENTARY_DUCK_DB: float = float(os.getenv("COMMENTARY_DUCK_DB", "-7.0"))
    DUCK_ATTACK_MS: int = int(os.getenv("DUCK_ATTACK_MS", "65"))
    DUCK_RELEASE_MS: int = int(os.getenv("DUCK_RELEASE_MS", "145"))
    VOICE_GAIN_DB: float = float(os.getenv("VOICE_GAIN_DB", "0.0"))
    PEAK_CEILING_DBFS: float = float(os.getenv("PEAK_CEILING_DBFS", "-1.0"))
    MAX_TTS_OVERRUN_SEC: float = float(os.getenv("MAX_TTS_OVERRUN_SEC", "0.10"))
    PROTECTED_ASMR_REQUIRED: bool = True
    
    # Server
    HOST: str = os.getenv("HOST", "127.0.0.1")
    PORT: int = int(os.getenv("PORT", "8000"))

    @classmethod
    def ensure_dirs(cls) -> None:
        cls.DATA_DIR.mkdir(parents=True, exist_ok=True)
        (cls.DATA_DIR / "sources").mkdir(parents=True, exist_ok=True)

Config.ensure_dirs()
