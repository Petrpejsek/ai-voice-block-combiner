"""
Unit tests for FDA v2.7 Keyword Normalizer

Tests přesně odpovídají fail scénáři z produkce:
- Input: ["Titanic", "Southampton", "iceberg", "breached", "documents"]
- Expected: všechny 2-5 slov, deterministické, žádné duplicity
"""

import sys
sys.path.insert(0, '/Users/petrliesner/podcasts/backend')

from fda_keyword_normalizer import (
    normalize_keyword,
    normalize_scene_keywords,
    extract_main_entity,
    KEYWORD_DESCRIPTORS,
    GENERIC_SINGLE_WORDS,
    FDA_V27_PHYSICAL_OBJECT_TYPES,
    _contains_object_type
)


def test_extract_main_entity():
    """Test extraction of main entity from episode_topic."""
    print("\n" + "="*70)
    print("TEST: Extract main entity from episode_topic")
    print("="*70)
    
    tests = [
        ("The Titanic Disaster 1912", "Titanic Disaster"),  # 2 words (max_words=2)
        ("USS Cyclops Mystery", "USS Cyclops"),
        ("Napoleon's Russian Campaign", "Napoleon's Russian"),
        ("World War Two Pacific Theater", "World War"),
        ("simple", "simple"),
        ("", "historical"),  # Empty → fallback
    ]
    
    all_passed = True
    for topic, expected in tests:
        result = extract_main_entity(topic)
        status = "✅ PASS" if result == expected else "❌ FAIL"
        print(f"{status}: '{topic}' → '{result}' (expected '{expected}')")
        if result != expected:
            all_passed = False
    
    if all_passed:
        print("\n✅ TEST PASSED: Main entity extraction")
    else:
        print("\n❌ TEST FAILED: Some extractions incorrect")
    
    return all_passed


def test_physical_objects_enforcement():
    """Test that min 3 keywords contain physical objects (FDA validator requirement)."""
    print("\n" + "="*70)
    print("TEST: Physical objects enforcement (min 3)")
    print("="*70)
    
    # Input: keywords with only 1 physical object ("documents")
    keywords = ["Titanic", "Southampton", "service", "time", "documents", "maiden", "voyage", "Atlantic"]
    episode_topic = "The Titanic Disaster 1912"
    
    print(f"Input keywords: {keywords}")
    
    normalized, diagnostics = normalize_scene_keywords(keywords, episode_topic, scene_id="sc_phys", verbose=True)
    
    # Count physical objects using SAME logic as FDA validator
    physical_count = sum(1 for kw in normalized if _contains_object_type(kw, FDA_V27_PHYSICAL_OBJECT_TYPES))
    
    print(f"\nNormalized keywords:")
    for i, kw in enumerate(normalized):
        has_physical = _contains_object_type(kw, FDA_V27_PHYSICAL_OBJECT_TYPES)
        marker = "🏛️" if has_physical else "  "
        print(f"  [{i}] {marker} '{kw}'")
    
    print(f"\nPhysical objects count: {physical_count}/8 (min 3 required)")
    print(f"Diagnostics physical_count: {diagnostics.get('physical_count')}")
    print(f"Diagnostics physical_fixed: {diagnostics.get('physical_fixed')}")
    
    # Validation
    if physical_count >= 3:
        print(f"\n✅ TEST PASSED: {physical_count} keywords contain physical objects (>= 3)")
        return True
    else:
        print(f"\n❌ TEST FAILED: Only {physical_count} keywords contain physical objects (need >= 3)")
        return False


def test_regression_real_fail_case():
    """Test EXACT regression case from production: empty, 1-word, 9 count, 1 physical."""
    print("\n" + "="*70)
    print("TEST: Regression - real production fail case")
    print("="*70)
    
    # EXACT fail case:
    # - 1 empty keyword ("")
    # - Multiple 1-word: Titanic, Southampton, iceberg, collision, documents
    # - Count: 9 (expected 8)
    # - Physical objects: only 1 (expected >= 3)
    keywords = ["", "Titanic", "Southampton", "iceberg", "collision", "documents", "service", "time", "largest"]
    episode_topic = "The Titanic Disaster 1912"
    
    print(f"Input: {len(keywords)} keywords (expected 8)")
    print(f"Keywords: {keywords}")
    
    normalized, diagnostics = normalize_scene_keywords(keywords, episode_topic, scene_id="sc_regression", verbose=True)
    
    # Validations (all must pass)
    checks = []
    
    # 1. Exactly 8 keywords
    checks.append(("Exactly 8 keywords", len(normalized) == 8))
    
    # 2. All 2-5 words
    all_valid_length = all(2 <= len(kw.split()) <= 5 for kw in normalized)
    checks.append(("All 2-5 words", all_valid_length))
    
    # 3. No empty keywords
    no_empty = all(kw.strip() != "" for kw in normalized)
    checks.append(("No empty keywords", no_empty))
    
    # 4. Physical objects >= 3
    physical_count = sum(1 for kw in normalized if _contains_object_type(kw, FDA_V27_PHYSICAL_OBJECT_TYPES))
    checks.append((f"Physical objects >= 3 (actual: {physical_count})", physical_count >= 3))
    
    # 5. "largest" removed (LLM filler)
    largest_removed = "largest" not in [kw.lower() for kw in normalized]
    checks.append(("LLM filler 'largest' removed", largest_removed))
    
    print(f"\nOutput: {len(normalized)} keywords")
    for i, kw in enumerate(normalized):
        has_physical = _contains_object_type(kw, FDA_V27_PHYSICAL_OBJECT_TYPES)
        marker = "🏛️" if has_physical else "  "
        print(f"  [{i}] {marker} '{kw}'")
    
    print(f"\nValidation:")
    for check_name, passed in checks:
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"  {status}: {check_name}")
    
    if all(c[1] for c in checks):
        print("\n✅ TEST PASSED: Regression case fixed!")
        return True
    else:
        print("\n❌ TEST FAILED: Regression case still has issues")
        return False
    """Test that single-word keywords expand to 2-5 words."""
    print("\n" + "="*70)
    print("TEST: Single-word keywords expand to 2-5 words")
    print("="*70)
    
    episode_topic = "The Titanic Disaster 1912"
    main_entity = extract_main_entity(episode_topic)
    
    single_words = ["Titanic", "Southampton", "iceberg", "breached", "documents"]
    
    all_valid = True
    used_phrases = set()
    
    for word in single_words:
        normalized = normalize_keyword(word, episode_topic, main_entity, used_phrases)
        word_count = len(normalized.split())
        status = "✅ PASS" if 2 <= word_count <= 5 else "❌ FAIL"
        print(f"{status}: '{word}' → '{normalized}' ({word_count} words)")
        
        if not (2 <= word_count <= 5):
            all_valid = False
        
        used_phrases.add(normalized.lower())
    
    if all_valid:
        print("\n✅ TEST PASSED: All single words expanded to 2-5 words")
    else:
        print("\n❌ TEST FAILED: Some keywords not in 2-5 word range")
    
    return all_valid


def test_generic_keyword_filter():
    """Test that generic single words are expanded with entity prefix."""
    print("\n" + "="*70)
    print("TEST: Generic keyword filter (CRITICAL for production fail)")
    print("="*70)
    
    # EXACT FAIL CASE from production
    keywords = ["Titanic", "Southampton", "service", "time", "documents"]
    episode_topic = "The Titanic Disaster 1912"
    
    print(f"Input (production fail case): {keywords}")
    print(f"Episode topic: '{episode_topic}'")
    
    normalized, diagnostics = normalize_scene_keywords(
        keywords + ["maiden", "voyage", "Atlantic"],  # Pad to 8
        episode_topic,
        scene_id="sc_0001",
        verbose=True
    )
    
    print(f"\nDiagnostics:")
    print(f"  single_word_before: {diagnostics['single_word_before']}")
    print(f"  generic_single_before: {diagnostics['generic_single_before']}")
    print(f"  single_word_after: {diagnostics['single_word_after']}")
    print(f"  rewrites: {diagnostics['rewrites_sample']}")
    
    print(f"\nNormalized keywords:")
    for i, kw in enumerate(normalized):
        word_count = len(kw.split())
        is_generic = kw.lower() in GENERIC_SINGLE_WORDS
        status = "✅" if word_count >= 2 and not is_generic else "❌"
        print(f"  [{i}] {status} '{kw}' ({word_count} words)")
    
    # Validate
    all_valid = True
    errors = []
    
    # 1. No single words
    for i, kw in enumerate(normalized):
        word_count = len(kw.split())
        if word_count < 2:
            errors.append(f"Keyword[{i}] '{kw}' is single word")
            all_valid = False
    
    # 2. No generic singletons
    for i, kw in enumerate(normalized):
        if kw.lower() in GENERIC_SINGLE_WORDS:
            errors.append(f"Keyword[{i}] '{kw}' is generic singleton")
            all_valid = False
    
    # 3. single_word_after must be 0
    if diagnostics['single_word_after'] != 0:
        errors.append(f"single_word_after={diagnostics['single_word_after']}, expected 0")
        all_valid = False
    
    if all_valid:
        print("\n✅ TEST PASSED: Generic keyword filter working correctly")
    else:
        print(f"\n❌ TEST FAILED: {'; '.join(errors)}")
    
    return all_valid


def test_exact_production_fail():
    """Test EXACT production fail case: ["Titanic","Southampton","service","time","documents"]"""
    print("\n" + "="*70)
    print("TEST: EXACT production fail case (original 8 keywords)")
    print("="*70)
    
    # EXACT INPUT from your fail
    keywords = ["Titanic", "Southampton", "service", "time", "documents", "maiden", "voyage", "Atlantic"]
    episode_topic = "The Titanic Disaster 1912"
    
    normalized, diagnostics = normalize_scene_keywords(keywords, episode_topic, scene_id="sc_0001", verbose=False)
    
    print(f"Original: {keywords}")
    print(f"Normalized:")
    for i, kw in enumerate(normalized):
        orig = keywords[i] if i < len(keywords) else "N/A"
        word_count = len(kw.split())
        print(f"  [{i}] '{orig}' → '{kw}' ({word_count} words)")
    
    # Critical checks
    checks = []
    
    # 1. All 2-5 words
    all_valid_length = all(2 <= len(kw.split()) <= 5 for kw in normalized)
    checks.append(("All 2-5 words", all_valid_length))
    
    # 2. No generic singletons
    no_generic = all(kw.lower() not in GENERIC_SINGLE_WORDS for kw in normalized)
    checks.append(("No generic singletons", no_generic))
    
    # 3. Exactly 8 keywords
    correct_count = len(normalized) == 8
    checks.append(("Exactly 8 keywords", correct_count))
    
    # 4. No duplicates
    no_dupes = len(set(kw.lower() for kw in normalized)) == len(normalized)
    checks.append(("No duplicates", no_dupes))
    
    print(f"\nValidation:")
    for check_name, passed in checks:
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"  {status}: {check_name}")
    
    if all(c[1] for c in checks):
        print("\n✅ TEST PASSED: Production fail case fixed!")
        return True
    else:
        print("\n❌ TEST FAILED: Still has issues")
        return False


def test_nine_keywords_trim_to_eight():
    """Test that 9 keywords are trimmed to exactly 8."""
    print("\n" + "="*70)
    print("TEST: 9 keywords → trim to 8 (production fail: expected 8, got 9)")
    print("="*70)
    
    # Input: 9 keywords (one extra)
    keywords = ["Southampton", "Titanic", "largest", "service", "time", "documents", "maiden", "voyage", "Atlantic"]
    episode_topic = "The Titanic Disaster 1912"
    
    print(f"Input: {len(keywords)} keywords")
    print(f"Keywords: {keywords}")
    
    normalized, diagnostics = normalize_scene_keywords(keywords, episode_topic, scene_id="sc_0002", verbose=True)
    
    print(f"\nOutput: {len(normalized)} keywords")
    for i, kw in enumerate(normalized):
        word_count = len(kw.split())
        print(f"  [{i}] '{kw}' ({word_count} words)")
    
    # Checks
    checks = []
    
    # 1. Exactly 8 (not 9)
    checks.append(("Exactly 8 keywords", len(normalized) == 8))
    
    # 2. All 2-5 words
    all_valid_length = all(2 <= len(kw.split()) <= 5 for kw in normalized)
    checks.append(("All 2-5 words", all_valid_length))
    
    # 3. "largest" should be removed (LLM filler)
    largest_removed = "largest" not in [kw.lower() for kw in normalized]
    checks.append(("LLM filler 'largest' removed", largest_removed))
    
    # 4. No single words
    no_single_words = all(len(kw.split()) >= 2 for kw in normalized)
    checks.append(("No single words", no_single_words))
    
    print(f"\nValidation:")
    for check_name, passed in checks:
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"  {status}: {check_name}")
    
    print(f"\nDiagnostics:")
    print(f"  original_count: {diagnostics.get('original_count')}")
    print(f"  llm_filler_removed: {diagnostics.get('llm_filler_removed')}")
    print(f"  trimmed: {diagnostics.get('trimmed')}")
    print(f"  final_count: {diagnostics.get('final_count')}")
    
    if all(c[1] for c in checks):
        print("\n✅ TEST PASSED: 9 keywords correctly trimmed to 8")
        return True
    else:
        print("\n❌ TEST FAILED: Trimming failed")
        return False


def test_seven_keywords_pad_to_eight():
    """Test that 7 keywords are padded to exactly 8."""
    print("\n" + "="*70)
    print("TEST: 7 keywords → pad to 8")
    print("="*70)
    
    # Input: 7 keywords (one missing)
    keywords = ["Titanic", "Southampton", "iceberg", "breached", "documents", "maiden", "voyage"]
    episode_topic = "The Titanic Disaster 1912"
    
    print(f"Input: {len(keywords)} keywords")
    print(f"Keywords: {keywords}")
    
    normalized, diagnostics = normalize_scene_keywords(keywords, episode_topic, scene_id="sc_0003", verbose=True)
    
    print(f"\nOutput: {len(normalized)} keywords")
    for i, kw in enumerate(normalized):
        word_count = len(kw.split())
        print(f"  [{i}] '{kw}' ({word_count} words)")
    
    # Checks
    checks = []
    
    # 1. Exactly 8 (not 7)
    checks.append(("Exactly 8 keywords", len(normalized) == 8))
    
    # 2. All 2-5 words
    all_valid_length = all(2 <= len(kw.split()) <= 5 for kw in normalized)
    checks.append(("All 2-5 words", all_valid_length))
    
    # 3. No duplicates
    no_dupes = len(set(kw.lower() for kw in normalized)) == len(normalized)
    checks.append(("No duplicates", no_dupes))
    
    print(f"\nValidation:")
    for check_name, passed in checks:
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"  {status}: {check_name}")
    
    print(f"\nDiagnostics:")
    print(f"  original_count: {diagnostics.get('original_count')}")
    print(f"  padded: {diagnostics.get('padded')}")
    print(f"  final_count: {diagnostics.get('final_count')}")
    
    if all(c[1] for c in checks):
        print("\n✅ TEST PASSED: 7 keywords correctly padded to 8")
        return True
    else:
        print("\n❌ TEST FAILED: Padding failed")
        return False
    """Test normalize_scene_keywords with real production fail case."""
    print("\n" + "="*70)
    print("TEST: Full scene normalization (production fail case)")
    print("="*70)
    
    # Exact fail case from screenshot
    keywords = ["Titanic", "Southampton", "iceberg", "breached", "documents", "maiden", "voyage", "Atlantic"]
    episode_topic = "The Titanic Disaster 1912"
    
    normalized = normalize_scene_keywords(keywords, episode_topic, scene_id="sc_0001", verbose=True)
    
    print(f"\nOriginal keywords: {keywords}")
    print(f"Normalized keywords:")
    for i, kw in enumerate(normalized):
        word_count = len(kw.split())
        print(f"  [{i}] '{kw}' ({word_count} words)")
    
    # Validate
    all_valid = True
    errors = []
    
    # Check count
    if len(normalized) != 8:
        errors.append(f"Expected 8 keywords, got {len(normalized)}")
        all_valid = False
    
    # Check word count
    for i, kw in enumerate(normalized):
        word_count = len(kw.split())
        if not (2 <= word_count <= 5):
            errors.append(f"Keyword[{i}] '{kw}' has {word_count} words (need 2-5)")
            all_valid = False
    
    # Check no empty
    if any(not kw.strip() for kw in normalized):
        errors.append("Some keywords are empty")
        all_valid = False
    
    # Check no exact duplicates (case-insensitive)
    lowercase_set = [kw.lower() for kw in normalized]
    if len(lowercase_set) != len(set(lowercase_set)):
        errors.append("Duplicate keywords found")
        all_valid = False
    
    if all_valid:
        print("\n✅ TEST PASSED: Full scene normalization valid")
    else:
        print(f"\n❌ TEST FAILED: {'; '.join(errors)}")
    
    return all_valid


def test_truncate_long_keywords():
    """Test that keywords >5 words are truncated to 5."""
    print("\n" + "="*70)
    print("TEST: Long keywords (>5 words) truncated to 5")
    print("="*70)
    
    episode_topic = "The Titanic Disaster 1912"
    main_entity = extract_main_entity(episode_topic)
    
    long_keywords = [
        "This is a very long keyword phrase with many words",  # 10 words
        "Another extremely long historical archival photograph descriptor",  # 7 words
        "Six word long keyword phrase here",  # 6 words
    ]
    
    all_passed = True
    used_phrases = set()
    
    for kw in long_keywords:
        original_count = len(kw.split())
        normalized = normalize_keyword(kw, episode_topic, main_entity, used_phrases)
        word_count = len(normalized.split())
        
        status = "✅ PASS" if word_count <= 5 else "❌ FAIL"
        print(f"{status}: '{kw[:40]}...' ({original_count} words) → '{normalized}' ({word_count} words)")
        
        if word_count > 5:
            all_passed = False
        
        used_phrases.add(normalized.lower())
    
    if all_passed:
        print("\n✅ TEST PASSED: Long keywords truncated correctly")
    else:
        print("\n❌ TEST FAILED: Some keywords exceed 5 words")
    
    return all_passed


def test_full_scene_normalization():
    """Test normalize_scene_keywords with real production fail case."""
    print("\n" + "="*70)
    print("TEST: Full scene normalization (original test)")
    print("="*70)
    
    keywords = ["Titanic", "Southampton", "iceberg", "breached", "documents", "maiden", "voyage", "Atlantic"]
    episode_topic = "The Titanic Disaster 1912"
    
    normalized, diagnostics = normalize_scene_keywords(keywords, episode_topic, scene_id="sc_0001", verbose=True)
    
    print(f"\nOriginal keywords: {keywords}")
    print(f"Normalized keywords:")
    for i, kw in enumerate(normalized):
        word_count = len(kw.split())
        print(f"  [{i}] '{kw}' ({word_count} words)")
    
    # Validate
    all_valid = True
    errors = []
    
    # Check count
    if len(normalized) != 8:
        errors.append(f"Expected 8 keywords, got {len(normalized)}")
        all_valid = False
    
    # Check word count
    for i, kw in enumerate(normalized):
        word_count = len(kw.split())
        if not (2 <= word_count <= 5):
            errors.append(f"Keyword[{i}] '{kw}' has {word_count} words (need 2-5)")
            all_valid = False
    
    # Check no empty
    if any(not kw.strip() for kw in normalized):
        errors.append("Some keywords are empty")
        all_valid = False
    
    # Check no exact duplicates (case-insensitive)
    lowercase_set = [kw.lower() for kw in normalized]
    if len(lowercase_set) != len(set(lowercase_set)):
        errors.append("Duplicate keywords found")
        all_valid = False
    
    if all_valid:
        print("\n✅ TEST PASSED: Full scene normalization valid")
    else:
        print(f"\n❌ TEST FAILED: {'; '.join(errors)}")
    
    return all_valid


def test_deduplication():
    """Test that duplicate keywords are handled correctly."""
    print("\n" + "="*70)
    print("TEST: Duplicate keywords handled correctly")
    print("="*70)
    
    # Keywords with duplicates
    keywords = ["Titanic", "Titanic", "ship", "ship", "iceberg", "iceberg", "documents", "documents"]
    episode_topic = "The Titanic Disaster 1912"
    
    normalized, diagnostics = normalize_scene_keywords(keywords, episode_topic, scene_id="sc_test_dedup", verbose=True)
    
    print(f"\nOriginal (with duplicates): {keywords}")
    print(f"Normalized:")
    for i, kw in enumerate(normalized):
        print(f"  [{i}] '{kw}'")
    
    # Check for duplicates (case-insensitive)
    lowercase_set = [kw.lower() for kw in normalized]
    unique_count = len(set(lowercase_set))
    
    if unique_count == len(normalized):
        print(f"\n✅ TEST PASSED: All {len(normalized)} keywords unique (no duplicates)")
        return True
    else:
        print(f"\n❌ TEST FAILED: Found duplicates - {len(normalized)} keywords but only {unique_count} unique")
        return False


def test_determinism():
    """Test that same input produces same output (deterministic)."""
    print("\n" + "="*70)
    print("TEST: Determinism (same input → same output)")
    print("="*70)
    
    keywords = ["Titanic", "Southampton", "iceberg", "breached", "documents", "maiden", "voyage", "Atlantic"]
    episode_topic = "The Titanic Disaster 1912"
    
    # Run 3 times
    results = []
    for run in range(3):
        normalized, diagnostics = normalize_scene_keywords(keywords, episode_topic, scene_id=f"run_{run}", verbose=False)
        results.append(normalized)  # Only compare keywords, not diagnostics
    
    # Check all 3 runs are identical
    all_same = all(results[0] == results[i] for i in range(1, 3))
    
    print(f"Run 1: {results[0]}")
    print(f"Run 2: {results[1]}")
    print(f"Run 3: {results[2]}")
    
    if all_same:
        print("\n✅ TEST PASSED: All 3 runs produced identical output (deterministic)")
        return True
    else:
        print("\n❌ TEST FAILED: Runs produced different outputs (non-deterministic)")
        return False
    """Test that duplicate keywords are handled correctly."""
    print("\n" + "="*70)
    print("TEST: Duplicate keywords handled correctly")
    print("="*70)
    
    # Keywords with duplicates
    keywords = ["Titanic", "Titanic", "ship", "ship", "iceberg", "iceberg", "documents", "documents"]
    episode_topic = "The Titanic Disaster 1912"
    
    normalized = normalize_scene_keywords(keywords, episode_topic, scene_id="sc_test_dedup", verbose=True)
    
    print(f"\nOriginal (with duplicates): {keywords}")
    print(f"Normalized:")
    for i, kw in enumerate(normalized):
        print(f"  [{i}] '{kw}'")
    
    # Check for duplicates (case-insensitive)
    lowercase_set = [kw.lower() for kw in normalized]
    unique_count = len(set(lowercase_set))
    
    if unique_count == len(normalized):
        print(f"\n✅ TEST PASSED: All {len(normalized)} keywords unique (no duplicates)")
        return True
    else:
        print(f"\n❌ TEST FAILED: Found duplicates - {len(normalized)} keywords but only {unique_count} unique")
        return False


def test_descriptor_map():
    """Test that descriptor map works for common terms."""
    print("\n" + "="*70)
    print("TEST: Descriptor map for common terms")
    print("="*70)
    
    episode_topic = "Historical Events"
    main_entity = extract_main_entity(episode_topic)
    
    # Test common single words that should have descriptors
    test_words = ["documents", "map", "photo", "iceberg", "breached", "Southampton", "Titanic"]
    
    all_passed = True
    used_phrases = set()
    
    for word in test_words:
        normalized = normalize_keyword(word, episode_topic, main_entity, used_phrases)
        word_count = len(normalized.split())
        
        # Should be 2+ words
        status = "✅ PASS" if word_count >= 2 else "❌ FAIL"
        print(f"{status}: '{word}' → '{normalized}' ({word_count} words)")
        
        if word_count < 2:
            all_passed = False
        
        used_phrases.add(normalized.lower())
    
    if all_passed:
        print("\n✅ TEST PASSED: Descriptor map working correctly")
    else:
        print("\n❌ TEST FAILED: Some descriptors not applied")
    
    return all_passed


if __name__ == "__main__":
    print("="*70)
    print("FDA v2.7 KEYWORD NORMALIZER - TESTS (with PHYSICAL OBJECTS)")
    print("="*70)
    
    results = []
    results.append(("Main entity extraction", test_extract_main_entity()))
    results.append(("Physical objects enforcement", test_physical_objects_enforcement()))
    results.append(("Regression - real fail case", test_regression_real_fail_case()))
    results.append(("Generic keyword filter", test_generic_keyword_filter()))
    results.append(("EXACT production fail (8→8)", test_exact_production_fail()))
    results.append(("9 keywords → trim to 8", test_nine_keywords_trim_to_eight()))
    results.append(("7 keywords → pad to 8", test_seven_keywords_pad_to_eight()))
    results.append(("Full scene normalization", test_full_scene_normalization()))
    results.append(("Long keyword truncation", test_truncate_long_keywords()))
    results.append(("Deduplication", test_deduplication()))
    results.append(("Determinism", test_determinism()))
    results.append(("Descriptor map", test_descriptor_map()))
    
    print("\n" + "="*70)
    print("SUMMARY")
    print("="*70)
    for name, passed in results:
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{status}: {name}")
    
    if all(r[1] for r in results):
        print("\n🎉 ALL KEYWORD NORMALIZER TESTS PASSED!")
    else:
        print("\n❌ SOME TESTS FAILED")
        sys.exit(1)

