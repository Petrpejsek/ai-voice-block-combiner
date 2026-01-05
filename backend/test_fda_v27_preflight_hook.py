#!/usr/bin/env python3
"""
Regression test: ensure v2.7 validation path runs the last-mile hard gate
(`validate_shot_plan_hard_gate`) rather than calling `validate_fda_hard_v27`
directly (which would bypass keyword normalization).

Run:
  python3 backend/test_fda_v27_preflight_hook.py
"""

import unittest
from unittest import mock

import script_pipeline


class TestFDAV27PreflightHook(unittest.TestCase):
    def test_v27_uses_validate_shot_plan_hard_gate(self):
        episode_id = "ep_test_v27_gate"
        state = {
            "episode_id": episode_id,
            "metadata": {
                "tts_ready_package": {
                    "episode_id": episode_id,
                    "episode_metadata": {"topic": "The Titanic Disaster 1912"},
                    "narration_blocks": [
                        {"block_id": "b_0001", "text_tts": "Titanic sailed from Southampton.", "claim_ids": []},
                    ],
                }
            },
            "tts_ready_package": {
                "episode_id": episode_id,
                "episode_metadata": {"topic": "The Titanic Disaster 1912"},
                "narration_blocks": [
                    {"block_id": "b_0001", "text_tts": "Titanic sailed from Southampton.", "claim_ids": []},
                ],
            },
            "steps": {"footage_director": {"name": "footage_director", "status": "IDLE"}},
            "script_status": "IDLE",
            # Force v2.7 mode
            "footage_director_config": {
                "version": "fda_v2.7",
                "use_v3_mode": False,
                "use_cached_draft": True,
                "provider": "openrouter",
                "model": "openai/gpt-4o-mini",
            },
            # Provide cached draft path so no network/LLM is needed
            "footage_director_raw_output": {
                "response_json": {
                    "shot_plan": {
                        "version": "fda_v2.7",
                        "source": "tts_ready_package",
                        "assumptions": {},
                        "scenes": [
                            {
                                "scene_id": "sc_0001",
                                "start_sec": 0,
                                "end_sec": 5,
                                "narration_block_ids": ["b_0001"],
                                "narration_summary": "Titanic departs from Southampton.",
                                "emotion": "neutral",
                                "keywords": ["Titanic", "Southampton", "night", "world", "sinking", "documents", "service", "time", "largest"],
                                "shot_strategy": {"shot_types": ["archival_photograph"], "cut_rhythm": "medium"},
                                "search_queries": [
                                    "Titanic Southampton archival photograph document",
                                    "RMS Titanic departure Southampton archival photograph",
                                    "Titanic sinking night archival photograph",
                                    "Titanic passenger ship archival photograph",
                                    "Titanic official documents archival photograph",
                                ],
                            }
                        ],
                    }
                }
            },
            "shot_plan": None,
            "updated_at": script_pipeline._now_iso(),
        }

        class _FakeStore:
            def __init__(self, st: dict):
                self._st = st
                self.writes = []
                self.base_projects_dir = "/tmp/projects"

            def write_script_state(self, eid: str, st2: dict) -> None:
                self._st = st2
                self.writes.append(st2)

            def read_script_state(self, eid: str) -> dict:
                return self._st

            def episode_dir(self, eid: str) -> str:
                return f"/tmp/projects/{eid}"

        store = _FakeStore(state)

        # Patch deterministic/sanitizer steps to avoid unrelated failures.
        # We only want to prove the v2.7 path calls the canonical hard gate.
        with mock.patch("script_pipeline._write_raw_output_fda", return_value=None):
            with mock.patch("footage_director.PRE_FDA_SANITIZER_AVAILABLE", True):
                with mock.patch("footage_director.sanitize_and_log", side_effect=lambda x: x):
                    with mock.patch("footage_director.apply_deterministic_generators_v27", side_effect=lambda draft, tts_pkg, eid: draft):
                        # Patch the hard gate to prove the pipeline *calls it*.
                        with mock.patch(
                            "footage_director.validate_shot_plan_hard_gate",
                            side_effect=RuntimeError("LOCAL_PREFLIGHT_FAILED: sentinel"),
                        ) as m_gate:
                            with self.assertRaises(RuntimeError) as ctx:
                                script_pipeline._run_footage_director(
                                    state,
                                    episode_id,
                                    topic="test topic",
                                    language="en",
                                    target_minutes=None,
                                    channel_profile=None,
                                    # No API key: forces cached draft path (deterministic, no network).
                                    provider_api_keys={},
                                    store=store,
                                )

        self.assertTrue(m_gate.called, "Expected validate_shot_plan_hard_gate to be called in v2.7 path")
        self.assertIn("LOCAL_PREFLIGHT_FAILED", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()


