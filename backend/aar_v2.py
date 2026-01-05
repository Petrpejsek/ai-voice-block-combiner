"""
AAR v2 - Archive Asset Resolver s Query Director integrací

Nová pipeline:
1. Načte query_director_output.json (strategic queries)
2. Pro každý query provede search (Archive.org + multi-source)
3. Aplikuje license gate + quality filter
4. Uloží RAW results do aar_raw_results.json (bez selection/dedupe)
5. Zachová topic_relevance_score z AAR v14

Pozn: Stará AAR logika (resolve_shot_plan_assets) zůstává pro backward compatibility.
"""

import json
import os
from datetime import datetime, timezone
from typing import Dict, List, Any, Optional, Tuple, Callable


VERSION = "aar_v2_raw_results"


def _now_iso() -> str:
    """ISO timestamp pro metadata"""
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def run_aar_v2_search(
    query_director_output: Dict[str, Any],
    episode_id: str,
    cache_dir: str,
    output_path: str,
    episode_topic: Optional[str] = None,
    throttle_delay_sec: float = 0.2,
    verbose: bool = False,
    progress_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
) -> Tuple[Dict[str, Any], str]:
    """
    Hlavní entry point pro AAR v2.
    
    Args:
        query_director_output: Output z Query Director (strategic_queries[])
        episode_id: ID epizody
        cache_dir: Cache složka pro search results
        output_path: Cesta kam uložit aar_raw_results.json
        episode_topic: Episode topic pro LLM relevance validation
        throttle_delay_sec: Delay mezi API calls
        verbose: Logování detailů
        progress_callback: Optional callback pro progress updates
    
    Returns:
        (output_dict, output_file_path)
    """
    if verbose:
        print(f"🔍 AAR v2: Starting search for episode {episode_id}")
    
    # Import AAR dependencies
    try:
        from archive_asset_resolver import ArchiveAssetResolver
    except ImportError as e:
        raise RuntimeError(f"AAR v2: Failed to import ArchiveAssetResolver: {e}")
    
    # Extract strategic queries
    strategic_queries = query_director_output.get("strategic_queries", [])
    if not strategic_queries:
        raise ValueError("AAR v2: No strategic queries found in Query Director output")
    
    if verbose:
        print(f"   - Strategic queries: {len(strategic_queries)}")
    
    # Initialize resolver
    resolver = ArchiveAssetResolver(
        cache_dir=cache_dir,
        throttle_delay_sec=throttle_delay_sec,
        verbose=verbose,
        enable_multi_source=True,
        preview_mode=False,
    )
    
    # Search for each query
    results_by_query = []
    total_candidates = 0
    
    for i, sq in enumerate(strategic_queries, start=1):
        query_id = sq.get("query_id", "")
        query_str = sq.get("query", "")
        priority = sq.get("priority", 5)
        visual_type = sq.get("visual_type", "general")
        
        if not query_str:
            if verbose:
                print(f"   - Skipping query {query_id}: empty query string")
            continue
        
        if verbose:
            print(f"   - [{i}/{len(strategic_queries)}] {query_id}: {query_str} (priority={priority})")
        
        # Progress callback
        if progress_callback:
            try:
                progress_callback({
                    "step": "aar_v2_search",
                    "progress": int((i / len(strategic_queries)) * 100),
                    "message": f"Searching: {query_str[:50]}...",
                })
            except Exception:
                pass
        
        # Perform search
        try:
            # Use resolver's multi-source search directly
            raw_candidates = resolver.search_multi_source(query_str, max_results=10)
            
            # Apply topic relevance validation (AAR v14 feature)
            if episode_topic and raw_candidates:
                try:
                    from archive_asset_resolver import validate_candidates_topic_relevance
                    
                    validated, rejected, validation_meta = validate_candidates_topic_relevance(
                        candidates=raw_candidates,
                        episode_topic=episode_topic,
                        scene_context=None,
                        max_candidates=10,
                        verbose=False,
                        use_vision=True,
                    )
                    
                    candidates = validated
                    
                    if verbose and rejected:
                        print(f"      ⚠️ Topic validation rejected {len(rejected)} candidates")
                
                except Exception as e:
                    if verbose:
                        print(f"      ⚠️ Topic validation failed: {e}")
                    candidates = raw_candidates
            else:
                candidates = raw_candidates
            
            # Enrich candidates with query metadata
            for candidate in candidates:
                candidate["query_source_id"] = query_id
                candidate["query_priority"] = priority
                candidate["visual_type"] = visual_type
            
            total_candidates += len(candidates)
            
            results_by_query.append({
                "query_id": query_id,
                "query": query_str,
                "priority": priority,
                "visual_type": visual_type,
                "results_count": len(candidates),
                "results": candidates,
            })
            
            if verbose:
                print(f"      → {len(candidates)} candidates")
        
        except Exception as e:
            if verbose:
                print(f"      ⚠️ Search failed: {e}")
            
            results_by_query.append({
                "query_id": query_id,
                "query": query_str,
                "priority": priority,
                "visual_type": visual_type,
                "results_count": 0,
                "results": [],
                "error": str(e),
            })
    
    # Build output
    output = {
        "version": VERSION,
        "episode_id": episode_id,
        "generated_at": _now_iso(),
        "queries": [
            {
                "query_id": sq.get("query_id"),
                "query": sq.get("query"),
                "priority": sq.get("priority"),
                "visual_type": sq.get("visual_type"),
            }
            for sq in strategic_queries
        ],
        "results_by_query": results_by_query,
        "summary": {
            "total_queries": len(strategic_queries),
            "successful_queries": len([r for r in results_by_query if r.get("results_count", 0) > 0]),
            "total_candidates": total_candidates,
        },
    }
    
    # Write to file
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    
    if verbose:
        print(f"✅ AAR v2: Raw results saved to {output_path}")
        print(f"   - Total candidates: {total_candidates}")
    
    return output, output_path


def load_aar_raw_results(file_path: str) -> Dict[str, Any]:
    """Helper: načte AAR raw results z JSON souboru"""
    with open(file_path, "r", encoding="utf-8") as f:
        return json.load(f)


if __name__ == "__main__":
    # Simple test
    test_qd_output = {
        "version": "query_director_v1",
        "episode_id": "test_ep",
        "strategic_queries": [
            {
                "query_id": "q_001",
                "query": "Napoleon 1812 map",
                "priority": 9,
                "visual_type": "map",
            },
            {
                "query_id": "q_002",
                "query": "Moscow fire 1812 documents",
                "priority": 8,
                "visual_type": "document",
            },
        ],
    }
    
    # Note: This will fail without proper AAR setup, but shows the interface
    try:
        output, path = run_aar_v2_search(
            test_qd_output,
            episode_id="test_ep",
            cache_dir="/tmp/aar_cache",
            output_path="/tmp/aar_raw_results.json",
            episode_topic="Napoleon's 1812 Russian Campaign",
            verbose=True,
        )
        print("\n✅ AAR v2 test completed")
    except Exception as e:
        print(f"\n⚠️ AAR v2 test failed (expected without full setup): {e}")

