#!/usr/bin/env python3
"""
Retroaktivní spuštění LLM-assisted FDA na starých projektech

Usage:
    python3 run_fda_on_project.py <episode_id>

Example:
    python3 run_fda_on_project.py ep_9509895b9283
"""

import sys
import os
import json
from project_store import ProjectStore
from footage_director import run_sceneplan_llm
from visual_planning_v3 import coerce_sceneplan_v3, compile_shotplan_v3, validate_shotplan_v3_minimal


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 run_fda_on_project.py <episode_id>")
        print("\nExample: python3 run_fda_on_project.py ep_9509895b9283")
        sys.exit(1)
    
    episode_id = sys.argv[1]
    
    print(f"🎬 Spouštím LLM-assisted FDA na projektu: {episode_id}\n")
    
    # Load project
    store = ProjectStore('../projects')
    
    try:
        state = store.read_script_state(episode_id)
    except FileNotFoundError:
        print(f"❌ Projekt {episode_id} nenalezen!")
        sys.exit(1)
    
    # Check prerequisites
    print("📋 Kontrola předpokladů...")
    
    if not state.get('tts_ready_package'):
        print("❌ Projekt nemá tts_ready_package - FDA nelze spustit")
        print("   (projekt musí mít dokončený TTS Formatting krok)")
        sys.exit(1)
    
    print("✅ tts_ready_package nalezen")
    
    if state.get('shot_plan'):
        print("⚠️  Projekt již má shot_plan - přepíši ho novým")
    
    # Add footage_director step if missing
    if 'footage_director' not in state.get('steps', {}):
        print("🔧 Přidávám footage_director step do state...")
        state['steps']['footage_director'] = {
            "name": "footage_director",
            "status": "IDLE",
            "started_at": None,
            "finished_at": None,
            "error": None,
        }
    
    # Add config if missing
    if 'footage_director_config' not in state:
        print("🔧 Přidávám footage_director_config...")
        state['footage_director_config'] = {
            "provider": "openrouter",
            "model": "openai/gpt-4o-mini",
            "temperature": 0.2,
            "prompt_template": None,
            "step": "footage_director"
        }
    
    # API keys
    provider_api_keys = {
        'openai': os.getenv('OPENAI_API_KEY', ''),
        'openrouter': os.getenv('OPENROUTER_API_KEY', ''),
    }
    
    if not provider_api_keys['openai'] and not provider_api_keys['openrouter']:
        print("❌ Chybí API key (OPENAI_API_KEY nebo OPENROUTER_API_KEY)")
        print("   Nastav: export OPENAI_API_KEY=sk-...")
        sys.exit(1)
    
    print(f"✅ API key nalezen ({list(k for k,v in provider_api_keys.items() if v)})")
    
    # Run FDA
    print("\n🎬 Spouštím LLM-assisted FDA...")
    
    try:
        from datetime import datetime, timezone
        
        # Mark as running
        state['steps']['footage_director']['status'] = 'RUNNING'
        state['steps']['footage_director']['started_at'] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        store.write_script_state(episode_id, state)
        
        # v3: LLM ScenePlan (best-effort) -> deterministic ShotPlan v3
        config = state.get('footage_director_config', {
            "provider": "openai",
            "model": "gpt-4o-mini",
            "temperature": 0.2,
        })
        
        print(f"   Model: {config.get('model')}, Temp: {config.get('temperature')}")
        
        raw_sceneplan = None
        raw_text = ""
        metadata = {}
        warnings = []
        try:
            raw_sceneplan, raw_text, metadata = run_sceneplan_llm(state, provider_api_keys, config)
        except Exception as e:
            warnings.append({"code": "FDA_LLM_FAILED", "message": str(e)})

        tts_pkg = state.get("tts_ready_package") or {}
        sceneplan_v3, w1 = coerce_sceneplan_v3(raw_sceneplan, tts_pkg)
        fixed_wrapper, w2 = compile_shotplan_v3(tts_pkg, sceneplan_v3, words_per_minute=150)
        validate_shotplan_v3_minimal(fixed_wrapper, tts_pkg, episode_id=episode_id)
        shot_plan = fixed_wrapper.get("shot_plan", {}) if isinstance(fixed_wrapper, dict) else {}
        
        # Save raw output
        state['footage_director_raw_output'] = {
            "provider": metadata.get("provider"),
            "model": metadata.get("model"),
            "temperature": metadata.get("temperature"),
            "timestamp": metadata.get("timestamp"),
            "prompt_used": metadata.get("prompt_used", ""),
            "response_text": raw_text,
            "response_json": raw_sceneplan if isinstance(raw_sceneplan, dict) else None,
            "scene_plan_saved": sceneplan_v3,
            "shot_plan_saved": fixed_wrapper,
            "warnings": (warnings + w1 + w2)[:200],
            "llm_meta": metadata.get("llm_meta", {}),
        }
        
        # Save shot_plan (canonical wrapper) to metadata + top-level for backward compatibility
        if not isinstance(state.get("metadata"), dict):
            state["metadata"] = {}
        state["metadata"]["scene_plan"] = sceneplan_v3
        state["metadata"]["shot_plan"] = fixed_wrapper
        state['shot_plan'] = fixed_wrapper
        state['steps']['footage_director']['status'] = 'DONE'
        state['steps']['footage_director']['finished_at'] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        state['steps']['footage_director']['error'] = None
        state['script_status'] = 'DONE'  # Nastavit DONE pro UI
        
        store.write_script_state(episode_id, state)
        
        print("\n✅ FDA dokončen úspěšně!")
        print(f"\n📊 Výsledek:")
        print(f"   Scén: {shot_plan.get('total_scenes', len(shot_plan.get('scenes', [])))}")
        print(f"   Celková délka: {shot_plan.get('total_duration_sec', 0)}s")
        print(f"   Verze: {shot_plan.get('version')}")
        if warnings:
            print(f"   WARNINGS: {len(warnings)} (LLM best-effort)")
        
        # Show first scene
        if shot_plan['scenes']:
            sc = shot_plan['scenes'][0]
            print(f"\n🎬 První scéna:")
            print(f"   ID: {sc['scene_id']}")
            print(f"   Čas: {sc['start_sec']}-{sc['end_sec']}s")
            print(f"   Emoce: {sc['emotion']}")
            print(f"   Shot types: {', '.join(sc['shot_strategy']['shot_types'])}")
        
        print(f"\n💾 Shot plan uložen do: projects/{episode_id}/script_state.json")
        print(f"\n🎉 Hotovo! Projekt nyní má shot_plan a můžeš ho vidět v UI.")
        
    except Exception as e:
        print(f"\n❌ FDA selhal: {e}")
        
        # Mark as error
        state['steps']['footage_director']['status'] = 'ERROR'
        state['steps']['footage_director']['finished_at'] = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        state['steps']['footage_director']['error'] = {"message": str(e)}
        store.write_script_state(episode_id, state)
        
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
