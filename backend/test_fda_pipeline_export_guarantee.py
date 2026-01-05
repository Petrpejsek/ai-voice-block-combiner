"""
Test FDA Pipeline Export Guarantee

Ověřuje, že pipeline ukládá a exportuje POUZE post-processed shot plan,
nikdy raw LLM output.
"""

import json
from typing import Dict, Any

def test_v27_export_guarantee():
    """
    Test: Exported state contains clean fda_v2.7 shot plan without extra fields.
    
    This test simulates what _run_footage_director saves to state and verifies
    the hard assertions would catch any violations.
    """
    print("\n" + "="*70)
    print("TEST: FDA v2.7 Export Guarantee")
    print("="*70)
    
    # Simulate a GOOD v2.7 shot plan (post-processed)
    good_shot_plan = {
        "shot_plan": {
            "version": "fda_v2.7",
            "source": "tts_ready_package",
            "assumptions": {"words_per_minute": 150},
            "scenes": [
                {
                    "scene_id": "sc_0001",
                    "start_sec": 0,
                    "end_sec": 15,
                    "narration_block_ids": ["b_0001"],
                    "narration_summary": "Napoleon entered Moscow in 1812.",
                    "emotion": "neutral",
                    "keywords": [
                        "Napoleon military map",
                        "Moscow historical document",
                        "1812 period engraving",
                        "official dispatch letter",
                        "historical document archive",
                        "city ruins photograph",
                        "battle illustration scene",
                        "diplomatic correspondence manuscript"
                    ],
                    "shot_strategy": {
                        "shot_types": ["archival_documents", "maps_context"],
                        "clip_length_sec_range": [4, 7],
                        "cut_rhythm": "medium",
                        "source_preference": ["archive_org"]  # ✅ list
                    },
                    "search_queries": [
                        "Moscow 1812 historical city map",
                        "Moscow city 1812 period engraving",
                        "Napoleon 1812 historical burned ruins",
                        "Tsar Alexander I period kremlin interior",
                        "Napoleon Moscow 1812 military letter"
                    ]
                }
            ]
        }
    }
    
    # Validate good shot plan
    print("\n✅ Testing GOOD v2.7 shot plan...")
    try:
        validate_v27_hard_assertions(good_shot_plan, use_v27_mode=True)
        print("   ✅ Passed all hard assertions")
    except Exception as e:
        print(f"   ❌ FAILED: {e}")
        raise
    
    # Test BAD examples
    bad_examples = [
        {
            "name": "Wrong version",
            "shot_plan": {
                "shot_plan": {
                    "version": "shotplan_v3",  # ❌ Wrong
                    "source": "tts_ready_package",
                    "scenes": []
                }
            }
        },
        {
            "name": "Extra field total_duration_sec",
            "shot_plan": {
                "shot_plan": {
                    "version": "fda_v2.7",
                    "source": "tts_ready_package",
                    "total_duration_sec": 120,  # ❌ Extra field
                    "scenes": []
                }
            }
        },
        {
            "name": "String source_preference",
            "shot_plan": {
                "shot_plan": {
                    "version": "fda_v2.7",
                    "source": "tts_ready_package",
                    "scenes": [
                        {
                            "scene_id": "sc_0001",
                            "shot_strategy": {
                                "source_preference": "archive_org"  # ❌ String, not list
                            }
                        }
                    ]
                }
            }
        },
    ]
    
    print("\n❌ Testing BAD v2.7 shot plans (should all fail)...")
    for example in bad_examples:
        print(f"\n   Testing: {example['name']}")
        try:
            validate_v27_hard_assertions(example['shot_plan'], use_v27_mode=True)
            print(f"   ❌ ERROR: Should have failed but didn't!")
            raise AssertionError(f"{example['name']} should have failed validation")
        except RuntimeError as e:
            print(f"   ✅ Correctly rejected: {str(e)[:80]}")
    
    print("\n" + "="*70)
    print("✅ FDA v2.7 Export Guarantee TEST PASSED")
    print("="*70)
    
    return True


def validate_v27_hard_assertions(shot_plan_wrapper: Dict[str, Any], use_v27_mode: bool) -> None:
    """
    Replicate hard assertions from script_pipeline.py:_run_footage_director
    
    This simulates what the pipeline checks before saving.
    """
    sp = shot_plan_wrapper.get("shot_plan")
    
    if not isinstance(sp, dict):
        raise RuntimeError("FDA_INVALID_OUTPUT: shot_plan must be a dict")
    
    # Check version
    sp_version = sp.get("version", "")
    if use_v27_mode:
        if sp_version != "fda_v2.7":
            raise RuntimeError(f"FDA_VERSION_MISMATCH: Expected 'fda_v2.7', got '{sp_version}'")
    
    # Check source
    sp_source = sp.get("source", "")
    if use_v27_mode and sp_source != "tts_ready_package":
        raise RuntimeError(f"FDA_SOURCE_MISMATCH: Expected 'tts_ready_package', got '{sp_source}'")
    
    # Check no extra top-level keys (v2.7 only)
    if use_v27_mode:
        allowed_keys = {"version", "source", "assumptions", "scenes"}
        extra_keys = set(sp.keys()) - allowed_keys
        if extra_keys:
            raise RuntimeError(f"FDA_EXTRA_FIELDS: shot_plan contains forbidden fields: {list(extra_keys)}")
    
    # Check source_preference in scenes (v2.7 only)
    sp_scenes = sp.get("scenes", [])
    if use_v27_mode and isinstance(sp_scenes, list):
        for i, scene in enumerate(sp_scenes):
            if not isinstance(scene, dict):
                continue
            shot_strategy = scene.get("shot_strategy", {})
            if isinstance(shot_strategy, dict):
                source_pref = shot_strategy.get("source_preference")
                if source_pref is not None:  # Allow missing (will be added by deterministic generator)
                    if not isinstance(source_pref, list):
                        raise RuntimeError(f"FDA_INVALID_SOURCE_PREF: Scene {i}: source_preference must be list, got {type(source_pref).__name__}")
                    if source_pref != ["archive_org"]:
                        raise RuntimeError(f"FDA_INVALID_SOURCE_PREF: Scene {i}: source_preference must be ['archive_org'], got {source_pref}")


if __name__ == "__main__":
    test_v27_export_guarantee()



