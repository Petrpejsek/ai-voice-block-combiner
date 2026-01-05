"""
E2E Test Runner - Kompletní Visual Pipeline Test

Spustí celou pipeline na test fixtures a ověří akceptační kritéria.
"""

import os
import sys
import json
import tempfile
from typing import Dict, Any


def run_e2e_test(
    fixture: Dict[str, Any],
    output_dir: str,
    run_full_pipeline: bool = False,
    verbose: bool = True,
) -> Dict[str, Any]:
    """
    Spustí E2E test na fixture.
    
    Args:
        fixture: Test fixture (NAPOLEON_1812_FIXTURE nebo MOSCOW_FIRE_FIXTURE)
        output_dir: Output složka pro artefakty
        run_full_pipeline: Pokud True, spustí i AAR + CB (pomalé, vyžaduje API)
        verbose: Print detaily
    
    Returns:
        test_results dict
    """
    if verbose:
        print(f"\n{'='*70}")
        print(f"E2E TEST: {fixture['episode_id']}")
        print(f"Topic: {fixture['episode_topic']}")
        print('='*70)
    
    # Setup
    episode_id = fixture["episode_id"]
    tts_ready_package = fixture["tts_ready_package"]
    
    os.makedirs(output_dir, exist_ok=True)
    
    results = {
        "episode_id": episode_id,
        "fixture_topic": fixture["episode_topic"],
        "steps_completed": [],
        "steps_failed": [],
        "acceptance_report": None,
    }
    
    # ========================================================================
    # STEP 1: FDA (simulace - vytvoříme shot_plan manually pro test)
    # ========================================================================
    if verbose:
        print("\n📝 STEP 1: FDA (simulated)")
    
    try:
        # Pro test vytvoříme shot_plan manually (normálně by to dělal FDA)
        from visual_planning_v3 import compile_shotplan_v3, build_default_sceneplan_v3
        
        # Build default sceneplan
        sceneplan_v3, warnings = build_default_sceneplan_v3(tts_ready_package)
        
        # Compile shotplan
        shotplan_wrapper, comp_warnings = compile_shotplan_v3(
            tts_ready_package,
            sceneplan_v3,
            words_per_minute=150,
        )
        
        shot_plan = shotplan_wrapper.get("shot_plan", {})
        
        # Save shot_plan
        shot_plan_path = os.path.join(output_dir, "shot_plan.json")
        with open(shot_plan_path, "w", encoding="utf-8") as f:
            json.dump(shotplan_wrapper, f, indent=2, ensure_ascii=False)
        
        results["steps_completed"].append("fda")
        
        if verbose:
            print(f"   ✓ Shot plan created: {len(shot_plan.get('scenes', []))} scenes")
    
    except Exception as e:
        results["steps_failed"].append({"step": "fda", "error": str(e)})
        if verbose:
            print(f"   ✗ FDA failed: {e}")
        return results
    
    # ========================================================================
    # STEP 2: Query Director
    # ========================================================================
    if verbose:
        print("\n🎯 STEP 2: Query Director")
    
    try:
        from query_director import run_query_director
        
        qd_output_path = os.path.join(output_dir, "query_director_output.json")
        qd_output, _ = run_query_director(
            shot_plan=shotplan_wrapper,
            episode_id=episode_id,
            output_path=qd_output_path,
            verbose=verbose,
        )
        
        results["steps_completed"].append("query_director")
        results["query_director_output"] = qd_output
        
        if verbose:
            print(f"   ✓ Strategic queries: {len(qd_output.get('strategic_queries', []))}")
    
    except Exception as e:
        results["steps_failed"].append({"step": "query_director", "error": str(e)})
        if verbose:
            print(f"   ✗ Query Director failed: {e}")
        return results
    
    # ========================================================================
    # STEP 3: AAR v2 (optional - pomalé, vyžaduje network)
    # ========================================================================
    if run_full_pipeline:
        if verbose:
            print("\n🔍 STEP 3: AAR v2 (searching...)")
        
        try:
            from aar_v2 import run_aar_v2_search
            
            cache_dir = os.path.join(output_dir, "aar_cache")
            aar_output_path = os.path.join(output_dir, "aar_raw_results.json")
            
            aar_output, _ = run_aar_v2_search(
                query_director_output=qd_output,
                episode_id=episode_id,
                cache_dir=cache_dir,
                output_path=aar_output_path,
                episode_topic=fixture["episode_topic"],
                throttle_delay_sec=0.5,
                verbose=verbose,
            )
            
            results["steps_completed"].append("aar_v2")
            results["aar_output"] = aar_output
            
            if verbose:
                print(f"   ✓ Total candidates: {aar_output.get('summary', {}).get('total_candidates', 0)}")
        
        except Exception as e:
            results["steps_failed"].append({"step": "aar_v2", "error": str(e)})
            if verbose:
                print(f"   ✗ AAR v2 failed: {e}")
            return results
    else:
        if verbose:
            print("\n⏭️  STEP 3: AAR v2 (skipped - use --full to enable)")
        
        # Create mock AAR output for testing downstream steps
        mock_aar_output = {
            "version": "aar_v2_raw_results",
            "episode_id": episode_id,
            "results_by_query": [
                {
                    "query_id": sq.get("query_id"),
                    "query": sq.get("query"),
                    "results": _create_mock_assets(sq.get("visual_type", "general"), 5),
                }
                for sq in qd_output.get("strategic_queries", [])[:3]  # Mock first 3 queries
            ],
            "summary": {
                "total_queries": len(qd_output.get("strategic_queries", [])),
                "total_candidates": 15,
            },
        }
        
        aar_output_path = os.path.join(output_dir, "aar_raw_results.json")
        with open(aar_output_path, "w", encoding="utf-8") as f:
            json.dump(mock_aar_output, f, indent=2, ensure_ascii=False)
        
        results["steps_completed"].append("aar_v2_mock")
        aar_output = mock_aar_output
    
    # ========================================================================
    # STEP 4: Visual Curator
    # ========================================================================
    if verbose:
        print("\n🎨 STEP 4: Visual Curator")
    
    try:
        from visual_curator import run_visual_curator
        
        coverage_requirements = qd_output.get("coverage_requirements", {})
        vc_output_path = os.path.join(output_dir, "visual_curator_output.json")
        
        vc_output, _ = run_visual_curator(
            aar_raw_results=aar_output,
            shot_plan=shotplan_wrapper,
            coverage_requirements=coverage_requirements,
            episode_id=episode_id,
            output_path=vc_output_path,
            verbose=verbose,
        )
        
        results["steps_completed"].append("visual_curator")
        results["visual_curator_output"] = vc_output
        
        if verbose:
            print(f"   ✓ Curated assets: {len(vc_output.get('curated_assets', []))}")
    
    except Exception as e:
        results["steps_failed"].append({"step": "visual_curator", "error": str(e)})
        if verbose:
            print(f"   ✗ Visual Curator failed: {e}")
        return results
    
    # ========================================================================
    # STEP 5: Source Pack Builder
    # ========================================================================
    if verbose:
        print("\n📦 STEP 5: Source Pack Builder")
    
    try:
        from source_pack_builder import run_source_pack_builder
        
        sp_output_path = os.path.join(output_dir, "source_pack.json")
        
        sp_output, _ = run_source_pack_builder(
            visual_curator_output=vc_output,
            shot_plan=shotplan_wrapper,
            episode_id=episode_id,
            output_path=sp_output_path,
            min_assets_per_scene=2,
            verbose=verbose,
        )
        
        results["steps_completed"].append("source_pack_builder")
        results["source_pack"] = sp_output
        
        if verbose:
            print(f"   ✓ Scene assignments: {len(sp_output.get('scene_assignments', []))}")
    
    except Exception as e:
        results["steps_failed"].append({"step": "source_pack_builder", "error": str(e)})
        if verbose:
            print(f"   ✗ Source Pack Builder failed: {e}")
        return results
    
    # ========================================================================
    # STEP 6: Acceptance Tests
    # ========================================================================
    if verbose:
        print("\n🧪 STEP 6: Acceptance Tests")
    
    try:
        from test_visual_pipeline_acceptance import generate_acceptance_report, print_acceptance_report
        
        sp_path = os.path.join(output_dir, "source_pack.json")
        
        acceptance_report = generate_acceptance_report(
            qd_output,
            vc_output,
            sp_output,
            sp_path,
        )
        
        results["acceptance_report"] = acceptance_report
        
        if verbose:
            print_acceptance_report(acceptance_report)
    
    except Exception as e:
        results["steps_failed"].append({"step": "acceptance_tests", "error": str(e)})
        if verbose:
            print(f"   ✗ Acceptance tests failed: {e}")
        return results
    
    # ========================================================================
    # DONE
    # ========================================================================
    if verbose:
        print(f"\n{'='*70}")
        print("✅ E2E TEST COMPLETE")
        print(f"   Steps completed: {len(results['steps_completed'])}")
        print(f"   Steps failed: {len(results['steps_failed'])}")
        
        if results["acceptance_report"]:
            summary = results["acceptance_report"]["summary"]
            print(f"   Acceptance: {summary['passed_tests']}/{summary['total_tests']} passed")
        
        print('='*70)
    
    return results


def _create_mock_assets(visual_type: str, count: int = 5) -> list:
    """Helper: Vytvoří mock assety pro testování bez AAR"""
    assets = []
    for i in range(count):
        assets.append({
            "archive_item_id": f"mock_{visual_type}_{i+1:03d}",
            "asset_url": f"https://archive.org/details/mock_{visual_type}_{i+1:03d}",
            "title": f"Mock {visual_type.title()} Asset {i+1}",
            "media_type": "image",
            "source": "archive_org",
            "thumbnail_url": f"https://archive.org/thumb/mock_{visual_type}_{i+1:03d}",
            "topic_relevance_score": 0.7 + (i * 0.05),
            "visual_type": visual_type,
        })
    return assets


def main():
    """CLI entry point"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Visual Pipeline E2E Test Runner")
    parser.add_argument("--fixture", choices=["napoleon", "moscow"], required=True, help="Test fixture to use")
    parser.add_argument("--output-dir", default=None, help="Output directory (default: temp)")
    parser.add_argument("--full", action="store_true", help="Run full pipeline including AAR (slow, requires network)")
    parser.add_argument("--verbose", action="store_true", default=True, help="Verbose output")
    
    args = parser.parse_args()
    
    # Import fixtures
    from test_visual_pipeline_acceptance import NAPOLEON_1812_FIXTURE, MOSCOW_FIRE_FIXTURE
    
    fixture = NAPOLEON_1812_FIXTURE if args.fixture == "napoleon" else MOSCOW_FIRE_FIXTURE
    
    # Setup output dir
    if args.output_dir:
        output_dir = args.output_dir
    else:
        output_dir = tempfile.mkdtemp(prefix=f"visual_pipeline_{fixture['episode_id']}_")
    
    print(f"📂 Output directory: {output_dir}")
    
    # Run test
    try:
        results = run_e2e_test(
            fixture=fixture,
            output_dir=output_dir,
            run_full_pipeline=args.full,
            verbose=args.verbose,
        )
        
        # Exit code
        if results["steps_failed"]:
            print(f"\n❌ TEST FAILED: {len(results['steps_failed'])} step(s) failed")
            sys.exit(1)
        
        if results["acceptance_report"]:
            summary = results["acceptance_report"]["summary"]
            if summary["failed_tests"] > 0:
                print(f"\n⚠️  TEST PASSED with {summary['failed_tests']} acceptance criteria failure(s)")
                sys.exit(2)
        
        print("\n✅ TEST PASSED: All steps completed, all acceptance criteria met")
        sys.exit(0)
    
    except Exception as e:
        print(f"\n❌ TEST CRASHED: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(3)


if __name__ == "__main__":
    main()


