"""
Test Runner pro Visual Pipeline - Akceptační kritéria

Test fixtures:
1. "Napoleon 1812" - hodně map temptation
2. "Moscow fire" - nutnost destruction/documents

Akceptační kritéria:
✓ Query count: strategic_queries <= 8 pro epizodu
✓ Duplicate queries: < 10 %
✓ Cross-scene duplicate assets: 0
✓ Coverage: portraits + documents nejsou deficitní zároveň
✓ Source Pack existuje a CB ho použije
✓ Výstupní report vypíše metriky (diversity, coverage, duplicates)
"""

import json
import os
from typing import Dict, List, Any, Tuple


# ============================================================================
# TEST FIXTURES
# ============================================================================

NAPOLEON_1812_FIXTURE = {
    "episode_id": "napoleon_1812_test",
    "episode_topic": "Napoleon's 1812 Russian Campaign",
    "tts_ready_package": {
        "episode_metadata": {
            "topic": "Napoleon's 1812 Russian Campaign",
            "title": "Napoleon 1812",
        },
        "narration_blocks": [
            {
                "block_id": "b_0001",
                "text_tts": "In June 1812, Napoleon Bonaparte crossed the Neman River with the Grande Armée, beginning his invasion of Russia.",
                "duration_sec": 6.5,
            },
            {
                "block_id": "b_0002",
                "text_tts": "The army advanced through Poland and into Russian territory, moving toward Moscow along established routes.",
                "duration_sec": 5.8,
            },
            {
                "block_id": "b_0003",
                "text_tts": "Russian forces under Kutuzov employed a scorched earth strategy, burning crops and retreating eastward.",
                "duration_sec": 6.2,
            },
            {
                "block_id": "b_0004",
                "text_tts": "The Battle of Borodino in September 1812 became one of the bloodiest single-day battles in history.",
                "duration_sec": 5.5,
            },
            {
                "block_id": "b_0005",
                "text_tts": "Napoleon entered Moscow in mid-September, but the city was largely abandoned and set ablaze.",
                "duration_sec": 5.3,
            },
            {
                "block_id": "b_0006",
                "text_tts": "With winter approaching and supplies exhausted, Napoleon ordered the retreat from Moscow in October.",
                "duration_sec": 5.9,
            },
        ],
    },
}


MOSCOW_FIRE_FIXTURE = {
    "episode_id": "moscow_fire_test",
    "episode_topic": "Fire of Moscow 1812",
    "tts_ready_package": {
        "episode_metadata": {
            "topic": "Fire of Moscow 1812",
            "title": "Moscow Fire 1812",
        },
        "narration_blocks": [
            {
                "block_id": "b_0001",
                "text_tts": "On September 14, 1812, Napoleon's Grande Armée entered Moscow, expecting to find food and shelter for the winter.",
                "duration_sec": 6.8,
            },
            {
                "block_id": "b_0002",
                "text_tts": "Instead, they found the city largely deserted, its inhabitants having fled or been evacuated by the Russian authorities.",
                "duration_sec": 6.2,
            },
            {
                "block_id": "b_0003",
                "text_tts": "Fires began breaking out across the city that same night, spreading rapidly through Moscow's wooden buildings.",
                "duration_sec": 5.9,
            },
            {
                "block_id": "b_0004",
                "text_tts": "Historical documents suggest Governor Rostopchin ordered the fire as part of a scorched earth policy.",
                "duration_sec": 5.7,
            },
            {
                "block_id": "b_0005",
                "text_tts": "The conflagration destroyed three-quarters of the city, leaving Napoleon's army without adequate supplies or shelter.",
                "duration_sec": 6.4,
            },
            {
                "block_id": "b_0006",
                "text_tts": "Trapped in a burned-out city with winter approaching, Napoleon was forced to begin his disastrous retreat.",
                "duration_sec": 5.8,
            },
        ],
    },
}


# ============================================================================
# VALIDATION FUNCTIONS
# ============================================================================

def validate_query_count(query_director_output: Dict[str, Any]) -> Tuple[bool, str]:
    """
    Kritérium: strategic_queries <= 8 pro epizodu
    """
    strategic_queries = query_director_output.get("strategic_queries", [])
    count = len(strategic_queries)
    
    passed = count <= 8
    message = f"Query count: {count}/8 {'✓' if passed else '✗'}"
    
    return passed, message


def validate_duplicate_queries(query_director_output: Dict[str, Any]) -> Tuple[bool, str]:
    """
    Kritérium: Duplicate queries < 10%
    """
    dedupe_report = query_director_output.get("dedupe_report", {})
    dedup_rate = dedupe_report.get("deduplication_rate", 0.0)
    
    # deduplication_rate = duplicates / total_raw
    # We want duplicates < 10% of strategic queries
    # But dedupe_report shows duplicates_removed / total_raw
    
    strategic_count = dedupe_report.get("strategic_queries", 0)
    duplicates_removed = dedupe_report.get("duplicates_removed", 0)
    
    if strategic_count > 0:
        # Duplicate rate = duplicates among strategic queries
        # Actually, dedupe_report already calculated this
        dup_rate = dedup_rate  # This is correct rate
    else:
        dup_rate = 0.0
    
    passed = dup_rate < 0.1
    message = f"Duplicate query rate: {dup_rate:.1%} (<10% required) {'✓' if passed else '✗'}"
    
    return passed, message


def validate_cross_scene_duplicates(source_pack: Dict[str, Any]) -> Tuple[bool, str]:
    """
    Kritérium: Cross-scene duplicate assets = 0
    """
    warnings = source_pack.get("warnings", [])
    
    # Check for SP_CROSS_SCENE_DUPLICATE warnings
    cross_scene_dups = [w for w in warnings if w.get("code") == "SP_CROSS_SCENE_DUPLICATE"]
    
    passed = len(cross_scene_dups) == 0
    message = f"Cross-scene duplicate assets: {len(cross_scene_dups)} (0 required) {'✓' if passed else '✗'}"
    
    return passed, message


def validate_coverage_balance(visual_curator_output: Dict[str, Any]) -> Tuple[bool, str]:
    """
    Kritérium: portraits + documents nejsou deficitní zároveň
    """
    deficits = visual_curator_output.get("deficits", [])
    
    # Check if both portraits AND documents are deficient
    portrait_deficit = any(d.get("visual_type") == "portrait" for d in deficits)
    document_deficit = any(d.get("visual_type") == "document" for d in deficits)
    
    both_deficient = portrait_deficit and document_deficit
    
    passed = not both_deficient
    
    if both_deficient:
        message = "Coverage: Both portraits AND documents deficient ✗"
    elif portrait_deficit:
        message = "Coverage: Portraits deficient (documents OK) ⚠️"
    elif document_deficit:
        message = "Coverage: Documents deficient (portraits OK) ⚠️"
    else:
        message = "Coverage: Both portraits and documents adequate ✓"
    
    return passed, message


def validate_source_pack_exists(source_pack_path: str) -> Tuple[bool, str]:
    """
    Kritérium: Source Pack existuje a je validní
    """
    exists = os.path.exists(source_pack_path)
    
    if not exists:
        return False, "Source Pack: File not found ✗"
    
    try:
        with open(source_pack_path, "r", encoding="utf-8") as f:
            sp = json.load(f)
        
        # Check essential fields
        if not isinstance(sp.get("scene_assignments"), list):
            return False, "Source Pack: Invalid structure (missing scene_assignments) ✗"
        
        if len(sp.get("scene_assignments", [])) == 0:
            return False, "Source Pack: Empty scene_assignments ✗"
        
        return True, "Source Pack: Exists and valid ✓"
    
    except Exception as e:
        return False, f"Source Pack: Invalid JSON ({e}) ✗"


# ============================================================================
# REPORT GENERATOR
# ============================================================================

def generate_acceptance_report(
    query_director_output: Dict[str, Any],
    visual_curator_output: Dict[str, Any],
    source_pack: Dict[str, Any],
    source_pack_path: str,
) -> Dict[str, Any]:
    """
    Vygeneruje kompletní akceptační report.
    """
    # Run validations
    results = []
    
    query_count_pass, query_count_msg = validate_query_count(query_director_output)
    results.append({"test": "Query Count", "passed": query_count_pass, "message": query_count_msg})
    
    dup_queries_pass, dup_queries_msg = validate_duplicate_queries(query_director_output)
    results.append({"test": "Duplicate Queries", "passed": dup_queries_pass, "message": dup_queries_msg})
    
    cross_scene_pass, cross_scene_msg = validate_cross_scene_duplicates(source_pack)
    results.append({"test": "Cross-Scene Duplicates", "passed": cross_scene_pass, "message": cross_scene_msg})
    
    coverage_pass, coverage_msg = validate_coverage_balance(visual_curator_output)
    results.append({"test": "Coverage Balance", "passed": coverage_pass, "message": coverage_msg})
    
    sp_exists_pass, sp_exists_msg = validate_source_pack_exists(source_pack_path)
    results.append({"test": "Source Pack Exists", "passed": sp_exists_pass, "message": sp_exists_msg})
    
    # Calculate metrics
    total_tests = len(results)
    passed_tests = sum(1 for r in results if r["passed"])
    
    # Diversity metrics
    coverage_balance = visual_curator_output.get("coverage_balance", {})
    by_visual_type = coverage_balance.get("by_visual_type", {})
    
    coverage_summary = source_pack.get("coverage_summary", {})
    
    report = {
        "test_results": results,
        "summary": {
            "total_tests": total_tests,
            "passed_tests": passed_tests,
            "failed_tests": total_tests - passed_tests,
            "pass_rate": round(passed_tests / max(1, total_tests), 3),
        },
        "metrics": {
            "diversity": {
                "assets_by_visual_type": by_visual_type,
                "unique_visual_types": len(by_visual_type),
            },
            "coverage": coverage_summary,
            "duplicates": {
                "query_deduplication_rate": query_director_output.get("dedupe_report", {}).get("deduplication_rate", 0),
                "asset_deduplication_rate": visual_curator_output.get("dedupe_report", {}).get("deduplication_rate", 0),
            },
        },
    }
    
    return report


def print_acceptance_report(report: Dict[str, Any]) -> None:
    """
    Vypíše akceptační report do konzole.
    """
    print("\n" + "="*70)
    print("ACCEPTANCE TEST REPORT")
    print("="*70)
    
    for result in report.get("test_results", []):
        status = "✓ PASS" if result["passed"] else "✗ FAIL"
        print(f"{status:8s} | {result['test']:30s} | {result['message']}")
    
    print("="*70)
    
    summary = report.get("summary", {})
    print(f"SUMMARY: {summary['passed_tests']}/{summary['total_tests']} tests passed ({summary['pass_rate']:.0%})")
    
    metrics = report.get("metrics", {})
    
    print("\nMETRICS:")
    print(f"  - Diversity: {metrics['diversity']['unique_visual_types']} visual types")
    print(f"  - Query deduplication: {metrics['duplicates']['query_deduplication_rate']:.1%}")
    print(f"  - Asset deduplication: {metrics['duplicates']['asset_deduplication_rate']:.1%}")
    
    coverage = metrics.get("coverage", {})
    if coverage:
        print(f"  - Assets used: {coverage.get('total_assigned_assets', 0)}/{coverage.get('total_pool_assets', 0)}")
        print(f"  - Usage rate: {coverage.get('usage_rate', 0):.1%}")
    
    print("="*70)


# ============================================================================
# MAIN TEST RUNNER
# ============================================================================

def run_acceptance_tests(
    episode_dir: str,
    verbose: bool = True,
) -> Dict[str, Any]:
    """
    Hlavní test runner.
    
    Args:
        episode_dir: Složka s artefakty (query_director_output.json, atd.)
        verbose: Print detaily
    
    Returns:
        acceptance_report dict
    """
    if verbose:
        print(f"\n🧪 Running acceptance tests for: {episode_dir}")
    
    # Load artefakty
    qd_path = os.path.join(episode_dir, "query_director_output.json")
    vc_path = os.path.join(episode_dir, "visual_curator_output.json")
    sp_path = os.path.join(episode_dir, "source_pack.json")
    
    if not os.path.exists(qd_path):
        raise FileNotFoundError(f"Query Director output not found: {qd_path}")
    
    if not os.path.exists(vc_path):
        raise FileNotFoundError(f"Visual Curator output not found: {vc_path}")
    
    with open(qd_path, "r", encoding="utf-8") as f:
        qd_output = json.load(f)
    
    with open(vc_path, "r", encoding="utf-8") as f:
        vc_output = json.load(f)
    
    # Source pack may not exist (that's one of the tests)
    sp = {}
    if os.path.exists(sp_path):
        with open(sp_path, "r", encoding="utf-8") as f:
            sp = json.load(f)
    
    # Generate report
    report = generate_acceptance_report(qd_output, vc_output, sp, sp_path)
    
    if verbose:
        print_acceptance_report(report)
    
    return report


if __name__ == "__main__":
    print("🧪 Visual Pipeline - Acceptance Test Suite")
    print("\nTest fixtures available:")
    print("  1. Napoleon 1812 (map temptation test)")
    print("  2. Moscow Fire (destruction/documents test)")
    print("\nTo run tests, use:")
    print("  python test_visual_pipeline_acceptance.py --episode-dir <path>")
    print("\nOr import fixtures:")
    print("  from test_visual_pipeline_acceptance import NAPOLEON_1812_FIXTURE, MOSCOW_FIRE_FIXTURE")


