#!/usr/bin/env python3
"""
Runtime proof helper (no network):
Reads a real episode script_state.json and prints EXACT checkpoint tags:
- FDA_RAW_VERSION  (right after "LLM JSON parse" equivalent: stored response_json)
- FDA_FINAL_VERSION (right before validate_fda_hard_v27)

This uses the same validators/postprocessors from backend/, but avoids any LLM call.
"""

import json
import os
import sys
from typing import Any, Dict, Optional

REPO_ROOT = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR = os.path.join(REPO_ROOT, "backend")
sys.path.insert(0, BACKEND_DIR)


def _get_version(obj: Any) -> Optional[str]:
    if isinstance(obj, dict) and isinstance(obj.get("shot_plan"), dict):
        return obj["shot_plan"].get("version")
    if isinstance(obj, dict):
        return obj.get("version")
    return None


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: python3 run_fda_version_checkpoints.py ep_<id>")
        return 2

    episode_id = sys.argv[1].strip()
    state_path = os.path.join(REPO_ROOT, "projects", episode_id, "script_state.json")
    if not os.path.exists(state_path):
        print(f"ERROR: script_state.json not found: {state_path}")
        return 2

    with open(state_path, "r", encoding="utf-8") as f:
        state: Dict[str, Any] = json.load(f)

    fdr = state.get("footage_director_raw_output") if isinstance(state.get("footage_director_raw_output"), dict) else {}
    raw_wrapper = fdr.get("response_json")
    raw_version = _get_version(raw_wrapper)

    # cached source (we are reading stored response_json from disk)
    print(f"FDA_LLM_SOURCE episode_id={episode_id} source=cached")

    # checkpoint 1 (raw)
    print(f"FDA_RAW_VERSION episode_id={episode_id} raw_version={raw_version} final_version=PENDING")

    # Construct the wrapper we would validate (prefer shot_plan_saved if present, else response_json)
    final_wrapper = fdr.get("shot_plan_saved") or raw_wrapper
    # v2.7 coercion kill-switch (should remove VERSION_MISMATCH)
    from footage_director import coerce_fda_v27_version_inplace  # noqa
    coerce_fda_v27_version_inplace(final_wrapper, episode_id=episode_id)

    final_version = _get_version(final_wrapper)

    # checkpoint 2 (final-before-validate)
    print(f"FDA_FINAL_VERSION episode_id={episode_id} raw_version={raw_version} final_version={final_version}")

    # Run the same hard validator used by pipeline (v2.7 strict).
    from footage_director import validate_fda_hard_v27  # noqa

    # tts_ready_package for validator coverage checks
    tts_pkg = state.get("tts_ready_package") or {}
    try:
        validate_fda_hard_v27(final_wrapper, tts_pkg, episode_id=episode_id)
        print("VALIDATION: PASS")
        return 0
    except Exception as e:
        print(f"VALIDATION: FAIL: {e}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())


