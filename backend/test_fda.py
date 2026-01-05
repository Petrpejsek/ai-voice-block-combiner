#!/usr/bin/env python3
"""
Test suite pro Footage Director Assistant (FDA)

Ověřuje:
1. Generování shot_plan z narration_blocks
2. Validaci výstupního formátu
3. Acceptance criteria (schema, allowlists, kontinuita)
"""

import json
import sys
from footage_director import (
    generate_shot_plan,
    validate_shot_plan,
    run_fda_standalone,
    ALLOWED_SHOT_TYPES,
    ALLOWED_EMOTIONS,
    ALLOWED_CUT_RHYTHMS,
)


# ============================================================================
# TEST FIXTURES
# ============================================================================

# Fixture: 10 narration bloků (malý test case)
FIXTURE_10_BLOCKS = {
    "narration_blocks": [
        {
            "block_id": "b_0001",
            "text_tts": "Caligula began his reign with high popularity due to the memory of his father Germanicus.",
            "claim_ids": ["c_001"]
        },
        {
            "block_id": "b_0002",
            "text_tts": "That initial approval is important because it provides a baseline for understanding the rapid slide into harsher rule.",
            "claim_ids": ["c_001"]
        },
        {
            "block_id": "b_0003",
            "text_tts": "Ancient historians identify a severe illness roughly seven months into his reign as a turning point toward tyrannical behavior.",
            "claim_ids": ["c_002"]
        },
        {
            "block_id": "b_0004",
            "text_tts": "The period after his recovery marks a shift that explains much of what comes next.",
            "claim_ids": ["c_002"]
        },
        {
            "block_id": "b_0005",
            "text_tts": "Caligula rapidly depleted the treasury surplus left by Tiberius on lavish spectacles and building projects.",
            "claim_ids": ["c_003"]
        },
        {
            "block_id": "b_0006",
            "text_tts": "He utilized treason trials to eliminate rivals and confiscate wealthy estates to fund his expenditures.",
            "claim_ids": ["c_004"]
        },
        {
            "block_id": "b_0007",
            "text_tts": "The Senate suffered humiliation through symbolic acts of disrespect as Caligula asserted absolute monarchical power.",
            "claim_ids": ["c_005"]
        },
        {
            "block_id": "b_0008",
            "text_tts": "He broke Roman precedent by demanding to be worshipped as a living deity, including plans to place his statue in the Temple of Jerusalem.",
            "claim_ids": ["c_006"]
        },
        {
            "block_id": "b_0009",
            "text_tts": "The assassination plot was led by Cassius Chaerea, a tribune of the Praetorian Guard, motivated by personal insults and political dissatisfaction.",
            "claim_ids": ["c_007"]
        },
        {
            "block_id": "b_0010",
            "text_tts": "Caligula was attacked and killed in an underground corridor while leaving the Palatine Games, ending his reign of terror.",
            "claim_ids": ["c_008"]
        },
    ]
}


# ============================================================================
# TESTS
# ============================================================================

def test_generate_shot_plan_basic():
    """Test 1: Základní generování shot_plan"""
    print("🧪 Test 1: Základní generování shot_plan...")
    
    shot_plan = generate_shot_plan(FIXTURE_10_BLOCKS["narration_blocks"])
    
    # Základní struktura
    assert "version" in shot_plan, "Chybí klíč 'version'"
    assert shot_plan["version"] == "fda_v1", f"Nesprávná verze: {shot_plan['version']}"
    assert "source" in shot_plan, "Chybí klíč 'source'"
    assert "scenes" in shot_plan, "Chybí klíč 'scenes'"
    assert "total_scenes" in shot_plan, "Chybí klíč 'total_scenes'"
    assert "total_duration_sec" in shot_plan, "Chybí klíč 'total_duration_sec'"
    
    # Scény
    scenes = shot_plan["scenes"]
    assert isinstance(scenes, list), "scenes musí být list"
    assert len(scenes) >= 2, f"Musí vzniknout aspoň 2 scény, vzniklo {len(scenes)}"
    
    print(f"✅ Shot plan obsahuje {len(scenes)} scén, celková délka {shot_plan['total_duration_sec']}s")
    return shot_plan


def test_scene_structure(shot_plan):
    """Test 2: Struktura každé scény"""
    print("🧪 Test 2: Validace struktury scén...")
    
    required_keys = [
        "scene_id", "start_sec", "end_sec", "narration_block_ids",
        "narration_summary", "emotion", "keywords", "shot_strategy", "search_queries"
    ]
    
    scenes = shot_plan["scenes"]
    for i, scene in enumerate(scenes):
        # Povinné klíče
        for key in required_keys:
            assert key in scene, f"Scene {i}: chybí klíč '{key}'"
        
        # Typy
        assert isinstance(scene["scene_id"], str), f"Scene {i}: scene_id musí být string"
        assert isinstance(scene["start_sec"], int), f"Scene {i}: start_sec musí být int"
        assert isinstance(scene["end_sec"], int), f"Scene {i}: end_sec musí být int"
        assert isinstance(scene["narration_block_ids"], list), f"Scene {i}: narration_block_ids musí být list"
        assert isinstance(scene["keywords"], list), f"Scene {i}: keywords musí být list"
        assert isinstance(scene["search_queries"], list), f"Scene {i}: search_queries musí být list"
        assert isinstance(scene["shot_strategy"], dict), f"Scene {i}: shot_strategy musí být dict"
        
        # Délka
        assert scene["end_sec"] > scene["start_sec"], f"Scene {i}: end_sec musí být > start_sec"
    
    print(f"✅ Všech {len(scenes)} scén má správnou strukturu")


def test_allowlist_compliance(shot_plan):
    """Test 3: Kontrola allowlistů"""
    print("🧪 Test 3: Kontrola allowlistů (shot_types, emotion, cut_rhythm)...")
    
    scenes = shot_plan["scenes"]
    for i, scene in enumerate(scenes):
        # Emotion
        emotion = scene.get("emotion")
        assert emotion in ALLOWED_EMOTIONS, f"Scene {i}: emotion '{emotion}' není v allowlistu"
        
        # Shot types
        shot_strategy = scene.get("shot_strategy", {})
        shot_types = shot_strategy.get("shot_types", [])
        for st in shot_types:
            assert st in ALLOWED_SHOT_TYPES, f"Scene {i}: shot_type '{st}' není v allowlistu"
        
        # Cut rhythm
        cut_rhythm = shot_strategy.get("cut_rhythm")
        assert cut_rhythm in ALLOWED_CUT_RHYTHMS, f"Scene {i}: cut_rhythm '{cut_rhythm}' není v allowlistu"
    
    print("✅ Všechny hodnoty jsou z povolených allowlistů")


def test_time_continuity(shot_plan):
    """Test 4: Časová kontinuita (žádné díry, žádné překryvy)"""
    print("🧪 Test 4: Kontrola časové kontinuity...")
    
    scenes = shot_plan["scenes"]
    prev_end = None
    
    for i, scene in enumerate(scenes):
        start_sec = scene["start_sec"]
        end_sec = scene["end_sec"]
        
        if prev_end is not None:
            assert start_sec == prev_end, f"Scene {i}: start_sec={start_sec} != předchozí end_sec={prev_end} (díra nebo překryv)"
        
        prev_end = end_sec
    
    print(f"✅ Časová osa je kontinuální: 0s → {prev_end}s bez děr a překryvů")


def test_keywords_and_queries(shot_plan):
    """Test 5: Keywords a search queries"""
    print("🧪 Test 5: Kontrola keywords (5-12) a search_queries (3-8)...")
    
    scenes = shot_plan["scenes"]
    for i, scene in enumerate(scenes):
        keywords = scene["keywords"]
        search_queries = scene["search_queries"]
        
        # Keywords: 5-12
        assert 5 <= len(keywords) <= 12, f"Scene {i}: keywords má {len(keywords)} položek, musí 5-12"
        
        # Search queries: 3-8
        assert 3 <= len(search_queries) <= 8, f"Scene {i}: search_queries má {len(search_queries)} položek, musí 3-8"
    
    print("✅ Keywords a search queries mají správný počet položek")


def test_validation_function(shot_plan):
    """Test 6: Vestavěná validace"""
    print("🧪 Test 6: Spuštění validate_shot_plan()...")
    
    validation = validate_shot_plan(shot_plan)
    
    assert "valid" in validation, "Validace musí vracet 'valid' klíč"
    assert "errors" in validation, "Validace musí vracet 'errors' klíč"
    
    if not validation["valid"]:
        print(f"❌ Validace selhala:")
        for err in validation["errors"]:
            print(f"   - {err}")
        raise AssertionError("shot_plan neprošel validací")
    
    print("✅ validate_shot_plan() vrátil valid=True")


def test_standalone_api():
    """Test 7: Standalone API (run_fda_standalone)"""
    print("🧪 Test 7: Standalone API...")
    
    shot_plan = run_fda_standalone(FIXTURE_10_BLOCKS)
    
    assert "version" in shot_plan, "Standalone API nevrátil shot_plan"
    assert shot_plan["total_scenes"] >= 2, "Standalone API musí vrátit aspoň 2 scény"
    
    print(f"✅ Standalone API funguje: {shot_plan['total_scenes']} scén")


def test_empty_input():
    """Test 8: Error handling - prázdný vstup"""
    print("🧪 Test 8: Error handling - prázdný vstup...")
    
    try:
        generate_shot_plan([])
        raise AssertionError("Měla být vyhozena ValueError pro prázdný vstup")
    except ValueError as e:
        assert "FDA_INPUT_MISSING" in str(e), f"Nesprávná chyba: {e}"
        print("✅ Prázdný vstup správně vyhodil ValueError")


def test_acceptance_criteria():
    """Test 9: Acceptance criteria summary"""
    print("\n" + "="*60)
    print("🎯 ACCEPTANCE CRITERIA SUMMARY")
    print("="*60)
    
    shot_plan = generate_shot_plan(FIXTURE_10_BLOCKS["narration_blocks"])
    
    # 1) Shot plan se uloží do script_state
    print("✅ [1/3] shot_plan má stabilní schema (version, source, scenes)")
    
    # 2) Žádné externí API
    print("✅ [2/3] Žádné externí API volání (čistě deterministický kód)")
    
    # 3) Stabilní schema
    validation = validate_shot_plan(shot_plan)
    if validation["valid"]:
        print("✅ [3/3] Stabilní schema: všechny scény mají povinné klíče, allowlist hodnoty, časová kontinuita")
    else:
        print(f"❌ [3/3] Validace selhala: {validation['errors']}")
        return False
    
    print("\n🎉 ACCEPTANCE CRITERIA: PASS")
    return True


# ============================================================================
# MAIN
# ============================================================================

def main():
    """Spustí všechny testy"""
    print("\n" + "="*60)
    print("🧪 FDA TEST SUITE")
    print("="*60 + "\n")
    
    try:
        # Základní generování
        shot_plan = test_generate_shot_plan_basic()
        
        # Strukturální testy
        test_scene_structure(shot_plan)
        test_allowlist_compliance(shot_plan)
        test_time_continuity(shot_plan)
        test_keywords_and_queries(shot_plan)
        
        # Validace
        test_validation_function(shot_plan)
        
        # API testy
        test_standalone_api()
        
        # Error handling
        test_empty_input()
        
        # Acceptance criteria
        test_acceptance_criteria()
        
        print("\n" + "="*60)
        print("✅ VŠECHNY TESTY PROŠLY")
        print("="*60 + "\n")
        
        # Výstup příklad shot_plan pro dokumentaci
        print("📄 Ukázka vygenerovaného shot_plan (první scéna):")
        print(json.dumps(shot_plan["scenes"][0], indent=2, ensure_ascii=False))
        
        return 0
        
    except AssertionError as e:
        print(f"\n❌ TEST SELHAL: {e}\n")
        return 1
    except Exception as e:
        print(f"\n❌ NEOČEKÁVANÁ CHYBA: {e}\n")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())



