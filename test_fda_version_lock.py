#!/usr/bin/env python3
"""
Test script pro ověření FDA version lock
Tento script testuje, že verze shot_plan.version zůstává fda_v2.7 po celou pipeline.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'backend'))

from footage_director import FDA_V27_VERSION, apply_deterministic_generators_v27
from pre_fda_sanitizer import sanitize_shot_plan

def test_version_constant():
    """Test 1: Ověření že konstanta FDA_V27_VERSION existuje a má správnou hodnotu"""
    print("🧪 Test 1: FDA_V27_VERSION constant")
    print(f"   FDA_V27_VERSION = '{FDA_V27_VERSION}'")
    assert FDA_V27_VERSION == "fda_v2.7", f"❌ Očekáváno 'fda_v2.7', ale máme '{FDA_V27_VERSION}'"
    print("   ✅ PASS: Konstanta má správnou hodnotu\n")

def test_sanitizer_preserves_version():
    """Test 2: Ověření že Pre-FDA Sanitizer nemění verzi"""
    print("🧪 Test 2: Pre-FDA Sanitizer preserves version")
    
    test_shot_plan = {
        "version": "fda_v2.7",
        "source": "tts_ready_package",
        "scenes": [
            {
                "scene_id": "sc_0001",
                "keywords": ["test", "strategic", "footage"],
                "search_queries": ["test query", "battle footage"],
                "narration_summary": "Test summary with strategic importance.",
                "shot_strategy": {
                    "shot_types": ["archival_documents"]
                }
            }
        ]
    }
    
    original_version = test_shot_plan["version"]
    print(f"   Original version: '{original_version}'")
    
    sanitized, log_data = sanitize_shot_plan(test_shot_plan)
    
    final_version = sanitized.get("version")
    print(f"   Final version: '{final_version}'")
    
    assert final_version == original_version, f"❌ Verze změněna: '{original_version}' → '{final_version}'"
    assert final_version == "fda_v2.7", f"❌ Očekáváno 'fda_v2.7', ale máme '{final_version}'"
    print("   ✅ PASS: Sanitizer zachoval verzi\n")

def test_deterministic_generators_preserve_version():
    """Test 3: Ověření že apply_deterministic_generators_v27 nemění verzi"""
    print("🧪 Test 3: Deterministic generators preserve version")
    
    test_wrapper = {
        "shot_plan": {
            "version": "fda_v2.7",
            "source": "tts_ready_package",
            "scenes": [
                {
                    "scene_id": "sc_0001",
                    "start_sec": 0,
                    "end_sec": 10,
                    "narration_block_ids": ["b_0001"],
                    "narration_summary": "Test summary.",
                    "keywords": ["test", "document", "map"],
                    "shot_strategy": {
                        "shot_types": ["archival_documents"],
                        "source_preference": ["archive_org"]
                    },
                    "search_queries": ["test query"]
                }
            ]
        }
    }
    
    tts_package = {
        "narration_blocks": [
            {
                "block_id": "b_0001",
                "text_tts": "This is a test narration about Napoleon in Moscow in 1812."
            }
        ]
    }
    
    original_version = test_wrapper["shot_plan"]["version"]
    print(f"   Original version: '{original_version}'")
    
    result = apply_deterministic_generators_v27(test_wrapper, tts_package, episode_id="test_ep")
    
    final_version = result["shot_plan"].get("version")
    print(f"   Final version: '{final_version}'")
    
    assert final_version == original_version, f"❌ Verze změněna: '{original_version}' → '{final_version}'"
    assert final_version == "fda_v2.7", f"❌ Očekáváno 'fda_v2.7', ale máme '{final_version}'"
    print("   ✅ PASS: Deterministic generators zachovaly verzi\n")

def test_wrong_version_detection():
    """Test 4: Ověření že validátor detekuje špatnou verzi"""
    print("🧪 Test 4: Validator detects wrong version")
    
    from footage_director import validate_fda_hard_v27
    
    test_wrapper = {
        "shot_plan": {
            "version": "fda_v3.0",  # ❌ Špatná verze!
            "source": "tts_ready_package",
            "scenes": []
        }
    }
    
    tts_package = {
        "narration_blocks": []
    }
    
    try:
        validate_fda_hard_v27(test_wrapper, tts_package, episode_id="test_ep")
        print("   ❌ FAIL: Validátor by měl vyhodit RuntimeError pro špatnou verzi!")
        return False
    except RuntimeError as e:
        error_msg = str(e)
        print(f"   Caught expected error: {error_msg[:100]}...")
        assert "FDA_VALIDATION_FAILED" in error_msg, f"❌ Očekáván error 'FDA_VALIDATION_FAILED', ale máme: {error_msg[:50]}"
        assert "VERSION_MISMATCH" in error_msg, f"❌ Očekáván 'VERSION_MISMATCH', ale máme: {error_msg[:50]}"
        print("   ✅ PASS: Validátor správně detekoval špatnou verzi\n")
        return True


def test_v27_coercion_gate_prevents_version_mismatch_violation():
    """Test 5: v2.7 coercion gate forces version to fda_v2.7 and validator must not report VERSION_MISMATCH."""
    print("🧪 Test 5: v2.7 coercion gate forces version and removes VERSION_MISMATCH")

    from footage_director import coerce_fda_v27_version_inplace, validate_fda_hard_v27

    # Minimal wrapper that reaches version check; other violations are allowed.
    wrapper = {
        "shot_plan": {
            "version": "fda_v3.0",  # wrong on purpose
            "source": "tts_ready_package",
            "assumptions": {"words_per_minute": 150},
            "scenes": [],
        }
    }
    tts_pkg = {"narration_blocks": []}

    coerced = coerce_fda_v27_version_inplace(wrapper, episode_id="test_ep_coerce")
    assert coerced is True, "❌ Expected coercion to occur"
    assert wrapper["shot_plan"]["version"] == FDA_V27_VERSION, "❌ Coercion did not set FDA_V27_VERSION"

    try:
        validate_fda_hard_v27(wrapper, tts_pkg, episode_id="test_ep_coerce")
        print("   ✅ PASS: Validator passed after coercion\n")
        return True
    except RuntimeError as e:
        msg = str(e)
        assert "VERSION_MISMATCH" not in msg, f"❌ Validator still reports VERSION_MISMATCH after coercion: {msg[:200]}"
        print("   ✅ PASS: Validator failed for other reasons, but NOT VERSION_MISMATCH\n")
        return True


def run_all_tests():
    """Spustí všechny testy"""
    print("=" * 70)
    print("FDA VERSION LOCK TEST SUITE")
    print("=" * 70)
    print()
    
    tests = [
        test_version_constant,
        test_sanitizer_preserves_version,
        test_deterministic_generators_preserve_version,
        test_wrong_version_detection,
        test_v27_coercion_gate_prevents_version_mismatch_violation,
    ]
    
    passed = 0
    failed = 0
    
    for test in tests:
        try:
            result = test()
            if result is False:
                failed += 1
            else:
                passed += 1
        except Exception as e:
            print(f"   ❌ FAIL: {e}\n")
            failed += 1
    
    print("=" * 70)
    print(f"RESULTS: {passed} passed, {failed} failed")
    print("=" * 70)
    
    return failed == 0

if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)

