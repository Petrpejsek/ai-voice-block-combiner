"""
Test FDA compatibility layer in query guardrails.

Tests that generated queries pass FDA validator requirements:
- 5-9 words
- No forbidden start words
- No duplicate consecutive words
"""

import sys
sys.path.insert(0, '/Users/petrliesner/podcasts/backend')

from query_guardrails import (
    validate_fda_word_count,
    has_forbidden_start_word,
    has_duplicate_words,
    is_fda_compatible,
    refine_query,
    generate_safe_query,
    validate_and_fix_queries
)


def test_fda_word_count():
    """Test FDA 5-9 word requirement."""
    print("\n" + "="*70)
    print("TEST: FDA word count (5-9 words)")
    print("="*70)
    
    tests = [
        ("USS Cyclops disappearance archival photograph", True, "5 words"),
        ("USS Cyclops mysterious disappearance Bermuda Triangle archival photograph", True, "7 words"),
        ("USS Cyclops", False, "2 words (too short)"),
        ("USS Cyclops mysterious disappearance in the Bermuda Triangle region archival photograph", False, "11 words (too long)"),
    ]
    
    all_passed = True
    for query, expected, description in tests:
        result = validate_fda_word_count(query)
        word_count = len(query.split())
        status = "✅ PASS" if result == expected else "❌ FAIL"
        print(f"{status}: '{query}' ({word_count} words) - {description}")
        if result != expected:
            all_passed = False
    
    if all_passed:
        print("\n✅ TEST PASSED: FDA word count validation")
    else:
        print("\n❌ TEST FAILED: Some word count checks failed")
    
    return all_passed


def test_forbidden_start_words():
    """Test forbidden start word detection."""
    print("\n" + "="*70)
    print("TEST: Forbidden start words")
    print("="*70)
    
    tests = [
        ("although Titanic sank 1912 archival photograph", True, "starts with 'although'"),
        ("The Titanic sank 1912 archival photograph", True, "starts with 'the' (article)"),
        ("A Titanic memorial monument archival photograph", True, "starts with 'a' (article)"),
        ("Titanic sank 1912 archival photograph", False, "valid start"),
        ("However the ship went down archival photo", True, "starts with 'however'"),
        ("Despite efforts rescue failed archival document", True, "starts with 'despite'"),
    ]
    
    all_passed = True
    for query, expected, description in tests:
        result = has_forbidden_start_word(query)
        status = "✅ PASS" if result == expected else "❌ FAIL"
        print(f"{status}: '{query}' - {description}")
        if result != expected:
            all_passed = False
    
    if all_passed:
        print("\n✅ TEST PASSED: Forbidden start word detection")
    else:
        print("\n❌ TEST FAILED: Some checks failed")
    
    return all_passed


def test_duplicate_words():
    """Test duplicate consecutive word detection."""
    print("\n" + "="*70)
    print("TEST: Duplicate consecutive words")
    print("="*70)
    
    tests = [
        ("although although archival photograph", True, "duplicate 'although'"),
        ("USS Cyclops archival archival photograph", True, "duplicate 'archival'"),
        ("Titanic maiden voyage archival photograph", False, "no duplicates"),
    ]
    
    all_passed = True
    for query, expected, description in tests:
        result = has_duplicate_words(query)
        status = "✅ PASS" if result == expected else "❌ FAIL"
        print(f"{status}: '{query}' - {description}")
        if result != expected:
            all_passed = False
    
    if all_passed:
        print("\n✅ TEST PASSED: Duplicate word detection")
    else:
        print("\n❌ TEST FAILED: Some checks failed")
    
    return all_passed


def test_fda_compatible():
    """Test combined FDA compatibility check."""
    print("\n" + "="*70)
    print("TEST: Combined FDA compatibility")
    print("="*70)
    
    tests = [
        ("USS Cyclops disappearance Bermuda Triangle archival photograph", True, []),
        ("although ships disappeared archival photograph", False, ["FDA_FORBIDDEN_START (although)", "FDA_WORD_COUNT (4 words, need 5-9)"]),
        ("Titanic sank", False, ["FDA_WORD_COUNT (2 words, need 5-9)"]),
        ("USS although although Cyclops archival photograph", False, ["FDA_DUPLICATE_WORDS"]),
    ]
    
    all_passed = True
    for query, expected_valid, expected_violations in tests:
        is_valid, violations = is_fda_compatible(query)
        status = "✅ PASS" if is_valid == expected_valid else "❌ FAIL"
        print(f"{status}: '{query}'")
        if violations:
            print(f"   Violations: {violations}")
        if is_valid != expected_valid:
            all_passed = False
    
    if all_passed:
        print("\n✅ TEST PASSED: FDA compatibility check")
    else:
        print("\n❌ TEST FAILED: Some checks failed")
    
    return all_passed


def test_refine_query_fda():
    """Test that refine_query produces FDA-compatible output."""
    print("\n" + "="*70)
    print("TEST: refine_query produces FDA-compatible queries")
    print("="*70)
    
    tests = [
        # (query, beat_text, anchors, shot_type, expected_min_words)
        ("Some stories", "Titanic maiden voyage", ["Titanic"], None, 5),
        ("although sailors", "USS Cyclops disappeared", ["USS Cyclops"], None, 5),
        ("Titanic", "maiden voyage disaster", ["Titanic"], "document", 5),
    ]
    
    all_passed = True
    for query, beat, anchors, shot_type, min_words in tests:
        refined = refine_query(query, beat, anchors, shot_type, episode_topic="USS Cyclops")
        is_valid, violations = is_fda_compatible(refined)
        word_count = len(refined.split())
        
        status = "✅ PASS" if is_valid and word_count >= min_words else "❌ FAIL"
        print(f"{status}: '{query}' → '{refined}' ({word_count} words)")
        if not is_valid:
            print(f"   ⚠️  FDA violations: {violations}")
            all_passed = False
        if word_count < min_words:
            print(f"   ⚠️  Too short: {word_count} < {min_words}")
            all_passed = False
    
    if all_passed:
        print("\n✅ TEST PASSED: refine_query produces FDA-compatible queries")
    else:
        print("\n❌ TEST FAILED: Some refined queries not FDA-compatible")
    
    return all_passed


def test_generate_safe_query_fda():
    """Test that generate_safe_query produces FDA-compatible output."""
    print("\n" + "="*70)
    print("TEST: generate_safe_query produces FDA-compatible queries")
    print("="*70)
    
    tests = [
        # (beat_text, anchors, shot_type)
        ("Titanic maiden voyage disaster", ["Titanic"], None),
        ("USS Cyclops disappeared mysteriously", ["USS Cyclops"], "document"),
        ("Napoleon invasion Russia winter", ["Napoleon"], "map"),
    ]
    
    all_passed = True
    for beat, anchors, shot_type in tests:
        safe_query = generate_safe_query(beat, anchors, shot_type, episode_topic="Historical Topic")
        is_valid, violations = is_fda_compatible(safe_query)
        word_count = len(safe_query.split())
        
        status = "✅ PASS" if is_valid else "❌ FAIL"
        print(f"{status}: Generated '{safe_query}' ({word_count} words)")
        if not is_valid:
            print(f"   ⚠️  FDA violations: {violations}")
            all_passed = False
    
    if all_passed:
        print("\n✅ TEST PASSED: generate_safe_query produces FDA-compatible queries")
    else:
        print("\n❌ TEST FAILED: Some safe queries not FDA-compatible")
    
    return all_passed


def test_full_pipeline_fda():
    """Test that validate_and_fix_queries produces FDA-compatible output."""
    print("\n" + "="*70)
    print("TEST: Full pipeline produces FDA-compatible queries")
    print("="*70)
    
    # Real-world example from error log
    queries = [
        "Some stories archival photograph",  # 4 words, too short
        "Titanic maiden document",  # 3 words, too short
        "although Titanic sank archival photograph",  # forbidden start
    ]
    
    beat_text = "The Titanic's maiden voyage ended in disaster when the ship struck an iceberg."
    shot_types = ["wide", "document", "close"]
    
    validated, diagnostics = validate_and_fix_queries(
        queries,
        beat_text,
        shot_types=shot_types,
        episode_topic="RMS Titanic",
        min_valid_queries=5,
        max_regen_attempts=2,
        verbose=True
    )
    
    print(f"\nFinal validated queries: {len(validated)}")
    all_fda_ok = True
    for i, query in enumerate(validated):
        is_valid, violations = is_fda_compatible(query)
        word_count = len(query.split())
        status = "✅ FDA OK" if is_valid else "❌ FDA FAIL"
        print(f"  {i+1}. {status}: '{query}' ({word_count} words)")
        if not is_valid:
            print(f"     Violations: {violations}")
            all_fda_ok = False
    
    if all_fda_ok and len(validated) == 5:  # MUST be exactly 5 (FDA v2.7 requirement)
        print("\n✅ TEST PASSED: Full pipeline produces FDA-compatible queries")
        return True
    else:
        if not all_fda_ok:
            print("\n❌ TEST FAILED: Some queries not FDA-compatible")
        else:
            print(f"\n❌ TEST FAILED: Insufficient coverage ({len(validated)}/3 minimum)")
        return False


if __name__ == "__main__":
    print("="*70)
    print("FDA COMPATIBILITY TESTS")
    print("="*70)
    
    results = []
    results.append(("Word count", test_fda_word_count()))
    results.append(("Forbidden start", test_forbidden_start_words()))
    results.append(("Duplicate words", test_duplicate_words()))
    results.append(("FDA compatible", test_fda_compatible()))
    results.append(("Refine query FDA", test_refine_query_fda()))
    results.append(("Generate safe FDA", test_generate_safe_query_fda()))
    results.append(("Full pipeline FDA", test_full_pipeline_fda()))
    
    print("\n" + "="*70)
    print("SUMMARY")
    print("="*70)
    for name, passed in results:
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{status}: {name}")
    
    if all(r[1] for r in results):
        print("\n🎉 ALL FDA COMPATIBILITY TESTS PASSED!")
    else:
        print("\n❌ SOME TESTS FAILED")
        sys.exit(1)

