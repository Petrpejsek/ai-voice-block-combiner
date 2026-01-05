#!/usr/bin/env python3
"""
Minimal step runner for debugging individual pipeline steps.

Usage (from repo root):
  python backend/run_step.py --episode ep_... --step AAR --verbose
"""

import argparse
import sys
from pathlib import Path

from project_store import ProjectStore
from archive_asset_resolver import resolve_shot_plan_assets


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--episode", required=True, help="Episode ID, e.g. ep_9f2ea4ca9f19")
    p.add_argument("--step", required=True, choices=["AAR"], help="Pipeline step to run")
    p.add_argument("--verbose", action="store_true", help="Enable verbose per-query audit logs")
    return p.parse_args()


def main() -> int:
    args = _parse_args()

    repo_root = Path(__file__).resolve().parent.parent
    projects_dir = repo_root / "projects"
    store = ProjectStore(str(projects_dir))

    episode_id = args.episode
    if not store.exists(episode_id):
        print(f"❌ Episode not found: {episode_id} (expected {store.script_state_path(episode_id)})")
        return 2

    state = store.read_script_state(episode_id)

    if args.step == "AAR":
        shot_plan = state.get("shot_plan")
        if not shot_plan:
            print("❌ Missing shot_plan in script_state.json (run FDA first)")
            return 3

        tts_ready_package = state.get("tts_ready_package")
        episode_dir = Path(store.episode_dir(episode_id))

        cache_dir = episode_dir / "archive_cache"
        manifest_path = episode_dir / "archive_manifest.json"
        voiceover_dir = episode_dir / "voiceover"

        cache_dir.mkdir(parents=True, exist_ok=True)

        _, out_path = resolve_shot_plan_assets(
            shot_plan=shot_plan,
            cache_dir=str(cache_dir),
            manifest_output_path=str(manifest_path),
            throttle_delay_sec=0.5,
            tts_ready_package=tts_ready_package,
            voiceover_dir=str(voiceover_dir) if voiceover_dir.exists() else None,
            episode_id=episode_id,
            verbose=bool(args.verbose),
        )

        print(f"✅ AAR done: {out_path}")
        return 0

    print(f"❌ Unsupported step: {args.step}")
    return 4


if __name__ == "__main__":
    raise SystemExit(main())




