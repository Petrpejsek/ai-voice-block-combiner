"""
FDA v2.7 Golden Contract Tests

Testy pro ověření klíčových kontraktů FDA validátoru a generátorů:
- TEST A: Object-type overlap detection (city map = 1 type, ne 2)
- TEST B: Generator nevytváří queries se 2 object types
- TEST C: Salvage broken LLM output (These, string source_preference, atd.)
"""

import json
from typing import Dict, Any, List

# Import FDA functions
from footage_director import (
    _count_object_types,
    FDA_V27_QUERY_OBJECT_TYPES,
    _generate_deterministic_queries_v27,
    apply_deterministic_generators_v27,
    validate_fda_hard_v27,
    estimate_speech_duration_seconds_int,
    ALLOWED_SHOT_TYPES,
)


# ============================================================================
# TEST A: Object-type overlap detection
# ============================================================================

def test_a_city_map_overlap():
    """
    TEST A: Overlap detection for "city map"
    
    Query: "Moscow 1812 historical city map"
    Expected: 1 object type detected ("city map"), NOT 2 ("map" + "city map")
    """
    print("\n" + "="*70)
    print("TEST A: City Map Overlap Detection")
    print("="*70)
    
    query = "Moscow 1812 historical city map"
    
    # Count object types
    count = _count_object_types(query, FDA_V27_QUERY_OBJECT_TYPES)
    
    print(f"Query: {query}")
    print(f"Object types detected: {count}")
    
    # Assertion
    assert count == 1, f"Expected 1 object type, got {count}"
    
    print("✅ TEST A PASSED: 'city map' correctly detected as 1 object type")
    return True


def test_a_burned_ruins_overlap():
    """
    TEST A variant: Overlap detection for "burned ruins"
    
    Query: "Moscow 1812 burned ruins"
    Expected: 1 object type detected ("burned ruins"), NOT 2 ("ruins" + "burned ruins")
    """
    print("\n" + "="*70)
    print("TEST A (variant): Burned Ruins Overlap Detection")
    print("="*70)
    
    query = "Moscow 1812 burned ruins"
    
    count = _count_object_types(query, FDA_V27_QUERY_OBJECT_TYPES)
    
    print(f"Query: {query}")
    print(f"Object types detected: {count}")
    
    assert count == 1, f"Expected 1 object type, got {count}"
    
    print("✅ TEST A (variant) PASSED: 'burned ruins' correctly detected as 1 object type")
    return True


def test_a_route_map_overlap():
    """
    TEST A variant: Overlap detection for "route map"
    
    Query: "Napoleon 1812 route map retreat"
    Expected: 1 object type detected ("route map"), NOT 2
    """
    print("\n" + "="*70)
    print("TEST A (variant): Route Map Overlap Detection")
    print("="*70)
    
    query = "Napoleon 1812 route map retreat"
    
    count = _count_object_types(query, FDA_V27_QUERY_OBJECT_TYPES)
    
    print(f"Query: {query}")
    print(f"Object types detected: {count}")
    
    assert count == 1, f"Expected 1 object type, got {count}"
    
    print("✅ TEST A (variant) PASSED: 'route map' correctly detected as 1 object type")
    return True


# ============================================================================
# TEST B: Generator doesn't create double object types
# ============================================================================

def test_b_generator_no_double_object_types():
    """
    TEST B: Generator validation
    
    Generátor _generate_deterministic_queries_v27 NESMÍ vytvořit query
    se 2 object types (např. "Moscow 1812 burned ruins engraving").
    
    Expected: Všechny vygenerované queries mají EXACTLY 1 object type.
    """
    print("\n" + "="*70)
    print("TEST B: Generator No Double Object Types")
    print("="*70)
    
    # Test narration texts for different scene types
    test_cases = [
        ("Napoleon entered Moscow in 1812 after the battle.", "leaders"),
        ("The city was burned and destroyed by fires.", "fire_ruins"),
        ("Napoleon waited for peace negotiations from the Tsar.", "waiting_negotiation"),
        ("The Grande Armée began its retreat from Moscow.", "movement"),
        ("Historical events unfolded in Moscow during 1812.", "generic"),
    ]
    
    all_passed = True
    total_queries = 0
    failed_queries = []
    
    for narration_text, expected_type in test_cases:
        print(f"\n📝 Testing scene type: {expected_type}")
        print(f"   Narration: {narration_text[:60]}...")
        
        # Generate queries
        queries = _generate_deterministic_queries_v27(narration_text, scene_index=0)
        
        print(f"   Generated {len(queries)} queries:")
        
        for i, query in enumerate(queries):
            count = _count_object_types(query, FDA_V27_QUERY_OBJECT_TYPES)
            total_queries += 1
            
            status = "✅" if count == 1 else "❌"
            print(f"   {status} Query {i+1}: {query} (object types: {count})")
            
            if count != 1:
                all_passed = False
                failed_queries.append({
                    "query": query,
                    "count": count,
                    "scene_type": expected_type
                })
    
    print(f"\n{'='*70}")
    print(f"Total queries tested: {total_queries}")
    print(f"Failed queries: {len(failed_queries)}")
    
    if failed_queries:
        print("\n❌ FAILED QUERIES:")
        for fq in failed_queries:
            print(f"   - {fq['query']} (count={fq['count']}, type={fq['scene_type']})")
    
    assert all_passed, f"{len(failed_queries)} queries have wrong object type count"
    
    print("\n✅ TEST B PASSED: All generated queries have exactly 1 object type")
    return True


# ============================================================================
# TEST C: Salvage broken LLM output
# ============================================================================

def test_c_salvage_broken_llm_output():
    """
    TEST C: Salvage broken LLM output
    
    Vezme broken FDA output s:
    - "These" v query
    - source_preference jako string místo array
    - Chybějící/špatné keywords
    
    Expected: Po apply_deterministic_generators_v27 projde validate_fda_hard_v27
    """
    print("\n" + "="*70)
    print("TEST C: Salvage Broken LLM Output")
    print("="*70)
    
    # Broken LLM output (simulace špatného výstupu)
    broken_output = {
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
                    "narration_summary": "These events unfolded in Moscow",  # Bad: starts with "These"
                    "emotion": "neutral",
                    "keywords": ["the Moscow", "a city", "these events"],  # Bad: forbidden tokens
                    "shot_strategy": {
                        "shot_types": ["archival_documents"],
                        "clip_length_sec_range": [4, 7],
                        "cut_rhythm": "medium",
                        "source_preference": "archive_org"  # Bad: string instead of array
                    },
                    "search_queries": [
                        "These Moscow events 1812",  # Bad: starts with "These"
                        "The city of Moscow 1812",   # Bad: starts with "The"
                        "Moscow fires",              # Bad: no object type
                        "Napoleon retreat",          # Bad: no object type
                        "1812 Russia"                # Bad: no object type
                    ]
                }
            ]
        }
    }
    
    # Mock tts_ready_package
    tts_ready_package = {
        "episode_id": "test_ep_001",
        "narration_blocks": [
            {
                "block_id": "b_0001",
                "text_tts": "Napoleon entered Moscow in 1812 after the Battle of Borodino. The city was largely evacuated and soon caught fire.",
            }
        ]
    }
    
    print("📥 Input (broken LLM output):")
    print(f"   Summary: {broken_output['shot_plan']['scenes'][0]['narration_summary']}")
    print(f"   Keywords: {broken_output['shot_plan']['scenes'][0]['keywords']}")
    print(f"   Queries: {broken_output['shot_plan']['scenes'][0]['search_queries'][:2]}")
    print(f"   source_preference: {broken_output['shot_plan']['scenes'][0]['shot_strategy']['source_preference']} (type: {type(broken_output['shot_plan']['scenes'][0]['shot_strategy']['source_preference']).__name__})")
    
    # Apply deterministic generators
    print("\n🔧 Applying deterministic generators...")
    fixed_output = apply_deterministic_generators_v27(
        broken_output,
        tts_ready_package,
        episode_id="test_ep_001"
    )
    
    print("\n📤 Output (after generators):")
    scene = fixed_output['shot_plan']['scenes'][0]
    print(f"   Summary: {scene['narration_summary']}")
    print(f"   Keywords (first 3): {scene['keywords'][:3]}")
    print(f"   Queries (first 3): {scene['search_queries'][:3]}")
    print(f"   source_preference: {scene['shot_strategy']['source_preference']} (type: {type(scene['shot_strategy']['source_preference']).__name__})")
    
    # Validate with hard validator
    print("\n🔍 Running hard validator...")
    try:
        validate_fda_hard_v27(fixed_output, tts_ready_package, episode_id="test_ep_001")
        print("✅ Hard validator PASSED")
        validation_passed = True
    except RuntimeError as e:
        print(f"❌ Hard validator FAILED: {str(e)[:200]}")
        validation_passed = False
    
    # Assertions
    assert validation_passed, "Hard validator should pass after applying generators"
    
    # Check specific fixes
    assert isinstance(scene['shot_strategy']['source_preference'], list), "source_preference should be array"
    assert scene['shot_strategy']['source_preference'] == ["archive_org"], "source_preference should be ['archive_org']"
    
    # Check keywords don't have forbidden tokens
    for kw in scene['keywords']:
        assert "the " not in kw.lower(), f"Keyword '{kw}' contains 'the'"
        assert " a " not in kw.lower(), f"Keyword '{kw}' contains 'a'"
        assert "these" not in kw.lower(), f"Keyword '{kw}' contains 'these'"
    
    # Check queries don't start with forbidden words
    forbidden_starts = {"these", "the", "a", "an"}
    for query in scene['search_queries']:
        first_word = query.split()[0].lower() if query.split() else ""
        assert first_word not in forbidden_starts, f"Query '{query}' starts with forbidden word '{first_word}'"
    
    # Check all queries have exactly 1 object type
    for query in scene['search_queries']:
        count = _count_object_types(query, FDA_V27_QUERY_OBJECT_TYPES)
        assert count == 1, f"Query '{query}' has {count} object types (expected 1)"
    
    print("\n✅ TEST C PASSED: Broken output successfully salvaged and validated")
    return True


# ============================================================================
# TEST D: Timing + shot_types enum hardening
# ============================================================================

def test_d_timing_recomputed_and_shot_types_allowlisted():
    """
    TEST D:
    - If LLM outputs unrealistic timings (e.g. 0-2s for a 30-word block), deterministic generators
      must recompute start/end from word_count-based VO estimate.
    - shot_types must always be in the ALLOWED_SHOT_TYPES enum.
    """
    print("\n" + "="*70)
    print("TEST D: Timing recompute + shot_types allowlist")
    print("="*70)

    # 30-ish words → ~12s at 150 WPM
    text = (
        "Napoleon entered Moscow in 1812 and waited for Tsar Alexander I, "
        "but the city soon burned and the army faced a difficult retreat."
    )

    broken_output = {
        "shot_plan": {
            "version": "fda_v2.7",
            "source": "tts_ready_package",
            "assumptions": {"words_per_minute": 150},
            "scenes": [
                {
                    "scene_id": "sc_0001",
                    "start_sec": 0,
                    "end_sec": 2,  # ❌ unrealistic on purpose
                    "narration_block_ids": ["b_0001"],
                    "narration_summary": "Following the events, ...",  # will be overwritten
                    "emotion": "neutral",
                    "keywords": ["these events"],  # will be overwritten
                    "shot_strategy": {"shot_types": ["leader_closeups"], "cut_rhythm": "medium"},  # ❌ invalid enum on purpose
                    "search_queries": ["historical historical Moscow 1812"],  # will be overwritten
                }
            ],
        }
    }

    tts_ready_package = {
        "episode_id": "test_ep_timing_001",
        "narration_blocks": [
            {"block_id": "b_0001", "text_tts": text},
        ],
    }

    fixed = apply_deterministic_generators_v27(broken_output, tts_ready_package, episode_id="test_ep_timing_001")
    scene = fixed["shot_plan"]["scenes"][0]

    expected = estimate_speech_duration_seconds_int(text, words_per_minute=150, min_seconds=2)
    actual = scene["end_sec"] - scene["start_sec"]

    print(f"Expected duration: {expected}s | Actual duration: {actual}s")
    assert actual == expected, f"Timing mismatch: expected {expected}, got {actual}"

    # shot_types must be valid enums
    sts = scene.get("shot_strategy", {}).get("shot_types") or []
    assert isinstance(sts, list) and sts, "shot_types missing"
    for st in sts:
        assert st in ALLOWED_SHOT_TYPES, f"Invalid shot_type '{st}'"

    # Hard validator should pass
    validate_fda_hard_v27(fixed, tts_ready_package, episode_id="test_ep_timing_001")
    print("\n✅ TEST D PASSED")
    return True


# ============================================================================
# TEST E: Episode Anchor Lock blocks off-topic contamination
# ============================================================================

def test_e_episode_anchor_lock_blocks_off_topic():
    """
    TEST E:
    - For a Lidice-anchored episode, queries like "Moscow 1812 ..." MUST be rejected by the hard validator.
    """
    print("\n" + "="*70)
    print("TEST E: Episode Anchor Lock blocks off-topic anchors")
    print("="*70)

    tts_ready_package = {
        "episode_id": "test_ep_anchor_lock_001",
        "narration_blocks": [
            {
                "block_id": "b_0001",
                "text_tts": "In 1942, the village of Lidice was destroyed after the assassination of Reinhard Heydrich.",
            }
        ],
    }

    contaminated = {
        "shot_plan": {
            "version": "fda_v2.7",
            "source": "tts_ready_package",
            "assumptions": {"words_per_minute": 150},
            "scenes": [
                {
                    "scene_id": "sc_0001",
                    "start_sec": 0,
                    "end_sec": 12,
                    "narration_block_ids": ["b_0001"],
                    "narration_summary": "In 1942, Lidice was destroyed after the assassination of Reinhard Heydrich.",
                    "emotion": "neutral",
                    "keywords": [
                        "Lidice archival photograph",
                        "Heydrich official letter",
                        "Nazi decree document",
                        "Czech police report",
                        "Memorial monument",
                        "Village burned ruins",
                        "Gestapo document",
                        "Children photograph",
                    ],
                    "shot_strategy": {
                        "shot_types": ["archival_documents", "destruction_aftermath"],
                        "clip_length_sec_range": [4, 7],
                        "cut_rhythm": "medium",
                        "source_preference": ["archive_org"],
                    },
                    # ❌ Off-topic anchors not present in the episode narration:
                    "search_queries": [
                        "Moscow 1812 city map archive scan",
                        "Napoleon 1812 engraving original print",
                        "Tsar Alexander I 1812 letter archive",
                        "Borodino 1812 route map archive scan",
                        "Moscow 1812 photograph archive print",
                    ],
                }
            ],
        }
    }

    try:
        validate_fda_hard_v27(contaminated, tts_ready_package, episode_id="test_ep_anchor_lock_001")
    except RuntimeError as e:
        msg = str(e)
        print(f"✅ Validator rejected off-topic anchors: {msg[:180]}")
        assert ("QUERY_ANCHOR_NOT_IN_EPISODE" in msg) or ("QUERY_MISSING_EPISODE_ANCHOR" in msg), msg
        return True

    raise AssertionError("Validator should have rejected off-topic Moscow/Napoleon anchors for Lidice episode")

# ============================================================================
# Test Runner
# ============================================================================

def run_all_tests():
    """Run all golden contract tests"""
    print("\n" + "="*70)
    print("FDA v2.7 GOLDEN CONTRACT TESTS")
    print("="*70)
    
    tests = [
        ("TEST A: City Map Overlap", test_a_city_map_overlap),
        ("TEST A (variant): Burned Ruins Overlap", test_a_burned_ruins_overlap),
        ("TEST A (variant): Route Map Overlap", test_a_route_map_overlap),
        ("TEST B: Generator No Double Object Types", test_b_generator_no_double_object_types),
        ("TEST C: Salvage Broken LLM Output", test_c_salvage_broken_llm_output),
        ("TEST D: Timing recompute + shot_types allowlist", test_d_timing_recomputed_and_shot_types_allowlisted),
        ("TEST E: Episode Anchor Lock blocks off-topic anchors", test_e_episode_anchor_lock_blocks_off_topic),
    ]
    
    results = []
    
    for test_name, test_func in tests:
        try:
            result = test_func()
            results.append((test_name, "PASSED", None))
        except AssertionError as e:
            results.append((test_name, "FAILED", str(e)))
            print(f"\n❌ {test_name} FAILED: {e}")
        except Exception as e:
            results.append((test_name, "ERROR", str(e)))
            print(f"\n💥 {test_name} ERROR: {e}")
    
    # Summary
    print("\n" + "="*70)
    print("TEST SUMMARY")
    print("="*70)
    
    passed = sum(1 for _, status, _ in results if status == "PASSED")
    failed = sum(1 for _, status, _ in results if status == "FAILED")
    errors = sum(1 for _, status, _ in results if status == "ERROR")
    
    for test_name, status, error in results:
        icon = "✅" if status == "PASSED" else "❌" if status == "FAILED" else "💥"
        print(f"{icon} {test_name}: {status}")
        if error:
            print(f"   Error: {error[:100]}")
    
    print(f"\n{'='*70}")
    print(f"Total: {len(tests)} | Passed: {passed} | Failed: {failed} | Errors: {errors}")
    print(f"{'='*70}")
    
    if failed > 0 or errors > 0:
        raise AssertionError(f"Some tests failed: {failed} failures, {errors} errors")
    
    print("\n🎉 ALL TESTS PASSED!")
    return True


if __name__ == "__main__":
    run_all_tests()

