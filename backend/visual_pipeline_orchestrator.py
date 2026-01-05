"""
Visual Pipeline Orchestrator - Integrace Query Director + Visual Curator + Source Pack do pipeline

Nová sekvence kroků:
1. FDA → shot_plan.json (existing)
2. Query Director → query_director_output.json (new)
3. AAR v2 → aar_raw_results.json (new)
4. Visual Curator → visual_curator_output.json (new)
5. Source Pack Builder → source_pack.json (new)
6. CB v2 → video.mp4 (new)

Compatibility:
- Pokud source_pack.json neexistuje, CB fallback na archive_manifest.json (legacy)
"""

import json
import os
from typing import Dict, Any, Optional, Callable


def _mark_step_running(state: dict, step_name: str, message: str = "") -> None:
    """Helper: Označí krok jako běžící"""
    try:
        from datetime import datetime, timezone
        if "steps" not in state:
            state["steps"] = {}
        if step_name not in state["steps"]:
            state["steps"][step_name] = {}
        state["steps"][step_name]["status"] = "RUNNING"
        state["steps"][step_name]["message"] = message or f"Running {step_name}..."
        state["steps"][step_name]["started_at"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    except Exception:
        pass


def _mark_step_done(state: dict, step_name: str) -> None:
    """Helper: Označí krok jako hotový"""
    try:
        from datetime import datetime, timezone
        if "steps" not in state:
            state["steps"] = {}
        if step_name not in state["steps"]:
            state["steps"][step_name] = {}
        state["steps"][step_name]["status"] = "DONE"
        state["steps"][step_name]["completed_at"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    except Exception:
        pass


def _mark_step_error(state: dict, step_name: str, error_msg: str, details: Optional[Dict[str, Any]] = None) -> None:
    """Helper: Označí krok jako chybný"""
    try:
        from datetime import datetime, timezone
        if "steps" not in state:
            state["steps"] = {}
        if step_name not in state["steps"]:
            state["steps"][step_name] = {}
        state["steps"][step_name]["status"] = "ERROR"
        state["steps"][step_name]["error"] = error_msg
        if details:
            state["steps"][step_name]["error_details"] = details
        state["steps"][step_name]["failed_at"] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    except Exception:
        pass


def run_query_director_step(
    state: dict,
    episode_id: str,
    store: Any,
    verbose: bool = False,
) -> None:
    """
    Krok: Query Director
    
    Input: shot_plan (z FDA)
    Output: query_director_output.json
    """
    from query_director import run_query_director
    
    if verbose:
        print(f"\n{'='*70}")
        print("KROK: Query Director")
        print('='*70)
    
    _mark_step_running(state, "query_director", "Generating strategic queries...")
    
    try:
        # Extract shot_plan
        shot_plan = None
        if isinstance(state.get("metadata"), dict) and isinstance(state["metadata"].get("shot_plan"), dict):
            shot_plan = {"shot_plan": state["metadata"]["shot_plan"]}
        elif isinstance(state.get("shot_plan"), dict):
            shot_plan = {"shot_plan": state["shot_plan"]}
        
        if not shot_plan:
            raise ValueError("Shot plan not found. Run FDA first.")
        
        # Output path
        output_path = os.path.join(store.episode_dir(episode_id), "query_director_output.json")
        
        # Run Query Director
        output, path = run_query_director(
            shot_plan=shot_plan,
            episode_id=episode_id,
            output_path=output_path,
            verbose=verbose,
        )
        
        # Store in state
        state["query_director_output_path"] = path
        state["query_director_output"] = output
        
        _mark_step_done(state, "query_director")
        store.write_script_state(episode_id, state)
        
        if verbose:
            print(f"✅ Query Director: Done")
            print(f"   - Strategic queries: {len(output.get('strategic_queries', []))}")
    
    except Exception as e:
        error_msg = f"Query Director failed: {str(e)}"
        _mark_step_error(state, "query_director", error_msg)
        store.write_script_state(episode_id, state)
        raise RuntimeError(error_msg)


def run_aar_v2_step(
    state: dict,
    episode_id: str,
    store: Any,
    cache_dir: str,
    episode_topic: Optional[str] = None,
    verbose: bool = False,
    progress_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
) -> None:
    """
    Krok: AAR v2 (raw search)
    
    Input: query_director_output.json
    Output: aar_raw_results.json
    """
    from aar_v2 import run_aar_v2_search
    
    if verbose:
        print(f"\n{'='*70}")
        print("KROK: AAR v2 (Raw Search)")
        print('='*70)
    
    _mark_step_running(state, "aar_v2", "Searching for assets...")
    
    try:
        # Load Query Director output
        qd_output_path = state.get("query_director_output_path")
        if not qd_output_path or not os.path.exists(qd_output_path):
            raise ValueError("Query Director output not found")
        
        with open(qd_output_path, "r", encoding="utf-8") as f:
            qd_output = json.load(f)
        
        # Output path
        output_path = os.path.join(store.episode_dir(episode_id), "aar_raw_results.json")
        
        # Run AAR v2
        output, path = run_aar_v2_search(
            query_director_output=qd_output,
            episode_id=episode_id,
            cache_dir=cache_dir,
            output_path=output_path,
            episode_topic=episode_topic,
            throttle_delay_sec=0.2,
            verbose=verbose,
            progress_callback=progress_callback,
        )
        
        # Store in state
        state["aar_raw_results_path"] = path
        state["aar_raw_results"] = output
        
        _mark_step_done(state, "aar_v2")
        store.write_script_state(episode_id, state)
        
        if verbose:
            print(f"✅ AAR v2: Done")
            print(f"   - Total candidates: {output.get('summary', {}).get('total_candidates', 0)}")
    
    except Exception as e:
        error_msg = f"AAR v2 failed: {str(e)}"
        _mark_step_error(state, "aar_v2", error_msg)
        store.write_script_state(episode_id, state)
        raise RuntimeError(error_msg)


def run_visual_curator_step(
    state: dict,
    episode_id: str,
    store: Any,
    verbose: bool = False,
) -> None:
    """
    Krok: Visual Curator
    
    Input: aar_raw_results.json + shot_plan
    Output: visual_curator_output.json
    """
    from visual_curator import run_visual_curator
    
    if verbose:
        print(f"\n{'='*70}")
        print("KROK: Visual Curator")
        print('='*70)
    
    _mark_step_running(state, "visual_curator", "Curating assets...")
    
    try:
        # Load AAR raw results
        aar_raw_path = state.get("aar_raw_results_path")
        if not aar_raw_path or not os.path.exists(aar_raw_path):
            raise ValueError("AAR raw results not found")
        
        with open(aar_raw_path, "r", encoding="utf-8") as f:
            aar_raw_results = json.load(f)
        
        # Extract shot_plan
        shot_plan = None
        if isinstance(state.get("metadata"), dict) and isinstance(state["metadata"].get("shot_plan"), dict):
            shot_plan = {"shot_plan": state["metadata"]["shot_plan"]}
        elif isinstance(state.get("shot_plan"), dict):
            shot_plan = {"shot_plan": state["shot_plan"]}
        
        if not shot_plan:
            raise ValueError("Shot plan not found")
        
        # Load Query Director output for coverage requirements
        qd_output_path = state.get("query_director_output_path")
        if not qd_output_path or not os.path.exists(qd_output_path):
            raise ValueError("Query Director output not found")
        
        with open(qd_output_path, "r", encoding="utf-8") as f:
            qd_output = json.load(f)
        
        coverage_requirements = qd_output.get("coverage_requirements", {})
        
        # Output path
        output_path = os.path.join(store.episode_dir(episode_id), "visual_curator_output.json")
        
        # Run Visual Curator
        output, path = run_visual_curator(
            aar_raw_results=aar_raw_results,
            shot_plan=shot_plan,
            coverage_requirements=coverage_requirements,
            episode_id=episode_id,
            output_path=output_path,
            verbose=verbose,
        )
        
        # Store in state
        state["visual_curator_output_path"] = path
        state["visual_curator_output"] = output
        
        _mark_step_done(state, "visual_curator")
        store.write_script_state(episode_id, state)
        
        if verbose:
            print(f"✅ Visual Curator: Done")
            print(f"   - Curated assets: {len(output.get('curated_assets', []))}")
    
    except Exception as e:
        error_msg = f"Visual Curator failed: {str(e)}"
        _mark_step_error(state, "visual_curator", error_msg)
        store.write_script_state(episode_id, state)
        raise RuntimeError(error_msg)


def run_source_pack_builder_step(
    state: dict,
    episode_id: str,
    store: Any,
    verbose: bool = False,
) -> None:
    """
    Krok: Source Pack Builder
    
    Input: visual_curator_output.json + shot_plan
    Output: source_pack.json
    """
    from source_pack_builder import run_source_pack_builder
    
    if verbose:
        print(f"\n{'='*70}")
        print("KROK: Source Pack Builder")
        print('='*70)
    
    _mark_step_running(state, "source_pack_builder", "Building source pack...")
    
    try:
        # Load Visual Curator output
        vc_output_path = state.get("visual_curator_output_path")
        if not vc_output_path or not os.path.exists(vc_output_path):
            raise ValueError("Visual Curator output not found")
        
        with open(vc_output_path, "r", encoding="utf-8") as f:
            vc_output = json.load(f)
        
        # Extract shot_plan
        shot_plan = None
        if isinstance(state.get("metadata"), dict) and isinstance(state["metadata"].get("shot_plan"), dict):
            shot_plan = {"shot_plan": state["metadata"]["shot_plan"]}
        elif isinstance(state.get("shot_plan"), dict):
            shot_plan = {"shot_plan": state["shot_plan"]}
        
        if not shot_plan:
            raise ValueError("Shot plan not found")
        
        # Output path
        output_path = os.path.join(store.episode_dir(episode_id), "source_pack.json")
        
        # Run Source Pack Builder
        output, path = run_source_pack_builder(
            visual_curator_output=vc_output,
            shot_plan=shot_plan,
            episode_id=episode_id,
            output_path=output_path,
            min_assets_per_scene=2,
            verbose=verbose,
        )
        
        # Store in state
        state["source_pack_path"] = path
        state["source_pack"] = output
        
        _mark_step_done(state, "source_pack_builder")
        store.write_script_state(episode_id, state)
        
        if verbose:
            print(f"✅ Source Pack Builder: Done")
            print(f"   - Scene assignments: {len(output.get('scene_assignments', []))}")
    
    except Exception as e:
        error_msg = f"Source Pack Builder failed: {str(e)}"
        _mark_step_error(state, "source_pack_builder", error_msg)
        store.write_script_state(episode_id, state)
        raise RuntimeError(error_msg)


def run_cb_v2_step(
    state: dict,
    episode_id: str,
    store: Any,
    storage_dir: str,
    output_dir: str,
    verbose: bool = False,
    progress_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
) -> None:
    """
    Krok: CB v2 (Compilation Builder s Source Pack)
    
    Input: source_pack.json + shot_plan
    Output: video.mp4
    
    Fallback: Pokud source_pack.json neexistuje, použije archive_manifest.json (legacy)
    """
    from cb_v2 import build_compilation_from_source_pack
    
    if verbose:
        print(f"\n{'='*70}")
        print("KROK: CB v2 (Compilation Builder)")
        print('='*70)
    
    _mark_step_running(state, "cb_v2", "Compiling video...")
    
    try:
        # Check for source_pack.json
        source_pack_path = state.get("source_pack_path")
        
        if source_pack_path and os.path.exists(source_pack_path):
            # NEW PATH: Use source pack
            if verbose:
                print("   - Using source_pack.json (new pipeline)")
            
            # Extract shot_plan path
            shot_plan_path = os.path.join(store.episode_dir(episode_id), "script_state.json")
            
            # Run CB v2
            output_video, metadata = build_compilation_from_source_pack(
                source_pack_path=source_pack_path,
                shot_plan_path=shot_plan_path,
                episode_id=episode_id,
                storage_dir=storage_dir,
                output_dir=output_dir,
                verbose=verbose,
                progress_callback=progress_callback,
            )
        
        else:
            # LEGACY PATH: Fallback to archive_manifest.json
            if verbose:
                print("   - Falling back to archive_manifest.json (legacy pipeline)")
            
            from compilation_builder import build_episode_compilation
            
            manifest_path = state.get("archive_manifest_path")
            if not manifest_path or not os.path.exists(manifest_path):
                raise ValueError("Neither source_pack.json nor archive_manifest.json found")
            
            output_video, metadata = build_episode_compilation(
                manifest_path=manifest_path,
                episode_id=episode_id,
                storage_dir=storage_dir,
                output_dir=output_dir,
                target_duration_sec=None,
                progress_callback=progress_callback,
            )
        
        if output_video is None:
            raise RuntimeError(f"Compilation failed: {metadata.get('error', 'Unknown error')}")
        
        # Store in state
        state["compilation_video_path"] = output_video
        state["compilation_builder_output"] = metadata
        
        _mark_step_done(state, "cb_v2")
        state["script_status"] = "DONE"
        store.write_script_state(episode_id, state)
        
        if verbose:
            print(f"✅ CB v2: Done")
            print(f"   - Video: {output_video}")
    
    except Exception as e:
        error_msg = f"CB v2 failed: {str(e)}"
        _mark_step_error(state, "cb_v2", error_msg)
        store.write_script_state(episode_id, state)
        raise RuntimeError(error_msg)


def run_full_visual_pipeline(
    state: dict,
    episode_id: str,
    store: Any,
    cache_dir: str,
    storage_dir: str,
    output_dir: str,
    episode_topic: Optional[str] = None,
    verbose: bool = False,
    progress_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
) -> None:
    """
    Spustí kompletní vizuální pipeline.
    
    Sekvence:
    1. Query Director
    2. AAR v2
    3. Visual Curator
    4. Source Pack Builder
    5. CB v2
    
    Note: Předpokládá, že FDA už běžel a shot_plan existuje.
    """
    if verbose:
        print(f"\n{'='*70}")
        print(f"VISUAL PIPELINE: Episode {episode_id}")
        print('='*70)
    
    # 1. Query Director
    run_query_director_step(state, episode_id, store, verbose=verbose)
    
    # 2. AAR v2
    run_aar_v2_step(state, episode_id, store, cache_dir, episode_topic=episode_topic, verbose=verbose, progress_callback=progress_callback)
    
    # 3. Visual Curator
    run_visual_curator_step(state, episode_id, store, verbose=verbose)
    
    # 4. Source Pack Builder
    run_source_pack_builder_step(state, episode_id, store, verbose=verbose)
    
    # 5. CB v2
    run_cb_v2_step(state, episode_id, store, storage_dir, output_dir, verbose=verbose, progress_callback=progress_callback)
    
    if verbose:
        print(f"\n{'='*70}")
        print("✅ VISUAL PIPELINE: Complete")
        print('='*70)


