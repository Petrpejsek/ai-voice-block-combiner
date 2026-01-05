#!/usr/bin/env python3
"""
Never-fail FDA tests (v3):

FDA is now split:
- LLM output: ScenePlan v3 (best-effort; may be invalid)
- Deterministic compiler: ShotPlan v3 (canonical; always valid)

These tests validate the new policy:
- FDA must NOT hard-fail due to LLM output shape/coverage.
- FDA must always save a valid ShotPlan v3 wrapper into metadata.shot_plan.
- AAR must not be started by FDA step itself.

Run:
  python3 backend/test_fda_fatal_pipeline_stop.py
"""

import copy
import os
import unittest


import script_pipeline
import footage_director


class _FakeStore:
    def __init__(self, initial_state: dict):
        self._state = initial_state
        self.writes = []
        self.base_projects_dir = "/tmp/projects"  # not used in these tests

    def write_script_state(self, episode_id: str, state: dict) -> None:
        # keep deep copy snapshots like a real store would persist
        self._state = copy.deepcopy(state)
        self.writes.append(copy.deepcopy(state))

    def read_script_state(self, episode_id: str) -> dict:
        return copy.deepcopy(self._state)

    def episode_dir(self, episode_id: str) -> str:
        return f"/tmp/projects/{episode_id}"


def _make_minimal_state(episode_id: str = "ep_test") -> dict:
    """
    Minimal script_state satisfying _run_footage_director() preconditions.
    """
    tts_pkg = {
        "episode_id": episode_id,
        "narration_blocks": [
            {"block_id": "b_0001", "text_tts": "ships maps documents campbeltown st nazaire", "claim_ids": []},
            {"block_id": "b_0002", "text_tts": "ships maps documents destroyer dry dock", "claim_ids": []},
            {"block_id": "b_0003", "text_tts": "ships maps documents explosion caisson", "claim_ids": []},
        ],
    }
    return {
        "episode_id": episode_id,
        "metadata": {"tts_ready_package": copy.deepcopy(tts_pkg)},
        "steps": {
            "footage_director": {"name": "footage_director", "status": "IDLE", "started_at": None, "finished_at": None, "error": None},
            "asset_resolver": {"name": "asset_resolver", "status": "IDLE", "started_at": None, "finished_at": None, "error": None},
        },
        "script_status": "IDLE",
        "footage_director_config": {"provider": "openai", "model": "gpt-4o-mini", "temperature": 0.2, "prompt_template": None, "step": "footage_director"},
        "tts_ready_package": copy.deepcopy(tts_pkg),
        "footage_director_raw_output": None,
        "shot_plan": None,
        "archive_manifest_path": None,
        "updated_at": script_pipeline._now_iso(),
    }


def _raw_llm_shot_plan_missing_last_block() -> dict:
    """
    Raw LLM JSON (may be imperfect). Missing b_0003 on purpose.
    """
    return {
        "scenes": [
            {
                "scene_id": "sc_0001",
                "start_sec": 0,
                "end_sec": 10,
                "narration_block_ids": ["b_0001", "b_0002"],  # missing b_0003
                "narration_summary": "ships maps documents at st nazaire",
                "emotion": "neutral",
                "keywords": ["ships", "maps", "documents", "campbeltown", "st nazaire"],
                "shot_strategy": {"shot_types": ["archival_documents"], "cut_rhythm": "medium"},
                "search_queries": ["ships maps", "documents st nazaire", "campbeltown dry dock"],
            }
        ]
    }

def _raw_llm_shot_plan_full_coverage() -> dict:
    """
    Raw LLM JSON that covers all blocks in correct order (so version/auto_fixed checks can trigger).
    """
    return {
        "scenes": [
            {
                "scene_id": "sc_0001",
                "start_sec": 0,
                "end_sec": 10,
                "narration_block_ids": ["b_0001", "b_0002", "b_0003"],
                "narration_summary": "ships maps documents campbeltown st nazaire",
                "emotion": "neutral",
                "keywords": ["ships", "maps", "documents", "campbeltown", "st nazaire"],
                "shot_strategy": {"shot_types": ["archival_documents"], "cut_rhythm": "medium"},
                "search_queries": ["ships maps", "documents st nazaire", "campbeltown dry dock"],
            }
        ]
    }


def _make_state_with_b7_variants(episode_id: str = "ep_b7_variants") -> dict:
    """
    Realistic regression reproducer:
    expected has b_0007a + b_0007b but FDA uses b_0007 (merge shortcut) + missing.
    """
    st = _make_minimal_state(episode_id)
    st["tts_ready_package"]["narration_blocks"] = [
        {"block_id": "b_0005", "text_tts": "maps documents ships", "claim_ids": []},
        {"block_id": "b_0006", "text_tts": "maps documents ships", "claim_ids": []},
        {"block_id": "b_0007a", "text_tts": "maps documents ships", "claim_ids": []},
        {"block_id": "b_0007b", "text_tts": "maps documents ships", "claim_ids": []},
    ]
    return st


def _raw_llm_uses_b0007_merge_id() -> dict:
    return {
        "scenes": [
            {
                "scene_id": "sc_0001",
                "start_sec": 0,
                "end_sec": 10,
                "narration_block_ids": ["b_0005", "b_0006", "b_0007"],  # WRONG: b_0007a/b expected
                "narration_summary": "maps documents ships",
                "emotion": "neutral",
                "keywords": ["maps", "documents", "ships", "st nazaire", "dry dock"],
                "shot_strategy": {"shot_types": ["archival_documents"], "cut_rhythm": "medium"},
                "search_queries": ["maps documents", "ships archive", "st nazaire documents"],
            }
        ]
    }


class TestFdaFatalStop(unittest.TestCase):
    def setUp(self):
        self._orig_run_sceneplan_llm = getattr(footage_director, "run_sceneplan_llm", None)

    def tearDown(self):
        if self._orig_run_sceneplan_llm is not None:
            footage_director.run_sceneplan_llm = self._orig_run_sceneplan_llm

    def test_llm_failure_falls_back_and_saves_shotplan_v3(self):
        state = _make_minimal_state("ep_nf_1")
        store = _FakeStore(state)

        def _fake_run_sceneplan_llm(*_args, **_kwargs):
            raise RuntimeError("LLM down / invalid / rate limited")

        footage_director.run_sceneplan_llm = _fake_run_sceneplan_llm

        provider_api_keys = {"openai": "dummy"}  # present, but we stub the call
        script_pipeline._run_footage_director(
            state=state,
            episode_id=state["episode_id"],
            topic="t",
            language="en",
            target_minutes=1,
            channel_profile="default",
            provider_api_keys=provider_api_keys,
            store=store,
        )

        final_state = store.read_script_state(state["episode_id"])
        self.assertEqual(final_state["steps"]["footage_director"]["status"], "DONE")
        self.assertEqual(final_state["steps"]["asset_resolver"]["status"], "IDLE")

        md = final_state.get("metadata") or {}
        self.assertTrue(isinstance(md, dict) and "shot_plan" in md)
        wrapper = md["shot_plan"]
        self.assertTrue(isinstance(wrapper, dict) and isinstance(wrapper.get("shot_plan"), dict))
        sp = wrapper["shot_plan"]

        from visual_planning_v3 import SHOTPLAN_V3_VERSION
        self.assertEqual(sp.get("version"), SHOTPLAN_V3_VERSION)
        scenes = sp.get("scenes") or []
        self.assertTrue(isinstance(scenes, list) and len(scenes) > 0)

        # Coverage: every block_id must appear at least once.
        expected = [b["block_id"] for b in final_state["tts_ready_package"]["narration_blocks"]]
        used = []
        for sc in scenes:
            used.extend(sc.get("narration_block_ids") or [])
        for bid in expected:
            self.assertIn(bid, used)

    def test_sceneplan_partial_coverage_is_repaired(self):
        state = _make_minimal_state("ep_nf_2")
        store = _FakeStore(state)

        # Missing b_0003 on purpose.
        def _fake_run_sceneplan_llm(*_args, **_kwargs):
            return (
                {
                    "version": "sceneplan_v3",
                    "scenes": [
                        {
                            "scene_id": "sc_0001",
                            "narration_block_ids": ["b_0001", "b_0002"],
                            "emotion": "neutral",
                            "shot_types": ["maps_context"],
                            "cut_rhythm": "medium",
                            "source_preference": "archive_org",
                            "focus_entities": [],
                        }
                    ],
                },
                "{}",
                {"provider": "openai", "model": "gpt-4o-mini"},
            )

        footage_director.run_sceneplan_llm = _fake_run_sceneplan_llm

        provider_api_keys = {"openai": "dummy"}
        script_pipeline._run_footage_director(
            state=state,
            episode_id=state["episode_id"],
            topic="t",
            language="en",
            target_minutes=1,
            channel_profile="default",
            provider_api_keys=provider_api_keys,
            store=store,
        )

        final_state = store.read_script_state(state["episode_id"])
        sp = final_state["metadata"]["shot_plan"]["shot_plan"]
        used = []
        for sc in sp.get("scenes") or []:
            used.extend(sc.get("narration_block_ids") or [])
        self.assertIn("b_0003", used)


if __name__ == "__main__":
    unittest.main(verbosity=2)


