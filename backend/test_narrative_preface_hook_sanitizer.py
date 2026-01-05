#!/usr/bin/env python3
"""
Regression test: deterministic sanitizer for narrative preface/hook.

Run:
  python3 backend/test_narrative_preface_hook_sanitizer.py
"""

import script_pipeline


def test_preface_claim_ids_are_filled_when_text_is_factual() -> None:
    research_report = {
        "claims": [{"claim_id": "c_001", "text": "X", "importance": "high"}],
        "entities": [{"name": "Napoleon Bonaparte", "type": "person"}],
    }
    draft = {
        "title_candidates": ["t"],
        "hook": "A safe teaser.",
        "chapters": [{"chapter_id": "ch_01", "title": "x", "narration_blocks": [{"block_id": "b_0001", "text": "x", "claim_ids": ["c_001"]}]}],
        "supported_claim_ids": ["c_001"],
        "documentary_preface": {"block_id": "preface_0001", "text": "Napoleon Bonaparte entered the city in 1812.", "claim_ids": []},
    }
    out = script_pipeline._sanitize_narrative_preface_and_hook(draft, research_report)
    assert out["documentary_preface"]["claim_ids"] == ["c_001"]


def test_hook_is_replaced_when_it_contains_entity_or_year() -> None:
    research_report = {
        "claims": [{"claim_id": "c_001", "text": "X", "importance": "high"}],
        "entities": [{"name": "Moscow", "type": "place"}],
    }
    draft = {
        "title_candidates": ["t"],
        "hook": "In Moscow, in 1812, something happened.",
        "chapters": [{"chapter_id": "ch_01", "title": "x", "narration_blocks": [{"block_id": "b_0001", "text": "x", "claim_ids": ["c_001"]}]}],
        "supported_claim_ids": ["c_001"],
    }
    out = script_pipeline._sanitize_narrative_preface_and_hook(draft, research_report)
    assert out["hook"] == "When certainty vanishes, the next decision can change everything."


def main() -> int:
    test_preface_claim_ids_are_filled_when_text_is_factual()
    test_hook_is_replaced_when_it_contains_entity_or_year()
    print("✅ narrative preface/hook sanitizer tests: PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())




