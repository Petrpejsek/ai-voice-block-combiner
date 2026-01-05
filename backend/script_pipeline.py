import json
import os
import re
import threading
import time
import uuid
import glob
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple

# Cross-process lock support (macOS/Linux).
try:
    import fcntl  # type: ignore
    _FCNTL_AVAILABLE = True
except Exception:
    fcntl = None  # type: ignore
    _FCNTL_AVAILABLE = False

import requests

from project_store import ProjectStore
from footage_director import run_fda_llm
from archive_asset_resolver import resolve_shot_plan_assets
from compilation_builder import build_episode_compilation


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _safe_str(x: Any) -> str:
    return "" if x is None else str(x)


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def _coerce_list(val: Any) -> list:
    if val is None:
        return []
    if isinstance(val, list):
        return val
    return [val]


def _parse_json_from_text(text: str) -> Optional[dict]:
    """
    Best-effort JSON object parse:
    - direct json.loads
    - strip ```json fences
    - extract first {...} block
    - fix common JSON errors (e.g., missing quotes in arrays)
    """
    if text is None:
        return None
    raw = str(text).strip()
    if not raw:
        return None
    try:
        return json.loads(raw)
    except Exception:
        pass

    # strip fenced blocks
    fenced = re.sub(r"^```(?:json)?\s*", "", raw, flags=re.IGNORECASE).strip()
    fenced = re.sub(r"\s*```$", "", fenced).strip()
    if fenced != raw:
        try:
            return json.loads(fenced)
        except Exception:
            pass

    # extract first JSON object-ish substring
    m = re.search(r"\{[\s\S]*\}", raw)
    if m:
        candidate = m.group(0).strip()
        try:
            return json.loads(candidate)
        except Exception:
            # Attempt to fix common JSON errors (e.g., missing closing quotes in arrays)
            fixed = _fix_json_errors(candidate)
            if fixed != candidate:
                try:
                    return json.loads(fixed)
                except Exception:
                    pass
            return None
    return None


def _fix_json_errors(json_str: str) -> str:
    """
    Attempts to fix common JSON errors in LLM-generated JSON:
    - Missing closing quote for string in array (e.g., ["c_001", "c_002] → ["c_001", "c_002"])
    """
    # Fix: "c_NNN] → "c_NNN"]
    # This pattern specifically targets claim_ids in arrays where the closing quote is missing
    fixed = re.sub(r'"(c_\d{3})(\s*[,\]])', r'"\1"\2', json_str)
    
    return fixed


def _llm_chat_json_raw(
    provider: str,
    prompt: str,
    api_key: str,
    model: str = "gpt-4o",
    temperature: float = 0.4,
    timeout_s: int = 600,
) -> Tuple[str, Optional[dict], dict]:
    """
    Calls provider Chat Completions.
    For maximum compatibility (OpenRouter multi-provider), we DO NOT rely on response_format,
    and instead parse JSON from returned text. (Still stored as raw output for debugging.)
    Returns: (raw_text, parsed_json_or_none)
    """
    provider = (provider or "").strip().lower()
    if provider not in ("openai", "openrouter"):
        raise ValueError(f"Nepodporovaný provider: {provider}")

    if provider == "openai":
        url = "https://api.openai.com/v1/chat/completions"
        headers = {"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"}
    else:
        url = "https://openrouter.ai/api/v1/chat/completions"
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
            # Optional OpenRouter metadata headers (harmless if ignored)
            "HTTP-Referer": os.getenv("OPENROUTER_HTTP_REFERER", "http://localhost"),
            "X-Title": os.getenv("OPENROUTER_APP_TITLE", "podcasts"),
        }

    payload = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": "Return ONLY valid JSON (object) matching the requested schema. Do not include markdown.",
            },
            {"role": "user", "content": prompt},
        ],
        "temperature": temperature,
        "max_tokens": 16000,
    }
    resp = requests.post(url, headers=headers, json=payload, timeout=timeout_s)

    meta: dict = {
        "provider": provider,
        "url": url,
        "http_status": resp.status_code,
    }

    # Always try to capture provider JSON response (helps debugging cases where content is empty).
    # Store only a compact/safe subset to avoid bloating script_state.json.
    resp_json: Optional[dict] = None
    try:
        resp_json = resp.json()
    except Exception:
        meta["provider_response_text_head"] = _safe_str(resp.text)[:1500]

    if resp.status_code != 200:
        raise RuntimeError(f"{provider} API error {resp.status_code}: {_safe_str(resp.text)[:2000]}")

    # Compact provider response snapshot (for raw-output debugging)
    if isinstance(resp_json, dict):
        meta["provider_response"] = {
            "id": resp_json.get("id"),
            "model": resp_json.get("model"),
            "provider": resp_json.get("provider"),
            "usage": resp_json.get("usage"),
        }

    choices = (resp_json or {}).get("choices") if isinstance(resp_json, dict) else None
    c0 = choices[0] if isinstance(choices, list) and choices else {}
    msg = (c0.get("message") or {}) if isinstance(c0, dict) else {}

    meta["finish_reason"] = c0.get("finish_reason") if isinstance(c0, dict) else None
    meta["native_finish_reason"] = c0.get("native_finish_reason") if isinstance(c0, dict) else None

    content = msg.get("content")
    reasoning = msg.get("reasoning")
    meta["message_content_type"] = type(content).__name__
    meta["message_reasoning_type"] = type(reasoning).__name__
    meta["message_content_len"] = len(content) if isinstance(content, str) else None
    meta["message_reasoning_len"] = len(reasoning) if isinstance(reasoning, str) else None
    meta["message_refusal"] = msg.get("refusal")
    # Short heads (helps debugging without storing huge text twice)
    if isinstance(content, str):
        meta["message_content_head"] = content[:400]
    if isinstance(reasoning, str):
        meta["message_reasoning_head"] = reasoning[:400]

    # OpenRouter sometimes returns empty message.content and puts the generated text into message.reasoning.
    # To keep the pipeline stable, we fall back to reasoning if content is empty.
    text_for_parse = ""
    text_source = "none"
    if isinstance(content, str) and content.strip():
        text_for_parse = content
        text_source = "content"
    elif isinstance(reasoning, str) and reasoning.strip():
        text_for_parse = reasoning
        text_source = "reasoning"
    meta["response_text_source"] = text_source

    parsed = _parse_json_from_text(text_for_parse)
    return text_for_parse, parsed, meta


def _safe_format_template(template: str, values: dict) -> str:
    """
    Safe, explicit placeholder formatting using regex:
    - Replaces {key} ONLY if key is in values dict.
    - Leaves other {...} untouched (e.g., JSON examples like {"topic": "..."}).
    - This prevents KeyError on JSON examples in prompt templates.
    """
    import re
    
    def replacer(match):
        key = match.group(1)
        if key in values:
            return str(values[key])
        # If key not in values, leave it as-is
        return match.group(0)
    
    # Replace {word} patterns only if word is in values
    return re.sub(r'\{(\w+)\}', replacer, template)


def _default_step_config(step_key: str) -> dict:
    """
    Minimal per-step config, stored per episode_id.
    Provider is kept for future multi-provider support.
    """
    defaults = {
        "provider": "openai",
        "model": "gpt-4o",
        "temperature": 0.4,
        "prompt_template": None,
    }
    # Allow future per-step model defaults if needed.
    return {**defaults, "step": step_key}


def _make_initial_state(episode_id: str) -> dict:
    def step(name: str) -> dict:
        return {
            "name": name,
            "status": "IDLE",
            "started_at": None,
            "finished_at": None,
            "error": None,
        }

    return {
        "episode_id": episode_id,
        # Top-level metadata (safe place for canonical, non-raw artifacts)
        "metadata": {},
        # Immutable inputs for this episode (for reproducibility and retries)
        # Note: no fallbacks in runtime logic; if required fields are missing, pipeline must ERROR.
        "episode_input": {
            "topic": None,
            "language": None,
            "target_minutes": None,
            "channel_profile": None,
        },
        "script_status": "IDLE",
        "steps": {
            "research": step("research"),
            "narrative": step("narrative"),
            "validation": step("validation"),
            "composer": step("composer"),
            "tts_format": step("tts_format"),
            "footage_director": step("footage_director"),
            "asset_resolver": step("asset_resolver"),
            "compilation_builder": step("compilation_builder"),
        },
        "research_report": None,
        "draft_script": None,
        "validation_result": None,
        "script_package": None,
        "tts_ready_package": None,
        "shot_plan": None,
        "archive_manifest_path": None,
        "compilation_video_path": None,
        # attempts.narrative counts COMPLETED narrative runs, starting at 0.
        "attempts": {"narrative": 0},
        # Per-step configs (stored per episode_id for reproducibility)
        "research_config": _default_step_config("research"),
        "narrative_config": _default_step_config("narrative"),
        "validator_config": _default_step_config("validation"),
        "tts_format_config": _default_step_config("tts_format"),
        "footage_director_config": _default_step_config("footage_director"),
        # Raw outputs (MVP: steps 1-3 + 5 + 6). Stored to survive reloads.
        "research_raw_output": None,
        "narrative_raw_output": None,
        "validation_raw_output": None,
        "tts_format_raw_output": None,
        "footage_director_raw_output": None,
        "asset_resolver_output": None,
        "compilation_builder_output": None,
        "compilation_progress": None,  # Real-time progress from CB (phase, message, percent, details)
        "updated_at": _now_iso(),
    }


def _mark_step_running(state: dict, step_key: str, script_status: str) -> None:
    # Backward-compatible: older episodes may miss newer steps (e.g., footage_director).
    _ensure_step_exists(state, step_key)
    state["script_status"] = script_status
    step = state["steps"][step_key]
    step["status"] = "RUNNING"
    step["started_at"] = _now_iso()
    step["finished_at"] = None
    step["error"] = None
    state["updated_at"] = _now_iso()


def _mark_step_done(state: dict, step_key: str) -> None:
    _ensure_step_exists(state, step_key)
    step = state["steps"][step_key]
    step["status"] = "DONE"
    step["finished_at"] = _now_iso()
    step["error"] = None
    state["updated_at"] = _now_iso()


def _mark_step_error(state: dict, step_key: str, message: str, details: Optional[dict] = None) -> None:
    _ensure_step_exists(state, step_key)
    state["script_status"] = "ERROR"
    step = state["steps"][step_key]
    step["status"] = "ERROR"
    step["finished_at"] = _now_iso()
    step["error"] = {"message": message}
    if details is not None:
        step["error"]["details"] = details
    state["updated_at"] = _now_iso()


def _ensure_step_exists(state: dict, step_key: str) -> None:
    """
    Backward compatibility helper.
    Older script_state.json files may not contain newly introduced steps.
    This ensures state.steps[step_key] exists with the standard shape.
    """
    steps = state.get("steps")
    if not isinstance(steps, dict):
        steps = {}
        state["steps"] = steps
    if step_key in steps and isinstance(steps.get(step_key), dict):
        return
    steps[step_key] = {
        "name": step_key,
        "status": "IDLE",
        "started_at": None,
        "finished_at": None,
        "error": None,
    }


def _normalize_research_report(obj: dict) -> dict:
    _require(isinstance(obj, dict), "ResearchReport must be an object")
    _require("topic" in obj and _safe_str(obj.get("topic")).strip(), "ResearchReport.topic is required")
    _require("language" in obj and _safe_str(obj.get("language")).strip(), "ResearchReport.language is required")
    _require(isinstance(obj.get("timeline", None), list), "ResearchReport.timeline[] is required")
    _require(isinstance(obj.get("claims", None), list), "ResearchReport.claims[] is required")
    _require(isinstance(obj.get("entities", None), list), "ResearchReport.entities[] is required")

    # Minimal item checks
    for i, t in enumerate(obj["timeline"]):
        _require(isinstance(t, dict), f"timeline[{i}] must be object")
        _require(_safe_str(t.get("period")).strip(), f"timeline[{i}].period required")
        _require(_safe_str(t.get("event")).strip(), f"timeline[{i}].event required")

    claim_ids = set()
    for i, c in enumerate(obj["claims"]):
        _require(isinstance(c, dict), f"claims[{i}] must be object")
        cid = _safe_str(c.get("claim_id")).strip()
        _require(cid, f"claims[{i}].claim_id required")
        _require(_safe_str(c.get("text")).strip(), f"claims[{i}].text required")
        _require(_safe_str(c.get("importance")).strip(), f"claims[{i}].importance required")
        claim_ids.add(cid)

    for i, e in enumerate(obj["entities"]):
        _require(isinstance(e, dict), f"entities[{i}] must be object")
        _require(_safe_str(e.get("name")).strip(), f"entities[{i}].name required")
        _require(_safe_str(e.get("type")).strip(), f"entities[{i}].type required")

    # optional open_questions
    if "open_questions" in obj and obj["open_questions"] is not None:
        _require(isinstance(obj["open_questions"], list), "open_questions must be list if present")

    return obj


def _normalize_draft_script(obj: dict) -> dict:
    _require(isinstance(obj, dict), "DraftScript must be an object")
    _require(isinstance(obj.get("title_candidates", None), list) and obj["title_candidates"], "DraftScript.title_candidates[] is required")
    _require(_safe_str(obj.get("hook")).strip(), "DraftScript.hook is required")
    _require(isinstance(obj.get("chapters", None), list) and obj["chapters"], "DraftScript.chapters[] is required")
    _require(isinstance(obj.get("supported_claim_ids", None), list), "DraftScript.supported_claim_ids[] is required")

    for ci, ch in enumerate(obj["chapters"]):
        _require(isinstance(ch, dict), f"chapters[{ci}] must be object")
        _require(_safe_str(ch.get("chapter_id")).strip(), f"chapters[{ci}].chapter_id required")
        _require(_safe_str(ch.get("title")).strip(), f"chapters[{ci}].title required")
        _require(isinstance(ch.get("narration_blocks", None), list) and ch["narration_blocks"], f"chapters[{ci}].narration_blocks[] required")

        for bi, b in enumerate(ch["narration_blocks"]):
            _require(isinstance(b, dict), f"chapters[{ci}].narration_blocks[{bi}] must be object")
            _require(_safe_str(b.get("block_id")).strip(), f"block_id required at chapters[{ci}].narration_blocks[{bi}]")
            _require(_safe_str(b.get("text")).strip(), f"text required at chapters[{ci}].narration_blocks[{bi}]")
            # claim_ids[] is required field; may be empty list
            _require("claim_ids" in b, f"claim_ids[] field is required at chapters[{ci}].narration_blocks[{bi}]")
            _require(isinstance(b.get("claim_ids"), list), f"claim_ids must be list at chapters[{ci}].narration_blocks[{bi}]")

    return obj


def _sanitize_narrative_preface_and_hook(draft_script: dict, research_report: dict) -> dict:
    """
    Deterministic safety net to avoid common Validation FAIL patterns:
    - documentary_preface contains factual statements but has empty claim_ids
    - hook contains factual implications (names/dates/outcomes)
    
    Policy:
    - We NEVER add new factual content.
    - We may add claim_ids (references) using existing ResearchReport claim ids.
    - For hook, if it looks factual (mentions entities/dates), replace with a safe non-factual teaser.
    """
    if not isinstance(draft_script, dict):
        return draft_script
    if not isinstance(research_report, dict):
        return draft_script

    # Collect known anchors (entity names) + claim ids.
    language = _safe_str(research_report.get("language")).strip().lower() or "en"
    entities = _coerce_list(research_report.get("entities"))
    entity_names = []
    for e in entities:
        if isinstance(e, dict):
            n = _safe_str(e.get("name")).strip()
            if n:
                entity_names.append(n)
    claims = _coerce_list(research_report.get("claims"))
    claim_rows = []
    for c in claims:
        if not isinstance(c, dict):
            continue
        cid = _safe_str(c.get("claim_id")).strip()
        txt = _safe_str(c.get("text")).strip()
        imp = _safe_str(c.get("importance")).strip().lower()
        if cid and txt:
            claim_rows.append({"claim_id": cid, "text": txt, "importance": imp or "medium"})

    def _rank_imp(imp: str) -> int:
        if imp == "high":
            return 0
        if imp == "medium":
            return 1
        return 2

    claim_rows = sorted(claim_rows, key=lambda r: (_rank_imp(r.get("importance", "medium")), r.get("claim_id", "")))

    def _safe_nonfactual_hook(lang: str) -> str:
        if (lang or "").lower().startswith("cs"):
            return "Některé příběhy začínají otázkou, která nepustí. Pojďme sledovat, jak se postupně skládá obraz."
        return "Some stories begin with a question that won’t let go. Stay with us as the picture slowly comes into focus."

    def _safe_nonfactual_preface(lang: str) -> str:
        if (lang or "").lower().startswith("cs"):
            return "V tomto dokumentu se podíváme na jeden případ a na to, proč je důležitý. Zaměříme se na ověřená fakta a širší souvislosti."
        return "In this documentary, we examine one case and why it matters. We focus on verified facts and the broader context."

    # 1) documentary_preface: if present, ensure claim_ids is non-empty when text looks factual
    dp = draft_script.get("documentary_preface")
    if isinstance(dp, dict):
        txt = _safe_str(dp.get("text")).strip()
        cids = dp.get("claim_ids")
        if not isinstance(cids, list):
            cids = _coerce_list(cids)

        # Robust policy (deterministic):
        # - If preface has ANY text but claim_ids are empty/missing, rewrite preface to be directly supported by existing claims.
        #   This is safer than heuristics because validators treat many "high-level" statements as factual.
        if txt and len([x for x in cids if _safe_str(x).strip()]) == 0:
            picked = claim_rows[:2] if len(claim_rows) >= 2 else claim_rows[:1]
            if picked:
                dp["claim_ids"] = [r["claim_id"] for r in picked]
                dp["text"] = " ".join([r["text"] for r in picked]).strip()
            else:
                # No claims to reference: force a non-factual preface and keep claim_ids empty.
                dp["claim_ids"] = []
                dp["text"] = _safe_nonfactual_preface(language)
        # Ensure stable preface block_id if missing
        if not _safe_str(dp.get("block_id")).strip():
            dp["block_id"] = "preface_0001"
        draft_script["documentary_preface"] = dp

    # 2) hook: schema has no claim_ids, and validator requires it to be non-factual.
    # Deterministic safest behavior: always replace with a neutral non-factual teaser.
    draft_script["hook"] = _safe_nonfactual_hook(language)

    # #region agent log (hypothesis V)
    try:
        import time as _time
        import json as _json
        _dp = draft_script.get("documentary_preface") if isinstance(draft_script, dict) else None
        with open("/Users/petrliesner/podcasts/.cursor/debug.log", "a", encoding="utf-8") as _f:
            _f.write(_json.dumps({
                "sessionId": "debug-session",
                "runId": "validator-fix",
                "hypothesisId": "V",
                "location": "backend/script_pipeline.py:_sanitize_narrative_preface_and_hook",
                "message": "Applied deterministic intro sanitizer (preface/hook)",
                "data": {
                    "language": language,
                    "preface_block_id": (_dp or {}).get("block_id") if isinstance(_dp, dict) else None,
                    "preface_claim_ids_count": len((_dp or {}).get("claim_ids") or []) if isinstance(_dp, dict) else None,
                    "preface_text_head": (_safe_str((_dp or {}).get("text")).strip()[:120] if isinstance(_dp, dict) else None),
                    "hook_head": _safe_str(draft_script.get("hook")).strip()[:120] if isinstance(draft_script, dict) else None,
                },
                "timestamp": int(_time.time() * 1000),
            }) + "\n")
    except Exception:
        pass
    # #endregion

    return draft_script


def _normalize_validation_result(obj: dict) -> dict:
    _require(isinstance(obj, dict), "ValidationResult must be an object")
    status = _safe_str(obj.get("status")).strip().upper()
    _require(status in ("PASS", "FAIL"), "ValidationResult.status must be PASS or FAIL")
    issues = obj.get("issues", None)
    if issues is None and status == "PASS":
        issues = []
        obj["issues"] = issues
    _require(isinstance(issues, list), "ValidationResult.issues[] must be list (or omitted only when status=PASS)")

    # For PASS, issues must be empty (if present)
    if status == "PASS":
        _require(len(issues) == 0, "ValidationResult.issues must be [] when status=PASS")
    else:
        _require(len(issues) > 0, "ValidationResult.issues[] must be non-empty when status=FAIL")

    for ii, issue in enumerate(issues):
        _require(isinstance(issue, dict), f"issues[{ii}] must be object")
        _require(_safe_str(issue.get("issue_id")).strip(), f"issues[{ii}].issue_id required")
        _require(_safe_str(issue.get("severity")).strip(), f"issues[{ii}].severity required")
        _require(_safe_str(issue.get("message")).strip(), f"issues[{ii}].message required")
        _require(_safe_str(issue.get("suggested_fix")).strip(), f"issues[{ii}].suggested_fix required")
        # block_id/claim_id optional

    if status == "FAIL":
        _require(_safe_str(obj.get("patch_instructions")).strip(), "patch_instructions is required when status=FAIL")
    else:
        # Consistent: omit patch_instructions on PASS
        if "patch_instructions" in obj:
            obj.pop("patch_instructions", None)

    # risk_flags optional
    if "risk_flags" in obj and obj["risk_flags"] is not None:
        _require(isinstance(obj["risk_flags"], list), "risk_flags must be list if present")

    obj["status"] = status
    return obj


def _deterministic_compose(
    episode_id: str,
    language: str,
    target_minutes: Optional[int],
    channel_profile: Optional[str],
    research_report: dict,
    draft_script: dict,
    validation_result: dict,
) -> dict:
    """
    Composer (NO LLM): does not rewrite text. Only packages.
    Deterministically assembles script_package from validated inputs.
    
    Rules:
    - NO LLM calls
    - NO text modifications
    - NO claim_id guessing/fixing
    - ONLY structural packaging
    - Fails fast on integrity errors
    """
    _require(validation_result.get("status") == "PASS", "Composer requires ValidationResult.status=PASS")

    # 1) Select title (MUST exist, no fallbacks)
    title_candidates = _coerce_list(draft_script.get("title_candidates"))
    selected_title = _safe_str(title_candidates[0]).strip() if title_candidates else ""
    if not selected_title:
        raise ValueError("Composer error: draft_script.title_candidates[0] is empty or missing")

    # 2) Build claim_id index for integrity check
    claims = _coerce_list(research_report.get("claims"))
    valid_claim_ids = set()
    for c in claims:
        if isinstance(c, dict) and "claim_id" in c:
            valid_claim_ids.add(_safe_str(c.get("claim_id")).strip())

    # 3a) Process documentary_preface (if present) as first chapter/block
    chapters_out = []
    flat_blocks = []

    documentary_preface = draft_script.get("documentary_preface")
    if isinstance(documentary_preface, dict):
        preface_block_id = _safe_str(documentary_preface.get("block_id")).strip()
        if not preface_block_id:
            preface_block_id = "preface_0001"
        preface_text = _safe_str(documentary_preface.get("text")).strip()
        preface_claim_ids = documentary_preface.get("claim_ids")
        if not isinstance(preface_claim_ids, list):
            preface_claim_ids = _coerce_list(preface_claim_ids)
        
        # Integrity check for preface claim_ids
        for cid in preface_claim_ids:
            cid_str = _safe_str(cid).strip()
            if cid_str and cid_str not in valid_claim_ids:
                raise ValueError(
                    f"Composer integrity error: preface block_id={preface_block_id} references claim_id={cid_str} "
                    f"which does not exist in research_report.claims"
                )
        
        if preface_text:
            preface_block = {"block_id": preface_block_id, "text": preface_text, "claim_ids": preface_claim_ids}
            flat_blocks.append(preface_block)
            chapters_out.append({
                "chapter_id": "ch_00",
                "title": "Preface",
                "narration_blocks": [preface_block]
            })

    # 3b) Process hook (if present) as second chapter/block
    hook_text = _safe_str(draft_script.get("hook")).strip()
    if hook_text:
        hook_block = {
            "block_id": "hook_0001",
            "text": hook_text,
            "claim_ids": []  # Hook must be non-factual, so no claim_ids
        }
        flat_blocks.append(hook_block)
        chapters_out.append({
            "chapter_id": "ch_00a",
            "title": "Hook",
            "narration_blocks": [hook_block]
        })

    # 3c) Process main chapters and validate claim_ids
    for ch in draft_script.get("chapters", []):
        chapter_id = _safe_str(ch.get("chapter_id")).strip()
        chapter_title = _safe_str(ch.get("title")).strip()
        blocks_out = []

        for b in ch.get("narration_blocks", []):
            block_id = _safe_str(b.get("block_id")).strip()
            text = _safe_str(b.get("text")).strip()
            claim_ids = b.get("claim_ids")
            if not isinstance(claim_ids, list):
                claim_ids = _coerce_list(claim_ids)

            # Integrity check: all claim_ids must exist in research_report
            for cid in claim_ids:
                cid_str = _safe_str(cid).strip()
                if cid_str and cid_str not in valid_claim_ids:
                    raise ValueError(
                        f"Composer integrity error: block_id={block_id} references claim_id={cid_str} "
                        f"which does not exist in research_report.claims"
                    )

            block_obj = {"block_id": block_id, "text": text, "claim_ids": claim_ids}
            blocks_out.append(block_obj)
            flat_blocks.append(block_obj)

        chapters_out.append({"chapter_id": chapter_id, "title": chapter_title, "narration_blocks": blocks_out})

    # 4) Assemble final package
    pkg_language = language if language else _safe_str(research_report.get("language")).strip()
    if not pkg_language:
        raise ValueError("Composer error: language is missing (not in request nor research_report)")
    
    package = {
        "episode_id": episode_id,
        "language": pkg_language,
        "selected_title": selected_title,
        "chapters": chapters_out,
        "narration_blocks": flat_blocks,
        "fact_validation_status": "PASS",
        "metadata": {},
    }
    if target_minutes is not None:
        package["metadata"]["target_minutes"] = target_minutes
    if channel_profile is not None:
        package["metadata"]["channel_profile"] = channel_profile

    return package


def _prompt_research(topic: str, language: str, target_minutes: Optional[int], channel_profile: Optional[str]) -> str:
    return f"""
You are a Research Assistant (facts-only). No dramatization, no dialogue, no clickbait, no emotion.

Return a JSON object exactly matching this schema (minimal required fields):
{{
  "topic": string,
  "language": string,
  "timeline": [{{"period": string, "event": string}}],
  "claims": [{{"claim_id": string, "text": string, "importance": string}}],
  "entities": [{{"name": string, "type": string}}],
  "open_questions": [string]  // optional
}}

Rules:
- claims must be verifiable, phrased concretely.
- claim_id must be unique, like "c_001", "c_002"...
- importance should be one of: "high" | "medium" | "low"
- timeline must be chronological.
- entities.type must be one of: "person" | "place" | "organization" | "event" | "other"

Inputs:
- topic: {topic}
- language: {language}
- target_minutes: {target_minutes if target_minutes is not None else "null"}
- channel_profile: {channel_profile if channel_profile is not None else "null"}
""".strip()


def _prompt_narrative(
    research_report: dict,
    channel_profile: Optional[str],
    patch_instructions: Optional[str],
) -> str:
    patch_part = ""
    if patch_instructions:
        patch_part = f"\nPATCH INSTRUCTIONS (must follow):\n{patch_instructions}\n"

    return f"""
You are a Narrative Assistant (story-only). You MUST NOT invent facts beyond the provided ResearchReport.
You may be creative only in pacing, metaphors, and emotions—not in factual content.

Return a JSON object exactly matching this schema (minimal required fields):
{{
  "title_candidates": [string],
  "documentary_preface": {{
    "block_id": string,
    "text": string,
    "claim_ids": [string]
  }},
  "hook": string,
  "chapters": [
    {{
      "chapter_id": string,
      "title": string,
      "narration_blocks": [
        {{
          "block_id": string,
          "text": string,
          "claim_ids": [string]
        }}
      ]
    }}
  ],
  "supported_claim_ids": [string]
}}

Rules:
- Use claim_ids that reference ResearchReport.claims[*].claim_id only.
- claim_ids[] field is required for every block; it may be empty ONLY for pure rhetorical/transition blocks with NO factual claims.
- Do not add any concrete numbers/dates unless they appear in ResearchReport.claims.
- chapter_id should be like "ch_01", "ch_02"... block_id like "b_0001", "b_0002"...
- supported_claim_ids must include all claim_ids used anywhere in narration_blocks.
 - documentary_preface.text MUST NOT invent facts; if it contains any factual assertions, its claim_ids MUST cite the supporting ResearchReport claims.
 - hook MUST be a non-factual teaser: no dates/years, no named people/places/events, no implied outcomes ("never came", "was forced", etc.).
   Keep it abstract and atmospheric.

{patch_part}

ResearchReport:
{json.dumps(research_report, ensure_ascii=False)}
""".strip()


def _prompt_validator(research_report: dict, draft_script: dict) -> str:
    return f"""
You are a Fact Validator Assistant (gatekeeper).

Input:
- ResearchReport (facts)
- DraftScript (story)

Return a JSON object exactly matching this schema:
{{
  "status": "PASS" | "FAIL",
  "issues": [
    {{
      "issue_id": string,
      "severity": string,
      "block_id": string,     // optional
      "claim_id": string,     // optional
      "message": string,
      "suggested_fix": string
    }}
  ],
  "patch_instructions": string,   // REQUIRED ONLY WHEN status=FAIL; OMIT WHEN status=PASS
  "risk_flags": [string]          // optional
}}

Validation rules (MVP):
- FAIL if DraftScript introduces facts not grounded in ResearchReport.claims.
- FAIL if DraftScript uses claim_ids not present in ResearchReport.claims.
- FAIL if DraftScript.supported_claim_ids does not cover all claim_ids used in narration_blocks.
- For blocks with claim_ids=[], FAIL if they contain concrete factual assertions (numbers, dates, named events) not grounded in claims.

If FAIL:
- issues should point to block_id/claim_id when possible.
- patch_instructions must be concise and actionable for a re-run of Narrative.

If PASS:
- issues must be [].
- omit patch_instructions key.

ResearchReport:
{json.dumps(research_report, ensure_ascii=False)}

DraftScript:
{json.dumps(draft_script, ensure_ascii=False)}
""".strip()


def _prompt_tts_format(script_package: dict, language: str) -> str:
    """
    TTS Formatting prompt: Vezme hotový script_package a připraví TTS-ready text.
    NESMÍ přepisovat obsah, jen formátuje pro hlas (pauzy, intonace, segmenty).
    """
    return f"""
You are a TTS Formatting Assistant. Your task is to prepare the finalized script for text-to-speech generation.

CRITICAL RULES:
- DO NOT rewrite, change, or modify the script content
- DO NOT add, remove, or alter any facts or narrative elements
- ONLY format the existing text for voice delivery
- Add pauses, pronunciation hints, and prosody markers where appropriate
- Break into TTS-ready segments (blocks suitable for individual audio generation)

Input ScriptPackage:
{json.dumps(script_package, ensure_ascii=False, indent=2)}

Return a JSON object with this exact structure:
{{
  "episode_id": string,
  "language": string,
  "tts_segments": [
    {{
      "segment_id": string,       // e.g. "tts_001", "tts_002"
      "block_id": string,          // reference to original narration block
      "text": string,              // original text from script_package
      "tts_formatted_text": string,// text with SSML-like markers for pauses/intonation
      "pause_before_ms": number,   // milliseconds of silence before this segment
      "pause_after_ms": number,    // milliseconds of silence after this segment
      "metadata": {{
        "speaking_rate": string,   // "slow" | "normal" | "fast"
        "emphasis": string,        // "none" | "moderate" | "strong"
        "notes": string            // any TTS-specific notes
      }}
    }}
  ],
  "total_segments": number,
  "estimated_duration_seconds": number
}}

Formatting Guidelines:
1. Preserve all text exactly as written in script_package.narration_blocks[].text
2. Add natural pauses between sentences and paragraphs
3. Typical pause_before_ms: 300-600ms between blocks, 0ms for first block
4. Typical pause_after_ms: 600-1200ms at chapter boundaries
5. Use tts_formatted_text to add markers like:
   - <break time="500ms"/> for pauses
   - <emphasis level="moderate">word</emphasis> for stress
   - Keep it simple and compatible with common TTS engines
6. segment_id should be sequential: "tts_001", "tts_002", etc.
7. speaking_rate should be "normal" by default, "slow" for complex content
8. Estimate total duration based on ~150 words per minute for {language}

Output pure JSON. No explanations.
""".strip()


def _apply_step_prompt(step_key: str, state: dict, topic: str, language: str, target_minutes: Optional[int], channel_profile: Optional[str], patch_instructions: Optional[str]) -> Tuple[str, str]:
    """
    Returns (prompt_template_used, prompt_used_after_format).
    """
    if step_key == "research":
        config = state.get("research_config") or _default_step_config("research")
        template = config.get("prompt_template") or _prompt_research(topic, language, target_minutes, channel_profile)
        # Default prompt already includes variables; template may use placeholders.
        if config.get("prompt_template"):
            prompt_used = _safe_format_template(
                template,
                {
                    "topic": topic,
                    "language": language,
                    "target_minutes": target_minutes if target_minutes is not None else "null",
                    "channel_profile": channel_profile if channel_profile is not None else "null",
                },
            )
        else:
            prompt_used = template
        return template, prompt_used

    if step_key == "narrative":
        config = state.get("narrative_config") or _default_step_config("narrative")
        template = config.get("prompt_template") or _prompt_narrative(state["research_report"], channel_profile, patch_instructions)
        if config.get("prompt_template"):
            prompt_used = _safe_format_template(
                template,
                {
                    "research_report_json": json.dumps(state["research_report"], ensure_ascii=False),
                    "target_minutes": target_minutes if target_minutes is not None else "null",
                    "channel_profile": channel_profile if channel_profile is not None else "null",
                    "patch_instructions": patch_instructions or "",
                },
            )
        else:
            prompt_used = template
        # Hard, non-negotiable guardrails (independent of user prompt templates)
        prompt_used = (
            "HARD RULES (must obey):\n"
            "- You may ONLY source factual assertions from ResearchReport.claims[].\n"
            "- ResearchReport.timeline is NOT an allowed source of facts (use it only for ordering).\n"
            "- If a narration block has claim_ids = [], it must contain ZERO factual assertions.\n"
            "  That means: no dates, no numbers, no named works, no named events, and no specific claims.\n"
            "- If you cannot support a sentence with claim_ids from ResearchReport.claims, rewrite it to be non-factual or remove it.\n"
            "- Outcome discipline: If a claim does NOT explicitly state an outcome, you MUST NOT imply it.\n"
            "  Avoid evaluative/consequence phrasing unless it is explicitly in the claim text (e.g., dominance, secured control,\n"
            "  turned the tide, proved disastrous, decisive, catastrophic).\n"
            "  Prefer neutral phrasing: aimed to…, sought to…, expected that…, planned to…, intended to….\n"
            "- Self-check before output: each sentence must be a direct paraphrase of the referenced claim text.\n"
            "  If not, rewrite it to match the claim(s) exactly.\n"
            "- Never invent facts.\n\n"
        ) + prompt_used
        return template, prompt_used

    if step_key == "validation":
        config = state.get("validator_config") or _default_step_config("validation")
        template = config.get("prompt_template") or _prompt_validator(state["research_report"], state["draft_script"])
        if config.get("prompt_template"):
            prompt_used = _safe_format_template(
                template,
                {
                    "research_report_json": json.dumps(state["research_report"], ensure_ascii=False),
                    "draft_script_json": json.dumps(state["draft_script"], ensure_ascii=False),
                },
            )
        else:
            prompt_used = template
        # Hard output contract + better suggested_fix behavior
        prompt_used = (
            "HARD RULES (must obey):\n"
            "- If PASS, output exactly: {\"status\":\"PASS\",\"issues\":[]} (no patch_instructions).\n"
            "- If FAIL, issues[] must be non-empty and patch_instructions must be present.\n"
            "- When suggesting fixes: if NO claim in ResearchReport.claims supports a statement, do NOT suggest adding a claim_id.\n"
            "  Instead, instruct to rewrite/remove the unsupported statement so it matches ONLY existing claims.\n\n"
        ) + prompt_used
        return template, prompt_used

    if step_key == "tts_format":
        config = state.get("tts_format_config") or _default_step_config("tts_format")
        script_package = state.get("script_package")
        if not script_package:
            raise ValueError("TTS Formatting requires script_package to exist")
        template = config.get("prompt_template") or _prompt_tts_format(script_package, language)
        if config.get("prompt_template"):
            prompt_used = _safe_format_template(
                template,
                {
                    "script_package_json": json.dumps(script_package, ensure_ascii=False),
                    "language": language,
                },
            )
        else:
            prompt_used = template
        return template, prompt_used

    raise ValueError(f"Unknown step for prompt: {step_key}")


def _run_tts_formatting(
    state: dict,
    episode_id: str,
    topic: str,
    language: str,
    target_minutes: Optional[int],
    channel_profile: Optional[str],
    provider_api_keys: dict,
    store: 'ProjectStore',
) -> None:
    """Helper to run TTS formatting step (used in multiple places)."""
    _mark_step_running(state, "tts_format", "RUNNING_TTS_FORMAT")
    store.write_script_state(episode_id, state)
    try:
        cfg = _step_config_for(state, "tts_format")
        provider = _safe_str(cfg.get("provider")).strip().lower()
        if not provider:
            raise RuntimeError("TTS Format: config.provider is missing")
        model = _safe_str(cfg.get("model")).strip()
        if not model:
            raise RuntimeError("TTS Format: config.model is missing")
        api_key = _safe_str((provider_api_keys or {}).get(provider)).strip()
        if not api_key:
            raise RuntimeError(f"Chybí API key pro provider '{provider}' (TTS Format)")
        prompt_template, prompt_used = _apply_step_prompt("tts_format", state, topic, language, target_minutes, channel_profile, None)
        raw_text, parsed, meta = _llm_chat_json_raw(
            provider,
            prompt_used,
            api_key,
            model=model,
            temperature=float(cfg.get("temperature", 0.4)),
        )
        _write_raw_output(state, "tts_format", raw_text, parsed, prompt_template, prompt_used, meta=meta)
        store.write_script_state(episode_id, state)
        if parsed is None:
            fr = (meta or {}).get("finish_reason")
            src = (meta or {}).get("response_text_source")
            raise RuntimeError(f"TTS Format: LLM vrátil nevalidní JSON (source={src}, finish_reason={fr})")
        state["tts_ready_package"] = parsed

        # Canonicalize TTS package: ensure narration_blocks[] exists (expected source for FDA coverage gate).
        # We derive it deterministically from tts_segments[] (text_tts := tts_formatted_text).
        try:
            tts_pkg = state.get("tts_ready_package") or {}
            if isinstance(tts_pkg, dict):
                # --------------------------------------------------------------------
                # CRITICAL: Ensure canonical episode_metadata.topic exists for downstream
                # query/keyword guardrails. This is NOT a heuristic: we persist the
                # step's explicit `topic` into the TTS package if missing (legacy fix).
                # --------------------------------------------------------------------
                em = tts_pkg.get("episode_metadata")
                if not isinstance(em, dict):
                    em = {}
                    tts_pkg["episode_metadata"] = em
                if not _safe_str(em.get("topic")).strip():
                    # Single canonical source: episode_metadata["topic"]
                    # Populate from the pipeline's explicit topic input.
                    em["topic"] = _safe_str(topic).strip()

                nb = tts_pkg.get("narration_blocks")
                if not (isinstance(nb, list) and nb):
                    segs = tts_pkg.get("tts_segments")
                    if isinstance(segs, list) and segs:
                        derived = []
                        for seg in segs:
                            if not isinstance(seg, dict):
                                continue
                            block_id = _safe_str(seg.get("block_id") or seg.get("segment_id")).strip()
                            if not block_id:
                                continue
                            text_tts = seg.get("tts_formatted_text")
                            if not text_tts or not isinstance(text_tts, str) or not text_tts.strip():
                                # Keep strict: FDA will raise FDA_TEXT_TTS_MISSING later.
                                text_tts = ""
                            derived.append({"block_id": block_id, "text_tts": text_tts, "claim_ids": []})
                        if derived:
                            tts_pkg["narration_blocks"] = derived
        except Exception:
            # Non-fatal here; FDA step will enforce and fail with FDA_INPUT_MISSING / FDA_TEXT_TTS_MISSING if required.
            pass

        # Persist canonical expected source in metadata too (defensive: gates can prefer metadata.tts_ready_package)
        md = state.get("metadata")
        if not isinstance(md, dict):
            md = {}
            state["metadata"] = md
        if isinstance(state.get("tts_ready_package"), dict):
            md["tts_ready_package"] = state["tts_ready_package"]

        _mark_step_done(state, "tts_format")
        state["script_status"] = "DONE"
        state["updated_at"] = _now_iso()
        store.write_script_state(episode_id, state)
    except Exception as e:
        _mark_step_error(state, "tts_format", f"TTS Format krok selhal: {str(e)}")
        store.write_script_state(episode_id, state)
        raise


def _run_footage_director(
    state: dict,
    episode_id: str,
    topic: str,
    language: str,
    target_minutes: Optional[int],
    channel_profile: Optional[str],
    provider_api_keys: dict,
    store: 'ProjectStore',
) -> None:
    """Helper to run Footage Director Assistant (FDA) step - LLM-assisted shot planning."""
    _mark_step_running(state, "footage_director", "RUNNING_FOOTAGE_DIRECTOR")
    store.write_script_state(episode_id, state)
    try:
        # FDA je LLM-assisted (gpt-4o-mini default)
        if not state.get("tts_ready_package"):
            raise RuntimeError("Footage Director: tts_ready_package is missing")
        
        from footage_director import FDA_V27_VERSION
        
        cfg = _step_config_for(state, "footage_director")
        # v2.7 mode is DEFAULT (high quality deterministicgenerators + guardrails)
        # v3 mode can be explicitly requested with use_v3_mode=True
        use_v27_mode = not cfg.get("use_v3_mode", False)  # Default: v2.7
        if cfg.get("version") == FDA_V27_VERSION:
            use_v27_mode = True
        
        # v3 policy: LLM call is best-effort. Missing provider/model/api_key is NOT fatal.
        provider = _safe_str(cfg.get("provider")).strip().lower() or "openrouter"
        model = _safe_str(cfg.get("model")).strip() or "openai/gpt-4o-mini"
        api_key = _safe_str((provider_api_keys or {}).get(provider)).strip()
        
        # Expected source (canonical): metadata.tts_ready_package if present, otherwise state.tts_ready_package.
        tts_pkg = None
        if isinstance(state.get("metadata"), dict):
            tts_pkg = state["metadata"].get("tts_ready_package")
        if not isinstance(tts_pkg, dict):
            tts_pkg = state.get("tts_ready_package", {}) or {}

        # --------------------------------------------------------------------
        # LEGACY MIGRATION (NO HEURISTICS):
        # Some older episodes have tts_ready_package without episode_metadata.
        # Downstream guardrails require canonical episode_metadata["topic"].
        # If missing, we backfill it from this step's explicit `topic` input
        # and persist it into state + metadata.
        # --------------------------------------------------------------------
        try:
            if isinstance(tts_pkg, dict):
                em = tts_pkg.get("episode_metadata")
                if not isinstance(em, dict):
                    em = {}
                    tts_pkg["episode_metadata"] = em
                if not _safe_str(em.get("topic")).strip():
                    explicit_topic = _safe_str(topic).strip()
                    if explicit_topic:
                        em["topic"] = explicit_topic
                        # Persist back into state + metadata (canonical source).
                        state["tts_ready_package"] = tts_pkg
                        md = state.get("metadata")
                        if not isinstance(md, dict):
                            md = {}
                            state["metadata"] = md
                        md["tts_ready_package"] = tts_pkg
                        state["updated_at"] = _now_iso()
                        store.write_script_state(episode_id, state)
                        print(f"⚠️  EPISODE_METADATA_BACKFILL episode_id={episode_id} field=episode_metadata.topic")
        except Exception:
            # If something goes wrong here, the strict getter in footage_director
            # will produce a loud EPISODE_METADATA_MISSING/EPISODE_TOPIC_MISSING.
            pass

        fda_warnings = []
        
        # ============================================================================
        # v2.7 MODE: Full deterministic generation with guardrails
        # ============================================================================
        if use_v27_mode:
            from footage_director import (
                run_fda_llm,
                apply_deterministic_generators_v27,
                validate_shot_plan_hard_gate,
                coerce_fda_v27_version_inplace,
                PRE_FDA_SANITIZER_AVAILABLE,
                sanitize_and_log,
            )
            
            raw_llm_draft = None
            raw_text = ""
            llm_meta = None
            
            # Optional cached draft usage (explicit or forced when no api_key).
            cached_wrapper = None
            try:
                fdr = state.get("footage_director_raw_output")
                if isinstance(fdr, dict) and isinstance(fdr.get("response_json"), dict):
                    cached_wrapper = fdr.get("response_json")
            except Exception:
                cached_wrapper = None

            use_cached = bool(cfg.get("use_cached_draft") or cfg.get("use_cached_response_json"))
            if (not api_key) and cached_wrapper:
                use_cached = True

            # Acquire raw draft (cached or fresh LLM)
            if use_cached and cached_wrapper:
                print(f"FDA_LLM_SOURCE episode_id={episode_id} source=cached")
                raw_llm_draft = cached_wrapper
                raw_text = ""
                llm_meta = {"raw_llm_version": None, "source": "cached"}
                # Raw checkpoint (cached)
                try:
                    sp0 = raw_llm_draft.get("shot_plan") if isinstance(raw_llm_draft, dict) else None
                    v0 = sp0.get("version") if isinstance(sp0, dict) else None
                except Exception:
                    v0 = None
                llm_meta["raw_llm_version"] = v0
                print(f"FDA_RAW_VERSION episode_id={episode_id} raw_version={v0} final_version=PENDING")

                # v2.7 coercion gate must happen BEFORE sanitizer/deterministic/validation
                try:
                    coerce_fda_v27_version_inplace(raw_llm_draft, episode_id=episode_id)
                except Exception:
                    pass

                # Postprocess cached draft similarly to run_fda_llm (sanitizer + deterministic generators)
                if PRE_FDA_SANITIZER_AVAILABLE:
                    try:
                        shot_plan_to_sanitize = raw_llm_draft
                        if isinstance(raw_llm_draft, dict) and "shot_plan" in raw_llm_draft:
                            shot_plan_to_sanitize = raw_llm_draft["shot_plan"]

                        sanitized_shot_plan = sanitize_and_log(shot_plan_to_sanitize)

                        if isinstance(raw_llm_draft, dict) and "shot_plan" in raw_llm_draft:
                            if isinstance(sanitized_shot_plan, dict) and "shot_plan" in sanitized_shot_plan:
                                raw_llm_draft["shot_plan"] = sanitized_shot_plan["shot_plan"]
                            else:
                                raw_llm_draft["shot_plan"] = sanitized_shot_plan
                        else:
                            raw_llm_draft = sanitized_shot_plan
                    except Exception as e:
                        raise RuntimeError(f"FDA_SANITIZER_FAILED: {e}")
                else:
                    raise RuntimeError("FDA_SANITIZER_UNAVAILABLE: Pre-FDA Sanitizer není dostupný")

                try:
                    raw_llm_draft = apply_deterministic_generators_v27(raw_llm_draft, tts_pkg, episode_id)
                except Exception as e:
                    print(f"⚠️  Deterministic generators failed (cached path): {e}")

                fixed_wrapper = raw_llm_draft

            # Try fresh LLM call (best-effort)
            elif api_key:
                try:
                    print(f"FDA_LLM_SOURCE episode_id={episode_id} source=fresh_llm")
                    raw_llm_draft, raw_text, llm_meta = run_fda_llm(
                        state,
                        provider_api_keys,
                        config={**cfg, "provider": provider, "model": model},
                    )
                    print(f"📝 FDA v2.7: Got LLM draft (will be post-processed)")
                except Exception as e:
                    fda_warnings.append({"code": "FDA_LLM_FAILED", "message": str(e)})
                    print(f"⚠️  FDA v2.7: LLM call failed, using deterministic fallback")
            else:
                fda_warnings.append({"code": "FDA_LLM_SKIPPED_NO_API_KEY", "message": f"Missing API key for provider '{provider}'"})
                print(f"📝 FDA_LLM_DRAFT_IGNORED {{reason: 'no_api_key'}}")
            
            # Save raw LLM draft for debugging (NEVER used downstream)
            _write_raw_output_fda(state, raw_text, raw_llm_draft if isinstance(raw_llm_draft, dict) else None, llm_meta or {})
            store.write_script_state(episode_id, state)
            
            # IMPORTANT: raw_llm_draft is processed inside run_fda_llm via apply_deterministic_generators_v27
            # The returned value is already post-processed
            if raw_llm_draft is None:
                # No LLM output - this shouldn't happen as run_fda_llm should always return something
                raise RuntimeError("FDA_V27_FAILED: No shot plan generated (LLM failed and no fallback)")
            
            if raw_llm_draft is not None and "fixed_wrapper" not in locals():
                fixed_wrapper = raw_llm_draft  # This is already post-processed by run_fda_llm
            
            # Hard validation (FAIL-STOP)
            try:
                # Required checkpoint tag (user request): include episode_id + raw_version + final_version
                try:
                    raw_v = (llm_meta or {}).get("raw_llm_version")
                except Exception:
                    raw_v = None
                final_v = None
                try:
                    sp_tmp = fixed_wrapper.get("shot_plan") if isinstance(fixed_wrapper, dict) else None
                    final_v = sp_tmp.get("version") if isinstance(sp_tmp, dict) else None
                except Exception:
                    final_v = None
                print(
                    f"FDA_FINAL_VERSION episode_id={episode_id} raw_version={raw_v} final_version={final_v}"
                )
                # CRITICAL: Must validate the *post-processed* shot plan using the canonical hard gate.
                # This is the single last-mile hook that also enforces the FDA keyword contract
                # (2–5 words each, exactly 8, >=3 physical objects) before the strict validator runs.
                validate_shot_plan_hard_gate(fixed_wrapper, tts_pkg, episode_id=episode_id)
            except RuntimeError as e:
                error_msg = str(e)
                if ("FDA_VALIDATION_FAILED" in error_msg) or ("LOCAL_PREFLIGHT_FAILED" in error_msg):
                    print(f"❌ FDA v2.7 validation FAILED: {error_msg[:200]}")
                    raise RuntimeError(f"FDA_V27_VALIDATION_FAILED: Post-processed shot plan failed validation: {error_msg}")
                raise
            
            sp_w = []  # v2.7 warnings captured in fda_warnings
            comp_w = []
        
        # ============================================================================
        # v3 MODE (default): ScenePlan → ShotPlan compilation
        # ============================================================================
        else:
            from footage_director import run_sceneplan_llm
            from visual_planning_v3 import coerce_sceneplan_v3, compile_shotplan_v3, validate_shotplan_v3_minimal

            raw_sceneplan = None
            raw_text = ""
            llm_meta = None
            if api_key:
                try:
                    raw_sceneplan, raw_text, llm_meta = run_sceneplan_llm(
                        state,
                        provider_api_keys,
                        config={**cfg, "provider": provider, "model": model},
                    )
                except Exception as e:
                    fda_warnings.append({"code": "FDA_LLM_FAILED", "message": str(e)})
            else:
                fda_warnings.append({"code": "FDA_LLM_SKIPPED_NO_API_KEY", "message": f"Missing API key for provider '{provider}', using deterministic fallback"})

            # Save raw output for debugging (never used downstream).
            _write_raw_output_fda(state, raw_text, raw_sceneplan if isinstance(raw_sceneplan, dict) else None, llm_meta or {})
            store.write_script_state(episode_id, state)

            # Coerce ScenePlan + compile ShotPlan v3 deterministically.
            sceneplan_v3, sp_w = coerce_sceneplan_v3(raw_sceneplan, tts_pkg)
            fixed_wrapper, comp_w = compile_shotplan_v3(tts_pkg, sceneplan_v3, words_per_minute=150)
            # Minimal hard gate (should always pass unless there's an internal bug).
            validate_shotplan_v3_minimal(fixed_wrapper, tts_pkg, episode_id=episode_id)

        # ============================================================================
        # HARD ASSERTION (FAIL-STOP) before saving
        # ============================================================================
        sp = fixed_wrapper.get("shot_plan") if isinstance(fixed_wrapper, dict) else None
        
        if not isinstance(sp, dict):
            raise RuntimeError("FDA_INVALID_OUTPUT: fixed_wrapper['shot_plan'] must be a dict")
        
        # Check version
        sp_version = sp.get("version", "")
        
        # ========================================================================
        # DIAGNOSTIC LOG: Final version check před emit
        # ========================================================================
        print(f"🔍 FDA_DIAGNOSTIC {{episode_id: '{episode_id}', stage: 'final_before_emit', version: '{sp_version}', use_v27_mode: {use_v27_mode}}}")
        
        if use_v27_mode:
            # v2.7 mode: MUST be fda_v2.7
            if sp_version != FDA_V27_VERSION:
                # v2.7 kill-switch: never fail on VERSION_MISMATCH (last resort before emit)
                try:
                    from footage_director import coerce_fda_v27_version_inplace
                    coerced = coerce_fda_v27_version_inplace(fixed_wrapper, episode_id=episode_id)
                    if coerced:
                        sp_version = sp.get("version", "")
                except Exception:
                    pass
            if sp_version != FDA_V27_VERSION:
                raise RuntimeError(f"FDA_VERSION_MISMATCH: Expected '{FDA_V27_VERSION}', got '{sp_version}'")
        # v3 mode: MUST be shotplan_v3 (checked by validate_shotplan_v3_minimal above)
        
        # Check source
        sp_source = sp.get("source", "")
        if use_v27_mode and sp_source != "tts_ready_package":
            raise RuntimeError(f"FDA_SOURCE_MISMATCH: Expected 'tts_ready_package', got '{sp_source}'")
        
        # Check no extra top-level keys (v2.7 only)
        if use_v27_mode:
            allowed_keys = {"version", "source", "assumptions", "scenes"}
            extra_keys = set(sp.keys()) - allowed_keys
            if extra_keys:
                raise RuntimeError(f"FDA_EXTRA_FIELDS: shot_plan contains forbidden fields: {list(extra_keys)}")
        
        # Check source_preference in scenes (v2.7 only)
        sp_scenes = sp.get("scenes", [])
        if use_v27_mode and isinstance(sp_scenes, list):
            for i, scene in enumerate(sp_scenes):
                if not isinstance(scene, dict):
                    continue
                shot_strategy = scene.get("shot_strategy", {})
                if isinstance(shot_strategy, dict):
                    source_pref = shot_strategy.get("source_preference")
                    if not isinstance(source_pref, list):
                        raise RuntimeError(f"FDA_INVALID_SOURCE_PREF: Scene {i}: source_preference must be list, got {type(source_pref).__name__}")
                    if source_pref != ["archive_org"]:
                        raise RuntimeError(f"FDA_INVALID_SOURCE_PREF: Scene {i}: source_preference must be ['archive_org'], got {source_pref}")
        
        # 3) Telegraph log před uložením (1 řádek)
        sp_assumptions = sp.get("assumptions", {}) if isinstance(sp, dict) else {}

        used_block_ids = []
        if isinstance(sp_scenes, list):
            for scene in sp_scenes:
                if not isinstance(scene, dict):
                    continue
                bids = scene.get("narration_block_ids")
                if isinstance(bids, list):
                    used_block_ids.extend([_safe_str(x).strip() for x in bids if _safe_str(x).strip()])

        expected_block_ids = []
        nb = tts_pkg.get("narration_blocks")
        if isinstance(nb, list) and nb:
            for b in nb:
                if not isinstance(b, dict):
                    continue
                bid = _safe_str(b.get("block_id")).strip()
                if bid:
                    expected_block_ids.append(bid)
        else:
            segs = tts_pkg.get("tts_segments")
            if isinstance(segs, list) and segs:
                for seg in segs:
                    if not isinstance(seg, dict):
                        continue
                    bid = _safe_str(seg.get("block_id") or seg.get("segment_id")).strip()
                    if bid:
                        expected_block_ids.append(bid)
            else:
                chapters = tts_pkg.get("chapters")
                if isinstance(chapters, list) and chapters:
                    for ch in chapters:
                        if not isinstance(ch, dict):
                            continue
                        blocks = ch.get("narration_blocks")
                        if not isinstance(blocks, list):
                            continue
                        for b in blocks:
                            if not isinstance(b, dict):
                                continue
                            bid = _safe_str(b.get("block_id")).strip()
                            if bid:
                                expected_block_ids.append(bid)

        # FDA_FINAL_PLAN_SAVED logging (1 line)
        print(
            "FDA_FINAL_PLAN_SAVED { "
            f"version={sp_version}, "
            f"scene_count={len(sp_scenes) if isinstance(sp_scenes, list) else 0}, "
            f"episode_id={episode_id}, "
            f"mode={'v2.7' if use_v27_mode else 'v3'}, "
            f"post_processed={True if use_v27_mode else 'deterministic_compiler'}"
            " }"
        )

        # 4) Ulož canonical wrapper do state (metadata + backward-compat top-level)
        md = state.get("metadata")
        if not isinstance(md, dict):
            md = {}
            state["metadata"] = md
        # Store ScenePlan v3 for debugging / audit (v3 mode only).
        if not use_v27_mode:
            md["scene_plan"] = sceneplan_v3
        md["shot_plan"] = fixed_wrapper
        state["shot_plan"] = fixed_wrapper

        # 5) Doplnění debug raw output + warnings (safe: UI/debug only; downstream se nesmí řídit raw)
        if isinstance(state.get("footage_director_raw_output"), dict):
            if not use_v27_mode:
                state["footage_director_raw_output"]["scene_plan_saved"] = sceneplan_v3
            state["footage_director_raw_output"]["shot_plan_saved"] = fixed_wrapper
            state["footage_director_raw_output"]["warnings"] = (fda_warnings + sp_w + comp_w)[:200]

        # Persist step-level warnings (UI can render DONE + WARNINGS)
        try:
            state.setdefault("pipeline_warnings", [])
            if isinstance(state.get("pipeline_warnings"), list):
                state["pipeline_warnings"].extend((fda_warnings + sp_w + comp_w)[:200])
            step_obj = ((state.get("steps") or {}).get("footage_director") or {})
            step_obj["warnings"] = (fda_warnings + sp_w + comp_w)[:200]
            (state.get("steps") or {})["footage_director"] = step_obj
        except Exception:
            pass

        _mark_step_done(state, "footage_director")
        state["script_status"] = "DONE"
        state["updated_at"] = _now_iso()
        store.write_script_state(episode_id, state)
        
        # ============================================================================
        # AUTO-GENERATE AAR QUERIES (NEW: After FDA completion)
        # Generate episode-level queries and save to archive_manifest.json
        # This allows users to see/edit queries BEFORE clicking Preview!
        # ============================================================================
        try:
            from archive_asset_resolver import _extract_episode_queries
            import json as json_lib
            
            print(f"🎯 Auto-generating AAR queries after FDA completion...")
            
            # Extract episode topic
            episode_topic = state.get("topic") or ""
            if isinstance(state.get("metadata"), dict):
                episode_topic = state["metadata"].get("topic") or episode_topic

            # #region agent log (hypothesis B/C)
            try:
                import time as _time
                import json as _json
                md0 = state.get("metadata") if isinstance(state.get("metadata"), dict) else {}
                ep_in0 = state.get("episode_input") if isinstance(state.get("episode_input"), dict) else {}
                with open("/Users/petrliesner/podcasts/.cursor/debug.log", "a", encoding="utf-8") as _f:
                    _f.write(_json.dumps({
                        "sessionId": "debug-session",
                        "runId": "run1",
                        "hypothesisId": "C",
                        "location": "backend/script_pipeline.py:_run_footage_director",
                        "message": "FDA completed; about to auto-generate AAR queries (topic sources)",
                        "data": {
                            "episode_id": episode_id,
                            "state_topic": str(state.get("topic") or ""),
                            "metadata_topic": str(md0.get("topic") or ""),
                            "episode_input_topic": str(ep_in0.get("topic") or ""),
                            "episode_input_title": str(ep_in0.get("title") or ""),
                            "selected_title": str(state.get("selected_title") or ""),
                            "channel_profile": str(channel_profile or ""),
                            "episode_topic_used_for_queries": str(episode_topic or ""),
                            "scenes_count": len(sp_scenes) if isinstance(sp_scenes, list) else None,
                        },
                        "timestamp": int(_time.time() * 1000),
                    }) + "\n")
            except Exception:
                pass
            # #endregion
            
            # Generate queries
            episode_queries = _extract_episode_queries(sp_scenes, max_queries=12, episode_topic=episode_topic)
            print(f"📝 Generated {len(episode_queries)} AAR queries: {episode_queries}")

            # #region agent log (hypothesis A/B)
            try:
                import time as _time
                import json as _json
                with open("/Users/petrliesner/podcasts/.cursor/debug.log", "a", encoding="utf-8") as _f:
                    _f.write(_json.dumps({
                        "sessionId": "debug-session",
                        "runId": "run1",
                        "hypothesisId": "A",
                        "location": "backend/script_pipeline.py:_run_footage_director",
                        "message": "Auto-generated AAR episode_pool queries after FDA",
                        "data": {
                            "episode_id": episode_id,
                            "queries_count": len(episode_queries) if isinstance(episode_queries, list) else None,
                            "queries_head": (episode_queries or [])[:8] if isinstance(episode_queries, list) else None,
                        },
                        "timestamp": int(_time.time() * 1000),
                    }) + "\n")
            except Exception:
                pass
            # #endregion
            
            # Save to archive_manifest.json
            episode_dir = store.episode_dir(episode_id)
            manifest_path = os.path.join(episode_dir, 'archive_manifest.json')
            
            # Load or create manifest
            manifest = {}
            if os.path.exists(manifest_path):
                try:
                    with open(manifest_path, 'r', encoding='utf-8') as f:
                        manifest = json_lib.load(f)
                except Exception:
                    manifest = {}
            
            # Update episode_pool section
            if 'episode_pool' not in manifest:
                manifest['episode_pool'] = {}
            
            manifest['episode_pool']['queries_used'] = episode_queries
            manifest['episode_pool']['queries_generated_at'] = _now_iso()
            manifest['episode_pool']['mode'] = 'episode_first'
            
            # Save manifest
            os.makedirs(os.path.dirname(manifest_path), exist_ok=True)
            with open(manifest_path, 'w', encoding='utf-8') as f:
                json_lib.dump(manifest, f, ensure_ascii=False, indent=2)
            
            print(f"✅ AAR queries auto-saved to {manifest_path}")
            
        except Exception as e:
            print(f"⚠️ Failed to auto-generate AAR queries: {e}")
            # Non-fatal: user can still run Preview to generate them
        
        # ============================================================================
        store.write_script_state(episode_id, state)
        
        # Log pro debugging
        print(f"✅ FDA: Saved {sp_version} shot_plan with {len(sp_scenes)} scenes (mode: {'v2.7' if use_v27_mode else 'v3'})")
        
    except Exception as e:
        # Still fatal only for true internal/runtime failures (not LLM format/style).
        error_msg = str(e)
        _mark_step_error(state, "footage_director", f"Footage Director krok selhal: {error_msg}")
        store.write_script_state(episode_id, state)
        raise


def _run_fda_output_validator(
    state: dict,
    episode_id: str,
    store: 'ProjectStore',
) -> None:
    """
    Deterministic validation checkpoint between FDA and AAR.
    Must stop the pipeline if shot_plan is invalid.
    """
    _ensure_step_exists(state, "fda_output_validator")
    try:
        _mark_step_running(state, "fda_output_validator", "RUNNING_FDA_OUTPUT_VALIDATOR")
        store.write_script_state(episode_id, state)

        md = state.get("metadata")
        if not isinstance(md, dict):
            raise RuntimeError("FDA_INVALID_SHOT_PLAN: state.metadata missing (expected metadata.shot_plan + metadata.tts_ready_package)")

        shot_plan_wrapper = md.get("shot_plan")
        if not (isinstance(shot_plan_wrapper, dict) and isinstance(shot_plan_wrapper.get("shot_plan"), dict)):
            raise RuntimeError("FDA_INVALID_SHOT_PLAN: metadata.shot_plan must be wrapper {'shot_plan': {...}}")

        tts_pkg = md.get("tts_ready_package")
        if not isinstance(tts_pkg, dict):
            raise RuntimeError("FDA_INPUT_MISSING: metadata.tts_ready_package missing (expected for FDA_OUTPUT_VALIDATOR)")

        # v3 minimal gate only (no strict stylistic policing).
        from footage_director import validate_shot_plan_hard_gate
        validate_shot_plan_hard_gate(shot_plan_wrapper, tts_pkg, episode_id=episode_id)

        _mark_step_done(state, "fda_output_validator")
        store.write_script_state(episode_id, state)

    except Exception as e:
        msg = str(e)
        details = None
        # Try to parse JSON diagnostic from validator failures
        if msg.startswith("FDA_OUTPUT_VALIDATOR_FAIL:"):
            try:
                tail = msg.split("FDA_OUTPUT_VALIDATOR_FAIL:", 1)[1].strip()
                details = json.loads(tail) if tail else None
            except Exception:
                details = None

        _mark_step_error(state, "fda_output_validator", f"FDA_OUTPUT_VALIDATOR krok selhal: {msg}", details=details)
        store.write_script_state(episode_id, state)
        raise


def _run_asset_resolver(
    state: dict,
    episode_id: str,
    store: 'ProjectStore',
    cache_dir: str,
    skip_validation: bool = False,
) -> None:
    """
    Helper to run Archive Asset Resolver (AAR) step.
    
    Args:
        skip_validation: If True, skips FDA hard gate validation (for preview mode).
    """
    _ensure_step_exists(state, "asset_resolver")
    try:
        # Load shot plan wrapper (robust loader):
        # - preferred: state.metadata.shot_plan (canonical wrapper {'shot_plan': {...}})
        # - fallback: state.shot_plan (backward compat)
        # - fallback: state.footage_director_raw_output.shot_plan_saved
        # - fallback: episode files: steps/footage_director/output.json OR shot_plan.json
        md = state.get("metadata") if isinstance(state.get("metadata"), dict) else {}

        def _normalize_to_wrapper(obj: Any) -> Optional[dict]:
            # Accept: wrapper {'shot_plan': {...}}
            if isinstance(obj, dict) and isinstance(obj.get("shot_plan"), dict):
                return obj
            # Accept: raw shot_plan dict {'scenes': [...]}
            if isinstance(obj, dict) and isinstance(obj.get("scenes"), list):
                return {"shot_plan": obj}
            return None

        shot_plan_wrapper = _normalize_to_wrapper(md.get("shot_plan"))
        if not shot_plan_wrapper:
            shot_plan_wrapper = _normalize_to_wrapper(state.get("shot_plan"))
        if not shot_plan_wrapper:
            fdr = state.get("footage_director_raw_output")
            if isinstance(fdr, dict):
                shot_plan_wrapper = _normalize_to_wrapper(fdr.get("shot_plan_saved")) or _normalize_to_wrapper(fdr.get("response_json"))

        if not shot_plan_wrapper:
            episode_dir = store.episode_dir(episode_id)
            candidate_paths = [
                os.path.join(episode_dir, "steps", "footage_director", "output.json"),
                os.path.join(episode_dir, "steps", "footage_director", "shot_plan.json"),
                os.path.join(episode_dir, "shot_plan.json"),
            ]
            for p in candidate_paths:
                if not os.path.exists(p):
                    continue
                try:
                    with open(p, "r", encoding="utf-8") as f:
                        obj = json.load(f)
                    shot_plan_wrapper = _normalize_to_wrapper(obj)
                    if shot_plan_wrapper:
                        print(f"🔍 AAR: Loaded shot plan from file: {p}")
                        break
                except Exception as e:
                    print(f"⚠️  AAR: Failed to load shot plan from {p}: {e}")

        if not (isinstance(shot_plan_wrapper, dict) and isinstance(shot_plan_wrapper.get("shot_plan"), dict)):
            raise RuntimeError(
                "FDA_INVALID_SHOT_PLAN: shot plan wrapper missing. "
                "Expected wrapper {'shot_plan': {...}} in state.metadata.shot_plan or saved artifacts."
            )

        # Expected IDs source (canonical): metadata.tts_ready_package.narration_blocks[]
        tts_pkg = md.get("tts_ready_package") if isinstance(md.get("tts_ready_package"), dict) else state.get("tts_ready_package")
        if not isinstance(tts_pkg, dict):
            raise RuntimeError("FDA_INPUT_MISSING: tts_ready_package missing (expected for coverage gate)")

        # Hard gate validation (skip for preview mode - user wants quick results without fixing FDA errors)
        if not skip_validation:
            from footage_director import validate_shot_plan_hard_gate
            try:
                validate_shot_plan_hard_gate(shot_plan_wrapper, tts_pkg, episode_id=episode_id)
            except Exception as e:
                # Self-heal: in older runs we accidentally mutated metadata.shot_plan during AAR overrides.
                # If validation fails, try to reload a fresh shot plan from saved artifacts and validate that one.
                print(f"⚠️  AAR: FDA validation failed on current shot_plan wrapper, attempting recovery from artifacts: {e}")
                recovered = None
                episode_dir = store.episode_dir(episode_id)
                candidate_paths = [
                    os.path.join(episode_dir, "steps", "footage_director", "shot_plan.json"),
                    os.path.join(episode_dir, "steps", "footage_director", "output.json"),
                    os.path.join(episode_dir, "shot_plan.json"),
                ]
                for p in candidate_paths:
                    if not os.path.exists(p):
                        continue
                    try:
                        with open(p, "r", encoding="utf-8") as f:
                            obj = json.load(f)
                        cand = _normalize_to_wrapper(obj)
                        if not cand:
                            continue
                        validate_shot_plan_hard_gate(cand, tts_pkg, episode_id=episode_id)
                        recovered = cand
                        print(f"✅ AAR: Recovered valid shot plan from {p}")
                        break
                    except Exception:
                        continue
                if recovered:
                    shot_plan_wrapper = recovered
                else:
                    raise e
        else:
            print(f"⚠️  AAR: Skipping FDA validation (preview mode) - shot plan may have warnings")

        # IMPORTANT:
        # User overrides (user_search_queries / excluded_auto_queries) must NOT mutate the canonical shot_plan stored
        # in script_state.json. Otherwise later FDA validation (during full compile) will fail because we would
        # overwrite structured FDA-generated search_queries with plain strings.
        #
        # We therefore apply overrides on a deepcopy used only for AAR.
        import copy
        aar_shot_plan_wrapper = copy.deepcopy(shot_plan_wrapper)

        # UI override: user-provided search queries (global) to be included in AAR.
        # Stored in script_state.json as: user_search_queries: [str, ...]
        try:
            user_queries = state.get("user_search_queries")
            user_queries = user_queries if isinstance(user_queries, list) else []
            user_queries = [str(x).strip() for x in user_queries if str(x or "").strip()]
            # de-dupe (case-insensitive) while preserving order
            seen = set()
            uq: list = []
            for q in user_queries:
                qn = " ".join(q.split())
                key = qn.lower()
                if not qn or key in seen:
                    continue
                seen.add(key)
                uq.append(qn)

            if uq and isinstance(aar_shot_plan_wrapper, dict) and isinstance(aar_shot_plan_wrapper.get("shot_plan"), dict):
                sp = aar_shot_plan_wrapper.get("shot_plan") or {}
                scenes = sp.get("scenes") if isinstance(sp.get("scenes"), list) else []
                for sc in scenes:
                    if not isinstance(sc, dict):
                        continue
                    sq = sc.get("search_queries")
                    sq = sq if isinstance(sq, list) else []
                    # NOTE: For AAR we only need plain text queries. Structured objects are preserved in canonical shot_plan.
                    sq = [str(x.get("query")).strip() if isinstance(x, dict) else str(x).strip() for x in sq if str((x.get("query") if isinstance(x, dict) else x) or "").strip()]
                    # prepend user queries (high priority)
                    merged = uq + sq
                    # de-dupe merged
                    seen2 = set()
                    out = []
                    for x in merged:
                        xn = " ".join(str(x).split())
                        key2 = xn.lower()
                        if not xn or key2 in seen2:
                            continue
                        seen2.add(key2)
                        out.append(xn)
                    sc["search_queries"] = out
        except Exception as e:
            print(f"⚠️  AAR: Failed to apply user_search_queries overrides (AAR-only copy): {e}")

        # UI override: excluded auto queries (user clicked X on auto badge).
        # Stored in script_state.json as: excluded_auto_queries: [str, ...]
        # IMPORTANT: This must be applied BEFORE calling resolve_shot_plan_assets,
        # otherwise AAR will keep searching with excluded queries and the UI will feel broken.
        try:
            excluded_auto = state.get("excluded_auto_queries")
            excluded_auto = excluded_auto if isinstance(excluded_auto, list) else []
            excluded_auto_norm = []
            seen_ex = set()
            for q in excluded_auto:
                qn = " ".join(str(q or "").split()).strip()
                if not qn:
                    continue
                key = qn.lower()
                if key in seen_ex:
                    continue
                seen_ex.add(key)
                excluded_auto_norm.append(qn)
            excluded_set = {q.lower() for q in excluded_auto_norm}

            if excluded_set and isinstance(aar_shot_plan_wrapper, dict) and isinstance(aar_shot_plan_wrapper.get("shot_plan"), dict):
                sp = aar_shot_plan_wrapper.get("shot_plan") or {}
                scenes = sp.get("scenes") if isinstance(sp.get("scenes"), list) else []
                for sc in scenes:
                    if not isinstance(sc, dict):
                        continue
                    sq = sc.get("search_queries")
                    sq = sq if isinstance(sq, list) else []
                    sq_norm = [
                        " ".join(str((x.get("query") if isinstance(x, dict) else x) or "").split()).strip()
                        for x in sq
                        if str((x.get("query") if isinstance(x, dict) else x) or "").strip()
                    ]
                    filtered = [q for q in sq_norm if q.lower() not in excluded_set]
                    sc["search_queries"] = filtered
        except Exception as e:
            print(f"⚠️  AAR: Failed to apply excluded_auto_queries overrides (AAR-only copy): {e}")

        # Only now mark as RUNNING (safe: gate passed)
        _mark_step_running(state, "asset_resolver", "RUNNING_ASSET_RESOLVER")
        try:
            step = state.get("steps", {}).get("asset_resolver")
            if isinstance(step, dict):
                step["progress"] = 0
                step["message"] = "Hledám videa a obrázky na archive.org…"
        except Exception:
            pass
        store.write_script_state(episode_id, state)
        
        print(f"🔍 AAR: Starting asset resolution for episode {episode_id}...")
        
        # Manifest output path
        manifest_path = os.path.join(store.episode_dir(episode_id), "archive_manifest.json")
        voiceover_dir = os.path.join(store.episode_dir(episode_id), "voiceover")
        
        # Zavolej AAR - generuje manifest.
        # IMPORTANT: Local safety pack fallback is DISABLED by default because it can inject off-topic visuals
        # (random files from repo/images). Enable only with a curated pack.
        aar_warnings = []
        def _progress_cb(payload: dict) -> None:
            """
            Called from archive_asset_resolver during per-scene work.
            Writes lightweight progress to script_state for UI.
            """
            try:
                if not isinstance(payload, dict):
                    return
                si = int(payload.get("scene_index") or 0)
                st = int(payload.get("total_scenes") or 0)
                if st <= 0:
                    pct = 0
                else:
                    pct = max(0, min(100, int(round((si / st) * 100))))
                sid = str(payload.get("scene_id") or "").strip()

                latest = store.read_script_state(episode_id)
                steps = latest.get("steps")
                if not isinstance(steps, dict):
                    return
                ar = steps.get("asset_resolver")
                if not isinstance(ar, dict):
                    return
                ar["progress"] = pct
                ar["message"] = f"Hledám kandidáty pro scénu {si}/{st} ({sid})"
                latest["updated_at"] = _now_iso()
                store.write_script_state(episode_id, latest)
            except Exception:
                # best-effort; never break AAR
                return

        # Extract episode topic for LLM-based topic relevance validation (v14)
        # IMPORTANT: User "topic" can be sloppy / lowercased / too generic. Prefer a strong title when available.
        episode_input = state.get("episode_input") if isinstance(state.get("episode_input"), dict) else {}
        raw_topic = str(episode_input.get("topic") or "").strip()
        selected_title = str(state.get("selected_title") or "").strip()
        # Some states also store topic variants; prefer the most descriptive one.
        alt_topic = str(episode_input.get("title") or "").strip()

        episode_topic = raw_topic or None
        if episode_topic:
            # Heuristic: if topic is all-lowercase or very short, replace with selected_title (better anchor for LLM + search).
            if selected_title and (episode_topic == episode_topic.lower() or len(episode_topic.split()) < 3):
                episode_topic = selected_title
            elif alt_topic and (len(alt_topic.split()) >= len(episode_topic.split()) + 2):
                episode_topic = alt_topic
        elif selected_title:
            episode_topic = selected_title
        elif alt_topic:
            episode_topic = alt_topic

        if episode_topic:
            print(f"🎯 AAR: Episode topic for relevance validation: '{episode_topic}'")

        # #region agent log (hypothesis B/C)
        try:
            import time as _time
            import json as _json
            with open("/Users/petrliesner/podcasts/.cursor/debug.log", "a", encoding="utf-8") as _f:
                _f.write(_json.dumps({
                    "sessionId": "debug-session",
                    "runId": "run1",
                    "hypothesisId": "B",
                    "location": "backend/script_pipeline.py:_run_asset_resolver",
                    "message": "AAR resolver computed episode_topic + sources",
                    "data": {
                        "episode_id": episode_id,
                        "episode_input_topic": str(episode_input.get("topic") or ""),
                        "episode_input_title": str(episode_input.get("title") or ""),
                        "selected_title": str(selected_title or ""),
                        "episode_topic_final": str(episode_topic or ""),
                        "skip_validation": bool(skip_validation),
                    },
                    "timestamp": int(_time.time() * 1000),
                }) + "\n")
        except Exception:
            pass
        # #endregion
        
        try:
            manifest_dict, manifest_file_path = resolve_shot_plan_assets(
                aar_shot_plan_wrapper,
                cache_dir=cache_dir,
                manifest_output_path=manifest_path,
                throttle_delay_sec=0.2,  # Reduced from 0.5s for faster preview
                tts_ready_package=tts_pkg,
                voiceover_dir=voiceover_dir,
                episode_id=episode_id,
                progress_callback=_progress_cb,
                preview_mode=bool(skip_validation),
                episode_topic=episode_topic,  # v14: LLM topic relevance validation
            )
        except Exception as e:
            aar_warnings.append({"code": "AAR_FAILED", "message": str(e)})
            enable_local_pack = str(os.getenv("AAR_ENABLE_LOCAL_SAFETY_PACK", "0")).strip().lower() in ("1", "true", "yes")

            # If disabled, fail fast with a clear error (UI can retry after fixing queries/network).
            if not enable_local_pack:
                raise RuntimeError(f"AAR_FAILED_NO_FALLBACK: {e}")

            # Minimal deterministic manifest that CB can render without network (curated safety pack only).
            from local_safety_pack import make_local_fallback_asset
            from datetime import datetime, timezone

            def _now_iso_local() -> str:
                return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

            sp = shot_plan_wrapper.get("shot_plan") if isinstance(shot_plan_wrapper, dict) else None
            sp = sp if isinstance(sp, dict) else {}
            scenes = sp.get("scenes") if isinstance(sp.get("scenes"), list) else []

            fb_manifest = {
                "version": "archive_manifest_v2",
                "generated_at": _now_iso_local(),
                "episode_id": episode_id,
                "source_shot_plan": {
                    "total_scenes": len(scenes),
                    "total_duration_sec": scenes[-1].get("end_sec", 0) if scenes else 0,
                },
                "compile_plan": {
                    "target_fps": 30,
                    "resolution": "1920x1080",
                    "music": "none",
                    "transitions_allowed": ["hard_cut", "fade"],
                    "max_clip_repeat_sec": 0,
                    "caption_style": "none",
                    "subclip_policy": {
                        "min_in_sec": 30,
                        "avoid_ranges": [[0, 30]],
                        "reason": "Skip title cards, logos, credits commonly found in first 30s of archive videos",
                    },
                },
                "scenes": [],
            }

            for sc in scenes:
                if not isinstance(sc, dict):
                    continue
                sid = str(sc.get("scene_id") or "unknown")
                block_ids = sc.get("narration_block_ids") if isinstance(sc.get("narration_block_ids"), list) else []
                block_ids = [str(x) for x in block_ids if str(x or "").strip()]

                assets = []
                beats = []
                for bid in block_ids:
                    fb = make_local_fallback_asset(scene_id=sid, block_id=bid, reason="AAR_FAILED")
                    if fb:
                        assets.append(fb)
                        beats.append(
                            {
                                "block_id": bid,
                                "block_index": None,
                                "text_preview": None,
                                "target_duration_sec": None,
                                "keywords": [],
                                "asset_candidates": [
                                    {
                                        "archive_item_id": fb.get("archive_item_id"),
                                        "score": 0.01,
                                        "priority": fb.get("priority", 99),
                                        "media_type": fb.get("media_type"),
                                        "query_used": "local_safety_pack",
                                        "debug": {"gate_result": "FALLBACK"},
                                    }
                                ],
                                "fallback_used": True,
                            }
                        )
                    else:
                        beats.append({"block_id": bid, "asset_candidates": [], "fallback_used": True})

                fb_manifest["scenes"].append(
                    {
                        "scene_id": sid,
                        "start_sec": sc.get("start_sec", 0),
                        "end_sec": sc.get("end_sec", 0),
                        "emotion": sc.get("emotion"),
                        "narration_block_ids": block_ids,
                        "visual_beats": beats,
                        "search_queries": sc.get("search_queries", []) if isinstance(sc.get("search_queries"), list) else [],
                        "assets": assets,
                        "primary_assets": [],
                        "secondary_assets": [],
                        "fallback_assets": assets,
                        "resolve_diagnostics": {
                            "queries_attempted": [],
                            "reject_reasons_summary": {},
                            "total_candidates_found": 0,
                            "used_global_fallback": True,
                            "reason": "AAR_FAILED",
                        },
                    }
                )

            os.makedirs(os.path.dirname(manifest_path), exist_ok=True)
            with open(manifest_path, "w", encoding="utf-8") as f:
                json.dump(fb_manifest, f, ensure_ascii=False, indent=2)
            manifest_dict, manifest_file_path = fb_manifest, manifest_path
        
        # Ulož manifest path do state
        state["archive_manifest_path"] = manifest_file_path
        
        # Calculate per-scene stats for diagnostics
        scenes_list = manifest_dict.get("scenes", [])
        scenes_with_assets = sum(1 for sc in scenes_list if len(sc.get("assets", [])) > 0)
        scenes_without_assets = sum(1 for sc in scenes_list if len(sc.get("assets", [])) == 0)
        
        # Collect unresolved scene diagnostics for UI
        unresolved_scenes_diag = []
        for sc in scenes_list:
            if len(sc.get("assets", [])) == 0:
                diag = sc.get("resolve_diagnostics", {})
                unresolved_scenes_diag.append({
                    "scene_id": sc.get("scene_id"),
                    "queries_attempted": diag.get("queries_attempted", [])[:5],
                    "reject_reasons_summary": diag.get("reject_reasons_summary", {}),
                    "used_global_fallback": diag.get("used_global_fallback", False),
                })
        
        state["asset_resolver_output"] = {
            "manifest_path": manifest_file_path,
            "total_scenes": len(scenes_list),
            "total_assets_resolved": sum(
                len(scene.get("assets", []))
                for scene in scenes_list
            ),
            "scenes_with_assets": scenes_with_assets,
            "scenes_without_assets": scenes_without_assets,
            "unresolved_scenes": unresolved_scenes_diag[:10],  # Limit for UI
            "generated_at": manifest_dict.get("generated_at", "")
        }

        # Transparency counters (avoid "UI says 20 but progress says 50"):
        # - total_assets_resolved = number of ASSET ASSIGNMENTS across scenes (can reuse same asset many times)
        # - pool_selected_* = unique assets selected into episode pool
        # - pool_unique_* = unique ranked assets after dedup/ranking
        # - pool_raw_* = raw candidates before dedup
        try:
            ep_pool = manifest_dict.get("episode_pool") if isinstance(manifest_dict, dict) else None
            if isinstance(ep_pool, dict):
                raw = ep_pool.get("raw_candidates") if isinstance(ep_pool.get("raw_candidates"), dict) else {}
                uniq = ep_pool.get("unique_ranked") if isinstance(ep_pool.get("unique_ranked"), dict) else {}
                sel = ep_pool.get("selected_ranked") if isinstance(ep_pool.get("selected_ranked"), dict) else {}

                raw_v = raw.get("videos") if isinstance(raw.get("videos"), list) else []
                raw_i = raw.get("images") if isinstance(raw.get("images"), list) else []
                uniq_v = uniq.get("videos") if isinstance(uniq.get("videos"), list) else []
                uniq_i = uniq.get("images") if isinstance(uniq.get("images"), list) else []
                sel_v = sel.get("videos") if isinstance(sel.get("videos"), list) else []
                sel_i = sel.get("images") if isinstance(sel.get("images"), list) else []

                state["asset_resolver_output"].update(
                    {
                        # Prefer explicit lists; fallback to stored counters if lists not present
                        "pool_selected_total_assets": (len(sel_v) + len(sel_i)) if (sel_v or sel_i) else int(ep_pool.get("videos_count", 0) or 0) + int(ep_pool.get("images_count", 0) or 0),
                        "pool_selected_videos": len(sel_v) if sel_v else int(ep_pool.get("videos_count", 0) or 0),
                        "pool_selected_images": len(sel_i) if sel_i else int(ep_pool.get("images_count", 0) or 0),
                        "pool_unique_total_assets": len(uniq_v) + len(uniq_i),
                        "pool_unique_videos": len(uniq_v),
                        "pool_unique_images": len(uniq_i),
                        "pool_raw_total_assets": len(raw_v) + len(raw_i),
                        "pool_raw_videos": len(raw_v),
                        "pool_raw_images": len(raw_i),
                    }
                )
        except Exception:
            pass

        # Persist warnings for UI ("DONE + WARNINGS")
        if aar_warnings:
            try:
                state.setdefault("pipeline_warnings", [])
                if isinstance(state.get("pipeline_warnings"), list):
                    state["pipeline_warnings"].extend(aar_warnings[:200])
                step_obj = ((state.get("steps") or {}).get("asset_resolver") or {})
                step_obj["warnings"] = aar_warnings[:200]
                (state.get("steps") or {})["asset_resolver"] = step_obj
            except Exception:
                pass
        
        _mark_step_done(state, "asset_resolver")
        state["updated_at"] = _now_iso()
        store.write_script_state(episode_id, state)
        
        total_assets = state["asset_resolver_output"]["total_assets_resolved"]
        print(f"✅ AAR: Resolved {total_assets} assets, manifest saved to {manifest_file_path}")
        
    except Exception as e:
        # Never-fail policy: any failure here should already have been converted into a local-fallback manifest.
        err = str(e)
        print(f"❌ AAR FAILED (unexpected): {err}")
        _mark_step_error(state, "asset_resolver", err, details=getattr(e, "details", None))
        store.write_script_state(episode_id, state)
        raise


def _run_compilation_builder(
    state: dict,
    episode_id: str,
    store: 'ProjectStore',
    storage_dir: str,
    output_dir: str,
) -> None:
    """Helper to run Compilation Builder (CB) step."""
    _ensure_step_exists(state, "compilation_builder")
    _mark_step_running(state, "compilation_builder", "RUNNING_COMPILATION_BUILDER")
    store.write_script_state(episode_id, state)
    
    # Progress tracking - ukládá se do state pro polling z frontendu
    last_progress_write = [0.0]  # Use list to allow mutation in closure
    
    def progress_callback(update: dict):
        """Callback pro real-time progress updates od CB."""
        import time as _time
        now = _time.time()
        # Rate-limit writes to every 1 second to avoid disk thrashing
        if now - last_progress_write[0] < 1.0:
            return
        last_progress_write[0] = now
        
        # Update state with progress
        state["compilation_progress"] = {
            "phase": update.get("phase", "unknown"),
            "message": update.get("message", ""),
            "percent": update.get("percent", 0),
            "details": update.get("details", {}),
            "updated_at": _now_iso(),
        }
        state["updated_at"] = _now_iso()
        try:
            store.write_script_state(episode_id, state)
        except Exception as e:
            print(f"⚠️  Progress write failed: {e}")
    
    try:
        if not state.get("archive_manifest_path"):
            raise RuntimeError("Compilation Builder: archive_manifest_path is missing")
        
        manifest_path = state["archive_manifest_path"]
        if not os.path.exists(manifest_path):
            raise RuntimeError(f"Compilation Builder: manifest file not found: {manifest_path}")
        
        print(f"🎬 CB: Starting video compilation for episode {episode_id}...")
        print(f"   - Reading manifest: {manifest_path}")
        
        # Zavolej CB - čte manifest s progress callback
        output_video, metadata = build_episode_compilation(
            manifest_path=manifest_path,
            episode_id=episode_id,
            storage_dir=storage_dir,
            output_dir=output_dir,
            target_duration_sec=None,  # Vezme z scenes
            progress_callback=progress_callback
        )
        
        if output_video is None:
            # Persist full diagnostics (including ffmpeg stderr snippets) into step.error.details
            err_msg = f"Compilation Builder krok selhal: Compilation failed: {metadata.get('error', 'Unknown error')}"
            _mark_step_error(state, "compilation_builder", err_msg, details=metadata)
            store.write_script_state(episode_id, state)
            raise RuntimeError(f"Compilation failed: {metadata.get('error', 'Unknown error')}")
        
        # Ulož výsledky
        state["compilation_video_path"] = output_video
        state["compilation_builder_output"] = metadata
        
        _mark_step_done(state, "compilation_builder")
        state["script_status"] = "DONE"
        state["updated_at"] = _now_iso()
        store.write_script_state(episode_id, state)
        
        print(f"✅ CB: Compilation complete → {output_video}")
        print(f"   - Clips used: {metadata.get('clips_used', 0)}")
        print(f"   - File size: {metadata.get('output_size_bytes', 0) / (1024*1024):.1f} MB")
        
    except Exception as e:
        # Avoid overwriting a richer error already stored above (with details).
        try:
            step = (state.get("steps") or {}).get("compilation_builder") or {}
            already_error = step.get("status") == "ERROR" and step.get("error")
        except Exception:
            already_error = False

        if not already_error:
            _mark_step_error(state, "compilation_builder", f"Compilation Builder krok selhal: {str(e)}")
            store.write_script_state(episode_id, state)
        raise


def _step_config_for(state: dict, step_key: str) -> dict:
    if step_key == "research":
        return state.get("research_config") or _default_step_config("research")
    if step_key == "narrative":
        return state.get("narrative_config") or _default_step_config("narrative")
    if step_key == "validation":
        return state.get("validator_config") or _default_step_config("validation")
    if step_key == "tts_format":
        return state.get("tts_format_config") or _default_step_config("tts_format")
    if step_key == "footage_director":
        cfg = state.get("footage_director_config") or _default_step_config("footage_director")
        # FDA defaults: gpt-4o-mini, temp 0.2
        if not cfg.get("model"):
            cfg["model"] = "gpt-4o-mini"
        if "temperature" not in cfg:
            cfg["temperature"] = 0.2
        return cfg
    return _default_step_config(step_key)


def _write_raw_output(
    state: dict,
    step_key: str,
    raw_text: str,
    parsed_json: Optional[dict],
    prompt_template: str,
    prompt_used: str,
    meta: Optional[dict] = None,
) -> None:
    config = _step_config_for(state, step_key)
    raw_obj = {
        "provider": config.get("provider", "openai"),
        "model": config.get("model", "gpt-4o"),
        "temperature": config.get("temperature", 0.4),
        "timestamp": _now_iso(),
        "prompt_template": prompt_template,
        "prompt_used": prompt_used,
        "response_text": raw_text,
        "response_json": parsed_json,
    }
    if isinstance(meta, dict) and meta:
        raw_obj["provider_meta"] = meta
    if step_key == "research":
        state["research_raw_output"] = raw_obj
    elif step_key == "narrative":
        state["narrative_raw_output"] = raw_obj
    elif step_key == "validation":
        state["validation_raw_output"] = raw_obj
    elif step_key == "tts_format":
        state["tts_format_raw_output"] = raw_obj


def _write_raw_output_fda(
    state: dict,
    raw_text: str,
    response_json: Optional[dict],
    metadata: dict,
) -> None:
    """Helper pro ukládání FDA raw output (má jiný formát než ostatní LLM kroky)"""
    state["footage_director_raw_output"] = {
        "provider": metadata.get("provider", "openai"),
        "model": metadata.get("model", "gpt-4o-mini"),
        "temperature": metadata.get("temperature", 0.2),
        "timestamp": metadata.get("timestamp", _now_iso()),
        "prompt_used": metadata.get("prompt_used", ""),
        "response_text": raw_text,
        "response_json": response_json,
        # Filled later (after deterministic fix + hard gate)
        "shot_plan_saved": None,
        "validation_errors": None,
        "auto_fixed": False,
        "llm_meta": metadata.get("llm_meta", {}),
    }


class ScriptPipelineService:
    """
    Orchestrates the 4-step pipeline with FS persistence and checkpointing.
    """

    def __init__(self, store: ProjectStore):
        self.store = store
        # Global pipeline lock (single pipeline at a time).
        # Uses OS file lock so parallel requests cannot run concurrent pipelines.
        self._lock_guard = threading.Lock()
        self._lock_acquired_at = None  # timestamp when lock was acquired
        self._lockfile_path = os.path.join(self.store.base_projects_dir, ".pipeline.lock")
        self._lockfile_fd: Optional[object] = None

    def start_pipeline_async(
        self,
        topic: str,
        language: str,
        target_minutes: Optional[int],
        channel_profile: Optional[str],
        provider_api_keys: dict,
        research_config: Optional[dict] = None,
        narrative_config: Optional[dict] = None,
        validator_config: Optional[dict] = None,
        tts_format_config: Optional[dict] = None,
        footage_director_config: Optional[dict] = None,
    ) -> str:
        # Před startem zkontroluj a uvolni stale lock (pokud žádný step neběží)
        self._check_and_force_unlock_if_no_running_steps()

        # Fail fast: if another pipeline is running, do NOT create an ERROR episode.
        # This prevents confusing "new episode immediately ERROR" states in the UI.
        if not self._try_acquire_lock():
            raise RuntimeError("PIPELINE_BUSY: Jiný Script pipeline právě běží (paralelní generování je zakázáno).")
        
        try:
            episode_id = f"ep_{uuid.uuid4().hex[:12]}"
            state = _make_initial_state(episode_id)
            state["episode_input"] = {
                "topic": topic,
                "language": language,
                "target_minutes": target_minutes,
                "channel_profile": channel_profile,
            }
            # Override configs (stored per episode for reproducibility)
            if isinstance(research_config, dict):
                state["research_config"] = {**state["research_config"], **research_config}
            if isinstance(narrative_config, dict):
                state["narrative_config"] = {**state["narrative_config"], **narrative_config}
            if isinstance(validator_config, dict):
                state["validator_config"] = {**state["validator_config"], **validator_config}
            if isinstance(tts_format_config, dict):
                state["tts_format_config"] = {**state["tts_format_config"], **tts_format_config}
            if isinstance(footage_director_config, dict):
                # Per-episode FDA config (provider/model/temp/template) for reproducibility
                state["footage_director_config"] = {**(state.get("footage_director_config") or {}), **footage_director_config}
            # Make state immediately reflect the first running stage for UI polling.
            _mark_step_running(state, "research", "RUNNING_RESEARCH")
            self.store.write_script_state(episode_id, state)

            t = threading.Thread(
                target=self._run_pipeline_thread_locked,
                args=(episode_id, topic, language, target_minutes, channel_profile, provider_api_keys),
                daemon=True,
            )
            t.start()
            return episode_id
        except Exception:
            # If anything goes wrong after acquiring the lock, ensure it is released.
            self._release_lock()
            raise

    def _run_pipeline_thread_locked(
        self,
        episode_id: str,
        topic: str,
        language: str,
        target_minutes: Optional[int],
        channel_profile: Optional[str],
        provider_api_keys: dict,
    ) -> None:
        """
        Pipeline runner when lock is already acquired by start_pipeline_async().
        Ensures lock is always released at the end.
        """
        try:
            self._run_pipeline(episode_id, topic, language, target_minutes, channel_profile, provider_api_keys)
        except Exception as e:
            try:
                state = self.store.read_script_state(episode_id)
                _mark_step_error(state, "composer", f"Neočekávaná chyba pipeline: {str(e)}")
                self.store.write_script_state(episode_id, state)
            except Exception:
                pass
        finally:
            self._release_lock()

    def _try_acquire_lock(self) -> bool:
        """
        Pokusí se získat lock a zaznamenat čas získání.
        Vrací True pokud se podařilo získat lock, False jinak.
        """
        with self._lock_guard:
            if self._lockfile_fd is not None:
                return False  # already held in this process
            if not _FCNTL_AVAILABLE:
                return False
            try:
                os.makedirs(self.store.base_projects_dir, exist_ok=True)
                fd = open(self._lockfile_path, "a+")
                try:
                    fcntl.flock(fd.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)  # type: ignore[attr-defined]
                except Exception:
                    try:
                        fd.close()
                    except Exception:
                        pass
                    return False
                self._lockfile_fd = fd
                self._lock_acquired_at = time.time()
                return True
            except Exception:
                return False
    
    def _release_lock(self) -> None:
        """
        Uvolní lock a vymaže tracking.
        """
        with self._lock_guard:
            try:
                if self._lockfile_fd is not None and _FCNTL_AVAILABLE:
                    try:
                        fcntl.flock(self._lockfile_fd.fileno(), fcntl.LOCK_UN)  # type: ignore[attr-defined]
                    except Exception:
                        pass
                    try:
                        self._lockfile_fd.close()
                    except Exception:
                        pass
                self._lockfile_fd = None
                self._lock_acquired_at = None
            except Exception:
                self._lockfile_fd = None
                self._lock_acquired_at = None
    
    def _force_unlock_if_stale(self, max_age_seconds: int = 3600) -> bool:
        """
        Pokud je lock zamčený déle než max_age_seconds, force unlock.
        POZOR: Tato metoda je bezpečná pouze pokud víme, že žádný step neběží.
        Vrací True pokud byl lock uvolněn, False pokud není zamčený nebo je čerstvý.
        """
        with self._lock_guard:
            if self._lock_acquired_at is None:
                return False  # Lock není zamčený
            
            age = time.time() - self._lock_acquired_at
            if age > max_age_seconds:
                # For file lock, we can only safely unlock if caller ensured nothing is running.
                # Best-effort: release our own held lock (if any).
                if self._lockfile_fd is not None:
                    try:
                        self._release_lock()
                        return True
                    except Exception:
                        return False
            return False
    
    def _check_and_force_unlock_if_no_running_steps(self) -> bool:
        """
        Zkontroluje, zda nějaký step je RUNNING. Pokud ne, force unlock.
        Používá se při resetu - pokud žádný step neběží, lock by měl být volný.
        """
        # Zkontroluj všechny projekty, zda nějaký step je RUNNING
        try:
            projects_dir = self.store.base_projects_dir
            if not os.path.exists(projects_dir):
                # Pokud projects_dir neexistuje, zkusíme uvolnit lock (pravděpodobně je stale)
                return self._force_unlock_if_stale(max_age_seconds=0)
            
            script_state_files = glob.glob(os.path.join(projects_dir, "ep_*/script_state.json"))
            
            for state_file in script_state_files:
                try:
                    with open(state_file, 'r', encoding='utf-8') as f:
                        state = json.load(f)
                    
                    steps = state.get("steps", {})
                    for step_key, step_data in steps.items():
                        if step_data.get("status") == "RUNNING":
                            # Nějaký step běží, lock by měl zůstat zamčený
                            return False
                except Exception:
                    continue
            
            # Žádný step neběží - můžeme force unlock
            with self._lock_guard:
                if self._lock_acquired_at is not None:
                    # Best-effort: release our held lock (if any).
                    try:
                        self._release_lock()
                        return True
                    except Exception:
                        return False
            return False
        except Exception:
            return False

    def _run_pipeline_thread(
        self,
        episode_id: str,
        topic: str,
        language: str,
        target_minutes: Optional[int],
        channel_profile: Optional[str],
        provider_api_keys: dict,
    ) -> None:
        # Před získáním locku zkontroluj, zda není starý
        self._force_unlock_if_stale(max_age_seconds=3600)  # 1 hodina
        
        if not self._try_acquire_lock():
            # Another script pipeline is running; mark this episode as ERROR.
            state = self.store.read_script_state(episode_id)
            _mark_step_error(state, "research", "Jiný Script pipeline právě běží (paralelní generování je zakázáno).")
            self.store.write_script_state(episode_id, state)
            return

        try:
            self._run_pipeline(episode_id, topic, language, target_minutes, channel_profile, provider_api_keys)
        except Exception as e:
            try:
                state = self.store.read_script_state(episode_id)
                _mark_step_error(state, "composer", f"Neočekávaná chyba pipeline: {str(e)}")
                self.store.write_script_state(episode_id, state)
            except Exception:
                pass
        finally:
            self._release_lock()

    def _run_pipeline(
        self,
        episode_id: str,
        topic: str,
        language: str,
        target_minutes: Optional[int],
        channel_profile: Optional[str],
        provider_api_keys: dict,
    ) -> None:
        state = self.store.read_script_state(episode_id)

        # 1) Research
        if state["steps"]["research"]["status"] != "RUNNING":
            _mark_step_running(state, "research", "RUNNING_RESEARCH")
            self.store.write_script_state(episode_id, state)
        try:
            cfg = _step_config_for(state, "research")
            provider = _safe_str(cfg.get("provider")).strip().lower()
            if not provider:
                raise RuntimeError("Research: config.provider is missing")
            model = _safe_str(cfg.get("model")).strip()
            if not model:
                raise RuntimeError("Research: config.model is missing")
            api_key = _safe_str((provider_api_keys or {}).get(provider)).strip()
            if not api_key:
                raise RuntimeError(f"Chybí API key pro provider '{provider}' (Research)")
            prompt_template, prompt_used = _apply_step_prompt("research", state, topic, language, target_minutes, channel_profile, None)
            raw_text, parsed, meta = _llm_chat_json_raw(
                provider,
                prompt_used,
                api_key,
                model=model,
                temperature=float(cfg.get("temperature", 0.4)),
            )
            _write_raw_output(state, "research", raw_text, parsed, prompt_template, prompt_used, meta=meta)
            self.store.write_script_state(episode_id, state)
            if parsed is None:
                fr = (meta or {}).get("finish_reason")
                src = (meta or {}).get("response_text_source")
                raise RuntimeError(f"Research: LLM vrátil nevalidní JSON (source={src}, finish_reason={fr})")
            research = _normalize_research_report(parsed)
            state["research_report"] = research
            _mark_step_done(state, "research")
            self.store.write_script_state(episode_id, state)
        except Exception as e:
            _mark_step_error(state, "research", f"Research krok selhal: {str(e)}")
            self.store.write_script_state(episode_id, state)
            return

        # 2) Narrative (attempt 1)
        for attempt_index in range(2):  # max 2 attempts total
            _mark_step_running(state, "narrative", "RUNNING_NARRATIVE")
            self.store.write_script_state(episode_id, state)
            patch = None
            if attempt_index == 1:
                # Retry uses patch_instructions from previous validation_result
                patch = _safe_str((state.get("validation_result") or {}).get("patch_instructions")).strip() or None
            try:
                cfg = _step_config_for(state, "narrative")
                provider = _safe_str(cfg.get("provider")).strip().lower()
                if not provider:
                    raise RuntimeError("Narrative: config.provider is missing")
                model = _safe_str(cfg.get("model")).strip()
                if not model:
                    raise RuntimeError("Narrative: config.model is missing")
                api_key = _safe_str((provider_api_keys or {}).get(provider)).strip()
                if not api_key:
                    raise RuntimeError(f"Chybí API key pro provider '{provider}' (Narrative)")
                prompt_template, prompt_used = _apply_step_prompt("narrative", state, topic, language, target_minutes, channel_profile, patch)
                raw_text, parsed, meta = _llm_chat_json_raw(
                    provider,
                    prompt_used,
                    api_key,
                    model=model,
                    temperature=float(cfg.get("temperature", 0.4)),
                )
                _write_raw_output(state, "narrative", raw_text, parsed, prompt_template, prompt_used, meta=meta)
                self.store.write_script_state(episode_id, state)
                if parsed is None:
                    fr = (meta or {}).get("finish_reason")
                    src = (meta or {}).get("response_text_source")
                    raise RuntimeError(f"Narrative: LLM vrátil nevalidní JSON (source={src}, finish_reason={fr})")
                draft = _normalize_draft_script(parsed)
                # Deterministic safety net for common Validation FAIL patterns (preface/hook)
                draft = _sanitize_narrative_preface_and_hook(draft, state.get("research_report") or {})
                state["draft_script"] = draft
                # attempts.narrative counts completed narrative runs (starts at 0)
                state["attempts"]["narrative"] = int(state["attempts"].get("narrative", 0)) + 1
                _mark_step_done(state, "narrative")
                self.store.write_script_state(episode_id, state)
            except Exception as e:
                _mark_step_error(state, "narrative", f"Narrative krok selhal: {str(e)}")
                self.store.write_script_state(episode_id, state)
                return

            # 3) Validation
            _mark_step_running(state, "validation", "RUNNING_VALIDATION")
            self.store.write_script_state(episode_id, state)
            try:
                cfg = _step_config_for(state, "validation")
                provider = _safe_str(cfg.get("provider")).strip().lower()
                if not provider:
                    raise RuntimeError("Validation: config.provider is missing")
                model = _safe_str(cfg.get("model")).strip()
                if not model:
                    raise RuntimeError("Validation: config.model is missing")
                api_key = _safe_str((provider_api_keys or {}).get(provider)).strip()
                if not api_key:
                    raise RuntimeError(f"Chybí API key pro provider '{provider}' (Validation)")
                prompt_template, prompt_used = _apply_step_prompt("validation", state, topic, language, target_minutes, channel_profile, None)
                raw_text, parsed, meta = _llm_chat_json_raw(
                    provider,
                    prompt_used,
                    api_key,
                    model=model,
                    temperature=float(cfg.get("temperature", 0.4)),
                )
                _write_raw_output(state, "validation", raw_text, parsed, prompt_template, prompt_used, meta=meta)
                self.store.write_script_state(episode_id, state)
                if parsed is None:
                    fr = (meta or {}).get("finish_reason")
                    src = (meta or {}).get("response_text_source")
                    raise RuntimeError(f"Validation: LLM vrátil nevalidní JSON (source={src}, finish_reason={fr})")
                validation = _normalize_validation_result(parsed)
                state["validation_result"] = validation
                _mark_step_done(state, "validation")
                self.store.write_script_state(episode_id, state)
            except Exception as e:
                _mark_step_error(state, "validation", f"Validation krok selhal: {str(e)}")
                self.store.write_script_state(episode_id, state)
                return

            if state["validation_result"]["status"] == "PASS":
                break

            # FAIL
            if attempt_index == 0:
                # Allow one retry of Narrative
                continue

            # FAIL twice -> ERROR (manual review)
            state["script_status"] = "ERROR"
            state["updated_at"] = _now_iso()
            self.store.write_script_state(episode_id, state)
            return

        # Ensure PASS before composing
        if not state.get("validation_result") or state["validation_result"].get("status") != "PASS":
            state["script_status"] = "ERROR"
            state["updated_at"] = _now_iso()
            self.store.write_script_state(episode_id, state)
            return

        # 4) Composer (deterministic)
        _mark_step_running(state, "composer", "RUNNING_COMPOSER")
        self.store.write_script_state(episode_id, state)
        try:
            package = _deterministic_compose(
                episode_id=episode_id,
                language=language,
                target_minutes=target_minutes,
                channel_profile=channel_profile,
                research_report=state["research_report"],
                draft_script=state["draft_script"],
                validation_result=state["validation_result"],
            )
            state["script_package"] = package
            _mark_step_done(state, "composer")
            self.store.write_script_state(episode_id, state)
        except Exception as e:
            _mark_step_error(state, "composer", f"Composer krok selhal: {str(e)}")
            self.store.write_script_state(episode_id, state)
            return

        # 5) TTS Formatting (LLM)
        try:
            _run_tts_formatting(state, episode_id, topic, language, target_minutes, channel_profile, provider_api_keys, self.store)
        except Exception:
            # Error already written by helper
            return

        # 6) Footage Director Assistant (FDA) - LLM-assisted shot planning
        try:
            _run_footage_director(state, episode_id, topic, language, target_minutes, channel_profile, provider_api_keys, self.store)
        except Exception:
            # Error already written by helper
            return

        # 6b) FDA_OUTPUT_VALIDATOR - deterministic checkpoint before AAR
        try:
            _run_fda_output_validator(state, episode_id, self.store)
        except Exception:
            # Error already written by helper
            return
        
        # 7) Archive Asset Resolver (AAR) - resolve archive.org assets
        try:
            cache_dir = os.path.join(self.store.episode_dir(episode_id), "archive_cache")
            _run_asset_resolver(state, episode_id, self.store, cache_dir)
        except Exception:
            # Error already written by helper
            return
        
        # 8) Compilation Builder (CB) - download + compile video
        try:
            storage_dir = os.path.join(self.store.episode_dir(episode_id), "assets")
            output_dir = os.path.join(self.store.base_projects_dir, "..", "output")
            _run_compilation_builder(state, episode_id, self.store, storage_dir, output_dir)
        except Exception:
            # Error already written by helper
            return

    def retry_step_async(
        self,
        episode_id: str,
        step_key: str,
        provider_api_keys: dict,
    ) -> bool:
        """
        Retry a single step (research, narrative, validation, composer, tts_format, footage_director, asset_resolver, compilation_builder).
        - By default: only ERROR steps are retryable.
        - Additionally:
          - validation is retryable when DONE but ValidationResult.status=FAIL
          - narrative is retryable when DONE but ValidationResult.status=FAIL and attempts.narrative < 2
        Returns True if retry was started, False if retry not allowed (wrong status).
        """
        if step_key not in ("research", "narrative", "validation", "composer", "tts_format", "footage_director", "asset_resolver", "compilation_builder"):
            return False

        state = self.store.read_script_state(episode_id)
        # Backward compatibility: ensure new step exists for old episodes before accessing state["steps"][...]
        if step_key == "footage_director":
            _ensure_step_exists(state, "footage_director")
            # Ensure storage fields exist (non-breaking)
            if "shot_plan" not in state:
                state["shot_plan"] = None
            if "footage_director_raw_output" not in state:
                state["footage_director_raw_output"] = None
            self.store.write_script_state(episode_id, state)
        val_result = state.get("validation_result") or {}
        val_status = state.get("steps", {}).get("validation", {}).get("status")
        narrative_attempts = int((state.get("attempts") or {}).get("narrative", 0))

        # Determine retry eligibility (no implicit fallbacks)
        if step_key == "validation":
            if state["steps"]["validation"]["status"] != "ERROR":
                if not (val_status == "DONE" and val_result.get("status") == "FAIL"):
                    return False
        elif step_key == "narrative":
            if state["steps"]["narrative"]["status"] != "ERROR":
                # Allow narrative retry if validation FAILED and we still have retry budget
                if not (val_status == "DONE" and val_result.get("status") == "FAIL" and narrative_attempts < 2):
                    return False
        else:
            if state["steps"][step_key]["status"] != "ERROR":
                return False

        # Extract context deterministically (no invented defaults).
        # Prefer episode_input (new episodes). For legacy episodes without episode_input, derive from existing research_report.
        ep_in = state.get("episode_input") or {}
        rr = state.get("research_report") or {}

        topic = _safe_str(ep_in.get("topic") or rr.get("topic")).strip()
        if not topic:
            _mark_step_error(state, step_key, "Cannot retry: topic is missing (episode_input.topic / research_report.topic)")
            self.store.write_script_state(episode_id, state)
            return False

        language = _safe_str(ep_in.get("language") or rr.get("language")).strip()
        if not language:
            _mark_step_error(state, step_key, "Cannot retry: language is missing (episode_input.language / research_report.language)")
            self.store.write_script_state(episode_id, state)
            return False

        # target_minutes and channel_profile are optional and may be None (no defaults)
        target_minutes = ep_in.get("target_minutes", None)
        channel_profile = ep_in.get("channel_profile", None)

        # If episode_input is missing (legacy), store the deterministically derived inputs for future retries/audit.
        if not state.get("episode_input"):
            state["episode_input"] = {
                "topic": topic,
                "language": language,
                "target_minutes": target_minutes,
                "channel_profile": channel_profile,
            }

        # Reset the step and downstream dependencies to IDLE (deterministic, no guessing)
        def _reset_step(k: str) -> None:
            state["steps"][k]["status"] = "IDLE"
            state["steps"][k]["started_at"] = None
            state["steps"][k]["finished_at"] = None
            state["steps"][k]["error"] = None

        if step_key == "research":
            _reset_step("research")
            _reset_step("narrative")
            _reset_step("validation")
            _reset_step("composer")
            state["research_report"] = None
            state["draft_script"] = None
            state["validation_result"] = None
            state["script_package"] = None
            state["research_raw_output"] = None
            state["narrative_raw_output"] = None
            state["validation_raw_output"] = None
            state["attempts"]["narrative"] = 0
        elif step_key == "narrative":
            _reset_step("narrative")
            _reset_step("validation")
            _reset_step("composer")
            state["draft_script"] = None
            state["validation_result"] = None
            state["script_package"] = None
        elif step_key == "validation":
            _reset_step("validation")
            _reset_step("composer")
            state["validation_result"] = None
            state["script_package"] = None
        elif step_key == "composer":
            _reset_step("composer")
            state["script_package"] = None
        elif step_key == "asset_resolver":
            _reset_step("asset_resolver")
            _reset_step("compilation_builder")
            state["archive_manifest_path"] = None
            state["compilation_video_path"] = None
        elif step_key == "compilation_builder":
            _reset_step("compilation_builder")
            state["compilation_video_path"] = None

        state["script_status"] = "IDLE"
        state["updated_at"] = _now_iso()
        self.store.write_script_state(episode_id, state)

        # Start thread to re-run from this step
        t = threading.Thread(
            target=self._retry_step_thread,
            args=(episode_id, step_key, topic, language, target_minutes, channel_profile, provider_api_keys),
            daemon=True,
        )
        t.start()
        return True

    def retry_narrative_apply_patch_async(self, episode_id: str, provider_api_keys: dict) -> bool:
        """
        Narrative retry for the common case:
        Validation completed with FAIL and produced patch_instructions.

        Behavior (MVP):
        - Uses existing research_report (does NOT re-run research)
        - Uses latest validation_result.patch_instructions
        - Runs narrative ONCE (apply patch), then validation, and if PASS then composer.
        - Enforces retry budget: attempts.narrative must be < 2.
        """
        state = self.store.read_script_state(episode_id)

        # Must have a completed validation FAIL with patch instructions.
        val_result = state.get("validation_result") or {}
        _require(val_result.get("status") == "FAIL", "Cannot retry narrative: validation_result.status must be FAIL")
        patch = _safe_str(val_result.get("patch_instructions")).strip()
        _require(bool(patch), "Cannot retry narrative: validation_result.patch_instructions is missing")

        narrative_attempts = int((state.get("attempts") or {}).get("narrative", 0))
        if narrative_attempts >= 2:
            return False

        # Deterministic context (no defaults)
        ep_in = state.get("episode_input") or {}
        rr = state.get("research_report") or {}

        topic = _safe_str(ep_in.get("topic") or rr.get("topic")).strip()
        if not topic:
            _mark_step_error(state, "narrative", "Cannot retry narrative: topic is missing (episode_input.topic / research_report.topic)")
            self.store.write_script_state(episode_id, state)
            return False

        language = _safe_str(ep_in.get("language") or rr.get("language")).strip()
        if not language:
            _mark_step_error(state, "narrative", "Cannot retry narrative: language is missing (episode_input.language / research_report.language)")
            self.store.write_script_state(episode_id, state)
            return False

        target_minutes = ep_in.get("target_minutes", None)
        channel_profile = ep_in.get("channel_profile", None)

        # Ensure we have research_report available.
        if not state.get("research_report"):
            _mark_step_error(state, "narrative", "Cannot retry narrative: research_report missing")
            self.store.write_script_state(episode_id, state)
            return False

        # Reset narrative + downstream steps, but keep prior raw outputs for audit/debugging.
        def _reset_step(k: str) -> None:
            state["steps"][k]["status"] = "IDLE"
            state["steps"][k]["started_at"] = None
            state["steps"][k]["finished_at"] = None
            state["steps"][k]["error"] = None

        _reset_step("narrative")
        _reset_step("validation")
        _reset_step("composer")
        state["draft_script"] = None
        state["validation_result"] = None
        state["script_package"] = None
        state["script_status"] = "IDLE"
        state["updated_at"] = _now_iso()
        self.store.write_script_state(episode_id, state)

        t = threading.Thread(
            target=self._retry_narrative_apply_patch_thread,
            args=(episode_id, topic, language, target_minutes, channel_profile, provider_api_keys, patch),
            daemon=True,
        )
        t.start()
        return True

    def retry_validation_only_async(self, episode_id: str, provider_api_keys: dict) -> bool:
        """
        Validation-only retry (no narrative changes).
        Intended when draft_script was manually edited or regenerated and you only want to re-check it.
        """
        state = self.store.read_script_state(episode_id)
        if not state.get("draft_script"):
            return False

        # Deterministic context (no defaults)
        ep_in = state.get("episode_input") or {}
        rr = state.get("research_report") or {}
        topic = _safe_str(ep_in.get("topic") or rr.get("topic")).strip()
        language = _safe_str(ep_in.get("language") or rr.get("language")).strip()
        if not topic or not language:
            return False

        target_minutes = ep_in.get("target_minutes", None)
        channel_profile = ep_in.get("channel_profile", None)

        # Deterministic safety net before validation retry (works even when narrative retry budget is exhausted).
        try:
            state["draft_script"] = _sanitize_narrative_preface_and_hook(state.get("draft_script") or {}, rr)
            self.store.write_script_state(episode_id, state)
        except Exception:
            pass

        # Reset validation + composer only; keep draft_script intact.
        def _reset_step(k: str) -> None:
            state["steps"][k]["status"] = "IDLE"
            state["steps"][k]["started_at"] = None
            state["steps"][k]["finished_at"] = None
            state["steps"][k]["error"] = None

        _reset_step("validation")
        _reset_step("composer")
        state["validation_result"] = None
        state["script_package"] = None
        state["script_status"] = "IDLE"
        state["updated_at"] = _now_iso()
        self.store.write_script_state(episode_id, state)

        t = threading.Thread(
            target=self._retry_step_thread,
            args=(episode_id, "validation", topic, language, target_minutes, channel_profile, provider_api_keys),
            daemon=True,
        )
        t.start()
        return True

    def _retry_step_thread(
        self,
        episode_id: str,
        step_key: str,
        topic: str,
        language: str,
        target_minutes: Optional[int],
        channel_profile: Optional[str],
        provider_api_keys: dict,
    ) -> None:
        # Před získáním locku zkontroluj, zda není starý
        self._force_unlock_if_stale(max_age_seconds=3600)  # 1 hodina
        
        if not self._try_acquire_lock():
            state = self.store.read_script_state(episode_id)
            _mark_step_error(state, step_key, "Jiný Script pipeline právě běží (paralelní generování je zakázáno).")
            self.store.write_script_state(episode_id, state)
            return

        try:
            # Re-run pipeline from this step forward
            self._run_pipeline_from_step(episode_id, step_key, topic, language, target_minutes, channel_profile, provider_api_keys)
        except Exception as e:
            try:
                state = self.store.read_script_state(episode_id)
                _mark_step_error(state, step_key, f"Retry selhal: {str(e)}")
                self.store.write_script_state(episode_id, state)
            except Exception:
                pass
        finally:
            self._release_lock()

    def _retry_narrative_apply_patch_thread(
        self,
        episode_id: str,
        topic: str,
        language: str,
        target_minutes: Optional[int],
        channel_profile: Optional[str],
        provider_api_keys: dict,
        patch_instructions: str,
    ) -> None:
        # Před získáním locku zkontroluj, zda není starý
        self._force_unlock_if_stale(max_age_seconds=3600)  # 1 hodina
        
        if not self._try_acquire_lock():
            state = self.store.read_script_state(episode_id)
            _mark_step_error(state, "narrative", "Jiný Script pipeline právě běží (paralelní generování je zakázáno).")
            self.store.write_script_state(episode_id, state)
            return

        try:
            self._run_narrative_apply_patch(episode_id, topic, language, target_minutes, channel_profile, provider_api_keys, patch_instructions)
        except Exception as e:
            try:
                state = self.store.read_script_state(episode_id)
                _mark_step_error(state, "narrative", f"Retry narrative selhal: {str(e)}")
                self.store.write_script_state(episode_id, state)
            except Exception:
                pass
        finally:
            self._release_lock()

    def _run_narrative_apply_patch(
        self,
        episode_id: str,
        topic: str,
        language: str,
        target_minutes: Optional[int],
        channel_profile: Optional[str],
        provider_api_keys: dict,
        patch_instructions: str,
    ) -> None:
        """
        Narrative retry path for Validation FAIL:
        - narrative ONCE with patch_instructions
        - validation ONCE
        - composer only if PASS
        - if validation FAIL after this retry, script_status becomes ERROR (manual fix required)
        """
        state = self.store.read_script_state(episode_id)
        if not state.get("research_report"):
            _mark_step_error(state, "narrative", "Cannot retry narrative: research_report missing")
            self.store.write_script_state(episode_id, state)
            return

        # Narrative (single attempt, patched)
        _mark_step_running(state, "narrative", "RUNNING_NARRATIVE")
        self.store.write_script_state(episode_id, state)
        try:
            cfg = _step_config_for(state, "narrative")
            provider = _safe_str(cfg.get("provider")).strip().lower()
            if not provider:
                raise RuntimeError("Narrative: config.provider is missing")
            model = _safe_str(cfg.get("model")).strip()
            if not model:
                raise RuntimeError("Narrative: config.model is missing")
            api_key = _safe_str((provider_api_keys or {}).get(provider)).strip()
            if not api_key:
                raise RuntimeError(f"Chybí API key pro provider '{provider}' (Narrative)")
            prompt_template, prompt_used = _apply_step_prompt(
                "narrative",
                state,
                topic,
                language,
                target_minutes,
                channel_profile,
                patch_instructions,
            )
            raw_text, parsed, meta = _llm_chat_json_raw(
                provider,
                prompt_used,
                api_key,
                model=model,
                temperature=float(cfg.get("temperature", 0.4)),
            )
            _write_raw_output(state, "narrative", raw_text, parsed, prompt_template, prompt_used, meta)
            self.store.write_script_state(episode_id, state)
            if parsed is None:
                raise RuntimeError("Narrative: LLM vrátil nevalidní JSON")
            draft = _normalize_draft_script(parsed)
            # Deterministic safety net for common Validation FAIL patterns (preface/hook)
            draft = _sanitize_narrative_preface_and_hook(draft, state.get("research_report") or {})
            state["draft_script"] = draft
            state["attempts"]["narrative"] = int(state["attempts"].get("narrative", 0)) + 1
            _mark_step_done(state, "narrative")
            self.store.write_script_state(episode_id, state)
        except Exception as e:
            _mark_step_error(state, "narrative", f"Narrative krok selhal: {str(e)}")
            self.store.write_script_state(episode_id, state)
            return

        # Validation
        _mark_step_running(state, "validation", "RUNNING_VALIDATION")
        self.store.write_script_state(episode_id, state)
        try:
            cfg = _step_config_for(state, "validation")
            provider = _safe_str(cfg.get("provider")).strip().lower()
            if not provider:
                raise RuntimeError("Validation: config.provider is missing")
            model = _safe_str(cfg.get("model")).strip()
            if not model:
                raise RuntimeError("Validation: config.model is missing")
            api_key = _safe_str((provider_api_keys or {}).get(provider)).strip()
            if not api_key:
                raise RuntimeError(f"Chybí API key pro provider '{provider}' (Validation)")
            prompt_template, prompt_used = _apply_step_prompt("validation", state, topic, language, target_minutes, channel_profile, None)
            raw_text, parsed, meta = _llm_chat_json_raw(
                provider,
                prompt_used,
                api_key,
                model=model,
                temperature=float(cfg.get("temperature", 0.4)),
            )
            _write_raw_output(state, "validation", raw_text, parsed, prompt_template, prompt_used, meta)
            self.store.write_script_state(episode_id, state)
            if parsed is None:
                raise RuntimeError("Validation: LLM vrátil nevalidní JSON")
            validation = _normalize_validation_result(parsed)
            state["validation_result"] = validation
            _mark_step_done(state, "validation")
            self.store.write_script_state(episode_id, state)
        except Exception as e:
            _mark_step_error(state, "validation", f"Validation krok selhal: {str(e)}")
            self.store.write_script_state(episode_id, state)
            return

        # Composer only if PASS; otherwise manual fix required
        if state["validation_result"]["status"] != "PASS":
            state["script_status"] = "ERROR"
            state["updated_at"] = _now_iso()
            self.store.write_script_state(episode_id, state)
            return

        _mark_step_running(state, "composer", "RUNNING_COMPOSER")
        self.store.write_script_state(episode_id, state)
        try:
            package = _deterministic_compose(
                episode_id=episode_id,
                language=language,
                target_minutes=target_minutes,
                channel_profile=channel_profile,
                research_report=state["research_report"],
                draft_script=state["draft_script"],
                validation_result=state["validation_result"],
            )
            state["script_package"] = package
            _mark_step_done(state, "composer")
            self.store.write_script_state(episode_id, state)
        except Exception as e:
            _mark_step_error(state, "composer", f"Composer krok selhal: {str(e)}")
            self.store.write_script_state(episode_id, state)
            return

        # TTS Formatting (step 5)
        try:
            _run_tts_formatting(state, episode_id, topic, language, target_minutes, channel_profile, provider_api_keys, self.store)
        except Exception:
            # Error already persisted by helper
            return

        # Footage Director (step 6)
        try:
            _run_footage_director(state, episode_id, topic, language, target_minutes, channel_profile, provider_api_keys, self.store)
        except Exception:
            # Error already persisted by helper
            return
        
        # Archive Asset Resolver (step 7)
        try:
            cache_dir = os.path.join(self.store.episode_dir(episode_id), "archive_cache")
            _run_asset_resolver(state, episode_id, self.store, cache_dir)
        except Exception:
            return
        
        # Compilation Builder (step 8)
        try:
            storage_dir = os.path.join(self.store.episode_dir(episode_id), "assets")
            output_dir = os.path.join(self.store.base_projects_dir, "..", "output")
            _run_compilation_builder(state, episode_id, self.store, storage_dir, output_dir)
        except Exception:
            return

    def _run_pipeline_from_step(
        self,
        episode_id: str,
        start_step: str,
        topic: str,
        language: str,
        target_minutes: Optional[int],
        channel_profile: Optional[str],
        provider_api_keys: dict,
    ) -> None:
        state = self.store.read_script_state(episode_id)

        # If retrying research, run full pipeline from research
        if start_step == "research":
            self._run_pipeline(episode_id, topic, language, target_minutes, channel_profile, provider_api_keys)
            return

        # If retrying narrative, skip research and run from narrative forward
        if start_step == "narrative":
            if not state.get("research_report"):
                _mark_step_error(state, "narrative", "Cannot retry narrative: research_report missing")
                self.store.write_script_state(episode_id, state)
                return
            # Run narrative + validation + composer loop (like in _run_pipeline)
            for attempt_index in range(2):
                _mark_step_running(state, "narrative", "RUNNING_NARRATIVE")
                self.store.write_script_state(episode_id, state)
                patch = None
                if attempt_index == 1:
                    patch = _safe_str((state.get("validation_result") or {}).get("patch_instructions")).strip() or None
                try:
                    cfg = _step_config_for(state, "narrative")
                    provider = _safe_str(cfg.get("provider")).strip().lower()
                    if not provider:
                        raise RuntimeError("Narrative: config.provider is missing")
                    model = _safe_str(cfg.get("model")).strip()
                    if not model:
                        raise RuntimeError("Narrative: config.model is missing")
                    api_key = _safe_str((provider_api_keys or {}).get(provider)).strip()
                    if not api_key:
                        raise RuntimeError(f"Chybí API key pro provider '{provider}' (Narrative)")
                    prompt_template, prompt_used = _apply_step_prompt("narrative", state, topic, language, target_minutes, channel_profile, patch)
                    raw_text, parsed, meta = _llm_chat_json_raw(
                        provider,
                        prompt_used,
                        api_key,
                        model=model,
                        temperature=float(cfg.get("temperature", 0.4)),
                    )
                    _write_raw_output(state, "narrative", raw_text, parsed, prompt_template, prompt_used, meta)
                    self.store.write_script_state(episode_id, state)
                    if parsed is None:
                        raise RuntimeError("Narrative: LLM vrátil nevalidní JSON")
                    draft = _normalize_draft_script(parsed)
                    # Deterministic safety net for common Validation FAIL patterns (preface/hook)
                    draft = _sanitize_narrative_preface_and_hook(draft, state.get("research_report") or {})
                    state["draft_script"] = draft
                    state["attempts"]["narrative"] = int(state["attempts"].get("narrative", 0)) + 1
                    _mark_step_done(state, "narrative")
                    self.store.write_script_state(episode_id, state)
                except Exception as e:
                    _mark_step_error(state, "narrative", f"Narrative krok selhal: {str(e)}")
                    self.store.write_script_state(episode_id, state)
                    return

                # Validation
                _mark_step_running(state, "validation", "RUNNING_VALIDATION")
                self.store.write_script_state(episode_id, state)
                try:
                    cfg = _step_config_for(state, "validation")
                    provider = _safe_str(cfg.get("provider")).strip().lower()
                    if not provider:
                        raise RuntimeError("Validation: config.provider is missing")
                    model = _safe_str(cfg.get("model")).strip()
                    if not model:
                        raise RuntimeError("Validation: config.model is missing")
                    api_key = _safe_str((provider_api_keys or {}).get(provider)).strip()
                    if not api_key:
                        raise RuntimeError(f"Chybí API key pro provider '{provider}' (Validation)")
                    prompt_template, prompt_used = _apply_step_prompt("validation", state, topic, language, target_minutes, channel_profile, None)
                    raw_text, parsed, meta = _llm_chat_json_raw(
                        provider,
                        prompt_used,
                        api_key,
                        model=model,
                        temperature=float(cfg.get("temperature", 0.4)),
                    )
                    _write_raw_output(state, "validation", raw_text, parsed, prompt_template, prompt_used, meta)
                    self.store.write_script_state(episode_id, state)
                    if parsed is None:
                        raise RuntimeError("Validation: LLM vrátil nevalidní JSON")
                    validation = _normalize_validation_result(parsed)
                    state["validation_result"] = validation
                    _mark_step_done(state, "validation")
                    self.store.write_script_state(episode_id, state)
                except Exception as e:
                    _mark_step_error(state, "validation", f"Validation krok selhal: {str(e)}")
                    self.store.write_script_state(episode_id, state)
                    return

                if state["validation_result"]["status"] == "PASS":
                    break
                if attempt_index == 0:
                    continue
                state["script_status"] = "ERROR"
                state["updated_at"] = _now_iso()
                self.store.write_script_state(episode_id, state)
                return

            # Composer
            if not state.get("validation_result") or state["validation_result"].get("status") != "PASS":
                state["script_status"] = "ERROR"
                state["updated_at"] = _now_iso()
                self.store.write_script_state(episode_id, state)
                return

            _mark_step_running(state, "composer", "RUNNING_COMPOSER")
            self.store.write_script_state(episode_id, state)
            try:
                package = _deterministic_compose(
                    episode_id=episode_id,
                    language=language,
                    target_minutes=target_minutes,
                    channel_profile=channel_profile,
                    research_report=state["research_report"],
                    draft_script=state["draft_script"],
                    validation_result=state["validation_result"],
                )
                state["script_package"] = package
                _mark_step_done(state, "composer")
                self.store.write_script_state(episode_id, state)
            except Exception as e:
                _mark_step_error(state, "composer", f"Composer krok selhal: {str(e)}")
                self.store.write_script_state(episode_id, state)
                return

            # TTS Formatting
            try:
                _run_tts_formatting(state, episode_id, topic, language, target_minutes, channel_profile, provider_api_keys, self.store)
            except Exception:
                return

            # Footage Director
            try:
                _run_footage_director(state, episode_id, topic, language, target_minutes, channel_profile, provider_api_keys, self.store)
            except Exception:
                return
            
            # Archive Asset Resolver
            try:
                cache_dir = os.path.join(self.store.episode_dir(episode_id), "archive_cache")
                _run_asset_resolver(state, episode_id, self.store, cache_dir)
            except Exception:
                return
            
            # Compilation Builder
            try:
                storage_dir = os.path.join(self.store.episode_dir(episode_id), "assets")
                output_dir = os.path.join(self.store.base_projects_dir, "..", "output")
                _run_compilation_builder(state, episode_id, self.store, storage_dir, output_dir)
            except Exception:
                return
            return

        # If retrying validation, run just validation + composer
        if start_step == "validation":
            if not state.get("draft_script"):
                _mark_step_error(state, "validation", "Cannot retry validation: draft_script missing")
                self.store.write_script_state(episode_id, state)
                return

            _mark_step_running(state, "validation", "RUNNING_VALIDATION")
            self.store.write_script_state(episode_id, state)
            try:
                cfg = _step_config_for(state, "validation")
                provider = _safe_str(cfg.get("provider")).strip().lower()
                if not provider:
                    raise RuntimeError("Validation: config.provider is missing")
                model = _safe_str(cfg.get("model")).strip()
                if not model:
                    raise RuntimeError("Validation: config.model is missing")
                api_key = _safe_str((provider_api_keys or {}).get(provider)).strip()
                if not api_key:
                    raise RuntimeError(f"Chybí API key pro provider '{provider}' (Validation)")
                prompt_template, prompt_used = _apply_step_prompt("validation", state, topic, language, target_minutes, channel_profile, None)
                raw_text, parsed, meta = _llm_chat_json_raw(
                    provider,
                    prompt_used,
                    api_key,
                    model=model,
                    temperature=float(cfg.get("temperature", 0.4)),
                )
                _write_raw_output(state, "validation", raw_text, parsed, prompt_template, prompt_used, meta)
                self.store.write_script_state(episode_id, state)
                if parsed is None:
                    raise RuntimeError("Validation: LLM vrátil nevalidní JSON")
                validation = _normalize_validation_result(parsed)
                state["validation_result"] = validation
                _mark_step_done(state, "validation")
                self.store.write_script_state(episode_id, state)
            except Exception as e:
                _mark_step_error(state, "validation", f"Validation krok selhal: {str(e)}")
                self.store.write_script_state(episode_id, state)
                return

            if state["validation_result"]["status"] != "PASS":
                # Validation completed but did not pass; keep a non-error state so UI can show FAIL vs ERROR clearly.
                state["script_status"] = "IDLE"
                state["updated_at"] = _now_iso()
                self.store.write_script_state(episode_id, state)
                return

            # Composer
            _mark_step_running(state, "composer", "RUNNING_COMPOSER")
            self.store.write_script_state(episode_id, state)
            try:
                package = _deterministic_compose(
                    episode_id=episode_id,
                    language=language,
                    target_minutes=target_minutes,
                    channel_profile=channel_profile,
                    research_report=state["research_report"],
                    draft_script=state["draft_script"],
                    validation_result=state["validation_result"],
                )
                state["script_package"] = package
                _mark_step_done(state, "composer")
                self.store.write_script_state(episode_id, state)
            except Exception as e:
                _mark_step_error(state, "composer", f"Composer krok selhal: {str(e)}")
                self.store.write_script_state(episode_id, state)
                return

            # TTS Formatting
            try:
                _run_tts_formatting(state, episode_id, topic, language, target_minutes, channel_profile, provider_api_keys, self.store)
            except Exception:
                return
            
            # Footage Director
            try:
                _run_footage_director(state, episode_id, topic, language, target_minutes, channel_profile, provider_api_keys, self.store)
            except Exception:
                return
            
            # Archive Asset Resolver
            try:
                cache_dir = os.path.join(self.store.episode_dir(episode_id), "archive_cache")
                _run_asset_resolver(state, episode_id, self.store, cache_dir)
            except Exception:
                return
            
            # Compilation Builder
            try:
                storage_dir = os.path.join(self.store.episode_dir(episode_id), "assets")
                output_dir = os.path.join(self.store.base_projects_dir, "..", "output")
                _run_compilation_builder(state, episode_id, self.store, storage_dir, output_dir)
            except Exception:
                return

        # If retrying composer directly
        if start_step == "composer":
            if not state.get("validation_result") or state["validation_result"].get("status") != "PASS":
                _mark_step_error(state, "composer", "Cannot retry composer: validation_result is not PASS")
                self.store.write_script_state(episode_id, state)
                return

            _mark_step_running(state, "composer", "RUNNING_COMPOSER")
            self.store.write_script_state(episode_id, state)
            try:
                package = _deterministic_compose(
                    episode_id=episode_id,
                    language=language,
                    target_minutes=target_minutes,
                    channel_profile=channel_profile,
                    research_report=state["research_report"],
                    draft_script=state["draft_script"],
                    validation_result=state["validation_result"],
                )
                state["script_package"] = package
                _mark_step_done(state, "composer")
                self.store.write_script_state(episode_id, state)
            except Exception as e:
                _mark_step_error(state, "composer", f"Composer krok selhal: {str(e)}")
                self.store.write_script_state(episode_id, state)
                return

            # TTS Formatting
            try:
                _run_tts_formatting(state, episode_id, topic, language, target_minutes, channel_profile, provider_api_keys, self.store)
            except Exception:
                return

            # Footage Director
            try:
                _run_footage_director(state, episode_id, topic, language, target_minutes, channel_profile, provider_api_keys, self.store)
            except Exception:
                return

        # If retrying tts_format directly
        if start_step == "tts_format":
            if not state.get("script_package"):
                _mark_step_error(state, "tts_format", "Cannot retry tts_format: script_package missing")
                self.store.write_script_state(episode_id, state)
                return

            try:
                _run_tts_formatting(state, episode_id, topic, language, target_minutes, channel_profile, provider_api_keys, self.store)
            except Exception:
                return

            # Footage Director (po TTS formatting)
            try:
                _run_footage_director(state, episode_id, topic, language, target_minutes, channel_profile, provider_api_keys, self.store)
            except Exception:
                return

        # If retrying footage_director directly
        if start_step == "footage_director":
            if not state.get("tts_ready_package"):
                _mark_step_error(state, "footage_director", "Cannot retry footage_director: tts_ready_package missing")
                self.store.write_script_state(episode_id, state)
                return

            try:
                _run_footage_director(state, episode_id, topic, language, target_minutes, channel_profile, provider_api_keys, self.store)
            except Exception:
                return

            # After footage_director, continue with downstream steps (FDA_OUTPUT_VALIDATOR, AAR, CB) implicitly
            # via existing pipeline flow if user explicitly retries those steps later.

        # If retrying asset_resolver directly
        if start_step == "asset_resolver":
            cache_dir = os.path.join(self.store.episode_dir(episode_id), "archive_cache")
            try:
                _run_asset_resolver(state, episode_id, self.store, cache_dir)
            except Exception:
                return

            # Compilation Builder (after AAR)
            try:
                storage_dir = os.path.join(self.store.episode_dir(episode_id), "assets")
                output_dir = os.path.join(self.store.base_projects_dir, "..", "output")
                _run_compilation_builder(state, episode_id, self.store, storage_dir, output_dir)
            except Exception:
                return
            return

        # If retrying compilation_builder directly
        if start_step == "compilation_builder":
            try:
                storage_dir = os.path.join(self.store.episode_dir(episode_id), "assets")
                output_dir = os.path.join(self.store.base_projects_dir, "..", "output")
                _run_compilation_builder(state, episode_id, self.store, storage_dir, output_dir)
            except Exception:
                return
            return


