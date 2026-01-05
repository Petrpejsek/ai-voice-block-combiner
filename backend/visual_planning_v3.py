"""
Visual Planning v3

Goal: make the FDA → AAR → CB pipeline *never-fail* due to LLM format/style.

Contract split:
- LLM output: ScenePlan v3 (creative, best-effort; may be partially invalid)
- Deterministic compiler: ShotPlan v3 (canonical, always valid for downstream)

This module contains ONLY deterministic logic:
- ScenePlan v3 coercion + deterministic fallback generation
- ShotPlan v3 compilation
- Minimal hard-gate validation (no stylistic language policing)
"""

from __future__ import annotations

import hashlib
import math
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Query Guardrails (systematic query validation)
try:
    from query_guardrails import validate_and_fix_queries
    QUERY_GUARDRAILS_AVAILABLE = True
except ImportError as e:
    print(f"❌ CRITICAL: Query Guardrails import failed in visual_planning_v3: {e}")
    QUERY_GUARDRAILS_AVAILABLE = False

SCENEPLAN_V3_VERSION = "sceneplan_v3"
SHOTPLAN_V3_VERSION = "shotplan_v3"


# Keep enums intentionally small + stable.
ALLOWED_EMOTIONS = ["neutral", "tension", "tragedy", "hope", "victory", "mystery"]
ALLOWED_CUT_RHYTHMS = ["slow", "medium", "fast"]

# Match the existing FDA/AAR enum family in this repo (legacy-compatible).
ALLOWED_SHOT_TYPES = [
    "historical_battle_footage",
    "troop_movement",
    "leaders_speeches",
    "civilian_life",
    "destruction_aftermath",
    "industry_war_effort",
    "maps_context",
    "archival_documents",
    "atmosphere_transition",
]

# Keep as a simple string (downstream treats it as advisory).
DEFAULT_SOURCE_PREFERENCE = "archive_org"


def _safe_str(x: Any) -> str:
    return "" if x is None else str(x)


def _dedupe_preserve(items: List[str]) -> List[str]:
    seen = set()
    out: List[str] = []
    for it in items:
        s = _safe_str(it).strip()
        if not s:
            continue
        k = s.lower()
        if k in seen:
            continue
        seen.add(k)
        out.append(s)
    return out


def _count_words(s: str) -> int:
    return len([w for w in str(s or "").strip().split() if w])


def estimate_speech_duration_seconds(text: str, words_per_minute: int = 150) -> float:
    """
    Deterministic speech duration estimate used for timeline.
    (Downstream CB uses actual MP3 durations per block when available.)
    """
    if not text or not isinstance(text, str):
        return 0.0
    words = re.findall(r"\b\w+\b", text)
    wc = len(words)
    if wc <= 0:
        return 0.0
    return round((wc / max(1, int(words_per_minute))) * 60.0, 2)


def _first_sentence_summary(text: str, max_words: int = 22) -> str:
    """
    Deterministic narration_summary:
    - Take first sentence if possible, otherwise first max_words words.
    - Always end with '.' if non-empty.
    """
    if not text or not isinstance(text, str) or not text.strip():
        return ""
    raw = text.strip()
    # Keep it simple and robust.
    m = re.search(r"[\.\!\?](\s|$)", raw)
    sent = raw[: (m.end() if m else len(raw))].strip()
    words = sent.split()
    if len(words) > max_words:
        sent = " ".join(words[:max_words]).strip()
    sent = sent.rstrip(" ,;:!?")
    if sent and not sent.endswith("."):
        sent += "."
    return sent


def extract_narration_blocks(tts_ready_package: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Tolerant extraction of narration blocks:
    - Prefer narration_blocks[]
    - Fall back to tts_segments[]
    """
    pkg = tts_ready_package if isinstance(tts_ready_package, dict) else {}
    if isinstance(pkg.get("narration_blocks"), list) and pkg.get("narration_blocks"):
        out = []
        for b in pkg["narration_blocks"]:
            if not isinstance(b, dict):
                continue
            bid = _safe_str(b.get("block_id")).strip()
            if not bid:
                continue
            # Prefer text_tts, but tolerate other fields for resilience.
            txt = b.get("text_tts")
            if not isinstance(txt, str) or not txt.strip():
                txt = b.get("tts_formatted_text") or b.get("text") or ""
            out.append({"block_id": bid, "text_tts": _safe_str(txt).strip()})
        return out

    segs = pkg.get("tts_segments")
    if isinstance(segs, list) and segs:
        out = []
        for seg in segs:
            if not isinstance(seg, dict):
                continue
            bid = _safe_str(seg.get("block_id") or seg.get("segment_id")).strip()
            if not bid:
                continue
            txt = seg.get("tts_formatted_text") or seg.get("text") or ""
            out.append({"block_id": bid, "text_tts": _safe_str(txt).strip()})
        return out

    # Nothing usable.
    return []


def _expected_block_ids(tts_ready_package: Dict[str, Any]) -> List[str]:
    blocks = extract_narration_blocks(tts_ready_package)
    return [str(b.get("block_id") or "").strip() for b in blocks if str(b.get("block_id") or "").strip()]


def _block_text_map(tts_ready_package: Dict[str, Any]) -> Dict[str, str]:
    blocks = extract_narration_blocks(tts_ready_package)
    out: Dict[str, str] = {}
    for b in blocks:
        bid = _safe_str(b.get("block_id")).strip()
        if not bid:
            continue
        out[bid] = _safe_str(b.get("text_tts")).strip()
    return out


def _extract_focus_entities(text: str, max_items: int = 6) -> List[str]:
    """
    Very small deterministic entity extractor:
    - multiword Proper Noun phrases up to 3 words
    - standalone Proper Nouns
    - years
    """
    if not text:
        return []
    raw = str(text)
    entities: List[str] = []
    for m in re.findall(r"\b[A-Z][A-Za-z.'-]*(?:\s+[A-Z][A-Za-z.'-]*){1,2}\b", raw):
        entities.append(m.strip())
    for m in re.findall(r"\b[A-Z][a-z]{2,}\b", raw):
        entities.append(m.strip())
    for y in re.findall(r"\b(?:1[0-9]{3}|20[0-2][0-9])\b", raw):
        entities.append(y.strip())
    entities = _dedupe_preserve(entities)
    return entities[:max_items]


def _heuristic_shot_types(text: str) -> List[str]:
    """
    Never-fail heuristic for shot_types.
    """
    low = _safe_str(text).lower()
    picked: List[str] = []

    def add(st: str) -> None:
        if st in ALLOWED_SHOT_TYPES and st not in picked:
            picked.append(st)

    if any(w in low for w in ("map", "route", "campaign", "across", "toward", "into", "from", "border", "province")):
        add("maps_context")
    if any(w in low for w in ("letter", "decree", "treaty", "document", "dispatch", "correspondence", "proclamation")):
        add("archival_documents")
    if any(w in low for w in ("fire", "burn", "smoke", "ruins", "ashes", "destroyed", "destruction")):
        add("destruction_aftermath")
    if any(w in low for w in ("soldier", "army", "troops", "march", "retreat", "column", "regiment")):
        add("troop_movement")
    if any(w in low for w in ("tsar", "king", "queen", "president", "emperor", "napoleon", "alexander")):
        add("leaders_speeches")

    # Default backbone: always keep at least one type.
    if not picked:
        add("archival_documents")
    # Add atmosphere as a safe filler for rhythm/coverage diversity.
    if "atmosphere_transition" not in picked:
        add("atmosphere_transition")
    return picked[:4]


def build_default_sceneplan_v3(tts_ready_package: Dict[str, Any]) -> Tuple[Dict[str, Any], List[dict]]:
    """
    Deterministic fallback ScenePlan v3.
    Always succeeds if narration blocks exist.
    """
    warnings: List[dict] = []
    expected = _expected_block_ids(tts_ready_package)
    if not expected:
        # We'll let downstream hard-gate catch missing narration blocks.
        return {"version": SCENEPLAN_V3_VERSION, "scenes": []}, [{"code": "SCENEPLAN_NO_BLOCKS", "message": "tts_ready_package has no narration blocks"}]

    text_map = _block_text_map(tts_ready_package)
    # Aim for 6–12 scenes depending on size to avoid exploding AAR query count.
    n = len(expected)
    target_scenes = int(min(12, max(6, round(n / 3))))
    chunk = int(max(1, math.ceil(n / max(1, target_scenes))))

    scenes = []
    idx = 0
    scene_no = 1
    while idx < n:
        block_ids = expected[idx : idx + chunk]
        idx += chunk
        txt = " ".join([text_map.get(bid, "") for bid in block_ids]).strip()
        scenes.append(
            {
                "scene_id": f"sc_{scene_no:04d}",
                "narration_block_ids": block_ids,
                "emotion": "neutral",
                "shot_types": _heuristic_shot_types(txt),
                "cut_rhythm": "medium",
                "source_preference": DEFAULT_SOURCE_PREFERENCE,
                "focus_entities": _extract_focus_entities(txt),
            }
        )
        scene_no += 1

    warnings.append({"code": "SCENEPLAN_DEFAULT_USED", "message": "LLM ScenePlan missing/invalid; used deterministic default"})
    return {"version": SCENEPLAN_V3_VERSION, "scenes": scenes}, warnings


def coerce_sceneplan_v3(llm_obj: Any, tts_ready_package: Dict[str, Any]) -> Tuple[Dict[str, Any], List[dict]]:
    """
    Best-effort coercion into ScenePlan v3.
    Never raises; returns fallback ScenePlan on failure.
    """
    warnings: List[dict] = []
    expected = _expected_block_ids(tts_ready_package)
    if not expected:
        return {"version": SCENEPLAN_V3_VERSION, "scenes": []}, [{"code": "SCENEPLAN_NO_BLOCKS", "message": "tts_ready_package has no narration blocks"}]

    if not isinstance(llm_obj, dict):
        sp, w = build_default_sceneplan_v3(tts_ready_package)
        return sp, w + [{"code": "SCENEPLAN_LLM_NOT_OBJECT", "message": f"LLM output type={type(llm_obj).__name__}"}]

    version = _safe_str(llm_obj.get("version")).strip()
    if version and version != SCENEPLAN_V3_VERSION:
        warnings.append({"code": "SCENEPLAN_VERSION_MISMATCH", "message": f"Expected {SCENEPLAN_V3_VERSION}, got {version}"})

    raw_scenes = llm_obj.get("scenes")
    if not isinstance(raw_scenes, list) or not raw_scenes:
        sp, w = build_default_sceneplan_v3(tts_ready_package)
        return sp, w + [{"code": "SCENEPLAN_NO_SCENES", "message": "LLM ScenePlan.scenes missing/empty"}]

    # Normalize each scene.
    normalized: List[Dict[str, Any]] = []
    for i, sc in enumerate(raw_scenes, start=1):
        if not isinstance(sc, dict):
            continue
        scene_id = _safe_str(sc.get("scene_id")).strip() or f"sc_{i:04d}"
        nbids = sc.get("narration_block_ids")
        nbids_list = nbids if isinstance(nbids, list) else []
        nbids_list = [_safe_str(x).strip() for x in nbids_list if _safe_str(x).strip()]

        emotion = _safe_str(sc.get("emotion")).strip().lower() or "neutral"
        if emotion not in ALLOWED_EMOTIONS:
            emotion = "neutral"
        cut_rhythm = _safe_str(sc.get("cut_rhythm")).strip().lower() or "medium"
        if cut_rhythm not in ALLOWED_CUT_RHYTHMS:
            cut_rhythm = "medium"

        shot_types = sc.get("shot_types")
        st_list = shot_types if isinstance(shot_types, list) else []
        st_list = [_safe_str(x).strip() for x in st_list if _safe_str(x).strip()]
        st_list = [x for x in st_list if x in ALLOWED_SHOT_TYPES]

        source_pref = _safe_str(sc.get("source_preference")).strip() or DEFAULT_SOURCE_PREFERENCE
        focus = sc.get("focus_entities")
        focus_list = focus if isinstance(focus, list) else []
        focus_list = [_safe_str(x).strip() for x in focus_list if _safe_str(x).strip()]

        normalized.append(
            {
                "scene_id": scene_id,
                "narration_block_ids": nbids_list,
                "emotion": emotion,
                "shot_types": st_list,
                "cut_rhythm": cut_rhythm,
                "source_preference": source_pref,
                "focus_entities": focus_list[:10],
            }
        )

    if not normalized:
        sp, w = build_default_sceneplan_v3(tts_ready_package)
        return sp, w + [{"code": "SCENEPLAN_SCENES_INVALID", "message": "LLM ScenePlan.scenes had no usable scene objects"}]

    # Coverage repair (at least once, keep order).
    order = {bid: i for i, bid in enumerate(expected)}
    used = set()
    repaired: List[Dict[str, Any]] = []
    for sc in normalized:
        kept = [b for b in sc.get("narration_block_ids", []) if b in order and b not in used]
        kept.sort(key=lambda b: order[b])
        for b in kept:
            used.add(b)
        if not kept:
            continue
        sc2 = dict(sc)
        sc2["narration_block_ids"] = kept
        # If shot_types missing, infer from text.
        if not sc2.get("shot_types"):
            txt = " ".join([_block_text_map(tts_ready_package).get(b, "") for b in kept]).strip()
            sc2["shot_types"] = _heuristic_shot_types(txt)
            warnings.append({"code": "SCENEPLAN_SHOT_TYPES_INFERRED", "message": f"{sc2.get('scene_id')}: missing shot_types; inferred"})
        repaired.append(sc2)

    remaining = [b for b in expected if b not in used]
    if remaining:
        warnings.append({"code": "SCENEPLAN_COVERAGE_REPAIRED", "message": f"Added {len(remaining)} missing narration blocks into sceneplan"})
        if repaired:
            repaired[-1]["narration_block_ids"].extend(remaining)
        else:
            # Fallback: should not happen, but keep never-fail.
            sp, w = build_default_sceneplan_v3(tts_ready_package)
            return sp, w + warnings

    # Ensure deterministic IDs if duplicates.
    seen_ids = set()
    for i, sc in enumerate(repaired, start=1):
        sid = _safe_str(sc.get("scene_id")).strip() or f"sc_{i:04d}"
        if sid in seen_ids:
            sid = f"sc_{i:04d}"
        seen_ids.add(sid)
        sc["scene_id"] = sid

    out = {"version": SCENEPLAN_V3_VERSION, "scenes": repaired}
    return out, warnings


def _stable_pick(items: List[str], seed: str) -> Optional[str]:
    if not items:
        return None
    h = hashlib.sha256(seed.encode("utf-8")).hexdigest()
    idx = int(h[:8], 16) % len(items)
    return items[idx]


def _scene_anchor_tokens(text: str, focus_entities: List[str]) -> Dict[str, Optional[str]]:
    raw = _safe_str(text)
    years = re.findall(r"\b(?:1[0-9]{3}|20[0-2][0-9])\b", raw)
    proper = re.findall(r"\b[A-Z][a-z]{2,}\b", raw)
    # Prefer focus_entities, then proper nouns.
    ent = _stable_pick([e for e in focus_entities if isinstance(e, str) and e.strip()], seed=raw) or _stable_pick(proper, seed=raw)
    year = _stable_pick(years, seed=raw)
    return {"entity": ent, "year": year}


def _ensure_word_range(phrase: str, min_words: int, max_words: int, pad: Optional[str] = None) -> str:
    words = [w for w in _safe_str(phrase).strip().split() if w]
    if len(words) > max_words:
        words = words[:max_words]
    while len(words) < min_words:
        words.insert(0, pad or "archival")
        if len(words) > max_words:
            words = words[:max_words]
            break
    return " ".join(words).strip()


def _keywords_for_scene(text: str, focus_entities: List[str], shot_types: List[str]) -> List[str]:
    anchors = _scene_anchor_tokens(text, focus_entities)
    ent = anchors.get("entity")
    year = anchors.get("year")

    # Object phrases (2-3 words preferred)
    object_phrases: List[str] = []
    st_set = set(shot_types or [])
    if "maps_context" in st_set:
        object_phrases += ["archival map", "route map", "city map"]
    if "archival_documents" in st_set:
        object_phrases += ["handwritten letter", "government document", "archival correspondence"]
    if "destruction_aftermath" in st_set:
        object_phrases += ["burned ruins", "smoke over city", "aftermath ruins"]
    if "civilian_life" in st_set:
        object_phrases += ["city street", "market street scene", "everyday life"]
    if "troop_movement" in st_set:
        object_phrases += ["marching soldiers", "army camp", "military column"]
    if "leaders_speeches" in st_set:
        object_phrases += ["official portrait", "portrait photograph", "statesman portrait"]
    if not object_phrases:
        object_phrases = ["archival map", "handwritten letter", "historical engraving", "old photograph"]

    object_phrases = _dedupe_preserve(object_phrases)

    candidates: List[str] = []
    if ent:
        candidates.append(f"{ent} {object_phrases[0]}")
    if year and ent:
        candidates.append(f"{year} {ent} {object_phrases[1] if len(object_phrases) > 1 else object_phrases[0]}")
    if year:
        candidates.append(f"{year} {object_phrases[0]}")
    # Fill with object phrases directly.
    candidates.extend(object_phrases)
    # Add a couple of stable "safe visuals".
    candidates.extend(["archival documents", "historical engraving", "old photograph", "paper documents"])

    out: List[str] = []
    for c in candidates:
        kw = _ensure_word_range(c, 2, 5, pad="archival")
        if kw and kw.lower() not in {x.lower() for x in out}:
            out.append(kw)
        if len(out) >= 8:
            break
    # Guarantee exact 8 (never empty).
    while len(out) < 8:
        out.append(_ensure_word_range(f"archival {len(out)+1} documents", 2, 5, pad="archival"))
    return out[:8]


def _queries_for_scene(
    text: str,
    focus_entities: List[str],
    shot_types: List[str],
    episode_topic: Optional[str] = None
) -> List[str]:
    """
    Generate search queries for a scene with guardrails validation.
    
    Args:
        text: Scene narration text
        focus_entities: List of focus entities for anchoring
        shot_types: List of shot types (for media intent)
        episode_topic: Optional episode topic for fallback anchors
    
    Returns:
        List of validated queries (5 items)
    """
    anchors = _scene_anchor_tokens(text, focus_entities)
    ent = anchors.get("entity") or "history"
    year = anchors.get("year")

    # Use artefact-forward queries (avoid generic "documentary footage").
    base_objs = [
        ["archival", "map"],
        ["historical", "engraving"],
        ["portrait", "photograph"],
        ["handwritten", "letter"],
        ["archival", "documents"],
    ]

    # Prefer map/documents if shot types request it (deterministic reorder).
    st_set = set(shot_types or [])
    if "maps_context" in st_set:
        base_objs = [base_objs[0]] + base_objs[1:]
    if "archival_documents" in st_set:
        base_objs = [base_objs[4]] + [x for x in base_objs if x != base_objs[4]]

    out: List[str] = []
    for obj_tokens in base_objs:
        tokens: List[str] = []
        # Anchor first (better relevance).
        tokens.append(ent)
        if year:
            tokens.append(year)
        tokens.extend(obj_tokens)
        # Add a small, stable tail that improves hit rate but isn't "stylistic".
        tokens.extend(["public", "domain", "archive"])
        q = " ".join(tokens)
        q = _ensure_word_range(q, 5, 9, pad="archival")
        out.append(q)
        if len(out) >= 5:
            break

    # Guarantee exact 5.
    while len(out) < 5:
        filler = _ensure_word_range(f"{ent} archival image public domain", 5, 9, pad="archival")
        out.append(filler)

    # De-dupe while preserving order (still keep 5 by re-filling).
    out = _dedupe_preserve(out)
    while len(out) < 5:
        out.append(_ensure_word_range(f"{ent} archival map public domain archive", 5, 9, pad="archival"))
        out = _dedupe_preserve(out)
    
    # Apply guardrails if available (REQUIRED - fail if not available)
    if not QUERY_GUARDRAILS_AVAILABLE:
        raise RuntimeError(
            "QUERY_GUARDRAILS_UNAVAILABLE: Query guardrails module not loaded in visual_planning_v3. "
            "Cannot proceed with query generation without validation."
        )
    
    validated, diagnostics = validate_and_fix_queries(
        out,
        text,
        shot_types=shot_types,
        episode_topic=episode_topic or ent,
        min_valid_queries=5,
        max_regen_attempts=2,
        verbose=False
    )
    return validated[:5]


def compile_shotplan_v3(
    tts_ready_package: Dict[str, Any],
    sceneplan_v3: Dict[str, Any],
    words_per_minute: int = 150,
) -> Tuple[Dict[str, Any], List[dict]]:
    """
    Compile a ShotPlan v3 from tts_ready_package + ScenePlan v3.
    
    This is the deterministic compiler that guarantees valid output for AAR/CB.
    """
    # SINGLE ENTRYPOINT: Get episode_topic from metadata (PRIMARY GATE)
    # KANONICKÝ ZDROJ: episode_metadata["topic"]
    # title je jen UI label, NE fallback
    try:
        from query_guardrails_utils import get_episode_topic_strict
        episode_topic = get_episode_topic_strict(tts_ready_package)
    except ImportError:
        # Fallback if utils not available (but still strict - same logic)
        episode_metadata = tts_ready_package.get("episode_metadata", {})
        topic = episode_metadata.get("topic")
        if not topic or not str(topic).strip():
            raise ValueError(
                "EPISODE_TOPIC_MISSING: episode_metadata must contain non-empty 'topic' field. "
                "Cannot generate anchored queries without episode topic. "
                "title field is NOT used as fallback (UI label only)."
            )
        episode_topic = str(topic).strip()
    Deterministically compile ShotPlan v3 from ScenePlan v3 and tts_ready_package.
    Never raises; returns warnings and best-effort output.
    """
    warnings: List[dict] = []
    expected = _expected_block_ids(tts_ready_package)
    text_map = _block_text_map(tts_ready_package)
    if not expected:
        # Best-effort empty plan; validator will gate it if used.
        return {"shot_plan": {"version": SHOTPLAN_V3_VERSION, "source": "tts_ready_package", "assumptions": {"words_per_minute": int(words_per_minute)}, "scenes": [], "total_scenes": 0, "total_duration_sec": 0}}, [{"code": "SHOTPLAN_NO_BLOCKS", "message": "tts_ready_package has no narration blocks"}]

    scenes_in = sceneplan_v3.get("scenes") if isinstance(sceneplan_v3, dict) else None
    scenes_in = scenes_in if isinstance(scenes_in, list) else []
    if not scenes_in:
        sp, w = build_default_sceneplan_v3(tts_ready_package)
        warnings.extend(w)
        scenes_in = sp.get("scenes") or []

    # Normalize + coverage repair defensively (in case caller passed non-coerced sceneplan).
    coerced, w = coerce_sceneplan_v3({"version": SCENEPLAN_V3_VERSION, "scenes": scenes_in}, tts_ready_package)
    warnings.extend(w)
    scenes_in = coerced.get("scenes") or []

    # Build timeline.
    compiled_scenes: List[Dict[str, Any]] = []
    t = 0.0
    for i, sc in enumerate(scenes_in, start=1):
        sid = _safe_str(sc.get("scene_id")).strip() or f"sc_{i:04d}"
        nbids = sc.get("narration_block_ids") if isinstance(sc.get("narration_block_ids"), list) else []
        nbids = [_safe_str(x).strip() for x in nbids if _safe_str(x).strip()]
        # Ensure order matches expected.
        order = {bid: idx for idx, bid in enumerate(expected)}
        nbids = [b for b in nbids if b in order]
        nbids.sort(key=lambda b: order[b])
        if not nbids:
            continue

        scene_text = " ".join([text_map.get(b, "") for b in nbids]).strip()
        # Duration is derived from blocks (deterministic).
        dur = 0.0
        for b in nbids:
            dur += estimate_speech_duration_seconds(text_map.get(b, ""), words_per_minute=words_per_minute)
        if dur <= 0:
            dur = 3.5

        start_sec = int(round(t))
        end_sec = int(round(t + dur))
        if end_sec <= start_sec:
            end_sec = start_sec + 2
        if (end_sec - start_sec) < 2:
            end_sec = start_sec + 2
        t = float(end_sec)

        emotion = _safe_str(sc.get("emotion")).strip().lower() or "neutral"
        if emotion not in ALLOWED_EMOTIONS:
            emotion = "neutral"
        cut_rhythm = _safe_str(sc.get("cut_rhythm")).strip().lower() or "medium"
        if cut_rhythm not in ALLOWED_CUT_RHYTHMS:
            cut_rhythm = "medium"
        shot_types = sc.get("shot_types") if isinstance(sc.get("shot_types"), list) else []
        shot_types = [_safe_str(x).strip() for x in shot_types if _safe_str(x).strip()]
        shot_types = [x for x in shot_types if x in ALLOWED_SHOT_TYPES]
        if not shot_types:
            shot_types = _heuristic_shot_types(scene_text)
        source_pref = _safe_str(sc.get("source_preference")).strip() or DEFAULT_SOURCE_PREFERENCE
        focus = sc.get("focus_entities") if isinstance(sc.get("focus_entities"), list) else []
        focus = [_safe_str(x).strip() for x in focus if _safe_str(x).strip()]
        if not focus:
            focus = _extract_focus_entities(scene_text)

        # Deterministic "canonical" outputs required by AAR/CB.
        keywords = _keywords_for_scene(scene_text, focus, shot_types)
        queries = _queries_for_scene(scene_text, focus, shot_types, episode_topic=episode_topic)

        # Clip-length policy based on rhythm (deterministic).
        clip_range = [5, 8]
        if cut_rhythm == "slow":
            clip_range = [7, 12]
        elif cut_rhythm == "fast":
            clip_range = [3, 6]

        compiled_scenes.append(
            {
                "scene_id": sid,
                "start_sec": start_sec,
                "end_sec": end_sec,
                "narration_block_ids": nbids,
                "narration_summary": _first_sentence_summary(scene_text, max_words=22),
                "emotion": emotion,
                "keywords": keywords,  # exactly 8 (compiler-guaranteed)
                "search_queries": queries,  # exactly 5 (compiler-guaranteed)
                "shot_strategy": {
                    "clip_length_sec_range": clip_range,
                    "cut_rhythm": cut_rhythm,
                    "shot_types": shot_types,
                    "source_preference": source_pref,
                },
            }
        )

    # Last-resort: if nothing compiled, create 1 scene covering all blocks.
    if not compiled_scenes and expected:
        txt = " ".join([text_map.get(b, "") for b in expected]).strip()
        compiled_scenes = [
            {
                "scene_id": "sc_0001",
                "start_sec": 0,
                "end_sec": max(2, int(round(estimate_speech_duration_seconds(txt, words_per_minute=words_per_minute) or 5.0))),
                "narration_block_ids": expected,
                "narration_summary": _first_sentence_summary(txt, max_words=22),
                "emotion": "neutral",
                "keywords": _keywords_for_scene(txt, _extract_focus_entities(txt), ["archival_documents"]),
                "search_queries": _queries_for_scene(txt, _extract_focus_entities(txt), ["archival_documents"], episode_topic=episode_topic),
                "shot_strategy": {
                    "clip_length_sec_range": [5, 8],
                    "cut_rhythm": "medium",
                    "shot_types": ["archival_documents", "atmosphere_transition"],
                    "source_preference": DEFAULT_SOURCE_PREFERENCE,
                },
            }
        ]
        warnings.append({"code": "SHOTPLAN_SINGLE_SCENE_FALLBACK", "message": "No valid scenes compiled; created a single fallback scene"})

    total_duration_sec = int(compiled_scenes[-1]["end_sec"]) if compiled_scenes else 0
    shot_plan = {
        "version": SHOTPLAN_V3_VERSION,
        "source": "tts_ready_package",
        "assumptions": {"words_per_minute": int(words_per_minute)},
        "scenes": compiled_scenes,
        "total_scenes": len(compiled_scenes),
        "total_duration_sec": total_duration_sec,
    }
    return {"shot_plan": shot_plan}, warnings


def validate_shotplan_v3_minimal(
    shot_plan_wrapper: Dict[str, Any],
    tts_ready_package: Dict[str, Any],
    episode_id: Optional[str] = None,
) -> None:
    """
    Minimal hard-gate validator (format only; no stylistic policing):
    - wrapper + version
    - monotonic non-overlapping timeline
    - narration_block coverage: each block must appear at least once
    - exactly 8 keywords + 5 queries per scene, and non-empty strings
    """
    if not (isinstance(shot_plan_wrapper, dict) and isinstance(shot_plan_wrapper.get("shot_plan"), dict)):
        raise RuntimeError("SHOTPLAN_V3_INVALID: wrapper_missing_shot_plan")
    sp = shot_plan_wrapper["shot_plan"]
    if sp.get("version") != SHOTPLAN_V3_VERSION:
        raise RuntimeError(f"SHOTPLAN_V3_INVALID: version={sp.get('version')}")
    if sp.get("source") != "tts_ready_package":
        raise RuntimeError(f"SHOTPLAN_V3_INVALID: source={sp.get('source')}")

    scenes = sp.get("scenes") if isinstance(sp.get("scenes"), list) else []
    if not scenes:
        raise RuntimeError("SHOTPLAN_V3_INVALID: no_scenes")

    expected = _expected_block_ids(tts_ready_package)
    expected_set = set(expected)
    used: set = set()

    prev_end = None
    for i, sc in enumerate(scenes):
        if not isinstance(sc, dict):
            raise RuntimeError(f"SHOTPLAN_V3_INVALID: scene_not_object index={i}")
        start = sc.get("start_sec")
        end = sc.get("end_sec")
        if not isinstance(start, int) or not isinstance(end, int):
            raise RuntimeError(f"SHOTPLAN_V3_INVALID: non_int_timing scene_index={i}")
        if start < 0 or end <= start:
            raise RuntimeError(f"SHOTPLAN_V3_INVALID: bad_timing scene_index={i} start={start} end={end}")
        if prev_end is not None and start != prev_end:
            raise RuntimeError(f"SHOTPLAN_V3_INVALID: non_monotonic scene_index={i} start={start} prev_end={prev_end}")
        prev_end = end

        nbids = sc.get("narration_block_ids") if isinstance(sc.get("narration_block_ids"), list) else []
        for b in nbids:
            bid = _safe_str(b).strip()
            if bid in expected_set:
                used.add(bid)

        keywords = sc.get("keywords") if isinstance(sc.get("keywords"), list) else []
        queries = sc.get("search_queries") if isinstance(sc.get("search_queries"), list) else []
        if len(keywords) != 8:
            raise RuntimeError(f"SHOTPLAN_V3_INVALID: keywords_count scene_index={i} count={len(keywords)}")
        if len(queries) != 5:
            raise RuntimeError(f"SHOTPLAN_V3_INVALID: queries_count scene_index={i} count={len(queries)}")
        if any(not _safe_str(x).strip() for x in keywords):
            raise RuntimeError(f"SHOTPLAN_V3_INVALID: empty_keyword scene_index={i}")
        if any(not _safe_str(x).strip() for x in queries):
            raise RuntimeError(f"SHOTPLAN_V3_INVALID: empty_query scene_index={i}")

    missing = [b for b in expected if b not in used]
    if missing:
        raise RuntimeError(
            f"SHOTPLAN_V3_INVALID: coverage_missing_blocks count={len(missing)} episode_id={episode_id or ''}"
        )




