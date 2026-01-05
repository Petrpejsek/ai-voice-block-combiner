#!/usr/bin/env python3
"""
Test suite pro Pre-FDA Sanitizer

Ověřuje:
1. Deterministické nahrazení blacklisted termů
2. FATAL error handling bez fallbacků
3. Zachování konkrétních termínů (Napoleon, Moscow, atd.)
4. Správné mapování abstraktní → vizuální proxy
"""

import pytest
import json
from pre_fda_sanitizer import (
    sanitize_keywords,
    sanitize_search_queries,
    sanitize_narration_summary,
    sanitize_shot_plan,
    _is_blacklisted,
    _sanitize_token,
    BLACKLISTED_ABSTRACT_TERMS,
    VISUAL_PROXY_MAP,
)


def test_is_blacklisted():
    """Test _is_blacklisted funkce s word-boundary detection"""
    # Blacklisted termy (single-word: word-boundary match)
    assert _is_blacklisted("strategic") is True
    assert _is_blacklisted("Strategic") is True  # case-insensitive
    assert _is_blacklisted("STRATEGIC") is True
    assert _is_blacklisted("goal") is True
    assert _is_blacklisted("territory") is True
    assert _is_blacklisted("peace") is True
    
    # Word-boundary: "strategic" matchne, ale "strategically" NE (substring)
    assert _is_blacklisted("strategically") is False  # substring, ne word-boundary
    
    # Multi-word phrases (phrase match)
    assert _is_blacklisted("strategic importance") is True
    assert _is_blacklisted("archival footage") is True
    
    # Konkrétní termy (NOT blacklisted)
    assert _is_blacklisted("Napoleon") is False
    assert _is_blacklisted("Moscow") is False
    assert _is_blacklisted("surrender") is False
    assert _is_blacklisted("treaty") is False  # "treaty" NENÍ blacklisted (konkrétní vizuální objekt)
    assert _is_blacklisted("treaty document") is False  # "treaty" je povolený


def test_sanitize_token_basic():
    """Test sanitizace jednotlivého tokenu"""
    # Blacklisted term → náhrada (konkrétní noun phrase, NE metaterm)
    sanitized, was_replaced = _sanitize_token("strategic")
    assert sanitized == "military map"  # NE "archival_documents"
    assert was_replaced is True
    
    # Konkrétní term → beze změny
    sanitized, was_replaced = _sanitize_token("Napoleon")
    assert sanitized == "Napoleon"
    assert was_replaced is False
    
    # Blacklisted term s None mapping → DELETE
    sanitized, was_replaced = _sanitize_token("history")
    assert sanitized is None  # DELETE
    assert was_replaced is True


def test_sanitize_keywords_basic():
    """Test sanitizace keywords[] s mix blacklisted + concrete"""
    keywords = ["strategic", "Napoleon", "Moscow", "goal", "surrender"]
    sanitized, replacements = sanitize_keywords(keywords, "sc_0001")
    
    # Blacklisted termy nahrazeny (konkrétními noun phrases)
    assert "strategic" not in sanitized
    assert "goal" not in sanitized
    
    # Konkrétní termy zachovány
    assert "Napoleon" in sanitized
    assert "Moscow" in sanitized
    assert "surrender" in sanitized
    
    # Náhrady jsou konkrétní noun phrases (NE metaterms)
    assert "military map" in sanitized or "campaign map" in sanitized
    assert "official letter" in sanitized or "written orders" in sanitized
    assert "archival_documents" not in sanitized  # NESMÍ být metaterm
    
    # Replacements log
    assert len(replacements) == 2


def test_sanitize_keywords_all_blacklisted():
    """Test sanitizace keywords[] kde všechny jsou blacklisted"""
    keywords = ["strategic", "goal", "territory", "peace"]
    sanitized, replacements = sanitize_keywords(keywords, "sc_0001")
    
    # Všechny nahrazeny
    assert len(sanitized) == 4
    assert "strategic" not in sanitized
    assert "goal" not in sanitized
    assert "territory" not in sanitized
    assert "peace" not in sanitized
    
    # Náhrady jsou konkrétní noun phrases (NE metaterms)
    assert any(kw in sanitized for kw in ["military map", "campaign map"])
    assert any(kw in sanitized for kw in ["official letter", "written orders"])
    assert any(kw in sanitized for kw in ["border map", "marked map"])
    assert any(kw in sanitized for kw in ["signed treaty", "diplomatic meeting"])
    
    # NESMÍ obsahovat metaterms
    assert "archival_documents" not in sanitized
    assert "official_correspondence" not in sanitized


def test_sanitize_keywords_empty_input():
    """Test sanitizace prázdných keywords[] → FATAL"""
    with pytest.raises(RuntimeError, match="FDA_SANITIZER_EMPTY"):
        sanitize_keywords([], "sc_0001")


def test_sanitize_keywords_invalid_type():
    """Test sanitizace nevalidního typu keywords → FATAL"""
    with pytest.raises(RuntimeError, match="FDA_SANITIZER_FAILED"):
        sanitize_keywords("not_a_list", "sc_0001")


def test_sanitize_search_queries_basic():
    """Test sanitizace search_queries[] + footage transformace"""
    queries = [
        "strategic importance Napoleon",
        "Moscow 1812 archival",
        "goal of invasion",
        "surrender documents",
        "Moscow siege archival footage"
    ]
    sanitized, replacements = sanitize_search_queries(queries, "sc_0001")
    
    # Blacklisted termy odstraněny nebo nahrazeny
    assert not any("strategic" in q.lower() for q in sanitized)
    assert not any("goal" in q.lower() for q in sanitized)
    
    # "footage" transformováno na "newsreel"
    assert not any("footage" in q.lower() for q in sanitized)
    
    # Konkrétní termy zachovány
    assert any("Moscow" in q or "moscow" in q.lower() for q in sanitized)
    assert any("surrender" in q or "Surrender" in q for q in sanitized)


def test_sanitize_narration_summary():
    """Test sanitizace narration_summary"""
    summary = "Napoleon's strategic goal was to control Moscow territory"
    sanitized, replacements = sanitize_narration_summary(summary, "sc_0001")
    
    # Blacklisted termy odstraněny (pro volný text v summary odstraňujeme, ne nahrazujeme)
    assert "strategic" not in sanitized.lower()
    assert "goal" not in sanitized.lower()
    assert "territory" not in sanitized.lower()
    assert "control" not in sanitized.lower()  # "control" je také blacklisted
    
    # Konkrétní termy zachovány
    assert "Napoleon" in sanitized or "napoleon" in sanitized.lower()
    assert "Moscow" in sanitized or "moscow" in sanitized.lower()


def test_sanitize_shot_plan_integration():
    """Integration test: sanitizace celého shot_plan"""
    shot_plan = {
        "version": "fda_v2.0",
        "scenes": [
            {
                "scene_id": "sc_0001",
                "keywords": ["strategic", "Napoleon", "Moscow"],
                "search_queries": ["strategic importance", "Moscow 1812"],
                "narration_summary": "Napoleon's goal was territory control",
                "shot_strategy": {
                    "shot_types": ["maps_context", "archival_documents"]
                }
            },
            {
                "scene_id": "sc_0002",
                "keywords": ["surrender", "peace", "treaty"],
                "search_queries": ["surrender documents", "peace negotiations archival footage"],
                "narration_summary": "The peace treaty was signed",
                "shot_strategy": {
                    "shot_types": ["archival_documents"]
                }
            }
        ]
    }
    
    sanitized, log_data = sanitize_shot_plan(shot_plan)
    
    # Struktura zachována
    assert sanitized["version"] == "fda_v2.0"
    assert len(sanitized["scenes"]) == 2
    
    # Scene 1: blacklisted termy nahrazeny
    scene1 = sanitized["scenes"][0]
    assert "strategic" not in scene1["keywords"]
    assert "Napoleon" in scene1["keywords"]
    assert "Moscow" in scene1["keywords"]
    # NESMÍ obsahovat metaterms
    assert not any("archival_documents" in kw for kw in scene1["keywords"])
    
    # Scene 2: blacklisted termy nahrazeny
    scene2 = sanitized["scenes"][1]
    assert "peace" not in scene2["keywords"]
    assert "surrender" in scene2["keywords"]
    # "footage" transformováno
    assert not any("footage" in q.lower() for q in scene2["search_queries"])
    
    # Log data
    assert log_data["status"] == "FDA_SANITIZER_PASS"
    assert log_data["scenes_processed"] == 2
    assert log_data["total_replacements"] > 0


def test_sanitize_shot_plan_invalid_structure():
    """Test sanitizace nevalidního shot_plan → FATAL"""
    with pytest.raises(RuntimeError, match="FDA_SANITIZER_FAILED"):
        sanitize_shot_plan("not_a_dict")
    
    with pytest.raises(RuntimeError, match="FDA_SANITIZER_FAILED"):
        sanitize_shot_plan({"scenes": "not_a_list"})


def test_blacklist_coverage():
    """Verify že všechny blacklisted termy mají mapování"""
    for term in BLACKLISTED_ABSTRACT_TERMS:
        assert term in VISUAL_PROXY_MAP, f"Term '{term}' nemá mapování v VISUAL_PROXY_MAP"


def test_visual_proxy_are_concrete():
    """Verify že všechny visual proxy jsou konkrétní (ne další abstraktní)"""
    # Visual proxy nesmí obsahovat blacklisted termy
    for term, proxy in VISUAL_PROXY_MAP.items():
        assert not _is_blacklisted(proxy), f"Visual proxy '{proxy}' pro '{term}' je samo blacklisted!"


def test_no_leftover_blacklisted_after_sanitization():
    """HARD CHECK: po sanitizaci nesmí zůstat žádné blacklisted termy"""
    keywords = ["strategic", "goal", "Napoleon", "territory"]
    sanitized, _ = sanitize_keywords(keywords, "sc_0001")
    
    # Žádný sanitizovaný keyword nesmí být blacklisted
    for keyword in sanitized:
        assert not _is_blacklisted(keyword), f"Keyword '{keyword}' je stále blacklisted po sanitizaci!"


def test_case_insensitive_matching():
    """Test case-insensitive matching blacklisted termů"""
    keywords = ["STRATEGIC", "Strategic", "strategic", "StRaTeGiC"]
    sanitized, replacements = sanitize_keywords(keywords, "sc_0001")
    
    # Všechny varianty nahrazeny (konkrétním noun phrase)
    assert len(sanitized) == 4
    # Všechny by měly být nahrazeny stejným výrazem (military map nebo campaign map)
    assert all(kw in ["military map", "campaign map"] for kw in sanitized)


def test_compound_terms():
    """Test složených termů obsahujících blacklisted substring"""
    keywords = ["strategic importance", "war effort production"]
    sanitized, replacements = sanitize_keywords(keywords, "sc_0001")
    
    # Blacklisted substrings odstraněny nebo nahrazeny
    assert not any("strategic" in kw.lower() for kw in sanitized)
    assert not any("war effort" in kw.lower() for kw in sanitized)
    
    # Output je buď konkrétní noun phrase nebo DELETE
    # (nemůžeme testovat přesný output protože závisí na None mapping)


def test_concrete_terms_preserved():
    """Test že konkrétní historické termíny zůstávají zachovány"""
    concrete_terms = [
        "Napoleon", "Moscow", "Kremlin", "surrender", "delegation",
        "fires", "retreat", "winter", "supplies"
    ]
    
    for term in concrete_terms:
        sanitized, was_replaced = _sanitize_token(term)
        assert sanitized == term, f"Concrete term '{term}' byl nesprávně změněn na '{sanitized}'"
        assert was_replaced is False
    
    # META-TERMS jsou blacklisted, takže MUSÍ být nahrazeny
    metaterms_to_replace = [
        ("archival_documents", "document scan"),
        ("diplomatic_correspondence", "diplomatic meeting"),
    ]
    
    for metaterm, expected_replacement in metaterms_to_replace:
        sanitized, was_replaced = _sanitize_token(metaterm)
        assert sanitized == expected_replacement, f"Metaterm '{metaterm}' měl být nahrazen za '{expected_replacement}', ale je '{sanitized}'"
        assert was_replaced is True


def test_regression_napoleon_strategic_footage():
    """
    REGRESSION TEST pro konkrétní fail case:
    Input keywords: ["Napoleon","strategic","goal","territory","peace"]
    Input queries: ["Moscow siege archival footage"]
    
    Očekávání:
    - output keywords neobsahují žádný blacklist token
    - output queries neobsahují "footage" ani blacklist tokeny
    - output queries MUSÍ obsahovat PŘESNĚ: 1 broad + 2 object/action (min 3 total)
    """
    # Input (z reálného fail case)
    keywords = ["Napoleon", "strategic", "goal", "territory", "peace"]
    queries = ["Moscow siege archival footage"]
    
    # Sanitize keywords
    sanitized_keywords, kw_replacements = sanitize_keywords(keywords, "sc_0001")
    
    # Očekávání keywords:
    # 1. Žádné blacklist tokeny
    for kw in sanitized_keywords:
        assert not _is_blacklisted(kw), f"Keyword '{kw}' je stále blacklisted!"
    
    # 2. Konkrétní termy zachovány
    assert "Napoleon" in sanitized_keywords
    
    # 3. Blacklisted termy nahrazeny konkrétními noun phrases
    assert "strategic" not in sanitized_keywords
    assert "goal" not in sanitized_keywords
    assert "territory" not in sanitized_keywords
    assert "peace" not in sanitized_keywords
    
    # 4. NESMÍ obsahovat metaterms
    assert "archival_documents" not in sanitized_keywords
    assert "official_correspondence" not in sanitized_keywords
    
    # Sanitize queries
    shot_types = ["maps_context", "archival_documents"]  # Pro query mix guard
    sanitized_queries, q_replacements = sanitize_search_queries(queries, "sc_0001", shot_types)
    
    # Očekávání queries:
    # 1. "footage" transformováno na "newsreel"
    assert not any("footage" in q.lower() for q in sanitized_queries), "Query obsahuje 'footage'!"
    
    # 2. Žádné blacklist tokeny
    for q in sanitized_queries:
        assert not _is_blacklisted(q), f"Query '{q}' obsahuje blacklisted term!"
    
    # 3. "Moscow" zachováno (v jedné z queries)
    assert any("Moscow" in q or "moscow" in q.lower() for q in sanitized_queries)
    
    # 4. Obsahuje "newsreel" (transformace z "footage")
    assert any("newsreel" in q.lower() for q in sanitized_queries)
    
    # 5. QUERY MIX GUARD (HARD REQUIREMENT):
    # Min 1 broad + 2 object/action = min 3 queries total
    assert len(sanitized_queries) >= 3, f"Query mix guard failed: pouze {len(sanitized_queries)} queries (očekáváno >= 3)"
    
    # Kategorizuj queries
    BROAD_MARKERS = ["archival", "newsreel", "documentary", "historical film"]
    broad_queries = [q for q in sanitized_queries if any(m in q.lower() for m in BROAD_MARKERS)]
    object_queries = [q for q in sanitized_queries if q not in broad_queries]
    
    # ENFORCE: min 1 broad
    assert len(broad_queries) >= 1, f"Query mix guard failed: pouze {len(broad_queries)} broad queries (očekáváno >= 1)"
    
    # ENFORCE: min 2 object/action
    assert len(object_queries) >= 2, f"Query mix guard failed: pouze {len(object_queries)} object queries (očekáváno >= 2)"


def test_footage_transformation():
    """Test transformace 'archival footage' → 'newsreel'"""
    queries = [
        "Moscow siege archival footage",
        "Napoleon retreat footage",
        "Battle archival footage scenes"
    ]
    
    sanitized_queries, replacements = sanitize_search_queries(queries, "sc_0001")
    
    # Všechny queries musí mít "footage" nahrazeno za "newsreel"
    for q in sanitized_queries:
        assert "footage" not in q.lower(), f"Query '{q}' stále obsahuje 'footage'!"
        
    # Musí obsahovat "newsreel"
    assert any("newsreel" in q.lower() for q in sanitized_queries)


def test_query_mix_guard_enforces_1_broad_2_object():
    """Test že query mix guard VYNUTÍ přesně 1 broad + 2 object/action queries"""
    # Scéna s maps_context shot_type, ale jen 1 query (object)
    queries = ["Napoleon"]
    shot_types = ["maps_context"]
    
    sanitized_queries, replacements = sanitize_search_queries(queries, "sc_0001", shot_types)
    
    # Query mix guard MUSÍ vynutit min 3 queries (1 broad + 2 object)
    assert len(sanitized_queries) >= 3, f"Očekáváno >= 3 queries, ale je {len(sanitized_queries)}"
    
    # Kategorizuj queries
    BROAD_MARKERS = ["archival", "newsreel", "documentary", "historical film"]
    broad_queries = [q for q in sanitized_queries if any(m in q.lower() for m in BROAD_MARKERS)]
    object_queries = [q for q in sanitized_queries if q not in broad_queries]
    
    # ENFORCE: min 1 broad
    assert len(broad_queries) >= 1, f"Očekáváno >= 1 broad query, ale je {len(broad_queries)}"
    
    # ENFORCE: min 2 object/action
    assert len(object_queries) >= 2, f"Očekáváno >= 2 object queries, ale je {len(object_queries)}"
    
    # Měl by být přidán "archival military map" (pro maps_context)
    assert any("archival military map" in q.lower() for q in sanitized_queries)


def test_no_metaterms_in_output():
    """Property test: output NIKDY nesmí obsahovat metaterms"""
    FORBIDDEN_METATERMS = [
        "archival_documents",
        "official_correspondence",
        "diplomatic_correspondence",
        "archival_photographs",
    ]
    
    keywords = ["strategic", "goal", "peace", "Napoleon", "Moscow"]
    sanitized_keywords, _ = sanitize_keywords(keywords, "sc_0001")
    
    # ŽÁDNÝ metaterm nesmí být v outputu
    for kw in sanitized_keywords:
        for metaterm in FORBIDDEN_METATERMS:
            assert metaterm not in kw.lower(), f"Output obsahuje forbidden metaterm '{metaterm}' v '{kw}'!"


def test_regression_concrete_visual_noun_missing_keywords():
    """
    Regression: FDA_BEAT_LOCK_FAIL když keywords nemají žádný concrete visual noun.

    Example failing set (from UI):
    ['occupation','French','army','supply','worsened'] -> concrete_nouns_count: 0

    Expectation:
    - sanitizer deterministicky doplní 1 canonical concrete noun (documents/maps/...)
    - žádný blacklist token nezůstane
    """
    shot_plan = {
        "version": "fda_v2.0",
        "scenes": [
            {
                "scene_id": "sc_0008",
                "keywords": ["occupation", "French", "army", "supply", "worsened"],
                "search_queries": ["French army occupation archival footage"],
                "shot_strategy": {"shot_types": ["archival_documents"]},
            }
        ],
    }

    sanitized, _log = sanitize_shot_plan(shot_plan)
    scene = sanitized["scenes"][0]
    kws = scene["keywords"]

    # No blacklist tokens remain in keywords
    for kw in kws:
        assert not _is_blacklisted(kw), f"Keyword '{kw}' je stále blacklisted!"

    # Concrete noun enforced: must include at least one canonical noun
    canonical = ["documents", "letters", "maps", "streets", "ruins", "troops", "soldiers", "factories", "buildings", "officials"]
    assert any(any(c in kw.lower() for c in canonical) for kw in kws), f"Chybí canonical concrete noun v keywords: {kws}"


if __name__ == "__main__":
    print("🧪 Spouštím Pre-FDA Sanitizer testy...")
    pytest.main([__file__, "-v", "--tb=short"])

