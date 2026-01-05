import json
import os
import tempfile
from datetime import datetime, timezone


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


class ProjectStore:
    """
    FS-based per-episode store.
    Source of truth: podcasts/projects/<episode_id>/script_state.json
    """

    def __init__(self, base_projects_dir: str):
        self.base_projects_dir = base_projects_dir
        os.makedirs(self.base_projects_dir, exist_ok=True)

    def episode_dir(self, episode_id: str) -> str:
        return os.path.join(self.base_projects_dir, episode_id)

    def script_state_path(self, episode_id: str) -> str:
        return os.path.join(self.episode_dir(episode_id), "script_state.json")

    def exists(self, episode_id: str) -> bool:
        return os.path.exists(self.script_state_path(episode_id))

    def read_script_state(self, episode_id: str) -> dict:
        path = self.script_state_path(episode_id)
        if not os.path.exists(path):
            raise FileNotFoundError(path)
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    def write_script_state(self, episode_id: str, state: dict) -> None:
        """
        Atomic write: write to temp file in same dir, then replace.
        Always updates updated_at (UTC ISO) unless caller already set it.
        """
        episode_dir = self.episode_dir(episode_id)
        os.makedirs(episode_dir, exist_ok=True)

        if "updated_at" not in state:
            state["updated_at"] = _now_iso()

        path = self.script_state_path(episode_id)
        fd, tmp_path = tempfile.mkstemp(prefix="script_state_", suffix=".json", dir=episode_dir)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(state, f, ensure_ascii=False, indent=2)
                f.write("\n")
            os.replace(tmp_path, path)
        finally:
            try:
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)
            except Exception:
                pass





