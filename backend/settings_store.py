import json
import os
import tempfile
from datetime import datetime, timezone
from typing import Optional

from dotenv import load_dotenv


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


class SettingsStore:
    """
    FS-backed global settings store.
    - LLM defaults: podcasts/config/llm_defaults.json
    - OpenAI key: backend/.env (server-side only; never returned)
    """

    def __init__(self, base_dir: str, backend_dir: str):
        self.base_dir = base_dir
        self.config_dir = os.path.join(self.base_dir, "config")
        self.backend_dir = backend_dir
        os.makedirs(self.config_dir, exist_ok=True)

    def llm_defaults_path(self) -> str:
        return os.path.join(self.config_dir, "llm_defaults.json")
    
    def global_preferences_path(self) -> str:
        """Path to global user preferences (music gain, etc.)"""
        return os.path.join(self.config_dir, "global_preferences.json")

    def read_llm_defaults(self) -> dict:
        path = self.llm_defaults_path()
        if not os.path.exists(path):
            defaults = self._default_llm_defaults()
            self.write_llm_defaults(defaults)
            return defaults
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    def write_llm_defaults(self, defaults: dict) -> None:
        path = self.llm_defaults_path()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        # add metadata fields
        if isinstance(defaults, dict):
            defaults = {**defaults, "updated_at": _now_iso()}
        fd, tmp_path = tempfile.mkstemp(prefix="llm_defaults_", suffix=".json", dir=os.path.dirname(path))
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(defaults, f, ensure_ascii=False, indent=2)
                f.write("\n")
            os.replace(tmp_path, path)
        finally:
            try:
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)
            except Exception:
                pass

    def _default_llm_defaults(self) -> dict:
        base = {"provider": "openai", "model": "gpt-4o", "temperature": 0.4, "prompt_template": None}
        return {
            "research": {**base},
            # Narrative should be less creative by default to reduce extrapolation beyond claims.
            "narrative": {**base, "temperature": 0.3},
            "validation": {**base},
            "tts_format": {**base},
            "footage_director": {"provider": "openai", "model": "gpt-4o-mini", "temperature": 0.2, "prompt_template": None},
            "updated_at": _now_iso(),
        }

    def _env_key_configured(self, env_var: str) -> bool:
        val = (os.getenv(env_var) or "").strip()
        if not val:
            return False
        # Farm-proof sanity checks: avoid treating wrong-key-in-wrong-slot as "configured"
        if env_var == "OPENAI_API_KEY":
            # OpenRouter keys often start with sk-or-... and MUST NOT be used for OpenAI
            if val.startswith("sk-or-"):
                return False
        if env_var == "OPENROUTER_API_KEY":
            # OpenRouter keys typically start with sk-or-...
            if not val.startswith("sk-or-"):
                return False
        return True

    def _save_env_key(self, env_var: str, api_key: str, required_field_name: str) -> None:
        """
        Stores API key server-side in backend/.env and loads it into current process env.
        Never returns the key.
        """
        api_key = (api_key or "").strip()
        if not api_key:
            raise ValueError(f"{required_field_name} je povinné")

        dotenv_path = os.path.join(self.backend_dir, ".env")
        lines = []
        if os.path.exists(dotenv_path):
            with open(dotenv_path, "r", encoding="utf-8") as f:
                lines = f.read().splitlines()

        found = False
        new_lines = []
        for line in lines:
            if line.startswith(f"{env_var}="):
                new_lines.append(f"{env_var}={api_key}")
                found = True
            else:
                new_lines.append(line)
        if not found:
            new_lines.append(f"{env_var}={api_key}")

        with open(dotenv_path, "w", encoding="utf-8") as f:
            f.write("\n".join(new_lines).rstrip() + "\n")

        # Load into current process environment
        load_dotenv(dotenv_path, override=True)

    def openai_key_configured(self) -> bool:
        return self._env_key_configured("OPENAI_API_KEY")

    def save_openai_key(self, api_key: str) -> None:
        api_key = (api_key or "").strip()
        if api_key.startswith("sk-or-"):
            raise ValueError("Tohle vypadá jako OpenRouter klíč (sk-or-...). Pro OpenAI vložte OpenAI API key.")
        self._save_env_key("OPENAI_API_KEY", api_key, "openai_api_key")

    def elevenlabs_key_configured(self) -> bool:
        return self._env_key_configured("ELEVENLABS_API_KEY")

    def save_elevenlabs_key(self, api_key: str) -> None:
        self._save_env_key("ELEVENLABS_API_KEY", api_key, "elevenlabs_api_key")

    def youtube_key_configured(self) -> bool:
        return self._env_key_configured("YOUTUBE_API_KEY")

    def save_youtube_key(self, api_key: str) -> None:
        self._save_env_key("YOUTUBE_API_KEY", api_key, "youtube_api_key")

    def openrouter_key_configured(self) -> bool:
        return self._env_key_configured("OPENROUTER_API_KEY")

    def save_openrouter_key(self, api_key: str) -> None:
        api_key = (api_key or "").strip()
        if api_key and not api_key.startswith("sk-or-"):
            raise ValueError("OpenRouter API klíč musí začínat 'sk-or-...'.")
        self._save_env_key("OPENROUTER_API_KEY", api_key, "openrouter_api_key")
    
    # === Global Preferences ===
    
    def read_global_preferences(self) -> dict:
        """Read global user preferences (music gain, etc.)"""
        path = self.global_preferences_path()
        if not os.path.exists(path):
            defaults = self._default_global_preferences()
            self.write_global_preferences(defaults)
            return defaults
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    
    def write_global_preferences(self, prefs: dict) -> None:
        """Write global user preferences"""
        path = self.global_preferences_path()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        if isinstance(prefs, dict):
            prefs = {**prefs, "updated_at": _now_iso()}
        fd, tmp_path = tempfile.mkstemp(prefix="global_prefs_", suffix=".json", dir=os.path.dirname(path))
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(prefs, f, ensure_ascii=False, indent=2)
                f.write("\n")
            os.replace(tmp_path, path)
        finally:
            try:
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)
            except Exception:
                pass
    
    def _default_global_preferences(self) -> dict:
        """Default global preferences"""
        return {
            "music_bg_gain_db": -18.0,  # Background music gain in dB
            "updated_at": _now_iso(),
        }
    
    def get_music_bg_gain_db(self) -> float:
        """Get the last used music background gain (in dB)"""
        prefs = self.read_global_preferences()
        return float(prefs.get("music_bg_gain_db", -18.0))
    
    def set_music_bg_gain_db(self, gain_db: float) -> None:
        """Save music background gain for future use"""
        gain_db = max(-60.0, min(0.0, float(gain_db)))  # Clamp to safe range
        prefs = self.read_global_preferences()
        prefs["music_bg_gain_db"] = gain_db
        self.write_global_preferences(prefs)


