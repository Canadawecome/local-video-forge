"""GPT-5.6 Sol Adapter for Local Video Forge v2.6.
Connects to OpenAI-compatible base URL (e.g. https://api.trouter.cloud/v1) with model gpt-5.6-sol.
Ensures zero native video/audio sent to model; strictly text and image inputs only.
"""
from __future__ import annotations

import base64
import json
import logging
import time
import urllib.request
import urllib.error
from typing import Any

from config import Config
from local_video_forge_sol_source_contracts_v2_6 import SolRequestContentV26

logger = logging.getLogger("sol_adapter")

class SolModelUnavailableError(Exception):
    pass

class SolAdapter:
    def __init__(self, base_url: str | None = None, api_key: str | None = None, model: str | None = None):
        self.base_url = (base_url or Config.OPENAI_BASE_URL).rstrip("/")
        self.api_key = api_key or Config.OPENAI_API_KEY
        self.model = model or Config.OPENAI_MODEL

    def create_chat_completion(
        self,
        messages: list[dict[str, Any]],
        response_format: dict[str, str] | None = None,
        temperature: float = 0.2,
        max_tokens: int = 4096,
        retries: int = 3,
    ) -> dict[str, Any]:
        """Calls /chat/completions endpoint with model gpt-5.6-sol."""
        url = f"{self.base_url}/chat/completions"
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if response_format:
            payload["response_format"] = response_format

        data = json.dumps(payload).encode("utf-8")
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "User-Agent": "LocalVideoForge/2.6 (GPT-5.6 Sol Only)",
        }

        last_err = None
        for attempt in range(1, retries + 1):
            try:
                req = urllib.request.Request(url, data=data, headers=headers, method="POST")
                with urllib.request.urlopen(req, timeout=90) as resp:
                    resp_body = resp.read().decode("utf-8")
                    return json.loads(resp_body)
            except urllib.error.HTTPError as e:
                err_text = e.read().decode("utf-8", errors="replace")
                last_err = e
                if e.code in (401, 403, 404):
                    raise SolModelUnavailableError(f"HTTP {e.code} from Sol endpoint: {err_text}") from e
                if e.code == 429:
                    time.sleep(2 * attempt)
                    continue
                time.sleep(1.5 * attempt)
            except Exception as e:
                last_err = e
                time.sleep(1.5 * attempt)

        raise RuntimeError(f"Failed calling GPT-5.6 Sol after {retries} attempts: {last_err}")

    def generate_structured_json(
        self,
        system_prompt: str,
        user_prompt: str,
        image_paths: list[tuple[float, str]] | None = None,
        max_tokens: int = 8192,
    ) -> dict[str, Any]:
        """Sends prompt and optional timestamped images to gpt-5.6-sol and returns parsed JSON.
        Complies strictly with local_video_forge_sol_source_contracts_v2_6.
        """
        user_content: list[dict[str, Any]] = []
        user_content.append({"type": "text", "text": user_prompt})

        # Attach frames if provided (validate with SolRequestContentV26)
        if image_paths:
            for sec, img_path in image_paths:
                SolRequestContentV26(type="input_text", text=f"FRAME at {sec:.2f}s")
                user_content.append({"type": "text", "text": f"\n[Visual Keyframe Evidence at {sec:.2f}s]"})
                try:
                    with open(img_path, "rb") as f:
                        b64 = base64.b64encode(f.read()).decode("ascii")
                    SolRequestContentV26(type="input_image", image_url=f"data:image/jpeg;base64,{b64}")
                    user_content.append({
                        "type": "image_url",
                        "image_url": {"url": f"data:image/jpeg;base64,{b64}", "detail": "low"}
                    })
                except Exception as e:
                    logger.warning(f"Could not encode image {img_path}: {e}")

        messages = [
            {"role": "system", "content": system_prompt + "\nYou MUST reply with a single valid JSON object only. Do NOT output any thinking, reasoning, chain-of-thought, commentary, or markdown fences. Start your response directly with '{' and end with '}'."},
            {"role": "user", "content": user_content}
        ]

        resp = self.create_chat_completion(
            messages=messages,
            response_format={"type": "json_object"},
            max_tokens=max_tokens,
        )

        choice = resp.get("choices", [{}])[0]
        msg = choice.get("message", {})
        raw_text = msg.get("content") or msg.get("reasoning_content") or ""
        
        # Clean any accidental markdown fence if present
        cleaned = raw_text.strip()
        if cleaned.startswith("```json"):
            cleaned = cleaned[7:]
        elif cleaned.startswith("```"):
            cleaned = cleaned[3:]
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3]
        cleaned = cleaned.strip()

        # Try 1: standard json.loads with strict=False
        try:
            return json.loads(cleaned, strict=False)
        except Exception:
            pass

        # Try 2: Find '{' matching real JSON root object (key: value)
        import re
        cand_matches = list(re.finditer(r'\{(?:\s*"[A-Za-z0-9_]+"\s*:)', cleaned))
        for cm in cand_matches:
            c_start = cm.start()
            c_end = cleaned.rfind("}")
            if c_end > c_start:
                try:
                    return json.loads(cleaned[c_start:c_end+1], strict=False)
                except Exception:
                    pass

        # Try 3: slice outermost { ... }
        s_idx = cleaned.find("{")
        e_idx = cleaned.rfind("}")
        if s_idx != -1 and e_idx > s_idx:
            try:
                return json.loads(cleaned[s_idx:e_idx+1], strict=False)
            except Exception:
                pass

        # Try 3: Regex field extraction for structured fields
        import re
        res: dict[str, Any] = {}
        for key in ["title_en", "story_angle", "narration_mode", "en_script_text", "tts_text", "source_summary", "global_opus_prompt_en", "primary_craft_process", "description_en"]:
            m = re.search(rf'"{key}"\s*:\s*"(.*?)(?<!\\)"', cleaned, re.DOTALL)
            if m:
                res[key] = m.group(1).replace("\\n", "\n").replace('\\"', '"')

        win_match = re.search(r'"narration_windows"\s*:\s*(\[.*?\])', cleaned, re.DOTALL)
        if win_match:
            try:
                res["narration_windows"] = json.loads(win_match.group(1), strict=False)
            except Exception:
                pass

        arr_match = re.search(r'"(visible_actions|audio_events|hashtags)"\s*:\s*(\[.*?\])', cleaned, re.DOTALL)
        if arr_match:
            try:
                res[arr_match.group(1)] = json.loads(arr_match.group(2), strict=False)
            except Exception:
                pass

        if res:
            return res

        raise ValueError(f"Failed to parse JSON from Sol response: {raw_text[:300]}...")
