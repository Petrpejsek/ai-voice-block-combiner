"""
Test Harness for Query Guardrails

Tests 5 key scenarios to ensure guardrails work correctly.
"""

import sys
sys.path.insert(0, '/Users/petrliesner/podcasts/backend')

from query_guardrails import (
    validate_query,
    validate_and_fix_queries,
    extract_anchors_from_text,
    has_anchor,
    has_media_intent,
    has_noise_terms,
)


def test_scenario_1_clear_anchor():
    """
    Scenario 1: Beat with clear anchor (person/place name)
    Expected: Valid queries with intent tokens
    """
    print("\n" + "="*70)
    print("SCENARIO 1: Beat with clear anchor (Napoleon/Moscow)")
    print("="*70)
    
    beat_text = "Napoleon entered Moscow in September 1812, finding the city abandoned by its residents."
    queries = [
        "Napoleon Moscow historical photograph",
        "Moscow 1812 city map archive",
        "Napoleon army entering Moscow",
        "abandoned Moscow streets photograph",
    ]
    
    valid, diagnostics = validate_and_fix_queries(
        queries,
        beat_text,
        shot_types=['civilian_life', 'maps_context'],
        episode_topic="Napoleonic Wars",
        verbose=True
    )
    
    print(f"\n✓ Result: {diagnostics['final_count']}/{len(queries)} valid queries")
    print(f"  Valid queries: {valid}")
    
    assert diagnostics['final_count'] >= len(queries) * 0.9, "Should have >90% valid queries"
    print("\n✅ SCENARIO 1 PASSED")


def test_scenario_2_no_clear_anchor():
    """
    Scenario 2: Beat without clear anchor (generic text)
    Expected: Must use fallback anchor from episode/topic metadata
    """
    print("\n" + "="*70)
    print("SCENARIO 2: Beat without clear anchor (generic text)")
    print("="*70)
    
    beat_text = "The situation deteriorated rapidly as winter approached."
    queries = [
        "winter approaching historical photograph",
        "deteriorating situation archive",
        "rapid changes documentary footage",
    ]
    
    valid, diagnostics = validate_and_fix_queries(
        queries,
        beat_text,
        shot_types=['atmosphere_transition'],
        episode_topic="Napoleon 1812 Campaign",
        min_valid_queries=3,
        verbose=True
    )
    
    print(f"\n✓ Result: {diagnostics['final_count']}/{diagnostics['original_count']} valid queries")
    print(f"  Final queries: {valid}")
    
    # All queries should now have anchor (from episode topic or regeneration)
    for q in valid:
        assert has_anchor(q), f"Query '{q}' should have anchor"
    
    print("\n✅ SCENARIO 2 PASSED")


def test_scenario_3_noise_terms():
    """
    Scenario 3: LLM generates "band/game" type queries
    Expected: Stoplist must catch and regenerate
    """
    print("\n" + "="*70)
    print("SCENARIO 3: Queries with noise terms (band/game/meme)")
    print("="*70)
    
    beat_text = "The Grande Armée retreated through freezing conditions in November 1812."
    queries = [
        "Grande Armée band 1812",  # BAD: contains "band"
        "Napoleon retreat game footage",  # BAD: contains "game"
        "1812 retreat meme compilation",  # BAD: contains "meme"
        "Grande Armée retreat archival photograph",  # GOOD
    ]
    
    valid, diagnostics = validate_and_fix_queries(
        queries,
        beat_text,
        shot_types=['troop_movement'],
        episode_topic="Napoleonic Wars",
        min_valid_queries=4,
        verbose=True
    )
    
    print(f"\n✓ Result: {diagnostics['final_count']}/{diagnostics['original_count']} valid queries")
    print(f"  Rejection reasons: {diagnostics['rejection_reasons']}")
    
    # Check that noise terms were caught
    assert diagnostics['rejection_reasons'].get('STOPLIST_HIT', 0) >= 3, \
        "Should catch at least 3 noise terms"
    
    # Check that no valid query contains noise
    for q in valid:
        assert not has_noise_terms(q), f"Valid query '{q}' should not have noise terms"
    
    print("\n✅ SCENARIO 3 PASSED")


def test_scenario_4_map_shot():
    """
    Scenario 4: Beat with "map shot" type
    Expected: Queries must contain "map" media intent
    """
    print("\n" + "="*70)
    print("SCENARIO 4: Map shot type")
    print("="*70)
    
    beat_text = "Napoleon's route from Smolensk to Moscow covered 400 kilometers."
    queries = [
        "Napoleon route Smolensk Moscow",
        "1812 campaign path Russia",
        "Grande Armée march route",
    ]
    
    valid, diagnostics = validate_and_fix_queries(
        queries,
        beat_text,
        shot_types=['maps_context'],
        episode_topic="Napoleon's Russian Campaign",
        min_valid_queries=3,
        verbose=True
    )
    
    print(f"\n✓ Result: {diagnostics['final_count']}/{diagnostics['original_count']} valid queries")
    
    # All valid queries should have "map" intent
    map_count = sum(1 for q in valid if 'map' in q.lower())
    print(f"  Queries with 'map': {map_count}/{len(valid)}")
    
    assert map_count >= len(valid) * 0.7, "At least 70% of queries should contain 'map'"
    
    print("\n✅ SCENARIO 4 PASSED")


def test_scenario_5_low_coverage():
    """
    Scenario 5: Not enough valid queries (low coverage)
    Expected: Max 2 regen attempts, then mark as low_coverage and continue
    """
    print("\n" + "="*70)
    print("SCENARIO 5: Low coverage scenario (insufficient valid queries)")
    print("="*70)
    
    beat_text = "The situation was complex."  # Very generic, hard to extract good anchors
    queries = [
        "situation",  # Too short, no anchor
        "complex events",  # No anchor
    ]
    
    valid, diagnostics = validate_and_fix_queries(
        queries,
        beat_text,
        shot_types=['atmosphere_transition'],
        episode_topic="History",  # Generic topic
        min_valid_queries=6,
        max_regen_attempts=2,
        verbose=True
    )
    
    print(f"\n✓ Result: {diagnostics['final_count']}/{diagnostics['original_count']} queries")
    print(f"  Low coverage: {diagnostics['low_coverage']}")
    print(f"  Regenerated: {diagnostics['regenerated_count']}")
    
    # Should have marked as low coverage
    if diagnostics['final_count'] < 6:
        assert diagnostics['low_coverage'], "Should mark as low_coverage when insufficient"
    
    # Should have attempted regeneration
    assert diagnostics['regenerated_count'] > 0, "Should attempt regeneration"
    
    # Should NOT crash (graceful degradation)
    assert len(valid) > 0, "Should return at least some queries"
    
    print("\n✅ SCENARIO 5 PASSED (graceful degradation)")


def test_anchor_extraction():
    """
    Bonus test: Anchor extraction accuracy
    """
    print("\n" + "="*70)
    print("BONUS: Anchor extraction from beat text")
    print("="*70)
    
    test_cases = [
        ("Napoleon entered Moscow in 1812", ["1812", "Napoleon", "Moscow"]),
        ("The Battle of Waterloo ended in June 1815", ["1815", "Waterloo"]),
        ("\"Operation Barbarossa\" began on June 22, 1941", ["1941", "Operation Barbarossa"]),
        ("Churchill met with Roosevelt to discuss the war", ["Churchill", "Roosevelt"]),
    ]
    
    for text, expected_anchors in test_cases:
        anchors = extract_anchors_from_text(text)
        print(f"\nText: {text}")
        print(f"  Extracted: {anchors}")
        print(f"  Expected: {expected_anchors}")
        
        # Check that expected anchors are found
        for exp in expected_anchors:
            found = any(exp.lower() in a.lower() for a in anchors)
            assert found, f"Expected anchor '{exp}' not found in {anchors}"
        
        print("  ✓ Match")
    
    print("\n✅ ANCHOR EXTRACTION PASSED")


def run_all_tests():
    """Run all test scenarios."""
    print("\n" + "="*70)
    print("QUERY GUARDRAILS TEST SUITE")
    print("="*70)
    
    try:
        test_scenario_1_clear_anchor()
        test_scenario_2_no_clear_anchor()
        test_scenario_3_noise_terms()
        test_scenario_4_map_shot()
        test_scenario_5_low_coverage()
        test_anchor_extraction()
        
        print("\n" + "="*70)
        print("🎉 ALL TESTS PASSED!")
        print("="*70)
        return True
        
    except AssertionError as e:
        print(f"\n❌ TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False
    except Exception as e:
        print(f"\n❌ UNEXPECTED ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == '__main__':
    success = run_all_tests()
    sys.exit(0 if success else 1)


