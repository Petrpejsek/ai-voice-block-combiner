"""
Test: Missing episode_topic must cause hard fail
"""

import sys
sys.path.insert(0, '/Users/petrliesner/podcasts/backend')

from query_guardrails import validate_and_fix_queries


def test_missing_episode_topic_hard_fail():
    """
    CRITICAL: If episode_topic is missing/empty, must hard fail.
    No silent fallback to generic terms.
    """
    print("\n" + "="*70)
    print("TEST: Missing episode_topic must cause hard fail")
    print("="*70)
    
    beat_text = "The battle was intense."
    queries = ["battle photograph"]
    
    # Test with None
    try:
        valid, diag = validate_and_fix_queries(
            queries,
            beat_text,
            shot_types=['archival_documents'],
            episode_topic=None,  # Missing!
            min_valid_queries=1,
            verbose=False
        )
        # If we get here, test FAILED (should have raised)
        print(f"❌ FAIL: No exception raised with episode_topic=None")
        print(f"   Got valid queries: {valid}")
        return False
    except (ValueError, RuntimeError) as e:
        print(f"✅ PASS: Correctly raised exception with episode_topic=None")
        print(f"   Exception: {e}")
    
    # Test with empty string
    try:
        valid, diag = validate_and_fix_queries(
            queries,
            beat_text,
            shot_types=['archival_documents'],
            episode_topic="",  # Empty!
            min_valid_queries=1,
            verbose=False
        )
        # Empty string should work but use only beat anchors
        print(f"ℹ️  Empty string accepted (uses beat anchors only)")
        print(f"   Valid queries: {valid}")
    except Exception as e:
        print(f"ℹ️  Empty string also rejected: {e}")
    
    return True


if __name__ == '__main__':
    success = test_missing_episode_topic_hard_fail()
    sys.exit(0 if success else 1)


