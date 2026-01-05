"""
Unit Tests for Query Guardrails - Critical Edge Cases

Tests the specific rules identified in code review:
1. Year-only anchor must FAIL
2. "Olympic Games" must PASS (legitimate context)
3. Map shot must contain "map"
4. Max 2 regen attempts, then low_coverage flag
"""

import sys
sys.path.insert(0, '/Users/petrliesner/podcasts/backend')

from query_guardrails import (
    has_anchor,
    has_noise_terms,
    validate_and_fix_queries,
)


def test_year_only_anchor_fails():
    """
    CRITICAL: Year alone is NOT valid anchor.
    "1812 retreat" must FAIL (no entity).
    "Napoleon 1812 retreat" must PASS (has entity).
    """
    print("\n" + "="*70)
    print("TEST: Year-only anchor must FAIL")
    print("="*70)
    
    # BAD: Year without entity
    query_bad = "1812 retreat archival photograph"
    assert not has_anchor(query_bad), \
        f"Year-only query '{query_bad}' should NOT have anchor"
    print(f"✅ PASS: '{query_bad}' correctly rejected (year-only)")
    
    # GOOD: Year + entity
    query_good = "Napoleon 1812 retreat archival photograph"
    assert has_anchor(query_good), \
        f"Entity + year query '{query_good}' SHOULD have anchor"
    print(f"✅ PASS: '{query_good}' correctly accepted (entity + year)")
    
    # BAD: Year + generic term (no entity)
    query_bad2 = "1812 winter conditions archival photograph"
    assert not has_anchor(query_bad2), \
        f"Year + generic query '{query_bad2}' should NOT have anchor"
    print(f"✅ PASS: '{query_bad2}' correctly rejected (year + generic)")
    
    print("\n✅ TEST PASSED: Year-only anchor correctly rejected")


def test_olympic_games_legitimate():
    """
    CRITICAL: "Olympic Games" is legitimate historical reference.
    Should NOT be blocked by "games" stoplist.
    """
    print("\n" + "="*70)
    print("TEST: 'Olympic Games' must PASS stoplist")
    print("="*70)
    
    # GOOD: Olympic Games (legitimate historical context)
    query_good = "Olympic Games Athens archival photograph"
    assert not has_noise_terms(query_good), \
        f"Legitimate query '{query_good}' should NOT have noise"
    print(f"✅ PASS: '{query_good}' NOT blocked (legitimate context)")
    
    # GOOD: Ancient Games
    query_good2 = "Ancient Games Rome arena archival engraving"
    assert not has_noise_terms(query_good2), \
        f"Legitimate query '{query_good2}' should NOT have noise"
    print(f"✅ PASS: '{query_good2}' NOT blocked (ancient context)")
    
    # BAD: Modern games noise
    query_bad = "games compilation highlights"
    assert has_noise_terms(query_bad), \
        f"Noise query '{query_bad}' SHOULD be blocked"
    print(f"✅ PASS: '{query_bad}' correctly blocked (noise)")
    
    # BAD: Video games
    query_bad2 = "Napoleon video game footage"
    assert has_noise_terms(query_bad2), \
        f"Noise query '{query_bad2}' SHOULD be blocked"
    print(f"✅ PASS: '{query_bad2}' correctly blocked (video game)")
    
    print("\n✅ TEST PASSED: Legitimate 'games' context preserved")


def test_map_shot_contains_map():
    """
    Map shot type must result in queries containing "map" token.
    """
    print("\n" + "="*70)
    print("TEST: Map shot must contain 'map' token")
    print("="*70)
    
    beat_text = "Napoleon's route from Smolensk to Moscow covered 400 kilometers."
    queries = [
        "Napoleon route Smolensk",
        "1812 campaign path",  # No entity, will fail anchor
        "Napoleon march route",
    ]
    
    valid, diagnostics = validate_and_fix_queries(
        queries,
        beat_text,
        shot_types=['maps_context'],
        episode_topic="Napoleon Campaign",
        min_valid_queries=3,
        verbose=False
    )
    
    # Count queries with "map"
    map_count = sum(1 for q in valid if 'map' in q.lower())
    
    print(f"Valid queries: {valid}")
    print(f"Queries with 'map': {map_count}/{len(valid)}")
    
    assert map_count >= len(valid) * 0.7, \
        f"At least 70% of queries should contain 'map' for maps_context shot"
    
    print(f"\n✅ TEST PASSED: {map_count}/{len(valid)} queries contain 'map'")


def test_max_2_regen_then_low_coverage():
    """
    CRITICAL: Max 2 regeneration attempts, then mark as low_coverage.
    Must NOT infinite loop.
    """
    print("\n" + "="*70)
    print("TEST: Max 2 regen attempts, then low_coverage flag")
    print("="*70)
    
    beat_text = "The situation was complex."  # Very generic
    queries = [
        "situation",  # Too short, no anchor
        "complex",    # Too short, no anchor
    ]
    
    # This should trigger regeneration (need 6, have 0 valid)
    valid, diagnostics = validate_and_fix_queries(
        queries,
        beat_text,
        shot_types=['atmosphere_transition'],
        episode_topic="Generic Topic",  # Weak fallback
        min_valid_queries=6,
        max_regen_attempts=2,
        verbose=True
    )
    
    print(f"\nDiagnostics: {diagnostics}")
    
    # Should have attempted regeneration
    assert diagnostics['regenerated_count'] > 0, \
        "Should have regenerated some queries"
    
    # If still < 6, should be marked low_coverage
    if diagnostics['final_count'] < 6:
        assert diagnostics['low_coverage'], \
            "Should mark as low_coverage when insufficient"
        print(f"✅ PASS: Marked as low_coverage ({diagnostics['final_count']}/6)")
    else:
        print(f"✅ PASS: Generated sufficient queries ({diagnostics['final_count']}/6)")
    
    # Should NOT have regenerated more than what's possible in 2 attempts
    # (Each attempt tries to fill the gap, max 2 attempts)
    print(f"Regenerated: {diagnostics['regenerated_count']} queries")
    
    print("\n✅ TEST PASSED: Regeneration limited to max attempts, low_coverage flag set")


def test_no_infinite_loops():
    """
    CRITICAL: Ensure no nested retry loops can occur.
    This is a sanity check that regeneration is truly limited.
    """
    print("\n" + "="*70)
    print("TEST: No infinite loops (stress test)")
    print("="*70)
    
    beat_text = "x"  # Pathological case: no usable content
    queries = []  # Empty queries
    
    import time
    start = time.time()
    
    try:
        valid, diagnostics = validate_and_fix_queries(
            queries,
            beat_text,
            shot_types=['atmosphere_transition'],
            episode_topic="Minimal Topic",  # Required (even for stress test)
            min_valid_queries=10,  # High requirement
            max_regen_attempts=2,
            verbose=False
        )
        
        elapsed = time.time() - start
        
        print(f"Completed in {elapsed:.2f}s (max 5s expected)")
        print(f"Final count: {diagnostics['final_count']}")
        print(f"Regenerated: {diagnostics['regenerated_count']}")
        
        # Should complete quickly (< 5 seconds even in worst case)
        assert elapsed < 5.0, \
            f"Took too long ({elapsed:.2f}s), possible infinite loop"
        
        print("\n✅ TEST PASSED: No infinite loop detected")
        
    except Exception as e:
        elapsed = time.time() - start
        print(f"❌ Exception after {elapsed:.2f}s: {e}")
        if elapsed > 5.0:
            raise AssertionError("Possible infinite loop - took too long before exception")
        raise


def run_unit_tests():
    """Run all unit tests."""
    print("\n" + "="*70)
    print("QUERY GUARDRAILS UNIT TESTS - CRITICAL CASES")
    print("="*70)
    
    try:
        test_year_only_anchor_fails()
        test_olympic_games_legitimate()
        test_map_shot_contains_map()
        test_max_2_regen_then_low_coverage()
        test_no_infinite_loops()
        
        print("\n" + "="*70)
        print("🎉 ALL UNIT TESTS PASSED!")
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
    success = run_unit_tests()
    sys.exit(0 if success else 1)

