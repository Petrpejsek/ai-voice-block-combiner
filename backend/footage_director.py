"""
Footage Director Assistant (FDA) - 6. krok v pipeline

LLM-assisted planning assistant který generuje shot_plan JSON ze tts_ready_package.
Používá LLM (gpt-4o-mini) pro kreativní rozhodnutí + deterministickou validaci.

ŽÁDNÉ externí API (Archive.org, Pexels, YouTube)
ŽÁDNÉ stahování videí
ŽÁDNÉ renderování/ffmpeg/moviepy
POUZE JSON plánování
"""

import json
import re
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime, timezone

# Pre-FDA Sanitizer (deterministická jazyková disciplína)
try:
    from pre_fda_sanitizer import sanitize_and_log
    PRE_FDA_SANITIZER_AVAILABLE = True
    print("✅ Pre-FDA Sanitizer úspěšně načten")
except ImportError as e:
    print(f"❌ Chyba při importu Pre-FDA Sanitizer: {e}")
    PRE_FDA_SANITIZER_AVAILABLE = False

# Query Guardrails (systematic query validation)
try:
    from query_guardrails import validate_and_fix_queries
    QUERY_GUARDRAILS_AVAILABLE = True
    print("✅ Query Guardrails úspěšně načteny")
except ImportError as e:
    print(f"❌ CRITICAL: Query Guardrails import failed: {e}")
    print("❌ Pipeline will FAIL on query generation without guardrails!")
    QUERY_GUARDRAILS_AVAILABLE = False
    # NOTE: We still allow pipeline to start, but it will HARD FAIL on first query generation
    # This is better than silent degradation

# ============================================================================
# FDA VERSION CONSTANT (used throughout the module)
# ============================================================================
FDA_V27_VERSION = "fda_v2.7"


def coerce_fda_v27_version_inplace(
    shot_plan_wrapper: Any,
    episode_id: Optional[str] = None,
) -> bool:
    """
    v2.7 kill-switch: ensure shot_plan.version == FDA_V27_VERSION.

    IMPORTANT:
    - Only intended for FDA v2.7 flow.
    - Logs FDA_VERSION_COERCED only when a change is required.

    Returns:
        True if version was coerced, False otherwise.
    """
    try:
        sp = None
        if isinstance(shot_plan_wrapper, dict) and isinstance(shot_plan_wrapper.get("shot_plan"), dict):
            sp = shot_plan_wrapper["shot_plan"]
        elif isinstance(shot_plan_wrapper, dict) and isinstance(shot_plan_wrapper.get("scenes"), list):
            # raw shot_plan dict (no wrapper)
            sp = shot_plan_wrapper

        if not isinstance(sp, dict):
            return False

        got = sp.get("version")
        if got != FDA_V27_VERSION:
            sp["version"] = FDA_V27_VERSION
            print(f"FDA_VERSION_COERCED episode_id={episode_id} got={got} forced={FDA_V27_VERSION}")
            return True
        return False
    except Exception:
        return False

# ============================================================================
# v3 contracts (LLM ScenePlan vs deterministic ShotPlan compiler)
# ============================================================================
try:
    from visual_planning_v3 import SCENEPLAN_V3_VERSION, SHOTPLAN_V3_VERSION
except Exception:
    SCENEPLAN_V3_VERSION = "sceneplan_v3"
    SHOTPLAN_V3_VERSION = "shotplan_v3"


def _now_iso() -> str:
    """Vrací ISO timestamp pro metadata"""
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


# ============================================================================
# CONCRETE NOUN VALIDATION (new - for hard gate)
# ============================================================================

# Forbidden verb/adjective endings that indicate non-concrete-nouns
FORBIDDEN_KEYWORD_PATTERNS = {
    # Verb forms
    r'\w+ing$',      # capturing, approaching, spreading, entering, leaving
    r'\w+ed$',       # entered, abandoned, ordered, refused, arrived
    
    # Adjective forms  
    r'\w+al$',       # diplomatic, spiritual, tactical,etical
    r'\w+ly$',       # likely, largely, unreliable (adverbs too)
    r'\w+ive$',      # offensive, defensive, massive
    r'\w+ous$',      # glorious, disastrous
}

# Explicit forbidden keywords (verbs, adjectives, abstracts that slip through patterns)
# NOTE: "troop movement" is NOT in this list - it's a valid shot_type (troop_movement enum).
# Pre-FDA sanitizer handles it in keywords/search_queries with soft sanitization (no fail).
EXPLICIT_FORBIDDEN_KEYWORDS = {
    # Verbs
    "capturing", "entering", "abandoned", "left", "arrived", "ordered", "removal",
    "began", "spread", "approaching", "refused", "fleeing", "evacuating",
    "destroyed", "burning", "looting", "pillaging", "attacking", "defending",
    "sent", "broke",
    
    # Adjectives/abstracts
    "spiritual", "diplomatic", "tactical", "strategic", "unreliable",
    "massive", "significant", "important", "crucial",
    "before", "multiple", "locations", "three", "quarters", "first",
    "offers", "silence", "historic",
    
    # Concepts that need concrete proxy
    "capital",  # Must be "city of X" or "X capital building"
    "treaty",   # Must be "treaty document" or "signed treaty"
}


def _is_concrete_noun(keyword: str) -> Tuple[bool, Optional[str]]:
    """
    Check if keyword is a concrete visual noun (not verb/adjective/abstract).
    
    Returns:
        (is_valid, rejection_reason)
    """
    kw_lower = keyword.lower().strip()
    
    if not kw_lower:
        return False, "empty"
    
    # Check explicit forbidden list
    if kw_lower in EXPLICIT_FORBIDDEN_KEYWORDS:
        return False, f"forbidden_explicit_{kw_lower}"

    # Phrase-level constraints for abstract tokens that must be proxied into concrete artefacts
    # - Allow "treaty" only when it is explicitly an artefact (document/manuscript)
    if re.search(r"\btreaty\b", kw_lower) and not any(x in kw_lower for x in ("document", "manuscript", "documents", "manuscripts")):
        return False, "treaty_requires_document"
    # - Disallow "capital" anywhere (must be proxied, e.g. "city center", "government buildings")
    if re.search(r"\bcapital\b", kw_lower):
        return False, "capital_requires_proxy"
    
    # Check verb/adjective patterns
    for pattern in FORBIDDEN_KEYWORD_PATTERNS:
        if re.match(pattern, kw_lower):
            # Exception: common concrete nouns ending in -ing/-ed
            exceptions = {"building", "painting", "engraving", "drawing", "meeting", "wedding"}
            if kw_lower not in exceptions:
                return False, f"pattern_match_{pattern}"
    
    # Additional check: multi-word phrases should have noun at end
    words = kw_lower.split()
    if len(words) > 1:
        last_word = words[-1]
        # Last word should NOT be verb/adjective
        for pattern in FORBIDDEN_KEYWORD_PATTERNS:
            if re.match(pattern, last_word) and last_word not in {"building", "painting", "engraving"}:
                return False, f"multiword_bad_ending_{last_word}"
    
    return True, None


# ============================================================================
# NARRATION SUMMARY SANITY CHECK (new - for hard gate)
# ============================================================================

BROKEN_SENTENCE_PATTERNS = [
    r'\s+the\s+\.',              # "... the ."
    r'\s+of\s+\.',               # "... of ."
    r'\s+to\s+\.',               # "... to ."
    r'\bAs the continued\b',     # "As the continued, ..."
    r'\bthe French of Moscow\b', # "the French of Moscow" (bad grammar)
    r'\s{2,}',                   # Double whitespace
    r'^\s*\w+\s+the\s+\w*\s*,',  # "As the , ..." (missing subject)
    r'\bThe of\b',               # "The of Moscow" - article followed by preposition
    r'\bA of\b',                 # "A of ..." - article followed by preposition
    r'\bAn of\b',                # "An of ..." - article followed by preposition
    r"'s\s+,",                   # "Napoleon's ," - possessive with space before comma
    r"'s\s+\.",                  # "Napoleon's ." - possessive with space before period
    r'\s+,',                     # Any space before comma
    r',\s+,',                    # Double comma
    r'\.\s+\.',                  # Double period
    r'\bbecame a\s+[a-z]{1,4}\b(?!\w)',  # "became a fail" - incomplete phrase
    r'\bwas intended to be the\s+\w+\s+of\s+\w+\'s\s*,',  # Broken clause pattern
]


def _is_valid_narration_summary(summary: str) -> Tuple[bool, Optional[str]]:
    """
    Check if narration_summary is syntactically valid (no broken sentences).
    
    Returns:
        (is_valid, rejection_reason)
    """
    if not summary or not summary.strip():
        return False, "empty"
    
    # Check broken patterns
    for pattern in BROKEN_SENTENCE_PATTERNS:
        if re.search(pattern, summary):
            return False, f"broken_pattern_{pattern[:20]}"
    
    # Must have at least one sentence ending with period
    if not re.search(r'\.\s*$', summary):
        return False, "no_sentence_ending"
    
    # Check for placeholder fragments (single words followed by comma with no context)
    # E.g., "As the, French soldiers..."
    if re.search(r'\b\w{1,3}\s+\w{1,3}\s*,', summary):
        # Too aggressive? Let's check for specific bad patterns
        pass
    
    return True, None


def _generate_deterministic_summary(text_tts: str, max_words: int = 20) -> str:
    """
    Generate narration_summary DETERMINISTICALLY from the first sentence of text_tts.
    No LLM paraphrasing - just truncation.
    
    Rules:
    - First complete sentence, truncated to 18-22 words
    - Must preserve all named anchors (Napoleon, Moscow, 1812, etc.)
    - No creative paraphrasing (avoids broken LLM outputs like "through his of Russia")
    
    Args:
        text_tts: The full narration text
        max_words: Maximum number of words (default 20)
    
    Returns:
        Deterministic summary string
    """
    if not text_tts or not text_tts.strip():
        return ""
    
    text = text_tts.strip()
    
    # Extract first sentence (ending with . ! ? or ...)
    # Be careful with abbreviations like "Dr." "Mr." etc.
    sentence_end_pattern = r'(?<![A-Z][a-z])(?<!\b(?:Dr|Mr|Mrs|Ms|St|etc|vs|i\.e|e\.g))[\.\!\?]+(?:\s|$)'
    match = re.search(sentence_end_pattern, text)
    
    if match:
        first_sentence = text[:match.end()].strip()
    else:
        # No sentence end found - use first N words
        first_sentence = text
    
    # Count words
    words = first_sentence.split()
    
    if len(words) <= max_words:
        # Short enough - return as is
        summary = first_sentence
    else:
        # Truncate to max_words, but try to end at a natural break
        truncated_words = words[:max_words]
        
        # Try to find a good break point (end of clause)
        for i in range(len(truncated_words) - 1, max(len(truncated_words) - 5, 0), -1):
            word = truncated_words[i]
            # Good break points: after comma, before conjunction
            if word.endswith(',') or truncated_words[i].lower() in ('and', 'but', 'or', 'as', 'when', 'while'):
                truncated_words = truncated_words[:i]
                break
        
        summary = ' '.join(truncated_words)
        
        # Clean up trailing conjunctions/prepositions
        summary = re.sub(r'\s+(?:and|but|or|of|the|a|an|to|in|on|for|with|as)\s*$', '', summary, flags=re.IGNORECASE)
    
    # Ensure proper sentence ending
    summary = summary.rstrip(' .,;:!?')
    # Remove trailing prepositions/articles that make broken sentences
    summary = re.sub(r'\s+(?:and|but|or|of|the|a|an|to|in|on|for|with|as|by|from)\s*$', '', summary, flags=re.IGNORECASE)
    # Clean any trailing whitespace
    summary = summary.rstrip()
    if summary:
        summary += '.'
    # Final sanitization: remove any space before period
    summary = re.sub(r'\s+\.', '.', summary)
    # Ensure no double periods
    summary = re.sub(r'\.+', '.', summary)
    
    return summary


def _extract_anchors_from_text(text: str) -> List[str]:
    """Extract named anchors (proper nouns, years, places) from text."""
    anchors = []
    
    # Proper nouns (capitalized words, but not sentence-initial)
    # Pattern: word preceded by space + capital letter
    proper_nouns = re.findall(r'(?<=\s)[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*', ' ' + text)
    anchors.extend(proper_nouns)
    
    # Years (1700-1900 range typically for historical content)
    years = re.findall(r'\b1[0-9]{3}\b', text)
    anchors.extend(years)
    
    return list(dict.fromkeys(anchors))  # Dedupe while preserving order


# ============================================================================
# QUERY AUTO-FIX (post-LLM deterministic repair)
# ============================================================================

VALID_ARTEFACTS = {
    "map", "engraving", "lithograph", "letter", "letters", "correspondence",
    "document", "documents", "manuscript", "manuscripts", "photograph",
    "photographs", "painting", "portrait"
}

PREFERRED_ARTEFACT_ORDER = ["engraving", "map", "manuscript", "letter"]


def _has_artefakt(query: str) -> bool:
    """Check if query contains a valid artefakt."""
    q_lower = query.lower()
    return any(art in q_lower for art in VALID_ARTEFACTS)


def _extract_anchor_from_query(query: str, narration_text: str) -> Optional[str]:
    """Extract anchor (proper noun/place/year) from query or narration."""
    # Check for proper noun in query
    proper_nouns = re.findall(r'\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*', query)
    if proper_nouns:
        return proper_nouns[0]
    
    # Check for year
    years = re.findall(r'\b1[0-9]{3}\b', query)
    if years:
        return years[0]
    
    # Fallback: extract from narration
    if narration_text:
        proper_nouns = re.findall(r'\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*', narration_text)
        if proper_nouns:
            return proper_nouns[0]
        
        years = re.findall(r'\b1[0-9]{3}\b', narration_text)
        if years:
            return years[0]
    
    return None


def _fix_query_add_artefakt(query: str, narration_text: str, prefer_index: int = 0) -> Tuple[str, str]:
    """
    Fix query by adding artefakt if missing.
    
    Returns:
        (fixed_query, fix_reason)
    """
    # Extract anchor
    anchor = _extract_anchor_from_query(query, narration_text)
    
    if not anchor:
        # No anchor found - cannot fix safely
        return query, "no_anchor_found_cannot_fix"
    
    # Add preferred artefakt (must yield at least 3 words; archive/search safe)
    # Deterministically vary artefact choice to avoid collapsing multiple queries into duplicates.
    order = list(PREFERRED_ARTEFACT_ORDER) if PREFERRED_ARTEFACT_ORDER else ["engraving", "map", "manuscript", "letter"]
    start = int(prefer_index or 0) % max(1, len(order))
    for j in range(len(order)):
        artefakt = order[(start + j) % len(order)]
        # Avoid adding blacklisted words; ensure >= 3 words
        candidate = f"archival {artefakt} {anchor}".strip()
        
        # Quick blacklist check (basic)
        if "battle" not in candidate.lower() and "warfare" not in candidate.lower():
            return candidate, f"added_{artefakt}"
    
    # Fallback
    return f"archival engraving {anchor}".strip(), "added_engraving_fallback"


# ============================================================================
# VIDEO-FIRST QUERY TOKENS (newsreel/footage/documentary)
# These tokens have HIGH hit rate on archive.org for video content
# ============================================================================
VIDEO_INTENT_TOKENS = [
    "documentary footage",
    "archival footage",
    "newsreel",
    "film footage",
    "historical footage",
]

# Context objects for video queries (things that appear in documentaries)
VIDEO_CONTEXT_OBJECTS = [
    "battle",
    "army",
    "military",
    "city",
    "soldiers",
    "map",
    "ruins",
]


def _generate_video_first_queries(anchors: List[str]) -> List[str]:
    """
    Generate 2 video-first queries with high archive.org hit rate.
    Format: "anchor video_intent_token [context]"
    Example: "Napoleon 1812 documentary footage", "Moscow archival footage"
    """
    if not anchors:
        anchors = ["historical", "archival"]
    
    a1 = anchors[0] if len(anchors) > 0 else "historical"
    a2 = anchors[1] if len(anchors) > 1 else ""
    
    video_queries = []
    
    # Primary video query: anchor + documentary footage
    video_queries.append(f"{a1} documentary footage".strip())
    
    # Secondary video query: different anchor or context + archival footage
    if a2:
        video_queries.append(f"{a2} archival footage".strip())
    else:
        video_queries.append(f"{a1} archival newsreel".strip())
    
    return video_queries[:2]


def _generate_fallback_queries(narration_text: str, scene_id: str) -> List[str]:
    """
    Generate safe fallback queries when FDA fails completely.
    VIDEO-FIRST: First 2 queries are video-friendly (newsreel/footage/documentary).
    Uses anchors from narration + safe artefacts.
    """
    # Extract anchors from narration
    anchors = []
    
    # Proper nouns
    proper_nouns = re.findall(r'\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*', narration_text)
    anchors.extend(proper_nouns[:3])
    
    # Years
    years = re.findall(r'\b1[0-9]{3}\b', narration_text)
    anchors.extend(years[:1])
    
    if not anchors:
        # Ultra-safe generic fallback
        anchors = ["historical", "archival"]
    
    anchors_norm = [str(a or "").strip() for a in anchors if str(a or "").strip()]
    anchors_low = [a.lower() for a in anchors_norm]
    
    # ============================================================================
    # VIDEO-FIRST: First 2 queries are always video-friendly
    # ============================================================================
    video_queries = _generate_video_first_queries(anchors_norm[:2])

    # Context-specific queries (high hit-rate, video-first then document fallback)
    if any(a == "moscow" for a in anchors_low):
        return video_queries + [
            "Moscow Russia documentary footage",
            "Moscow city archival footage",
            "Moscow Kremlin engraving",
            "archival military map Moscow",
        ][:6]

    if any("borodino" in a for a in anchors_low):
        return video_queries + [
            "Borodino battle documentary footage",
            "Borodino historical footage",
            "Borodino area map",
            "archival map Borodino",
        ][:6]

    if any("napoleon" in a for a in anchors_low):
        return video_queries + [
            "Napoleon documentary footage",
            "Napoleonic Wars archival footage",
            "Napoleon portrait engraving",
            "French army 1812 documentary",
        ][:6]

    # Generic deterministic fallback: VIDEO-FIRST + artefakt
    a1 = anchors_norm[0] if anchors_norm else "historical"
    a2 = anchors_norm[1] if len(anchors_norm) > 1 else ""
    out = video_queries + [
        f"{a1} historical documentary footage",
        f"archival map {a1}".strip(),
        f"archival engraving {a1}".strip(),
        f"archival map {a2}".strip() if a2 else "",
    ]
    return [q for q in out if q][:6]


def _generate_deterministic_queries_v27(narration_text: str, scene_index: int) -> List[str]:
    """
    Generate EXACTLY 5 search queries deterministically from narration text.
    
    This is a PURE DETERMINISTIC function - no LLM, no "fixing", just generation.
    Always produces v2.7 compliant queries.
    
    Returns: List of exactly 5 queries, each 5-9 words, each with exactly 1 object type.
    """
    # Object types for rotation (one per query) - EXACTLY ONE per query
    obj_types = ["engraving", "map", "photograph", "illustration", "manuscript"]
    
    # Extensive skip list
    skip_words = {
        # Articles, prepositions, conjunctions
        "the", "a", "an", "upon", "soon", "after", "before", "during", "while",
        "and", "or", "but", "yet", "so", "with", "without", "into", "onto", "from", "to",
        "this", "that", "these", "those", "he", "she", "they", "it", "his", "her", "their", "its",
        "who", "which", "what", "when", "where", "how", "why", "as", "if", "then", "than",
        "began", "following", "although", "however", "therefore", "because", "since",
        # Common verbs
        "in", "on", "at", "for", "of", "was", "were", "is", "are", "been", "being",
        "have", "has", "had", "do", "does", "did", "will", "would", "could", "should",
        "may", "might", "must", "shall",
        # Ordinals and common words
        "first", "second", "third", "fourth", "fifth", "last", "next", "other",
        "many", "some", "most", "such", "only", "very", "just", "also", "even",
        # Generic terms
        "army", "battle", "war", "fire", "city", "forces", "troops", "system",
        "grande", "arm", "armée", "continental",
    }
    
    # Extract proper nouns (min 4 chars, not -ing/-ed/-ly)
    proper_nouns = re.findall(r'\b([A-Z][a-z]{3,})', narration_text)
    years = re.findall(r'\b(1[0-9]{3})\b', narration_text)
    
    anchors = [n for n in proper_nouns 
               if n.lower() not in skip_words 
               and len(n) >= 4
               and not n.lower().endswith('ing')
               and not n.lower().endswith('ed')
               and not n.lower().endswith('ly')
              ]
    anchors = list(dict.fromkeys(anchors))[:6]
    
    # Add years if found
    if years:
        anchors.extend(years[:2])
    
    # Safe fallbacks if not enough anchors
    if len(anchors) < 3:
        anchors = anchors + ["historical military", "period archive", "official records"]
    
    queries = []
    seen = set()
    
    for i in range(5):
        anchor = anchors[i % len(anchors)]
        obj_type = obj_types[i]  # Different object type for each query
        
        # Templates with EXACTLY 6 words each, EXACTLY 1 object type
        # Using scene_index to add variety between scenes
        variant = (scene_index + i) % 5
        templates = [
            f"historical {anchor} original {obj_type} collection",
            f"{anchor} period {obj_type} archive material",
            f"archival {anchor} {obj_type} museum collection",
            f"{anchor} historical {obj_type} archive piece",
            f"original {anchor} period {obj_type} record",
        ]
        
        query = templates[variant]
        
        # Ensure unique
        if query.lower() not in seen:
            queries.append(query)
            seen.add(query.lower())
        else:
            # Fallback with scene index for uniqueness
            fallback = f"historical scene{scene_index} {obj_type} archive record"
            queries.append(fallback)
    
    # Ensure exactly 5
    while len(queries) < 5:
        idx = len(queries)
        queries.append(f"historical archive {obj_types[idx]} collection material")
    
    return queries[:5]


def _filter_keyword_forbidden_tokens(keyword: str) -> bool:
    """
    Check if keyword contains forbidden tokens (returns True if clean, False if forbidden).
    
    Forbidden tokens per spec: the, a, an, this, these, those, that, and, or, but, 
    so, because, while, upon, after, before, during, within, without, toward + periods.
    """
    # Tokenize keyword (split by spaces and punctuation)
    tokens = re.findall(r'\b\w+\b', keyword.lower())
    
    forbidden_tokens = {
        "the", "a", "an", "this", "these", "those", "that",
        "and", "or", "but", "so", "because", "while",
        "upon", "after", "before", "during", "within", "without", "toward",
    }
    
    for token in tokens:
        if token in forbidden_tokens:
            return False
    
    # Check for periods
    if '.' in keyword:
        return False
    
    return True


def _validate_keywords_v27(keywords: List[str]) -> Tuple[bool, str]:
    """
    Validate keywords against v2.7 rules.
    
    Returns: (is_valid, reason_if_invalid)
    """
    # Must be exactly 8 keywords
    if len(keywords) != 8:
        return False, f"Expected 8 keywords, got {len(keywords)}"
    
    # Check each keyword
    object_type_count = 0
    for i, kw in enumerate(keywords):
        kw_str = str(kw or "").strip()
        
        # Must be 2-5 words
        word_count = len(kw_str.split())
        if word_count < 2 or word_count > 5:
            return False, f"Keyword {i}: '{kw_str[:30]}' has {word_count} words (need 2-5)"
        
        # Must not contain forbidden tokens
        if not _filter_keyword_forbidden_tokens(kw_str):
            return False, f"Keyword {i}: '{kw_str[:30]}' contains forbidden token"
        
        # Count object types
        if _contains_object_type(kw_str, FDA_V27_PHYSICAL_OBJECT_TYPES):
            object_type_count += 1
    
    # At least 3 keywords must contain object type
    if object_type_count < 3:
        return False, f"Only {object_type_count}/3 keywords contain object type"
    
    return True, ""


def _generate_deterministic_keywords_v27(
    narration_text: str,
    max_retries: int = 2,
    episode_anchor_hints: Optional[List[str]] = None,
) -> List[str]:
    """
    Generate EXACTLY 8 keywords deterministically from narration text with GUARDRAILS.
    
    GUARDRAILS:
    - Exactly 8 keywords
    - Each 2-5 words
    - NO forbidden tokens (the, a, an, this, these, those, that, and, or, but, so, 
      because, while, upon, after, before, during, within, without, toward, periods)
    - Min 3 keywords contain object type (map, engraving, letter, document, ruins, etc.)
    - Retry mechanism: max 2 attempts to generate valid keywords
    
    Returns: List of exactly 8 keywords.
    """
    for attempt in range(max_retries):
        scene_type = _detect_scene_type(narration_text)

        # Prefer real anchors from narration; avoid generic filler fallbacks like "Period/Military/Archive".
        # If not enough anchors are found, we still keep output deterministic and relevant by using stable,
        # episode-local anchors (proper nouns + year).
        skip_words = {
            # Forbidden tokens
            "the", "a", "an", "this", "these", "those", "that",
            "and", "or", "but", "so", "because", "while",
            "upon", "after", "before", "during", "within", "without", "toward",
            # Common glue words
            "in", "on", "at", "for", "of", "from", "to", "into", "onto", "with",
            # Pronouns
            "he", "she", "they", "it", "his", "her", "their", "its",
            # Other common non-anchors
            "began", "following", "although", "however", "therefore", "since",
            "first", "second", "third", "last", "next",
            # Generic terms (not helpful as anchors)
            "army", "battle", "war", "fire", "city", "forces", "troops", "movement",
        }

        raw_terms = _extract_anchor_terms_from_text_v27(narration_text, max_terms=24)
        if episode_anchor_hints:
            raw_terms = [str(x) for x in episode_anchor_hints if isinstance(x, str) and x.strip()] + raw_terms
        
        # CRITICAL: Prefer multi-word anchors for FDA compliance (keywords need 2-5 words)
        # Sort anchors: multi-word phrases first, then single words
        raw_terms_sorted = sorted(raw_terms, key=lambda t: (len(t.split()) == 1, t))
        
        anchors: List[str] = []
        for t in raw_terms_sorted:
            t = str(t or "").strip()
            if not t:
                continue
            # Keywords must NOT contain forbidden tokens (incl. "of/and/the").
            parts = t.split()
            if any(p.lower() in FDA_V27_FORBIDDEN_KEYWORD_TOKENS for p in parts):
                continue
            if any(p.lower() in skip_words for p in parts):
                continue
            if t.lower() in _V27_ANCHOR_STOPWORDS:
                continue
            anchors.append(t)
            if len(anchors) >= 8:
                break

        # If still low-signal, keep deterministic but avoid off-topic anchors.
        if len(anchors) < 1:
            anchors = ["Archive"]

        # Scene-type-specific suffixes (2-3 words) optimized for archive retrieval.
        # Keep them concrete and avoid repeating the same generic pair across scenes.
        # Keep keywords as editor-friendly tags; avoid "map" unless the scene implies movement/context.
        suffixes_by_type = {
            "leaders": ["portrait engraving", "official letter", "decree document", "dispatch document", "archival photograph", "manuscript page"],
            "fire_ruins": ["burned ruins", "city ruins", "archival photograph", "illustration", "report document", "engraving"],
            "waiting_negotiation": ["official letter", "dispatch document", "decree document", "manuscript page", "document report", "archival photograph"],
            "movement": ["route map", "city map", "military map", "archival photograph", "document report", "engraving"],
            "generic": ["archival photograph", "official letter", "decree document", "document report", "engraving", "memorial monument"],
        }
        suffixes = suffixes_by_type.get(scene_type, suffixes_by_type["generic"])

        keywords: List[str] = []
        seen = set()

        # Build 8 anchor+suffix combos first (low repetition, high specificity).
        i = 0
        tries = 0
        while len(keywords) < 8 and tries < 64:
            tries += 1
            anchor = anchors[i % len(anchors)]
            suffix = suffixes[i % len(suffixes)]
            kw = f"{anchor} {suffix}".strip()
            i += 1

            # Ensure 2-5 words
            parts = kw.split()
            if len(parts) > 5:
                kw = " ".join(parts[:5])
            elif len(parts) < 2:
                continue

            # Must not contain forbidden tokens
            if not _filter_keyword_forbidden_tokens(kw):
                continue

            low = kw.lower()
            if low in seen:
                continue
            keywords.append(kw)
            seen.add(low)

        # If we still don't have 8 (rare), fill with safe concrete suffix-only keywords.
        fillers = ["archival photograph", "official letter", "decree document", "document report", "engraving", "manuscript page", "burned ruins", "memorial monument"]
        for fb in fillers:
            if len(keywords) >= 8:
                break
            if not _filter_keyword_forbidden_tokens(fb):
                continue
            if fb.lower() in seen:
                continue
            keywords.append(fb)
            seen.add(fb.lower())

        is_valid, reason = _validate_keywords_v27(keywords[:8])
        if is_valid:
            print(f"✅ Keywords generated successfully on attempt {attempt + 1}")
            # DEBUG: Log final keywords to verify FDA compliance
            for i, kw in enumerate(keywords[:8]):
                word_count = len(kw.split())
                print(f"   Keyword[{i}]: '{kw}' ({word_count} words)")
            return keywords[:8]
        print(f"⚠️  Keywords validation failed (attempt {attempt + 1}): {reason}")
    
    # If all retries failed, return best-effort fallback (guaranteed valid)
    print(f"⚠️  Keywords generation failed after {max_retries} attempts, using fallback")
    return [
        "archival photograph",
        "official letter",
        "decree document",
        "document report",
        "portrait engraving",
        "manuscript page",
        "burned ruins",
        "memorial monument",
    ]


def _detect_scene_type(narration_text: str) -> str:
    """
    Detect scene type from narration text for query template selection.
    
    Returns: "leaders" | "fire_ruins" | "waiting_negotiation" | "movement" | "generic"
    """
    text_lower = narration_text.lower()
    
    # Leaders scene: high-level leadership / authority figures
    if any(term in text_lower for term in ["president", "prime minister", "minister", "king", "queen", "emperor", "tsar", "general", "commander", "leader", "governor", "protector"]):
        return "leaders"
    
    # Fire/ruins scene: mentions fire, burned, destroyed, ruins, flames
    if any(term in text_lower for term in ["fire", "burned", "destroyed", "ruins", "flames", "destruction", "ash"]):
        return "fire_ruins"
    
    # Waiting/negotiation: mentions wait, negotiate, delegation, dispatch, offer, refuse
    if any(term in text_lower for term in ["wait", "negotiate", "delegation", "dispatch", "offer", "refuse", "treaty", "peace"]):
        return "waiting_negotiation"
    
    # Movement: mentions retreat, advance, march, route, journey, troops
    if any(term in text_lower for term in ["retreat", "advance", "march", "route", "journey", "troops", "army", "movement"]):
        return "movement"
    
    return "generic"


def _generate_deterministic_queries_v27(
    narration_text: str,
    scene_index: int,
    max_retries: int = 2,
    episode_anchor_hints: Optional[List[str]] = None,
) -> List[str]:
    """
    Generate EXACTLY 5 search queries deterministically with STRICT TEMPLATES.
    
    RULES:
    - Exactly 5 queries per scene
    - Each 5-9 words
    - Each contains: >=1 episode anchor (derived from narration text) + exactly 1 object type
    - Remaining 3 queries: rotate by scene type
    - NO forbidden starts: Following/Upon/Soon/Although/He/She/They/This/These/The/A/An
    - NO periods
    - Dedupe by varying object types
    
    Returns: List of exactly 5 queries.
    """
    scene_type = _detect_scene_type(narration_text)

    # Episode Anchor Lock: derive anchors from narration (and optional episode hints).
    # This prevents off-topic "Moscow/Monaco" contamination across episodes.
    anchor_terms = _extract_anchor_terms_from_text_v27(narration_text, max_terms=24)
    if episode_anchor_hints:
        # Put hints first (more stable across scenes), then scene-local terms.
        anchor_terms = [str(x) for x in episode_anchor_hints if isinstance(x, str) and x.strip()] + anchor_terms

    # Build a conservative set of "object-type words" to avoid accidentally introducing 2 object types.
    # (FDA validator requires EXACTLY 1 object type per query.)
    _obj_type_words: set = set()
    for _ot in FDA_V27_QUERY_OBJECT_TYPES:
        for _w in str(_ot).lower().split():
            _obj_type_words.add(_w)

    # Prefer a year if available (optional).
    year = ""
    for t in anchor_terms:
        if re.fullmatch(r"(1\d{3}|20\d{2})", str(t).strip()):
            year = str(t).strip()
            break

    # Pick a primary anchor phrase (non-year, not stopword, not forbidden start).
    # CRITICAL: Primary anchor must NOT contain any object-type word (map/document/ruins/etc),
    # otherwise queries can end up with 2 object types (anchor contains one, obj_type adds another).
    primary_anchor = ""
    for t in anchor_terms:
        cand = str(t or "").strip()
        if not cand:
            continue
        if re.fullmatch(r"(1\d{3}|20\d{2})", cand):
            continue
        if cand.lower() in _V27_ANCHOR_STOPWORDS:
            continue
        first = cand.split()[0].lower() if cand.split() else ""
        if first in FDA_V27_FORBIDDEN_QUERY_STARTS:
            continue
        # Reject anchors that contain object-type words (or match an object type phrase).
        cand_words = {w.lower() for w in re.findall(r"[0-9A-Za-zÀ-ž]+(?:[-'][0-9A-Za-zÀ-ž]+)*", cand)}
        if cand_words & _obj_type_words:
            continue
        if _count_object_types(cand, FDA_V27_QUERY_OBJECT_TYPES) != 0:
            continue
        primary_anchor = cand
        break
    if not primary_anchor:
        # NO FALLBACKS: deterministic generator MUST have a real anchor.
        raise RuntimeError("LOCAL_PREFLIGHT_FAILED: NO_PRIMARY_ANCHOR_FOR_QUERIES")

    # Extract 2-3 content terms from narration_text to avoid guardrails TOO_SHORT.
    # These terms must NOT be object-type words and must not be generic filler.
    def _extract_content_terms(text: str, max_terms: int = 3) -> List[str]:
        if not text or not isinstance(text, str):
            return []
        stop = {
            # articles / connectors
            "the", "a", "an", "of", "in", "on", "at", "to", "for", "with", "without",
            "and", "or", "but", "so", "because", "while", "upon", "after", "before", "during",
            # generic
            "historical", "history", "events", "event", "context", "background",
            "archive", "archival", "archived", "original",
            "print", "scan", "copy", "page", "view", "aftermath",
            "city", "town", "village", "country", "empire",
        }
        words = re.findall(r"[0-9A-Za-zÀ-ž]+(?:[-'][0-9A-Za-zÀ-ž]+)*", text.lower())
        out: List[str] = []
        seen = set()
        for w in words:
            if len(w) < 5:
                continue
            if w in stop:
                continue
            if w in _obj_type_words:
                continue
            if w.isdigit():
                continue
            if w in seen:
                continue
            seen.add(w)
            out.append(w)
            if len(out) >= max_terms:
                break
        return out

    content_terms = _extract_content_terms(narration_text, max_terms=3)

    # Pick object types per scene type (artifact-specific, archive-friendly)
    by_type = {
        "leaders": ["engraving", "letter", "document", "manuscript", "dispatch"],
        "fire_ruins": ["burned ruins", "photograph", "engraving", "illustration", "report"],
        "waiting_negotiation": ["letter", "dispatch", "document", "manuscript", "decree"],
        "movement": ["route map", "city map", "engraving", "document", "report"],
        "generic": ["city map", "engraving", "document", "letter", "photograph"],
    }
    base_types = by_type.get(scene_type, by_type["generic"])
    # Rotate deterministically by scene_index for variety across scenes.
    shift = scene_index % len(base_types)
    object_types = base_types[shift:] + base_types[:shift]

    # Tail words per object type (must avoid introducing a second object type token)
    tail = {
        "city map": "archive scan",
        "route map": "archive scan",
        "engraving": "original print",
        "photograph": "archive print",
        "illustration": "original print",
        "manuscript": "archive page",
        "letter": "original handwriting",
        "dispatch": "archive copy",
        "decree": "official copy",
        "document": "archive scan",
        "report": "archive copy",
        "burned ruins": "aftermath view",
        "ruins": "aftermath view",
        "kremlin interior": "archive view",
        "city street": "archive view",
    }

    def _mk(anchor_phrase: str, year: str, obj_type: str) -> str:
        t = tail.get(obj_type, "archive scan")
        # Build query tokens deterministically; include content terms to satisfy guardrails TOO_SHORT.
        tokens: List[str] = []
        if anchor_phrase:
            tokens.extend(str(anchor_phrase).split())
        if year:
            tokens.append(year)
        # Add up to 2 content terms (not object-type words)
        for ct in content_terms[:2]:
            tokens.append(ct)
        tokens.extend(str(obj_type).split())
        tokens.extend(str(t).split())

        q = " ".join(tokens).strip()
        q = q.replace(".", "")
        # Normalize whitespace
        q = re.sub(r"\s+", " ", q).strip()
        # Ensure word count 5-9 by trimming only; if too short, add a deterministic non-object term.
        words = q.split()
        if len(words) < 5:
            # Prefer an extra content term if available, else add a neutral adjective.
            extra = content_terms[2] if len(content_terms) >= 3 else "notable"
            q = f"{q} {extra}".strip()
            q = re.sub(r"\s+", " ", q).strip()
            words = q.split()
        if len(words) > 9:
            q = " ".join(words[:9])
        return q

    queries: List[str] = []
    # Build queries with consistent episode anchor, rotate object types for variety.
    queries.append(_mk(primary_anchor, year, object_types[0]))
    queries.append(_mk(primary_anchor, year, object_types[1]))
    queries.append(_mk(primary_anchor, year, object_types[2]))
    queries.append(_mk(primary_anchor, year, object_types[3]))
    queries.append(_mk(primary_anchor, year, object_types[4]))

    cleaned: List[str] = []
    for q in queries[:5]:
        q = re.sub(r"\s+", " ", (q or "").strip())
        if not q:
            continue
        # Forbidden starts guard
        first = q.split()[0].lower() if q.split() else ""
        if first in FDA_V27_FORBIDDEN_QUERY_STARTS:
            q = f"{primary_anchor} {q}".strip()
        # Hard enforce 5-9 words (trim only; never pad with low-signal fillers)
        words = q.split()
        if len(words) < 5:
            # Add a safe token that is NOT an object type to reach minimum.
            q = f"{q} archive"
            words = q.split()
        if len(words) > 9:
            q = " ".join(words[:9])
        cleaned.append(q)

    # Ensure each query contains EXACTLY 1 object type (contract).
    final: List[str] = []
    seen = set()
    for qi, q in enumerate(cleaned):
        if _count_object_types(q, FDA_V27_QUERY_OBJECT_TYPES) != 1:
            # NO FALLBACK: this is a generator bug that must be fixed, fail loudly.
            raise RuntimeError(f"LOCAL_PREFLIGHT_FAILED: QUERY_OBJECT_TYPE_COUNT_NOT_1: '{q}'")
        low = q.lower()
        if low in seen:
            # Minor deterministic de-dupe: swap object type within the same scene.
            forced_obj = object_types[(qi + 1) % len(object_types)]
            q2 = _mk(primary_anchor, year, forced_obj)
            if _count_object_types(q2, FDA_V27_QUERY_OBJECT_TYPES) == 1:
                q = q2
                low = q.lower()
        seen.add(low)
        final.append(q)

    return final[:5]


def _generate_deterministic_summary_v27(narration_text: str) -> str:
    """
    Generate narration_summary DETERMINISTICALLY from narration text.
    
    MEANING-LOCK RULES (compress, not drop):
    - Process ALL sentences from text_tts (not just first)
    - Compress by removing filler words and redundancy
    - Join clauses with connecting words (and, while, as)
    - ONE sentence, NO semicolons, ends with exactly one period
    - Target ~15-20 words for readability
    
    Returns: Clean, valid summary string.
    """
    if not narration_text or not narration_text.strip():
        return "Historical events unfold."

    text = narration_text.strip()

    # Split into sentences (loose; we will rebuild exactly ONE sentence)
    sentences = re.split(r"[.!?]+", text)
    sentences = [s.strip() for s in sentences if s.strip() and len(s.strip()) > 8]

    if not sentences:
        return "Historical events unfold."

    # Prefer using a full, already-grammatical sentence rather than truncating mid-phrase.
    s1 = sentences[0]
    s2 = sentences[1] if len(sentences) > 1 else ""

    # If the first sentence is very short, append a second clause to keep meaning.
    base = s1
    if len(s1.split()) < 12 and s2:
        base = f"{s1} and {s2}"

    # Remove leading discourse markers
    base = re.sub(
        r"^(However|Moreover|Furthermore|Additionally|Meanwhile|Thus|Therefore|Hence|Indeed|In fact|In short)\s*,?\s*",
        "",
        base,
        flags=re.IGNORECASE,
    )

    # Remove parentheticals (often asides) and compress whitespace
    base = re.sub(r"\([^)]*\)", "", base)
    base = re.sub(r"\s+", " ", base).strip()

    # Remove trailing subordinate clause starting with which/that/who (keep main meaning)
    base = re.split(r",?\s+(which|that|who)\b", base, maxsplit=1, flags=re.IGNORECASE)[0].strip()

    # Soft length cap: trim by words, but never leave a dangling preposition/article at the end.
    max_words = 28
    stop_end = {"the", "a", "an", "of", "to", "in", "on", "for", "with", "and", "but", "or", "as", "by", "from", "that", "which", "who"}
    words = base.split()
    if len(words) > max_words:
        words = words[:max_words]
        while words and words[-1].lower() in stop_end:
            words = words[:-1]
        base = " ".join(words).strip()

    # Normalize punctuation: no internal sentence terminators; exactly one period at end.
    base = base.replace(";", ",")
    base = re.sub(r"[!?]+", "", base)
    base = base.replace(".", "")
    base = base.strip().rstrip(",")

    if not base:
        return "Historical events unfold."

    # Capitalize first letter (cosmetic; keeps validator happy and improves readability)
    base = base[0].upper() + base[1:] if base else base

    summary = base + "."
    summary = summary.replace(';', ',')
    
    # Ensure ends with period (remove all other punctuation first)
    summary = summary.rstrip(' .,;:!?')
    if summary:
        summary += '.'
    else:
        summary = "Historical events unfold."
    
    # Final check: remove double spaces
    summary = re.sub(r'\s+', ' ', summary)
    
    return summary


def _fix_shot_strategy_v27(scene: Dict[str, Any], narration_text: str) -> None:
    """
    Fix shot_strategy to ensure v2.7 compliance.
    
    - source_preference must be ["archive_org"]
    - shot_types max 2-3 types (conservative mapping)
    - For abstract blocks (waiting/negotiation): only archival_documents, maps_context, atmosphere_transition
    """
    shot_strategy = scene.get("shot_strategy", {})
    if not isinstance(shot_strategy, dict):
        shot_strategy = {}
    
    # Fix source_preference (MUST be ["archive_org"])
    shot_strategy["source_preference"] = ["archive_org"]
    
    # Analyze narration to determine appropriate shot_types
    text_lower = narration_text.lower()
    shot_types = []
    
    # Conservative mapping: max 2-3 types
    if any(term in text_lower for term in ["wait", "negotiate", "delegation", "dispatch", "offer", "refuse", "treaty", "peace"]):
        # Abstract blocks: waiting/negotiation
        shot_types = ["archival_documents", "maps_context"]
    elif any(term in text_lower for term in ["fire", "burned", "destroyed", "ruins", "flames", "destruction"]):
        # Destruction scenes
        shot_types = ["destruction_aftermath", "civilian_life"]
    elif any(term in text_lower for term in ["retreat", "advance", "march", "route", "journey"]):
        # Movement scenes
        shot_types = ["troop_movement", "maps_context"]
    elif any(term in text_lower for term in ["napoleon", "tsar", "alexander", "emperor", "commander"]):
        # Leader scenes
        # NOTE: "leader_closeups" is NOT a valid enum. Use the stable FDA enum family.
        shot_types = ["leaders_speeches", "archival_documents"]
    else:
        # Generic: documents + context
        shot_types = ["archival_documents", "maps_context"]
    
    # Limit to max 3 types
    shot_strategy["shot_types"] = shot_types[:3]
    
    # Set other defaults if missing
    if "clip_length_sec_range" not in shot_strategy:
        shot_strategy["clip_length_sec_range"] = [4, 7]
    if "cut_rhythm" not in shot_strategy:
        shot_strategy["cut_rhythm"] = "medium"
    
    scene["shot_strategy"] = shot_strategy


def _fix_scene_queries(
    scene: Dict[str, Any],
    narration_text: str,
    scene_index: int,
    errors: List[str],
    episode_topic: Optional[str] = None
) -> None:
    """
    DETERMINISTICALLY generate search_queries for a scene WITH GUARDRAILS.
    
    Phase 1: Generate queries deterministically
    Phase 2: Validate with guardrails (anchor + media intent + noise filter)
    Phase 3: Regenerate if needed (max 2 attempts)
    """
    # Phase 1: Generate queries
    raw_queries = _generate_deterministic_queries_v27(narration_text, scene_index)
    
    # Phase 2 & 3: Apply guardrails if available
    if QUERY_GUARDRAILS_AVAILABLE:
        shot_types = scene.get('shot_strategy', {}).get('shot_types', [])
        
        valid_queries, diagnostics = validate_and_fix_queries(
            raw_queries,
            narration_text,
            shot_types=shot_types,
            episode_topic=episode_topic,
            min_valid_queries=5,  # Require at least 5 valid queries
            max_regen_attempts=2,
            verbose=False  # Set to True for debugging
        )
        
        scene["search_queries"] = valid_queries
        scene["_query_diagnostics"] = diagnostics
        
        # Log diagnostics
        if diagnostics.get('low_coverage'):
            errors.append(
                f"Scene {scene_index}: LOW COVERAGE - only {diagnostics['final_count']}/5 valid queries"
            )
        if diagnostics.get('refined_count', 0) > 0:
            errors.append(
                f"Scene {scene_index}: refined {diagnostics['refined_count']} queries"
            )
        if diagnostics.get('rejection_reasons'):
            reasons_str = ', '.join(
                f"{k}={v}" for k, v in diagnostics['rejection_reasons'].items()
            )
            errors.append(f"Scene {scene_index}: rejected queries ({reasons_str})")
    else:
        # Fallback: use raw queries without guardrails
        scene["search_queries"] = raw_queries
        errors.append(f"Scene {scene_index}: queries generated deterministically (no guardrails)")


def _fix_scene_keywords(
    scene: Dict[str, Any],
    narration_text: str,
    scene_index: int,
    errors: List[str]
) -> None:
    """
    DETERMINISTICALLY generate keywords for a scene.
    Ignores LLM output completely - always generates fresh.
    """
    scene["keywords"] = _generate_deterministic_keywords_v27(narration_text)
    errors.append(f"Scene {scene_index}: keywords generated deterministically")
    return  # Early return - rest of function is legacy code


def _fix_scene_keywords_legacy(
    scene: Dict[str, Any],
    narration_text: str,
    scene_index: int,
    errors: List[str]
) -> None:
    """
    LEGACY: Fix keywords in-place for a scene (NON-CRITICAL metadata).
    Deterministic/mechanical normalization only; NEVER raises and MUST NOT break pipeline.
    - removes stopwords / junk tokens
    - replaces abstract/generic terms with concrete visual proxies
    - if an adjective-like token remains alone, append a generic physical object
    - if after normalization we still don't have enough signal, we simply keep keywords empty (ignored)
    
    Modifies scene["keywords"] in-place.
    """
    scene_id = scene.get("scene_id", f"sc_{scene_index:04d}")
    original_keywords = scene.get("keywords", [])
    if not isinstance(original_keywords, list):
        original_keywords = []
    
    fixed_keywords = []
    rejected = []

    # Deterministic stopword removal (mechanical, not linguistic AI)
    stopwords = {
        "the", "a", "an", "and", "or", "but", "if", "then", "else",
        "this", "that", "these", "those",
        "he", "she", "it", "they", "we", "you", "i", "me", "him", "her", "them", "us",
        "my", "your", "his", "her", "their", "our", "its",
        "upon", "shortly", "soon", "later", "early", "before", "after", "during", "while",
        "into", "onto", "from", "to", "of", "in", "on", "at", "by", "for", "with", "without",
        "as", "is", "are", "was", "were", "be", "been", "being",
    }
    # Generic-to-concrete mapping (very small, explicit)
    generic_to_concrete = {
        "fires": "burned city ruins",
        "fire": "burned city ruins",
        "ruins": "burned city ruins",
        "ruin": "burned city ruins",
        "destruction": "burned city ruins",
        "aftermath": "burned city ruins",
    }
    # Adjective-like tokens (demonym/nationality etc.) → append physical object
    adjective_to_object = {
        "french": "french military documents",
        "russian": "russian military documents",
        "german": "german military documents",
        "british": "british military documents",
        "american": "american military documents",
        "soviet": "soviet military documents",
        "ottoman": "ottoman military documents",
    }
    
    for kw in original_keywords:
        s = str(kw or "").strip()
        if not s:
            continue
        low = s.lower().strip()
        # Drop pure stopwords / trivial tokens
        if low in stopwords or len(low) < 3:
            rejected.append(f"{s} (removed: stopword)")
            continue

        # Replace known generic terms with concrete proxies
        if low in generic_to_concrete:
            fixed_keywords.append(generic_to_concrete[low])
            rejected.append(f"{s} → {generic_to_concrete[low]}")
            continue

        # Expand adjective-only tokens into physical objects
        if low in adjective_to_object:
            fixed_keywords.append(adjective_to_object[low])
            rejected.append(f"{s} → {adjective_to_object[low]}")
            continue

        is_valid, reason = _is_concrete_noun(s)
        
        if is_valid:
            fixed_keywords.append(s)
        else:
            # Try to find visual proxy replacement
            kw_lower = low
            
            # Visual proxy replacements (MUST align with pre_fda_sanitizer.py)
            replacements = {
                # Abstracts/adjectives
                "spiritual": "religious building",
                "capital": "city center",
                "historic": "historical building",
                "diplomatic": "diplomatic correspondence",
                "treaty": "treaty document",
                
                # Strategic/military concepts → concrete objects
                "strategic": "military map",
                # NOTE: "campaign" is blacklisted → avoid it in replacements
                "strategy": "military map",
                "goal": "official letter",
                "goals": "written orders",
                "campaign": "military map",
                "battle": "military map battlefield",
                "siege": "fortification walls",
                "occupation": "administrative headquarters",
                "invasion": "border crossing map",
                "advance": "military map forward movement",
                "retreat": "evacuation route map",
                
                # Political concepts → documents
                "peace": "signed treaty document",
                "negotiation": "diplomatic meeting",
                "treaty": "treaty document",
            }
            
            if kw_lower in replacements:
                fixed_keywords.append(replacements[kw_lower])
                rejected.append(f"{kw} → {replacements[kw_lower]}")
            else:
                rejected.append(f"{kw} (removed: {reason})")
    
    # Ensure minimum 3 keywords (if we can't, keywords are simply ignored)
    if len(fixed_keywords) < 3:
        # Extract safe keywords from narration (proper nouns, concrete objects)
        proper_nouns = re.findall(r'\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)*', narration_text)
        
        # Safe concrete nouns
        safe_nouns = ["soldiers", "army", "city", "building", "street", "map", 
                      "letter", "document", "troops", "population"]
        
        # Add proper nouns first
        for noun in proper_nouns:
            if noun not in fixed_keywords and len(fixed_keywords) < 8:
                fixed_keywords.append(noun)
        
        # Add safe nouns if still not enough
        for noun in safe_nouns:
            if len(fixed_keywords) >= 3:
                break
            if noun not in [k.lower() for k in fixed_keywords]:
                fixed_keywords.append(noun)
    
    # Deduplicate (case-insensitive)
    seen = set()
    unique_keywords = []
    for kw in fixed_keywords:
        kw_lower = kw.lower()
        if kw_lower not in seen:
            seen.add(kw_lower)
            unique_keywords.append(kw)
    
    # ═══════════════════════════════════════════════════════════════════════════
    # FDA v2.7 KEYWORD NORMALIZATION: exactly 8 keywords, 2-5 words each
    # ═══════════════════════════════════════════════════════════════════════════
    
    # Forbidden tokens that must be removed from keywords
    forbidden_tokens = {
        "the", "a", "an", "upon", "soon", "after", "before", "during", "while",
        "and", "or", "but", "yet", "so", "with", "without", "into", "onto", "from", "to",
        "this", "that", "these", "those", "he", "she", "they", "it", "his", "her", "their", "its",
        "who", "which", "what", "when", "where", "how", "as", "if", "then", "than",
        "began", "following", "although",
    }
    
    # Physical object types (for ensuring at least 3 keywords contain one)
    physical_objects = {
        "map", "maps", "engraving", "engravings", "lithograph", "letter", "letters",
        "document", "documents", "manuscript", "manuscripts", "photograph", "photographs",
        "illustration", "illustrations", "painting", "paintings", "portrait", "portraits",
        "ruins", "artifact", "artifacts", "medal", "medals", "uniform", "uniforms",
        "weapon", "weapons", "cannon", "cannons", "flag", "flags", "statue", "statues",
        "dispatch", "decree", "report", "correspondence", "proclamation",
    }
    
    def _normalize_keyword(kw: str) -> str:
        """Normalize keyword to 2-5 words, removing forbidden tokens."""
        words = kw.strip().split()
        # Remove forbidden tokens
        clean_words = [w for w in words if w.lower() not in forbidden_tokens]
        if not clean_words:
            return ""
        # If single word, try to expand with context
        if len(clean_words) == 1:
            word = clean_words[0]
            word_lower = word.lower()
            # Expand single words to 2-word phrases
            expansions = {
                "napoleon": "Napoleon portrait",
                "moscow": "Moscow city",
                "kremlin": "Kremlin building",
                "borodino": "Borodino battlefield",
                "army": "military army",
                "soldiers": "infantry soldiers",
                "troops": "military troops",
                "battle": "battle scene",
                "war": "war illustration",
                "retreat": "retreat map",
                "invasion": "invasion map",
                "fire": "city fire",
                "flames": "burning flames",
                "destruction": "destruction ruins",
                "force": "military force",
                "campaign": "military campaign",
            }
            if word_lower in expansions:
                return expansions[word_lower]
            # Default: add "historical" prefix
            return f"historical {word}"
        # If more than 5 words, truncate
        if len(clean_words) > 5:
            clean_words = clean_words[:5]
        return " ".join(clean_words)
    
    def _has_physical_object(kw: str) -> bool:
        """Check if keyword contains a physical object type."""
        kw_lower = kw.lower()
        for obj in physical_objects:
            if obj in kw_lower:
                return True
        return False
    
    # Normalize all keywords
    normalized = []
    for kw in unique_keywords:
        norm = _normalize_keyword(kw)
        if norm and 2 <= len(norm.split()) <= 5:
            normalized.append(norm)
    
    # Deduplicate again after normalization
    seen_norm = set()
    deduped = []
    for kw in normalized:
        kw_lower = kw.lower()
        if kw_lower not in seen_norm:
            seen_norm.add(kw_lower)
            deduped.append(kw)
    
    # Ensure at least 3 keywords have physical objects
    with_objects = [kw for kw in deduped if _has_physical_object(kw)]
    without_objects = [kw for kw in deduped if not _has_physical_object(kw)]
    
    # If not enough physical objects, generate from narration context
    if len(with_objects) < 3:
        # Extract proper nouns from narration
        proper_nouns = re.findall(r'\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)', narration_text)
        
        # Default physical object keywords based on context
        default_object_keywords = [
            "historical map",
            "military document",
            "period engraving",
            "official letter",
            "historical photograph",
            "battle illustration",
            "military portrait",
            "diplomatic dispatch",
        ]
        
        # Add proper noun + object combinations
        for noun in proper_nouns[:3]:
            if len(with_objects) >= 3:
                break
            combo = f"{noun} portrait"
            if combo.lower() not in seen_norm:
                with_objects.append(combo)
                seen_norm.add(combo.lower())
        
        # Fill remaining with defaults
        for default_kw in default_object_keywords:
            if len(with_objects) >= 3:
                break
            if default_kw.lower() not in seen_norm:
                with_objects.append(default_kw)
                seen_norm.add(default_kw.lower())
    
    # Combine: physical objects first, then others
    final_keywords = with_objects[:5] + without_objects[:3]
    
    # Ensure exactly 8 keywords
    if len(final_keywords) < 8:
        # Generate additional keywords from narration
        raw_proper_nouns = re.findall(r'\b([A-Z][a-z]+)', narration_text)
        # FILTER OUT forbidden tokens from proper nouns
        proper_nouns = [n for n in raw_proper_nouns if n.lower() not in forbidden_tokens]
        
        filler_templates = [
            "{} document",
            "{} map",
            "{} illustration",
            "historical {}",
            "{} portrait",
        ]
        
        for noun in proper_nouns:
            if len(final_keywords) >= 8:
                break
            for template in filler_templates:
                if len(final_keywords) >= 8:
                    break
                candidate = template.format(noun)
                if candidate.lower() not in seen_norm and 2 <= len(candidate.split()) <= 5:
                    final_keywords.append(candidate)
                    seen_norm.add(candidate.lower())
        
        # Last resort: generic historical keywords
        generic_fillers = [
            "historical archive",
            "military records",
            "period illustration",
            "official correspondence",
            "diplomatic letter",
            "historical engraving",
            "military map",
            "battle document",
        ]
        for filler in generic_fillers:
            if len(final_keywords) >= 8:
                break
            if filler.lower() not in seen_norm:
                final_keywords.append(filler)
                seen_norm.add(filler.lower())
    
    # Truncate to exactly 8
    final_keywords = final_keywords[:8]
    
    # ═══════════════════════════════════════════════════════════════════════════
    # FINAL VALIDATION: Ensure ALL keywords are v2.7 compliant
    # ═══════════════════════════════════════════════════════════════════════════
    def _is_keyword_valid(kw: str) -> bool:
        """Check if keyword meets all v2.7 requirements."""
        words = kw.split()
        # Must be 2-5 words
        if not (2 <= len(words) <= 5):
            return False
        # No word can be a forbidden token
        for w in words:
            if w.lower() in forbidden_tokens:
                return False
        return True
    
    # Replace invalid keywords with generic fillers
    validated_keywords = []
    generic_replacements = [
        "historical archive document",
        "military campaign map",
        "period portrait painting",
        "official state letter",
        "diplomatic correspondence record",
        "historical battlefield engraving",
        "military officer portrait",
        "administrative decree document",
    ]
    replacement_idx = 0
    
    for kw in final_keywords:
        if _is_keyword_valid(kw):
            validated_keywords.append(kw)
        else:
            # Replace with generic filler
            while replacement_idx < len(generic_replacements):
                replacement = generic_replacements[replacement_idx]
                replacement_idx += 1
                if replacement.lower() not in seen_norm:
                    validated_keywords.append(replacement)
                    seen_norm.add(replacement.lower())
                    break
    
    # Ensure we still have 8
    while len(validated_keywords) < 8 and replacement_idx < len(generic_replacements):
        replacement = generic_replacements[replacement_idx]
        replacement_idx += 1
        if replacement.lower() not in seen_norm:
            validated_keywords.append(replacement)
            seen_norm.add(replacement.lower())
    
    scene["keywords"] = validated_keywords[:8]
    
    if rejected:
        errors.append(
            f"FDA_KEYWORDS_NORMALIZED Scene {scene_index} ({scene_id}): {len(final_keywords)} keywords (normalized from {len(unique_keywords)})"
        )


# ============================================================================
# ALLOWLISTS (MVP - pevné hodnoty pro validaci)
# ============================================================================

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

ALLOWED_EMOTIONS = [
    "neutral",
    "tension",
    "tragedy",
    "hope",
    "victory",
    "mystery",
]

ALLOWED_CUT_RHYTHMS = [
    "slow",
    "medium",
    "fast",
]

# ============================================================================
# GENERIC FILLER BLACKLIST (HOTFIX: zakázat generické termy)
# ============================================================================

GENERIC_FILLER_BLACKLIST = [
    "history", "events", "situation", "conflict", "things", "background",
    "context", "footage", "montage", "strategic importance", "impact", "support",
    "war effort", "production", "industry"  # industry_war_effort jen když explicitně v textu
]

# ============================================================================
# ABSTRACT / NON-VISUAL KEYWORDS (explicit ban)
# ============================================================================

# These are abstract narrative concepts that must NOT appear in keywords/queries,
# even if they are present in narration text. FDA must convert them into concrete
# archival visual proxies (documents, maps, meetings, correspondence, proclamations, ...).
ABSTRACT_KEYWORD_BLACKLIST = [
    "strategic", "strategy", "goal", "aim", "ambition", "policy", "intention",
    "dominance", "influence", "control", "power", "pressure", "support", "impact",
    "significance", "consequence", "outcome", "turning point", "tide",
]

# ============================================================================
# CONCRETE VISUAL NOUNS (heuristika pro validaci)
# ============================================================================

CONCRETE_VISUAL_NOUNS = [
    "documents", "letters", "maps", "envelopes", "offices", "factories",
    "streets", "civilians", "ruins", "ships", "railways", "archives",
    "buildings", "smoke", "fire", "delegation", "officials", "roads",
    "wagons", "troops", "soldiers", "retreat", "winter", "snow",
    "shelter", "food", "supplies", "governor", "sabotage", "kremlin",
    "moscow", "napoleon", "surrender", "evacuated", "destroyed",
    # concrete proxies for abstract aims
    "treaty documents", "diplomatic meeting", "correspondence", "proclamations",
    "maps table", "meeting room", "signed treaty", "official letter",
]


def contains_abstract_term(text: str) -> bool:
    """
    Returns True if text contains an abstract / non-visual concept from the blacklist.
    We use substring match on lowercased text (covers multi-word phrases too).
    """
    if not text or not isinstance(text, str):
        return False
    low = text.lower()
    for t in ABSTRACT_KEYWORD_BLACKLIST:
        if t.lower() in low:
            return True
    return False


# ============================================================================
# UTILITY FUNCTIONS (pro prompt building)
# ============================================================================

def estimate_speech_duration_seconds(text: str, words_per_minute: int = 150) -> float:
    """
    Odhadne dobu řeči v sekundách na základě počtu slov.
    
    Args:
        text: Text k odhadu
        words_per_minute: Rychlost řeči (default 150 WPM)
    
    Returns:
        Odhadovaná doba v sekundách (float)
    """
    if not text or not isinstance(text, str):
        return 0.0
    
    words = re.findall(r'\b\w+\b', text)
    word_count = len(words)
    
    if word_count == 0:
        return 0.0
    
    duration_minutes = word_count / words_per_minute
    duration_seconds = duration_minutes * 60.0
    
    return round(duration_seconds, 1)


def estimate_speech_duration_seconds_int(
    text: str,
    words_per_minute: int = 150,
    min_seconds: int = 2,
) -> int:
    """
    Deterministic integer duration estimator for FDA timing.
    
    Spec rule:
      seconds = round((word_count/150)*60) and minimum 2s (for non-empty text)
    """
    if not text or not isinstance(text, str):
        return 0
    words = re.findall(r"\b\w+\b", text)
    wc = len(words)
    if wc <= 0:
        return 0
    sec = int(round((wc / float(words_per_minute)) * 60.0))
    if sec < int(min_seconds):
        sec = int(min_seconds)
    return sec


def _recompute_scene_timings_v27(
    scenes: List[Dict[str, Any]],
    narration_blocks: List[Dict[str, Any]],
    words_per_minute: int = 150,
) -> None:
    """
    Recompute start_sec/end_sec deterministically from narration_block_ids + text_tts.
    
    This prevents "2s per block" plans that desync video timing from voiceover.
    """
    if not isinstance(scenes, list) or not scenes:
        return
    if not isinstance(narration_blocks, list):
        narration_blocks = []
    block_dict = {str(b.get("block_id") or "").strip(): b for b in narration_blocks if isinstance(b, dict)}

    t = 0
    for scene in scenes:
        if not isinstance(scene, dict):
            continue
        bids = scene.get("narration_block_ids", [])
        if not isinstance(bids, list):
            bids = []

        dur = 0
        for bid in bids:
            b = block_dict.get(str(bid).strip()) or {}
            txt = b.get("text_tts") or ""
            sec = estimate_speech_duration_seconds_int(txt, words_per_minute=words_per_minute, min_seconds=2)
            if sec <= 0:
                # Defensive fallback: should never happen in production because FDA_INPUT enforces text_tts.
                sec = 3
            dur += sec

        if dur < 2:
            dur = 2

        scene["start_sec"] = int(t)
        scene["end_sec"] = int(t + dur)
        t = scene["end_sec"]


def _build_narration_summary(narration_blocks: List[Dict[str, Any]], words_per_minute: int = 150, episode_id: Optional[str] = None) -> str:
    """
    Vytvoří stručný přehled narration bloků pro LLM prompt.
    
    Raises:
        RuntimeError: s prefixem FDA_TEXT_TTS_MISSING pokud text_tts chybí
    """
    summary_lines = []
    for i, block in enumerate(narration_blocks[:10], 1):  # Max 10 pro přehlednost
        block_id = block.get("block_id", f"b_{i:03d}")
        
        # HOTFIX: text_tts-only, žádný fallback na text
        text_tts = block.get("text_tts")
        if not text_tts or not isinstance(text_tts, str) or not text_tts.strip():
            # Diagnostika pro error
            has_text = "text" in block
            text_type = type(block.get("text")).__name__ if has_text else "N/A"
            text_len = len(str(block.get("text", ""))) if has_text else 0
            
            diagnostic = {
                "episode_id": episode_id,
                "block_id": block_id,
                "has_text_field": has_text,
                "text_type": text_type,
                "text_length": text_len,
                "text_tts_present": "text_tts" in block,
                "text_tts_type": type(block.get("text_tts")).__name__ if "text_tts" in block else "N/A",
            }
            raise RuntimeError(
                f"FDA_TEXT_TTS_MISSING: block {block_id} nemá validní text_tts. "
                f"Diagnostic: {diagnostic}"
            )
        
        duration = estimate_speech_duration_seconds(text_tts, words_per_minute)
        
        # Zkrácení textu
        text_preview = text_tts[:100] + "..." if len(text_tts) > 100 else text_tts
        summary_lines.append(f"{block_id} (~{duration}s): {text_preview}")
    
    if len(narration_blocks) > 10:
        summary_lines.append(f"... (+ {len(narration_blocks) - 10} dalších bloků)")
    
    return "\n".join(summary_lines)


# ============================================================================
# TEXT_TTS-FIRST EXTRACTION (HOTFIX: beat-lock podle narration)
# ============================================================================

def extract_anchor_terms_from_text(text: str) -> List[str]:
    """
    Extrahuje anchor terms z text_tts (case-insensitive).
    
    Vrací konkrétní entity, místa, osoby, akce které se skutečně objeví v textu.
    """
    if not text or not isinstance(text, str):
        return []
    
    text_lower = text.lower()
    
    # Extrahuj významné termy (vlastní jména, konkrétní podstatná jména)
    # Pattern: slova s velkým písmenem nebo významné konkrétní termy
    words = re.findall(r'\b[A-Z][a-z]+\b|\b[a-z]{4,}\b', text)
    
    # Filtruj stop words a krátké termy
    stop_words = {
        "the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for",
        "of", "with", "by", "from", "as", "is", "was", "are", "were", "been",
        "be", "have", "has", "had", "do", "does", "did", "will", "would",
        "could", "should", "may", "might", "must", "can", "this", "that",
        "these", "those", "it", "its", "they", "them", "their", "there"
    }
    
    anchor_terms = []
    seen = set()
    
    for word in words:
        word_lower = word.lower()
        # Přeskoč stop words a krátké termy
        if word_lower in stop_words or len(word_lower) < 3:
            continue
        # Přeskoč duplikáty (case-insensitive)
        if word_lower not in seen:
            seen.add(word_lower)
            # Zachovej původní case (pro vlastní jména)
            anchor_terms.append(word)
    
    return anchor_terms


def get_scene_narration_text(narration_blocks: List[Dict[str, Any]], block_ids: List[str], episode_id: Optional[str] = None) -> str:
    """
    Vrátí spojený text_tts pro dané narration_block_ids.
    
    Raises:
        RuntimeError: s prefixem FDA_TEXT_TTS_MISSING pokud text_tts chybí
    """
    block_dict = {b.get("block_id", ""): b for b in narration_blocks}
    texts = []
    for bid in block_ids:
        block = block_dict.get(bid, {})
        
        # HOTFIX: text_tts-only, žádný fallback na text
        text_tts = block.get("text_tts")
        if not text_tts or not isinstance(text_tts, str) or not text_tts.strip():
            # Diagnostika pro error
            has_text = "text" in block
            text_type = type(block.get("text")).__name__ if has_text else "N/A"
            text_len = len(str(block.get("text", ""))) if has_text else 0
            
            diagnostic = {
                "episode_id": episode_id,
                "block_id": bid,
                "has_text_field": has_text,
                "text_type": text_type,
                "text_length": text_len,
                "text_tts_present": "text_tts" in block,
                "text_tts_type": type(block.get("text_tts")).__name__ if "text_tts" in block else "N/A",
            }
            raise RuntimeError(
                f"FDA_TEXT_TTS_MISSING: block {bid} nemá validní text_tts. "
                f"Diagnostic: {diagnostic}"
            )
        
        texts.append(text_tts)
    return " ".join(texts)


def get_scene_narration_context_text(
    narration_blocks: List[Dict[str, Any]],
    block_ids: List[str],
    episode_id: Optional[str] = None,
    neighbor_window: int = 1,
) -> str:
    """
    Vrátí "context" text_tts pro scénu:
    - text_tts pro vlastní narration_block_ids
    - + deterministicky i sousední bloky (± neighbor_window) podle pořadí v narration_blocks[]

    Motivace:
    Některé bloky jsou lokálně generické (např. "the city's fire-fighting equipment") a
    neobsahují žádné temporal anchors (Napoleon/Moscow/1812). Kontextové bloky ale
    obvykle obsahují proper nouns/years, které chceme použít pro ukotvení queries.
    """
    if not isinstance(neighbor_window, int) or neighbor_window < 0:
        neighbor_window = 1

    # Build index map for stable neighbor lookup
    id_to_idx: Dict[str, int] = {}
    for idx, b in enumerate(narration_blocks):
        bid = str(b.get("block_id", "")).strip()
        if bid and bid not in id_to_idx:
            id_to_idx[bid] = idx

    indices = [id_to_idx.get(str(bid).strip()) for bid in block_ids if str(bid).strip() in id_to_idx]
    if not indices:
        # Fallback: just the scene blocks (will still raise if text_tts missing)
        return get_scene_narration_text(narration_blocks, block_ids, episode_id=episode_id)

    lo = max(0, min(indices) - neighbor_window)
    hi = min(len(narration_blocks) - 1, max(indices) + neighbor_window)

    context_ids = [str(narration_blocks[i].get("block_id", "")).strip() for i in range(lo, hi + 1)]
    context_ids = [cid for cid in context_ids if cid]
    return get_scene_narration_text(narration_blocks, context_ids, episode_id=episode_id)


def check_generic_filler(term: str) -> bool:
    """
    Zkontroluje, zda term je na blacklistu generických fillerů.
    """
    term_lower = term.lower()
    for filler in GENERIC_FILLER_BLACKLIST:
        if filler.lower() in term_lower or term_lower in filler.lower():
            return True
    return False


def count_anchored_terms(keywords: List[str], narration_text: str) -> int:
    """
    Spočítá kolik keywords jsou skutečně anchored v narration textu (case-insensitive).
    """
    if not narration_text:
        return 0
    
    narration_lower = narration_text.lower()
    anchored_count = 0
    
    for keyword in keywords:
        keyword_lower = keyword.lower()
        # Zkontroluj, zda keyword nebo jeho část je v textu
        if keyword_lower in narration_lower:
            anchored_count += 1
        else:
            # Zkontroluj jednotlivá slova
            keyword_words = keyword_lower.split()
            if any(word in narration_lower for word in keyword_words if len(word) >= 3):
                anchored_count += 1
    
    return anchored_count


def count_concrete_visual_nouns(keywords: List[str]) -> int:
    """
    Spočítá kolik keywords jsou concrete visual nouns.
    """
    keywords_lower = [k.lower() for k in keywords]
    count = 0
    for noun in CONCRETE_VISUAL_NOUNS:
        if noun.lower() in keywords_lower or any(noun.lower() in k for k in keywords_lower):
            count += 1
    return count


def has_anchored_query(search_queries: List[str], narration_text: str) -> bool:
    """
    Zkontroluje, zda alespoň jedna query je anchored v narration textu.
    """
    if not narration_text:
        return False
    
    narration_lower = narration_text.lower()
    for query in search_queries:
        query_lower = query.lower()
        # Zkontroluj, zda query obsahuje termy z narration
        query_words = query_lower.split()
        narration_words = narration_lower.split()
        # Pokud alespoň 2 slova z query jsou v narration (nebo významné slovo)
        matches = sum(1 for qw in query_words if len(qw) >= 4 and qw in narration_lower)
        if matches >= 1:
            return True
    return False


def _extract_temporal_anchors_from_narration(narration_text: str) -> List[str]:
    """
    Vytáhne temporal anchors z narration: roky, proper nouns, ery.
    Vrací seřazené podle priority (roky first, pak klíčové proper nouns).
    """
    if not narration_text:
        return []
    
    anchors_by_priority = {
        "years": [],
        "key_proper_nouns": [],
        "other_proper_nouns": [],
        "eras": [],
    }
    
    # 1. Explicit years (highest priority)
    years = re.findall(r'\b(1[0-9]{3}s?|20[0-2][0-9])\b', narration_text)
    anchors_by_priority["years"] = years
    
    # 2. Multi-word proper nouns (e.g., "Grande Armée", "Tsar Alexander")
    proper_multi = re.findall(r'\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)+\b', narration_text)
    
    # 3. Single-word proper nouns (e.g., "Napoleon", "Moscow")
    proper_single = re.findall(r'\b[A-Z][a-z]{2,}\b', narration_text)
    
    # Filter out common generic words that are capitalized
    generic_stopwords = {
        "The", "A", "An", "This", "That", "These", "Those", "In", "On", "At", "For", "With",
        "During", "After", "Before", "When", "While", "Where", "Which", "Who", "How",
        "Approximately", "Roughly", "About", "Around", "Nearly", "Almost", "However",
        "Therefore", "Thus", "Hence", "Meanwhile", "Nevertheless", "Nonetheless",
        "Furthermore", "Moreover", "Additionally", "Consequently", "Subsequently",
        "Facing", "Following", "Regarding", "Concerning", "Considering",
    }
    
    # Categorize proper nouns: key vs other
    # Key proper nouns: appear in multi-word phrases or are historically significant
    key_names = {"Napoleon", "Alexander", "Moscow", "Russia", "France", "French", "Russian", 
                 "Tsar", "Emperor", "General", "Marshal"}
    
    for pn in proper_multi:
        if pn not in generic_stopwords:
            anchors_by_priority["key_proper_nouns"].append(pn)
    
    for pn in proper_single:
        if pn in generic_stopwords:
            continue
        # If it's a key historical name, prioritize it
        if pn in key_names or any(pn in multi for multi in proper_multi):
            if pn not in anchors_by_priority["key_proper_nouns"]:
                anchors_by_priority["key_proper_nouns"].append(pn)
        else:
            if pn not in anchors_by_priority["other_proper_nouns"]:
                anchors_by_priority["other_proper_nouns"].append(pn)
    
    # 4. Named eras (e.g., Napoleonic, WWII)
    era_patterns = [
        r'\bNapoleonic\b',
        r'\bVictorian\b',
        r'\bWWII\b',
        r'\bWW2\b',
        r'\bWorld War II\b',
        r'\bWorld War 2\b',
        r'\bCold War\b',
    ]
    for pattern in era_patterns:
        matches = re.findall(pattern, narration_text, re.IGNORECASE)
        anchors_by_priority["eras"].extend(matches)
    
    # Flatten by priority: years > key_proper_nouns > other_proper_nouns > eras
    result = []
    seen = set()
    
    for category in ["years", "key_proper_nouns", "other_proper_nouns", "eras"]:
        for anchor in anchors_by_priority[category]:
            if anchor.lower() not in seen:
                seen.add(anchor.lower())
                result.append(anchor)
    
    return result


def _query_has_temporal_anchor(query: str, narration_anchors: List[str]) -> bool:
    """
    Zkontroluje, zda query obsahuje alespoň jeden temporal anchor.
    """
    if not query or not narration_anchors:
        return False
    
    query_lower = query.lower()
    
    for anchor in narration_anchors:
        anchor_lower = anchor.lower()
        # Word-boundary match pro proper nouns (Napoleon, Moscow)
        # Pro roky (1812) a ery (Napoleonic) stačí substring
        if re.search(r'\b' + re.escape(anchor_lower) + r'\b', query_lower):
            return True
    
    return False


def _add_temporal_anchor_to_query(query: str, narration_anchors: List[str]) -> str:
    """
    Přidá temporal anchor do query, pokud tam chybí.
    Preferuje první 3 anchory z narration (nejdůležitější).
    """
    if not narration_anchors:
        # No anchors available - delete query
        return ""
    
    # Prefer the first anchor (usually the most important proper noun or year)
    anchor = narration_anchors[0]
    
    # Prepend anchor to query
    return f"{anchor} {query}"


def _fix_unanchored_queries(
    search_queries: List[str],
    narration_text: str,
    scene_id: str,
    log_replacements: bool = True,
    fallback_anchors: Optional[List[str]] = None,
) -> Tuple[List[str], List[str]]:
    """
    DETERMINISTICKÝ POST-LLM GUARD: zajistí, že každá query má temporal anchor.
    
    - Pokud query má anchor → keep
    - Pokud query nemá anchor → prepend first anchor from narration
    - Pokud žádný anchor neexistuje → delete query
    
    Returns:
        (fixed_queries, replacements_log)
    """
    narration_anchors = _extract_temporal_anchors_from_narration(narration_text)

    # If local narration has no anchors (common for generic sentences),
    # fall back to episode-level anchors (deterministic, extracted from full narration_blocks).
    if not narration_anchors and fallback_anchors:
        narration_anchors = [a for a in fallback_anchors if isinstance(a, str) and a.strip()]

    if not narration_anchors:
        # FATAL: no anchors anywhere -> cannot fix queries safely
        raise RuntimeError(
            f"FDA_NO_TEMPORAL_ANCHORS: Scene {scene_id} has NO temporal anchors in narration/context, "
            f"and no fallback anchors available. Cannot fix unanchored queries. "
            f"Narration: {narration_text[:200]}"
        )
    
    fixed_queries = []
    replacements = []
    
    for original_query in search_queries:
        query_has_anchor = _query_has_temporal_anchor(original_query, narration_anchors)
        
        if query_has_anchor:
            # Query already has anchor - keep as is
            fixed_queries.append(original_query)
        else:
            # Query missing anchor - prepend first anchor
            fixed_query = _add_temporal_anchor_to_query(original_query, narration_anchors)
            if fixed_query and fixed_query.strip():
                fixed_queries.append(fixed_query)
                replacements.append(f"[ANCHOR_ADDED]: '{original_query}' → '{fixed_query}'")
            else:
                # Could not fix - delete query
                replacements.append(f"[ANCHOR_MISSING_DELETED]: '{original_query}'")
    
    if log_replacements and replacements:
        print(f"📌 FDA: Fixed unanchored queries for {scene_id}:")
        for r in replacements:
            print(f"   {r}")
    
    return fixed_queries, replacements


# ============================================================================
# LLM PROMPT
# ============================================================================

def _prompt_footage_director(narration_blocks: List[Dict[str, Any]], words_per_minute: int = 150, episode_id: Optional[str] = None) -> str:
    """
    Vytvoří prompt pro LLM Footage Director Assistant.
    
    Raises:
        RuntimeError: s prefixem FDA_TEXT_TTS_MISSING pokud text_tts chybí
    """
    # Spočítej celkovou délku (text_tts-only, žádný fallback)
    total_duration = 0
    for b in narration_blocks:
        text_tts = b.get("text_tts")
        if not text_tts or not isinstance(text_tts, str) or not text_tts.strip():
            block_id = b.get("block_id", "unknown")
            diagnostic = {
                "episode_id": episode_id,
                "block_id": block_id,
                "has_text_field": "text" in b,
                "text_tts_present": "text_tts" in b,
            }
            raise RuntimeError(
                f"FDA_TEXT_TTS_MISSING: block {block_id} nemá validní text_tts při výpočtu délky. "
                f"Diagnostic: {diagnostic}"
            )
        total_duration += estimate_speech_duration_seconds(text_tts, words_per_minute)
    
    # Vytvoř přehled bloků
    narration_summary = _build_narration_summary(narration_blocks, words_per_minute, episode_id)
    
    return f"""
You are a Footage Director Assistant (FDA).

========================================
FDA v2.7 HARD FORMAT GUARD (MUST OBEY; OVERRIDES ANY CONFLICTS BELOW)
========================================
- Output MUST be exactly ONE JSON object with wrapper:
  {{
    "shot_plan": {{
      "version": "fda_v2.7",
      "source": "tts_ready_package",
      "assumptions": {{ "words_per_minute": 150 }},
      "scenes": [...]
    }}
  }}
- shot_plan.version MUST be "fda_v2.7" (exact)
- Scenes MUST cover ALL narration_block_ids exactly once and in order
- start_sec/end_sec MUST be integers, contiguous (no gaps/overlaps), min duration 2 sec
- narration_summary per scene:
  - exactly ONE sentence
  - no semicolons
  - ends with exactly one period
  - no fragments like "began his ."
- keywords per scene:
  - EXACTLY 8 items
  - each 2–5 words
  - must NOT contain stopword tokens like: the/a/an/upon/soon/after/before/with/without/...
  - at least 3 keywords contain a PHYSICAL OBJECT TYPE (map/engraving/letter/document/ruins/...)
- search_queries per scene:
  - EXACTLY 5 queries
  - each 5–9 words
  - none starts with: Following|Upon|Soon|Although|He|She|They|This|These|The|A|An
  - must NOT contain standalone "He" or "They" anywhere
  - each query MUST contain:
    (1) at least one anchor among: Moscow | Napoleon | Tsar Alexander I | Borodino | 1812
    (2) exactly one object type among:
        map | city map | route map | engraving | photograph | illustration | manuscript |
        letter | dispatch | decree | document | report | city street | ruins | burned ruins | kremlin interior

If any rule fails: fix your JSON BEFORE returning. Output JSON only.

----------------------------------------
Legacy guidance (keep consistent with the guard above)
----------------------------------------
Your task is to create a shot_plan (list of scenes) for video production based on narration blocks.

INPUT:
- Narration blocks (text + timing)
- Target: organize into scenes with visual strategy

OUTPUT: JSON object matching this EXACT schema:

{{
  "scenes": [
    {{
      "scene_id": "sc_0001",
      "start_sec": 0,
      "end_sec": 25,
      "narration_block_ids": ["b_0001", "b_0002", "b_0003"],
      "narration_summary": "Brief 1-sentence summary of what's narrated",
      "emotion": "neutral",
      "keywords": ["word1", "word2", "word3", "word4", "word5", "word6"],
      "shot_strategy": {{
        "shot_types": ["archival_documents", "maps_context"],
        "clip_length_sec_range": [4, 7],
        "cut_rhythm": "medium",
        "source_preference": ["archive_org"]
      }},
      "search_queries": ["query1", "query2", "query3", "query4"]
    }}
  ]
}}

STRICT RULES:
1. scene_id: "sc_0001", "sc_0002", ... (4-digit sequential)
2. start_sec/end_sec: must be continuous (no gaps, no overlaps)
3. narration_block_ids: array of block IDs from input (use ALL blocks, no skips)
4. emotion: ONLY one of: {', '.join(ALLOWED_EMOTIONS)}
5. keywords: 5-12 words (most important from narration)
6. shot_types: ONLY from: {', '.join(ALLOWED_SHOT_TYPES)}
7. clip_length_sec_range: [min, max] in seconds (typically 3-8)
8. cut_rhythm: ONLY one of: {', '.join(ALLOWED_CUT_RHYTHMS)}
9. search_queries: 3-8 queries for footage search

TEXT_TTS-FIRST EXTRACTION (MANDATORY - HOTFIX):
- You MUST extract anchor terms ONLY from text_tts in narration blocks
- keywords MUST contain at least 2 terms that appear in the narration text (case-insensitive)
- keywords MUST contain at least 1 concrete visual noun (documents, buildings, streets, ruins, etc.)
- search_queries MUST contain at least 1 query anchored to narration text
- NEVER use generic fillers: "history", "events", "situation", "conflict", "things", "background", "context", "footage", "montage", "strategic importance", "impact", "support"
- **CRITICAL: NEVER include shot type names in keywords/search_queries (e.g., "troop movement", "battle footage", "archival documents")**
- **Keywords are OBJECTS ONLY: map, letter, manuscript, palace, city street, engraving, soldiers, wagons, roads**
- If narration mentions "Napoleon", "Moscow", "surrender", "fires" → use these exact terms
- If narration mentions "delegation" → infer "official documents / officials / empty streets" (safe editor inference)
- If narration mentions "fires" → infer "burning buildings / smoke / ruins"
- If narration mentions "retreat" → infer "soldiers / wagons / roads" (NOT "troop movement")
- DO NOT invent visuals like "industry/war effort" unless narration explicitly mentions factories/production/industry

SHOT TYPES MAPPING (content-based - MUST match narration):
- "open city", "surrender delegation", "evacuated civilians" → civilian_life + archival_documents + atmosphere_transition
- "fires", "destroyed", "ruined", "lack of shelter/food" → destruction_aftermath + civilian_life
- "sabotage ordered by governor" → archival_documents + atmosphere_transition (NO battle)
- "retreat", "winter approaching", "supplies running low" → troop_movement + maps_context
- industry_war_effort ONLY if narration explicitly mentions factories/production/industry (NOT inferred)

QUERY GENERATOR (TEMPORAL ANCHOR MANDATORY):
**CRITICAL: Every search_query MUST contain a TEMPORAL ANCHOR (date/century/era/person name)**
**EVERY QUERY MISSING AN ANCHOR WILL BE AUTOMATICALLY REJECTED - NO FALLBACKS**

TEMPORAL ANCHOR TYPES (use at least ONE per query):
1. Explicit date/year (e.g., "1812", "1940s", "1917")
2. Era/period (e.g., "Napoleonic", "Victorian", "WWII", "Cold War")
3. Proper noun - person (e.g., "Napoleon", "Churchill", "Stalin")
4. Proper noun - specific event (e.g., "D-Day", "Pearl Harbor")

MANDATORY QUERY FORMAT:
**<ANCHOR> + <TERM>** (e.g., "Napoleon Moscow", "1812 fires", "Grande Armée looting")
**KEEP QUERIES SHORT: 2-4 words maximum!** (Archive.org favors broad queries)
NEVER write generic terms alone (e.g., "looting", "supplies", "occupation")

QUERY STRUCTURE (2-tier mix):
- Generate 1-2 BROAD queries: <ANCHOR> + place (e.g., "Napoleon Moscow", "1812 Russia")
  * 2-3 words ONLY
  * Simple and direct
- Generate 2-4 SPECIFIC queries: <ANCHOR> + object/action (e.g., "Napoleon retreat", "Moscow fires 1812")
  * 2-4 words ONLY
  * One key concept per query
- Deduplicate case-insensitively
- NEVER generate queries without temporal anchors (prevents matching modern conflicts)
- **CRITICAL: Archive.org finds MORE results with SHORTER queries!**

EXAMPLES (anchored to narration "Napoleon's main strategic goal in 1812..."):
  ✅ EXCELLENT (short & broad): 
    - "Napoleon Moscow" (2 words)
    - "1812 Russia" (2 words)
    - "Napoleonic Wars" (2 words)
    - "Moscow 1812" (2 words)
  ✅ GOOD (specific but short):
    - "Napoleon retreat 1812" (3 words)
    - "Moscow fires 1812" (3 words)
    - "Grande Armée 1812" (3 words)
  ❌ FORBIDDEN (too long/specific):
    - "archival photograph abandoned Moscow street" (5 words → too specific!)
    - "Napoleon nineteenth century Russian government building" (6 words → too long!)
    - "looting contributing to fire spread" (NO anchor → REJECTED)
  ❌ FORBIDDEN: "Russian army withdrawal Moscow" (NO temporal anchor → can match 2022 Ukraine!)
  ❌ FORBIDDEN: "civilian population fleeing" (NO temporal anchor → can match Syria 2017!)
  ❌ FORBIDDEN: "military strategies" (generic, no anchor)

QUALITY RULES (IMPORTANT):
- Prefer archival footage/photographs without large on-screen text.
- Avoid screen recordings, platform UI overlays (e.g., YouTube player), and footage with burned-in subtitles/captions.
- Avoid "trailer"/"promo" style queries; prefer descriptive archival terms (places, people, events, documents, maps).
- **MANDATORY: EVERY query must have temporal context (date/era/person) to prevent modern conflict matching**
- NEVER repeat the same query twice (no duplicates, case-insensitive dedup)
- Each query must be UNIQUE and SPECIFIC to what is ACTUALLY mentioned in narration text_tts

SCENE GROUPING RULES:
- One scene = 20-35 seconds OR 3-8 blocks (whichever comes first)
- Group blocks by thematic continuity
- Balance between too short (jarring) and too long (boring)

TIMING CALCULATION:
- words_per_minute = {words_per_minute}
- Use narration text length to estimate duration
- start_sec of scene N+1 MUST equal end_sec of scene N

NARRATION BLOCKS ({len(narration_blocks)} total, ~{int(total_duration)}s):
{narration_summary}

IMPORTANT:
- Return ONLY valid JSON matching the schema above
- Do NOT skip any narration blocks
- Do NOT add markdown, explanations, or comments
- Ensure all shot_types are from the allowed list
- Ensure all emotions are from the allowed list
- Ensure all cut_rhythms are from the allowed list
- NO extra fields beyond the schema
- Do NOT include assets[], archive_item_id, asset_url, or any download-related fields
- Do NOT include compile_plan or any compilation settings

SELF-CHECK BEFORE OUTPUT:
- For each scene, verify:
  * keywords contain at least 2 terms from narration text_tts
  * keywords contain at least 1 concrete visual noun
  * keywords do NOT contain blacklisted generic fillers
  * search_queries contain at least 1 anchored query
  * narration_summary does NOT use words not derivable from text_tts
  * shot_types (1-3) match the content of narration blocks
""".strip()


# ============================================================================
# SELF-CHECK (regresní kontrola před return)
# ============================================================================

def _self_check_shot_plan(shot_plan: Dict[str, Any], narration_blocks: List[Dict[str, Any]]) -> List[str]:
    """
    Rychlá regresní kontrola shot_plan před return.
    Vrací list warningů (ne fatal errors).
    """
    warnings = []
    scenes = shot_plan.get("scenes", [])
    
    for i, scene in enumerate(scenes):
        scene_id = scene.get("scene_id", f"sc_{i:04d}")
        block_ids = scene.get("narration_block_ids", [])
        narration_text = get_scene_narration_text(narration_blocks, block_ids)
        keywords = scene.get("keywords", [])
        search_queries = scene.get("search_queries", [])
        narration_summary = scene.get("narration_summary", "")
        shot_types = scene.get("shot_strategy", {}).get("shot_types", [])
        
        # 1. Zkontroluj, zda keywords nemají blacklisted termy
        for keyword in keywords:
            if check_generic_filler(keyword):
                warnings.append(f"Self-check Scene {i} ({scene_id}): keyword '{keyword}' is blacklisted generic filler")
        
        # 2. Zkontroluj, zda narration_summary nepoužívá slova, která nejsou odvoditelná z textu
        # (heuristika: pokud summary obsahuje významné slovo, které není v textu)
        summary_words = set(re.findall(r'\b[a-zA-Z]{4,}\b', narration_summary.lower()))
        text_words = set(re.findall(r'\b[a-zA-Z]{4,}\b', narration_text.lower()))
        suspicious_words = summary_words - text_words
        # Filtruj běžná slova, která mohou být inference
        common_inference_words = {"began", "started", "ended", "happened", "occurred", "took", "place", "during", "after", "before"}
        suspicious_words = suspicious_words - common_inference_words
        if suspicious_words and len(suspicious_words) > 2:  # Tolerance pro 1-2 inference slova
            warnings.append(f"Self-check Scene {i} ({scene_id}): narration_summary may contain words not derivable from text: {list(suspicious_words)[:3]}")
        
        # 3. Zkontroluj, zda shot_types jsou 1-3 a obsahově sedí s blocky
        if not (1 <= len(shot_types) <= 3):
            warnings.append(f"Self-check Scene {i} ({scene_id}): shot_types count is {len(shot_types)} (expected 1-3)")
        
        # 4. Zkontroluj, zda search_queries nemají blacklisted termy
        for query in search_queries:
            if check_generic_filler(query):
                warnings.append(f"Self-check Scene {i} ({scene_id}): search_query '{query}' contains blacklisted generic filler")
    
    return warnings


# ============================================================================
# SHOT PLAN VALIDATOR (deterministický postprocessing)
# ============================================================================

def _extract_narration_blocks_from_tts_ready_package(
    tts_pkg: Dict[str, Any],
    episode_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Vrátí narration_blocks ve tvaru [{block_id, text_tts, claim_ids}] z tts_ready_package.

    Preferuje:
    - tts_ready_package.narration_blocks[] (pokud existuje a není prázdné)
    Fallback:
    - tts_ready_package.tts_segments[] (TTS Format output)
    - tts_ready_package.chapters[].narration_blocks[] (legacy / manuální vstup)

    Pozn.: text_tts-only. Pokud text_tts není k dispozici, akceptujeme tts_formatted_text.
    """
    if not isinstance(tts_pkg, dict):
        raise ValueError("FDA_INPUT_MISSING: tts_ready_package must be an object")

    nb = tts_pkg.get("narration_blocks")
    if isinstance(nb, list) and nb:
        out: List[Dict[str, Any]] = []
        for b in nb:
            if not isinstance(b, dict):
                continue
            block_id = str(b.get("block_id") or "").strip()
            if not block_id:
                continue
            text_tts = b.get("text_tts")
            if not text_tts or not isinstance(text_tts, str) or not text_tts.strip():
                text_tts = b.get("tts_formatted_text")
            if not text_tts or not isinstance(text_tts, str) or not text_tts.strip():
                diagnostic = {
                    "episode_id": episode_id,
                    "block_id": block_id,
                    "text_tts_present": "text_tts" in b,
                    "tts_formatted_text_present": "tts_formatted_text" in b,
                    "has_text_field": "text" in b,
                }
                raise RuntimeError(f"FDA_TEXT_TTS_MISSING: block {block_id} nemá validní text_tts. Diagnostic: {diagnostic}")
            claim_ids = b.get("claim_ids", [])
            if not isinstance(claim_ids, list):
                claim_ids = []
            out.append({"block_id": block_id, "text_tts": text_tts, "claim_ids": claim_ids})
        if not out:
            raise ValueError("FDA_INPUT_MISSING: narration_blocks[] is empty or invalid")
        return out

    segs = tts_pkg.get("tts_segments")
    if isinstance(segs, list) and segs:
        out = []
        for seg in segs:
            if not isinstance(seg, dict):
                continue
            block_id = str(seg.get("block_id") or seg.get("segment_id") or "").strip()
            if not block_id:
                continue
            text_tts = seg.get("tts_formatted_text")
            if not text_tts or not isinstance(text_tts, str) or not text_tts.strip():
                diagnostic = {
                    "episode_id": episode_id,
                    "block_id": block_id,
                    "tts_formatted_text_present": "tts_formatted_text" in seg,
                    "has_text_field": "text" in seg,
                }
                raise RuntimeError(
                    f"FDA_TEXT_TTS_MISSING: tts_segment {block_id} nemá validní tts_formatted_text. Diagnostic: {diagnostic}"
                )
            out.append({"block_id": block_id, "text_tts": text_tts, "claim_ids": []})
        if not out:
            raise ValueError("FDA_INPUT_MISSING: tts_segments[] is empty or invalid")
        return out

    chapters = tts_pkg.get("chapters")
    if isinstance(chapters, list) and chapters:
        out = []
        for ch in chapters:
            if not isinstance(ch, dict):
                continue
            blocks = ch.get("narration_blocks")
            if not isinstance(blocks, list):
                continue
            for b in blocks:
                if not isinstance(b, dict):
                    continue
                block_id = str(b.get("block_id") or "").strip()
                if not block_id:
                    continue
                text_tts = b.get("text_tts")
                if not text_tts or not isinstance(text_tts, str) or not text_tts.strip():
                    text_tts = b.get("tts_formatted_text")
                if not text_tts or not isinstance(text_tts, str) or not text_tts.strip():
                    diagnostic = {
                        "episode_id": episode_id,
                        "block_id": block_id,
                        "text_tts_present": "text_tts" in b,
                        "tts_formatted_text_present": "tts_formatted_text" in b,
                        "has_text_field": "text" in b,
                    }
                    raise RuntimeError(
                        f"FDA_TEXT_TTS_MISSING: block {block_id} nemá validní text_tts. Diagnostic: {diagnostic}"
                    )
                claim_ids = b.get("claim_ids", [])
                if not isinstance(claim_ids, list):
                    claim_ids = []
                out.append({"block_id": block_id, "text_tts": text_tts, "claim_ids": claim_ids})
        if out:
            return out

    raise ValueError("FDA_INPUT_MISSING: narration_blocks[] not found in tts_ready_package")


def validate_and_fix_shot_plan(
    raw_llm_output: Any,
    tts_ready_package: Dict[str, Any],
    words_per_minute: int = 150,
    auto_fix: bool = True
) -> Tuple[Dict[str, Any], List[str]]:
    """
    Deterministická validace a oprava shot_plan z LLM.
    
    Args:
        raw_llm_output: Surový výstup z LLM (může být špatný tvar; někdy wrapper {"shot_plan": {...}})
        tts_ready_package: Původní tts_ready_package (pro cross-check)
        words_per_minute: WPM pro přepočet času
        auto_fix: Pokud True, pokusí se opravit chyby; pokud False, pouze vrátí errors

    Returns:
        (fixed_wrapper, errors) - fixed_wrapper je vždy canonical wrapper {"shot_plan": {...}}
    """
    import copy

    ep_id = tts_ready_package.get("episode_id") if isinstance(tts_ready_package, dict) else None
    narration_blocks: List[Dict[str, Any]] = _extract_narration_blocks_from_tts_ready_package(tts_ready_package, episode_id=ep_id)

    # Episode-level anchor pool (deterministic).
    # Used as fallback for scenes where local narration is generic and contains no proper nouns/years.
    try:
        _episode_text_parts = []
        for b in narration_blocks:
            t = b.get("text_tts")
            if isinstance(t, str) and t.strip():
                _episode_text_parts.append(t.strip())
        episode_narration_text = " ".join(_episode_text_parts)
    except Exception:
        episode_narration_text = ""
    episode_anchors: List[str] = _extract_temporal_anchors_from_narration(episode_narration_text)

    errors = []
    candidate = raw_llm_output
    if isinstance(candidate, dict) and isinstance(candidate.get("shot_plan"), dict):
        candidate = candidate.get("shot_plan")

    if not isinstance(candidate, dict):
        fixed = {
            "version": FDA_V27_VERSION,
            "source": "tts_ready_package",
            "assumptions": {"words_per_minute": words_per_minute},
            "scenes": [],
        }
        errors.append(f"FDA_INVALID_SHOT_PLAN: Expected object, got {type(raw_llm_output).__name__}")
        return {"shot_plan": fixed}, errors

    fixed = copy.deepcopy(candidate)
    
    # 1. Základní struktura
    if "scenes" not in fixed or not isinstance(fixed["scenes"], list):
        errors.append("Missing or invalid 'scenes' array")
        fixed["version"] = FDA_V27_VERSION
        fixed["source"] = "tts_ready_package"
        fixed["assumptions"] = {"words_per_minute": words_per_minute}
        return {"shot_plan": fixed}, errors
    
    scenes = fixed["scenes"]
    
    if len(scenes) == 0:
        errors.append("No scenes provided")
        fixed["version"] = FDA_V27_VERSION
        fixed["source"] = "tts_ready_package"
        fixed["assumptions"] = {"words_per_minute": words_per_minute}
        return {"shot_plan": fixed}, errors

    # PRE-FLIGHT COVERAGE CHECK (FATAL, before beat-lock/generic-filler checks)
    # Reason: if LLM outputs unknown/merged block_ids (e.g., b_0007 vs expected b_0007a/b_0007b),
    # we must fail deterministically with FDA_COVERAGE_FAIL (not FDA_TEXT_TTS_MISSING).
    expected_block_ids = [b.get("block_id", "") for b in narration_blocks if isinstance(b, dict) and b.get("block_id")]
    used_block_ids: List[str] = []
    for scene in scenes:
        if not isinstance(scene, dict):
            continue
        bids = scene.get("narration_block_ids", [])
        if not isinstance(bids, list):
            bids = []
        used_block_ids.extend([str(bid).strip() for bid in bids if str(bid).strip()])

    if used_block_ids != expected_block_ids:
        missing_blocks = [bid for bid in expected_block_ids if bid not in set(used_block_ids)]
        unexpected_blocks = [bid for bid in used_block_ids if bid not in set(expected_block_ids)]
        seen = set()
        dup = []
        for bid in used_block_ids:
            if bid in seen:
                dup.append(bid)
            seen.add(bid)
        duplicate_blocks = sorted(set(dup))
        order_mismatch = (
            not missing_blocks and not unexpected_blocks and not duplicate_blocks and
            set(used_block_ids) == set(expected_block_ids)
        )
        detail = {
            "missing": missing_blocks[:12],
            "unexpected": unexpected_blocks[:12],
            "duplicates": duplicate_blocks[:12],
            "order_mismatch": bool(order_mismatch),
        }
        
        # AUTO-FIX: Doplnění chybějících bloků
        if auto_fix and missing_blocks:
            print(f"⚠️  FDA AUTO-FIX: LLM vynechalo {len(missing_blocks)} bloků, doplňuji jako nové scény: {missing_blocks}")
            errors.append(f"FDA_COVERAGE_AUTOFIX: Added {len(missing_blocks)} missing blocks as new scenes: {missing_blocks[:5]}")
            
            # Najdeme nejvyšší scene_id číslo
            max_scene_num = 0
            for scene in scenes:
                if isinstance(scene, dict) and isinstance(scene.get("scene_id"), str):
                    sid = scene["scene_id"]
                    # Parse "sc_0001" -> 1
                    try:
                        num = int(sid.split("_")[-1])
                        if num > max_scene_num:
                            max_scene_num = num
                    except:
                        pass
            
            # Vytvoříme mapování block_id -> block data
            block_map = {b.get("block_id"): b for b in narration_blocks if isinstance(b, dict)}
            
            # Přidáme chybějící bloky na konec (zachováme pořadí z expected_block_ids)
            for bid in missing_blocks:
                if bid not in block_map:
                    continue
                
                max_scene_num += 1
                block_data = block_map[bid]
                text_tts = block_data.get("text_tts", "")
                
                # Odhadneme délku
                duration = max(3, int(round(estimate_speech_duration_seconds(text_tts, words_per_minute))))
                
                # Vytvoříme fallback scénu
                new_scene = {
                    "scene_id": f"sc_{max_scene_num:04d}",
                    "start_sec": 0,  # Přepočítáme později
                    "end_sec": duration,
                    "narration_block_ids": [bid],
                    "narration_summary": text_tts[:100] + "..." if len(text_tts) > 100 else text_tts,
                    "emotion": "neutral",
                    "keywords": [
                        "archival photograph", "historical document", "manuscript page",
                        "official letter", "decree document", "dispatch report",
                        "engraving print", "memorial monument"
                    ],
                    "shot_strategy": {
                        "shot_types": ["archival_documents", "maps_context"],
                        "clip_length_sec_range": [4, 9],
                        "cut_rhythm": "slow",
                        "source_preference": ["archive_org"]
                    },
                    "search_queries": [
                        "historical document archive scan",
                        "archival photograph original print",
                        "manuscript page archive copy",
                        "official letter original document",
                        "decree document archive scan"
                    ]
                }
                
                scenes.append(new_scene)
            
            # Seřadíme scény podle expected_block_ids pořadí
            scene_by_first_block = {}
            for scene in scenes:
                bids = scene.get("narration_block_ids", [])
                if bids and isinstance(bids, list) and bids[0]:
                    scene_by_first_block[bids[0]] = scene
            
            # Rebuild scenes v correct order
            ordered_scenes = []
            for bid in expected_block_ids:
                if bid in scene_by_first_block:
                    ordered_scenes.append(scene_by_first_block[bid])
            
            fixed["scenes"] = ordered_scenes
            scenes = ordered_scenes
            
            # Přepočítáme timing
            cumulative = 0
            for scene in scenes:
                scene["start_sec"] = cumulative
                duration = scene["end_sec"] - scene.get("start_sec", 0)
                if duration < 2:
                    duration = 2
                scene["end_sec"] = cumulative + duration
                cumulative = scene["end_sec"]
            
            # Update used_block_ids
            used_block_ids = []
            for scene in scenes:
                bids = scene.get("narration_block_ids", [])
                if isinstance(bids, list):
                    used_block_ids.extend([str(bid).strip() for bid in bids if str(bid).strip()])
        
        # Pokud stále není match, nebo auto_fix=False, vyhodíme error
        if used_block_ids != expected_block_ids:
            raise RuntimeError(
                "FDA_COVERAGE_FAIL: narration_block_ids musí přesně odpovídat tts_ready_package.narration_blocks[] "
                f"(stejné ID i pořadí). Diagnostic: {detail}"
            )
    
    # 1a. Validace že shot_plan NEOBSAHUJE assets[] nebo compile_plan (FDA má být čistý)
    # HARD ERROR - žádný auto-fix
    if "compile_plan" in fixed:
        errors.append("FDA_INVALID_FIELD: shot_plan must NOT contain 'compile_plan' (this is generated by AAR)")
        fixed["version"] = FDA_V27_VERSION
        fixed["source"] = "tts_ready_package"
        fixed["assumptions"] = {"words_per_minute": words_per_minute}
        return {"shot_plan": fixed}, errors
    
    # Check for assets in scenes - HARD ERROR
    for i, scene in enumerate(scenes):
        if "assets" in scene:
            errors.append(f"FDA_INVALID_FIELD: Scene {i} must NOT contain 'assets[]' (this is generated by AAR)")
            fixed["version"] = FDA_V27_VERSION
            fixed["source"] = "tts_ready_package"
            fixed["assumptions"] = {"words_per_minute": words_per_minute}
            return {"shot_plan": fixed}, errors
        
        # Check for any download-related fields - HARD ERROR
        forbidden_fields = ["archive_item_id", "asset_url", "download_url", "manifest"]
        for field in forbidden_fields:
            if field in scene:
                errors.append(f"FDA_INVALID_FIELD: Scene {i} must NOT contain '{field}' (this is generated by AAR)")
                fixed["version"] = FDA_V27_VERSION
                fixed["source"] = "tts_ready_package"
                fixed["assumptions"] = {"words_per_minute": words_per_minute}
                return {"shot_plan": fixed}, errors
    
    # 2. Validace každé scény
    all_block_ids_used = []
    prev_end_sec = None
    
    # ═══════════════════════════════════════════════════════════════════════════
    # IMPORTANT (v2.7 policy):
    # - When auto_fix=False (pipeline default), we MUST NOT mutate LLM output server-side.
    # - When auto_fix=True (legacy tooling), we may repair obvious issues, but NEVER add fallback
    #   search queries or rewrite content beyond mechanical normalization.
    # ═══════════════════════════════════════════════════════════════════════════
    if auto_fix:
        # Optional deterministic timing recalculation (legacy). In strict mode we do not do this.
        cumulative_time = 0.0
        for i, scene in enumerate(scenes):
            block_ids = scene.get("narration_block_ids", [])
            if not isinstance(block_ids, list):
                block_ids = []
            
            scene_duration = 0.0
            for bid in block_ids:
                for nb in narration_blocks:
                    if nb.get("block_id") == bid:
                        text_tts = nb.get("text_tts", "")
                        if text_tts:
                            scene_duration += estimate_speech_duration_seconds(text_tts, words_per_minute)
                        break
            
            if scene_duration < 1.0:
                scene_duration = 3.0
            
            scene["start_sec"] = int(round(cumulative_time))
            scene["end_sec"] = int(round(cumulative_time + scene_duration))
            if scene["end_sec"] - scene["start_sec"] < 2:
                scene["end_sec"] = scene["start_sec"] + 2
            cumulative_time = float(scene["end_sec"])
    
    for i, scene in enumerate(scenes):
        scene_errors = []
        
        # Povinné klíče
        required_keys = [
            "scene_id", "start_sec", "end_sec", "narration_block_ids",
            "narration_summary", "emotion", "keywords", "shot_strategy", "search_queries"
        ]
        
        for key in required_keys:
            if key not in scene:
                scene_errors.append(f"Scene {i}: missing key '{key}'")
        
        if scene_errors:
            errors.extend(scene_errors)
            continue
        
        # Validace emotion (allowlist)
        emotion = scene.get("emotion")
        if emotion not in ALLOWED_EMOTIONS:
            if auto_fix:
                scene["emotion"] = "neutral"  # Default fallback
                errors.append(f"Scene {i}: invalid emotion '{emotion}' → fixed to 'neutral'")
            else:
                errors.append(f"Scene {i}: invalid emotion '{emotion}' (allowed: {ALLOWED_EMOTIONS})")
        
        # Validace shot_types (allowlist)
        shot_strategy = scene.get("shot_strategy", {})
        shot_types = shot_strategy.get("shot_types", [])
        
        invalid_types = [st for st in shot_types if st not in ALLOWED_SHOT_TYPES]
        if invalid_types:
            if auto_fix:
                # Odfiltruj nepovolené
                fixed_types = [st for st in shot_types if st in ALLOWED_SHOT_TYPES]
                if not fixed_types:
                    fixed_types = ["archival_documents"]  # Default fallback
                scene["shot_strategy"]["shot_types"] = fixed_types
                errors.append(f"Scene {i}: invalid shot_types {invalid_types} → removed")
            else:
                errors.append(f"Scene {i}: invalid shot_types {invalid_types} (allowed: {ALLOWED_SHOT_TYPES})")
        
        # Validace cut_rhythm (allowlist)
        cut_rhythm = shot_strategy.get("cut_rhythm")
        if cut_rhythm not in ALLOWED_CUT_RHYTHMS:
            if auto_fix:
                scene["shot_strategy"]["cut_rhythm"] = "medium"  # Default fallback
                errors.append(f"Scene {i}: invalid cut_rhythm '{cut_rhythm}' → fixed to 'medium'")
            else:
                errors.append(f"Scene {i}: invalid cut_rhythm '{cut_rhythm}' (allowed: {ALLOWED_CUT_RHYTHMS})")
        
        # narration_summary: in strict mode we do NOT rewrite it server-side.
        # Any issues are handled by validate_fda_hard_v27 + LLM repair retry.
        
        # Build context text early (used for deterministic fixes below)
        # Use context text (scene blocks + neighbor blocks) to avoid false failures on generic sentences.
        block_ids = scene.get("narration_block_ids", [])
        narration_text = get_scene_narration_context_text(
            narration_blocks, block_ids, episode_id=ep_id, neighbor_window=1
        )

        # No placeholder stripping / keyword/query normalization in strict mode.
        if auto_fix:
            placeholder_patterns = (r"^keyword\d+$", r"^query\d+$", r"^word\d+$", r"^term\d+$")

            def _strip_placeholders(items: Any) -> Tuple[List[str], List[str]]:
                kept: List[str] = []
                removed: List[str] = []
                if not isinstance(items, list):
                    return kept, removed
                for it in items:
                    s = str(it or "").strip()
                    if not s:
                        continue
                    low = s.lower()
                    if any(re.match(p, low) for p in placeholder_patterns):
                        removed.append(s)
                        continue
                    kept.append(s)
                return kept, removed

            keywords_raw = scene.get("keywords", [])
            keywords, removed_kw = _strip_placeholders(keywords_raw)
            if removed_kw:
                errors.append(f"Scene {i}: removed placeholder keywords {removed_kw[:3]}")
            scene["keywords"] = keywords

            queries_raw = scene.get("search_queries", [])
            search_queries, removed_q = _strip_placeholders(queries_raw)
            if removed_q:
                errors.append(f"Scene {i}: removed placeholder queries {removed_q[:3]}")
            scene["search_queries"] = search_queries
        
        # NOTE (policy change):
        # Pipeline MUST NOT fail due to generic/abstract keywords or LLM artifacts.
        # We keep search_queries as the only critical input for AAR.
        
        # v2.7 policy: NO server-side query/keyword sanitization and NO fallback generation.
        # All strict enforcement is done by validate_fda_hard_v27 + LLM repair retries.
        
        # Validace časové kontinuity
        start_sec = scene.get("start_sec")
        end_sec = scene.get("end_sec")
        
        if prev_end_sec is not None:
            if start_sec != prev_end_sec:
                if auto_fix:
                    scene["start_sec"] = prev_end_sec
                    errors.append(f"Scene {i}: time gap/overlap at start ({start_sec} != {prev_end_sec}) → fixed")
                else:
                    errors.append(f"Scene {i}: time gap/overlap (start={start_sec} but should be {prev_end_sec})")
        
        prev_end_sec = scene.get("end_sec")
        
        # Collect block IDs
        block_ids = scene.get("narration_block_ids", [])
        all_block_ids_used.extend(block_ids)
    
    # 3. Cross-check: všechny bloky použity?
    expected_block_ids = [b.get("block_id", "") for b in narration_blocks]
    missing_blocks = set(expected_block_ids) - set(all_block_ids_used)
    duplicate_blocks = [bid for bid in all_block_ids_used if all_block_ids_used.count(bid) > 1]
    
    if missing_blocks:
        errors.append(f"Missing blocks: {missing_blocks}")
    
    if duplicate_blocks:
        errors.append(f"Duplicate blocks: {set(duplicate_blocks)}")
    
    # 3.5+ (v2.7): DO NOT repair keywords/search_queries server-side.
    # The pipeline relies on validate_fda_hard_v27 + LLM repair retry.
    
    # 5. HOTFIX: Self-check před return (regresní kontrola)
    self_check_errors = _self_check_shot_plan(fixed, narration_blocks)
    if self_check_errors:
        errors.extend(self_check_errors)
        # Self-check errors jsou warningy, ne fatal errors
    
    return {"shot_plan": fixed}, errors


# ============================================================================
# HARD GATE (blokující kontroly před uložením shot_planu)
# ============================================================================

def validate_shot_plan_hard_gate(
    shot_plan_wrapper: Dict[str, Any],
    tts_ready_package: Dict[str, Any],
    episode_id: Optional[str] = None,
) -> None:
    """
    v2.7 HARD GATE (server-side):
    - NO server-side auto-fix
    - NO fallback query generation
    - If FDA output is invalid → hard-stop BEFORE asset_resolver
    
    This function is kept for backwards compatibility across the pipeline.

    Policy (v3):
    - Prefer minimal hard-gate for ShotPlan v3 (format + coverage, no stylistic policing)
    - Keep strict v2.7 validator only for legacy episodes/artifacts
    """
    # v3 path
    try:
        sp = shot_plan_wrapper.get("shot_plan") if isinstance(shot_plan_wrapper, dict) else None
        ver = sp.get("version") if isinstance(sp, dict) else None
    except Exception:
        ver = None

    if ver == SHOTPLAN_V3_VERSION:
        from visual_planning_v3 import validate_shotplan_v3_minimal
        validate_shotplan_v3_minimal(shot_plan_wrapper, tts_ready_package, episode_id=episode_id)
        return

    # Legacy fallback (v2.7 strict)
    # ========================================================================
    # FDA v2.7 KEYWORD NORMALIZER - CRITICAL GATE
    # Normalize keywords to 2-5 words BEFORE validation (prevents KEYWORD_WORD_COUNT failures)
    # ========================================================================
    from fda_keyword_normalizer import normalize_all_scene_keywords
    from query_guardrails_utils import get_episode_topic_strict
    
    # Canonical episode_topic is REQUIRED (no heuristics, no narration fallback).
    episode_topic = get_episode_topic_strict(tts_ready_package)
    
    # Normalize all keywords (in-place) - MUST succeed, otherwise hard-stop.
    try:
        normalize_all_scene_keywords(shot_plan_wrapper, episode_topic, verbose=False)
        print(f"✅ FDA keyword normalizer applied (episode_topic: '{episode_topic[:30]}...')")
    except Exception as e:
        msg = str(e)
        # Preserve the explicit error code if already present.
        if "LOCAL_PREFLIGHT_FAILED" in msg:
            raise
        raise RuntimeError(f"LOCAL_PREFLIGHT_FAILED: keyword_normalizer_failed: {msg}") from e
    
    validate_fda_hard_v27(shot_plan_wrapper, tts_ready_package, episode_id=episode_id)


# ============================================================================
# FDA_OUTPUT_VALIDATOR (deterministic post-check; no LLM)
# ============================================================================

FDA_OUTPUT_VALIDATOR_ARTEFACTS = [
    "map",
    "engraving",
    "lithograph",
    "letter",
    "letters",
    "correspondence",
    "document",
    "documents",
    "manuscript",
    "manuscripts",
    "photograph",
    "photographs",
    "painting",
    "portrait",
]

FDA_OUTPUT_VALIDATOR_MIN_KEYWORDS = 5
FDA_OUTPUT_VALIDATOR_MAX_KEYWORDS = 10
FDA_OUTPUT_VALIDATOR_MIN_QUERIES = 3
FDA_OUTPUT_VALIDATOR_MAX_QUERIES = 6

# Extra stop/verb tokens that must never appear as keywords (conservative).
FDA_OUTPUT_VALIDATOR_FORBIDDEN_KEYWORDS_EXTRA = {
    "sent",
    "broke",
    "before",
    "multiple",
    "locations",
    "three",
    "quarters",
    "first",
    "offers",
    "silence",
    "make",
    "made",
}


def validate_fda_output_validator(
    shot_plan_wrapper: Dict[str, Any],
    tts_ready_package: Dict[str, Any],
    episode_id: Optional[str] = None,
) -> None:
    """
    Deterministic post-check BEFORE asset_resolver starts.
    POLICY: MUST NOT fail on keywords/stopwords/LLM style artefacts.
    Hard fail only for truly critical issues:
    - empty scenes
    - invalid timeline (missing/non-numeric/overlap/gap)
    - missing search_queries (0)
    """
    if not (isinstance(shot_plan_wrapper, dict) and isinstance(shot_plan_wrapper.get("shot_plan"), dict)):
        raise RuntimeError("FDA_OUTPUT_VALIDATOR_FAIL: wrapper_invalid")
    if not isinstance(tts_ready_package, dict):
        raise RuntimeError("FDA_OUTPUT_VALIDATOR_FAIL: tts_ready_package_invalid")

    sp = shot_plan_wrapper["shot_plan"]
    scenes = sp.get("scenes") if isinstance(sp.get("scenes"), list) else []

    # Schema checks (keep minimal)
    violations: List[Dict[str, Any]] = []
    schema_allowed_top = {"version", "source", "assumptions", "scenes"}
    extra_top = [k for k in sp.keys() if k not in schema_allowed_top]
    if extra_top:
        violations.append({"type": "SCHEMA_EXTRA_TOP_KEYS", "keys": extra_top[:10]})

    if sp.get("version") != FDA_V27_VERSION:
        violations.append({"type": "SCHEMA_VERSION", "value": sp.get("version")})
    if sp.get("source") != "tts_ready_package":
        violations.append({"type": "SCHEMA_SOURCE", "value": sp.get("source")})

    assumptions = sp.get("assumptions") if isinstance(sp.get("assumptions"), dict) else {}
    if assumptions.get("words_per_minute") != 150:
        violations.append({"type": "ASSUMPTIONS_WPM", "value": assumptions.get("words_per_minute")})

    # Episode anchors (for anchor validation)
    nb = tts_ready_package.get("narration_blocks")
    nb_list = nb if isinstance(nb, list) else []
    episode_text = " ".join([str(b.get("text_tts") or "").strip() for b in nb_list if isinstance(b, dict) and str(b.get("text_tts") or "").strip()])
    episode_anchors = _extract_temporal_anchors_from_narration(episode_text)
    episode_anchors_low = [a.lower() for a in episode_anchors]

    # Forbidden terms from prompt (exact lists used in guards)
    banned_terms = set([t.lower() for t in GENERIC_FILLER_BLACKLIST] + [t.lower() for t in ABSTRACT_KEYWORD_BLACKLIST])

    # Per-scene checks
    for si, scene in enumerate(scenes):
        if not isinstance(scene, dict):
            violations.append({"type": "SCENE_NOT_OBJECT", "scene_index": si})
            continue

        scene_id = str(scene.get("scene_id") or f"sc_{si:04d}")
        narration_summary = str(scene.get("narration_summary") or "")
        keywords = scene.get("keywords") if isinstance(scene.get("keywords"), list) else []
        queries = scene.get("search_queries") if isinstance(scene.get("search_queries"), list) else []

        # narration_summary + keywords are NON-CRITICAL: never fail here.

        # search_queries are CRITICAL: must exist (>=1). We do not enforce structure here.
        if len([q for q in queries if str(q or "").strip()]) < 1:
            violations.append({"type": "MISSING_SEARCH_QUERIES", "scene_id": scene_id})

    if violations:
        diagnostic = {
            "episode_id": episode_id,
            "error": "FDA_OUTPUT_VALIDATOR_FAIL",
            "violations": violations[:30],
        }
        # Preserve legacy prefix used by pipeline retry loop, but keep it only for critical failures.
        raise RuntimeError(f"FDA_OUTPUT_VALIDATOR_FAIL: {json.dumps(diagnostic, ensure_ascii=False)}")


# ============================================================================
# FDA V2.7 HARD VALIDATOR (strict production gate - NO fallbacks)
# ============================================================================

# Forbidden tokens for keywords (articles, prepositions, connectors)
FDA_V27_FORBIDDEN_KEYWORD_TOKENS = {
    "the", "a", "an",
    "upon", "soon", "after", "before", "during", "while",
    "and", "or", "but", "yet", "so",
    "with", "without", "into", "onto", "from", "to",
    "this", "that", "these", "those",
    "he", "she", "they", "it", "his", "her", "their", "its",
    "who", "which", "what", "when", "where", "how",
    "as", "if", "then", "than",
    "began", "began his", "began her", "began their",
    "following", "although",
}

# Physical object types required in keywords (at least 3 must contain one of these)
FDA_V27_PHYSICAL_OBJECT_TYPES = {
    "map", "maps", "city map", "route map", "military map", "battle map",
    "engraving", "engravings", "lithograph", "lithographs",
    "letter", "letters", "dispatch", "dispatches", "correspondence",
    "document", "documents", "decree", "decrees", "report", "reports",
    "manuscript", "manuscripts", "proclamation", "proclamations",
    "photograph", "photographs", "photo", "photos",
    "illustration", "illustrations", "drawing", "drawings",
    "painting", "paintings", "portrait", "portraits",
    "ruins", "burned ruins", "city ruins",
    "city street", "city streets", "street scene",
    "kremlin interior", "palace interior", "building interior",
    "artifact", "artifacts", "relic", "relics",
    "medal", "medals", "uniform", "uniforms", "weapon", "weapons",
    "cannon", "cannons", "flag", "flags", "banner", "banners",
    "statue", "statues", "monument", "monuments",
    "seal", "seals", "coat of arms",
}

# Object types required in search_queries (exactly 1 per query)
FDA_V27_QUERY_OBJECT_TYPES = {
    # EXACT list from spec (object types in search_queries; exactly 1 per query)
    "map",
    "city map",
    "route map",
    "engraving",
    "photograph",
    "illustration",
    "manuscript",
    "letter",
    "dispatch",
    "decree",
    "document",
    "report",
    "city street",
    "ruins",
    "burned ruins",
    "kremlin interior",
}

# Forbidden query start words
FDA_V27_FORBIDDEN_QUERY_STARTS = {
    "following", "upon", "soon", "although",
    "he", "she", "they", "it",
    "this", "these", "that", "those",
    "the", "a", "an",
}

# Forbidden pronoun anchors inside queries
FDA_V27_FORBIDDEN_PRONOUN_ANCHORS = {"he", "they"}  # Spec: forbid standalone pronoun anchors inside queries

# ============================================================================
# Episode Anchor Lock (NO off-topic anchors)
# ============================================================================
# v2.7 originally hard-coded required anchors (Moscow/Napoleon/1812). That caused
# catastrophic off-topic contamination (e.g., Lidice episode rendering Moscow visuals).
#
# We now compute anchors dynamically from the *episode narration* (tts_ready_package),
# and enforce that each query is anchored to the episode.

_V27_ANCHOR_CONNECTORS = {
    "of", "and", "the",
    "de", "da", "di", "du", "del", "della",
    "von", "van",
    # Czech-ish glue words that frequently appear in names/places
    "u", "v", "z", "na", "nad", "pod", "pri", "i",
}

_V27_ANCHOR_STOPWORDS = {
    # Query forbidden starts (also common false-positive titlecase tokens)
    *FDA_V27_FORBIDDEN_QUERY_STARTS,
    # Common sentence starters / prepositions
    "in", "on", "at", "as", "by", "for", "from", "into", "onto", "with", "without",
    # Generic non-anchors
    "history", "historical", "archive", "archival", "documentary",
    "war", "wars", "battle", "battles", "city", "village", "country", "empire",
    # Months (common false positives)
    "january", "february", "march", "april", "may", "june", "july", "august",
    "september", "october", "november", "december",
}


def _extract_anchor_terms_from_text_v27(text: str, max_terms: int = 32) -> List[str]:
    """
    Extract episode-local anchors from free text:
    - years (e.g., 1942)
    - proper-noun phrases (TitleCase sequences + acronyms)
    - plus components of multiword phrases (e.g., "Reinhard Heydrich" -> "Heydrich")
    """
    if not text or not isinstance(text, str):
        return []

    years = re.findall(r"\b(1\d{3}|20\d{2})\b", text)

    # Tokenize including diacritics; keep hyphenated names.
    tokens = re.findall(r"[0-9A-Za-zÀ-ž]+(?:[-'][0-9A-Za-zÀ-ž]+)*", text)

    def _is_titleish(tok: str) -> bool:
        if not tok:
            return False
        if tok.isupper() and len(tok) >= 2 and any(ch.isalpha() for ch in tok):
            return True
        return tok[0].isupper() and any(ch.isalpha() for ch in tok)

    phrases: List[str] = []
    i = 0
    while i < len(tokens):
        tok = tokens[i]
        low = tok.lower()
        if _is_titleish(tok) and low not in _V27_ANCHOR_STOPWORDS:
            parts = [tok]
            j = i + 1
            while j < len(tokens) and len(parts) < 5:
                t2 = tokens[j]
                l2 = t2.lower()
                if l2 in _V27_ANCHOR_CONNECTORS:
                    parts.append(t2)
                    j += 1
                    continue
                if _is_titleish(t2) and l2 not in _V27_ANCHOR_STOPWORDS:
                    parts.append(t2)
                    j += 1
                    continue
                break

            # Trim connectors at edges
            while parts and parts[0].lower() in _V27_ANCHOR_CONNECTORS:
                parts = parts[1:]
            while parts and parts[-1].lower() in _V27_ANCHOR_CONNECTORS:
                parts = parts[:-1]

            phrase = " ".join(parts).strip()
            if phrase and len(phrase) >= 3:
                phrases.append(phrase)
            i = j
            continue
        i += 1

    # Build final term list (years first), de-duped (case-insensitive).
    terms: List[str] = []
    seen: set = set()

    for y in years:
        yl = y.lower()
        if yl not in seen:
            terms.append(y)
            seen.add(yl)

    for ph in phrases:
        pl = ph.lower()
        if pl in seen:
            continue
        terms.append(ph)
        seen.add(pl)

        # Add components of multiword phrases as usable anchors (avoid connectors/stopwords).
        for part in ph.split():
            p = part.strip()
            if not p:
                continue
            l = p.lower()
            if l in _V27_ANCHOR_CONNECTORS or l in _V27_ANCHOR_STOPWORDS:
                continue
            if len(p) < 3:
                continue
            if l not in seen:
                terms.append(p)
                seen.add(l)

        if len(terms) >= max_terms:
            break

    return terms[:max_terms]


def _extract_episode_anchor_terms_v27(tts_ready_package: Dict[str, Any]) -> List[str]:
    """
    Compute episode anchors from tts_ready_package narration_blocks[*].text_tts,
    AND from canonical episode_metadata.topic (to capture digits like "1871" even
    when narration uses spoken years like "eighteen seventy-one").
    """
    if not isinstance(tts_ready_package, dict):
        return []
    blocks = tts_ready_package.get("narration_blocks", [])
    if not isinstance(blocks, list):
        return []
    all_texts = []
    for b in blocks:
        if isinstance(b, dict):
            t = b.get("text_tts")
            if isinstance(t, str) and t.strip():
                all_texts.append(t.strip())
    # Also include canonical topic text (no narration heuristics; metadata-only).
    try:
        em = tts_ready_package.get("episode_metadata")
        if isinstance(em, dict):
            topic = str(em.get("topic") or "").strip()
            if topic:
                all_texts.insert(0, topic)
    except Exception:
        pass
    return _extract_anchor_terms_from_text_v27(" ".join(all_texts), max_terms=48)


def _count_words(text: str) -> int:
    """Count words in text."""
    if not text or not isinstance(text, str):
        return 0
    return len(text.strip().split())


def _contains_object_type(text: str, object_types: set) -> bool:
    """Check if text contains any object type (phrase match with word boundaries)."""
    if not text:
        return False
    low = text.lower()
    for obj in sorted(object_types, key=len, reverse=True):
        pat = r"\b" + re.escape(obj.lower()) + r"\b"
        if re.search(pat, low):
            return True
    return False


def _count_object_types(text: str, object_types: set) -> int:
    """
    Count distinct object types in text using phrase word-boundary matching (longest first).
    
    IMPORTANT: Matches multi-word types BEFORE single-word types to prevent overlap.
    Example: "city map" should match as 1 type, not "city" + "map".
    
    Returns: Count of distinct, non-overlapping object types found.
    """
    if not text:
        return 0
    low = text.lower()
    matched_spans: List[Tuple[int, int]] = []
    
    # Sort by length (longest first) to match multi-word phrases before single words
    # This prevents "city map" from matching both "city map" and "map"
    sorted_types = sorted(object_types, key=lambda x: (len(x.split()), len(x)), reverse=True)
    
    for obj in sorted_types:
        pat = re.compile(r"\b" + re.escape(obj.lower()) + r"\b")
        for m in pat.finditer(low):
            span = (m.start(), m.end())
            # Check if this span overlaps with any already matched span
            has_overlap = False
            for existing_start, existing_end in matched_spans:
                # Overlap check: spans overlap if one starts before the other ends
                if not (span[1] <= existing_start or span[0] >= existing_end):
                    has_overlap = True
                    break
            
            if not has_overlap:
                matched_spans.append(span)
                # Only count this object type once (first non-overlapping match)
                break
    
    return len(matched_spans)


def _has_forbidden_token(text: str, forbidden: set) -> Optional[str]:
    """Check if text contains forbidden token. Returns the token if found."""
    if not text:
        return None
    words = text.lower().split()
    for word in words:
        # Clean punctuation
        word_clean = re.sub(r'[^\w\s]', '', word)
        if word_clean in forbidden:
            return word_clean
    return None


def _is_valid_narration_summary_v27(summary: str) -> Tuple[bool, Optional[str]]:
    """
    Validate narration_summary for v2.7:
    - Exactly 1 sentence
    - No semicolons
    - Ends with exactly one period
    - No broken fragments like "began his ."
    """
    if not summary or not isinstance(summary, str):
        return False, "empty_or_invalid"
    
    summary = summary.strip()
    
    # No semicolons
    if ";" in summary:
        return False, "contains_semicolon"
    
    # Must end with exactly one period
    if not summary.endswith("."):
        return False, "does_not_end_with_period"
    # Exactly one sentence → exactly one '.' character in the whole string (strict)
    if summary.count(".") != 1:
        return False, "multiple_periods_detected"
    # No other sentence terminators
    if "!" in summary or "?" in summary:
        return False, "contains_other_sentence_terminator"
    
    # Check for broken fragments
    broken_patterns = [
        (r'\s+\.$', "ends_with_space_period"),  # " ."
        (r'\bhis\s+\.$', "fragment_his_period"),  # "his ."
        (r'\bher\s+\.$', "fragment_her_period"),  # "her ."
        (r'\btheir\s+\.$', "fragment_their_period"),  # "their ."
        (r'\bthe\s+\.$', "fragment_the_period"),  # "the ."
        (r'\bof\s+\.$', "fragment_of_period"),  # "of ."
        (r'\bto\s+\.$', "fragment_to_period"),  # "to ."
        (r'\bbegan\s+his\s+\.$', "fragment_began_his"),  # "began his ."
        (r'\bbegan\s+her\s+\.$', "fragment_began_her"),  # "began her ."
        (r'\bbegan\s+\.$', "fragment_began_period"),  # "began ."
        (r'\s{2,}', "double_whitespace"),  # Multiple spaces
        (r'\bThe of\b', "article_preposition"),  # "The of Moscow"
        (r'\bA of\b', "article_preposition"),  # "A of ..."
        (r'\bAn of\b', "article_preposition"),  # "An of ..."
        (r"'s\s+,", "possessive_space_comma"),  # "Napoleon's ,"
        (r"'s\s+\.", "possessive_space_period"),  # "Napoleon's ."
        (r'\s+,', "space_before_comma"),  # Any space before comma
        (r',\s+,', "double_comma"),  # Double comma
    ]
    
    for pattern, reason in broken_patterns:
        if re.search(pattern, summary, re.IGNORECASE):
            return False, reason
    
    return True, None


def apply_deterministic_generators_v27(
    shot_plan_wrapper: Dict[str, Any],
    tts_ready_package: Dict[str, Any],
    episode_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Apply deterministic generators to FDA output (post-LLM processing).
    
    This function takes LLM output and applies strict deterministic generation for:
    - narration_summary (compress, not drop - meaning-lock)
    - keywords (exactly 8, with forbidden token filtering)
    - search_queries (exactly 5, with templates based on scene type)
    - shot_strategy (source_preference, conservative shot_types)
    
    CRITICAL: This function MUST NOT modify shot_plan.version.
    
    Returns: Updated shot_plan_wrapper
    """
    import copy
    
    if not isinstance(shot_plan_wrapper, dict) or not isinstance(shot_plan_wrapper.get("shot_plan"), dict):
        print("⚠️  apply_deterministic_generators_v27: Invalid wrapper, skipping")
        return shot_plan_wrapper
    
    # ========================================================================
    # VERSION LOCK: Preserve original version (MUST NOT be modified)
    # ========================================================================
    original_version = None
    try:
        if "shot_plan" in shot_plan_wrapper and isinstance(shot_plan_wrapper["shot_plan"], dict):
            original_version = shot_plan_wrapper["shot_plan"].get("version")
    except Exception:
        pass
    
    result = copy.deepcopy(shot_plan_wrapper)
    shot_plan = result["shot_plan"]
    
    # Extract narration blocks
    narration_blocks = tts_ready_package.get("narration_blocks", [])
    if not isinstance(narration_blocks, list):
        print("⚠️  apply_deterministic_generators_v27: No narration_blocks, skipping")
        return shot_plan_wrapper
    
    block_dict = {b.get("block_id", ""): b for b in narration_blocks if isinstance(b, dict)}
    
    scenes = shot_plan.get("scenes", [])
    if not isinstance(scenes, list):
        print("⚠️  apply_deterministic_generators_v27: No scenes, skipping")
        return shot_plan_wrapper
    
    print(f"🔧 Applying deterministic generators to {len(scenes)} scenes...")

    # SINGLE ENTRYPOINT: Get episode_topic from metadata (PRIMARY GATE)
    try:
        from query_guardrails_utils import get_episode_topic_strict
        episode_topic = get_episode_topic_strict(tts_ready_package)
        print(f"✅ Episode topic validated: '{episode_topic}'")
    except ImportError:
        # Fallback if utils not available (but still strict - same logic)
        episode_metadata = tts_ready_package.get("episode_metadata", {})
        topic = episode_metadata.get("topic")
        if not topic or not str(topic).strip():
            raise ValueError(
                "EPISODE_TOPIC_MISSING: episode_metadata must contain non-empty 'topic' field. "
                "Cannot generate anchored queries without episode topic."
            )
        episode_topic = str(topic).strip()
        print(f"✅ Episode topic validated (fallback): '{episode_topic}'")

    # Episode anchor hints (used only as optional stabilizers for deterministic keyword/query templates).
    # NOTE: This is NOT used as episode_topic (canonical topic is metadata-only).
    episode_anchor_hints = _extract_episode_anchor_terms_v27(tts_ready_package)
    
    for i, scene in enumerate(scenes):
        if not isinstance(scene, dict):
            continue
        
        scene_id = scene.get("scene_id", f"sc_{i:04d}")
        
        # Get narration text for this scene
        block_ids = scene.get("narration_block_ids", [])
        texts = []
        for bid in block_ids:
            block = block_dict.get(bid)
            if block:
                text_tts = block.get("text_tts", "")
                if text_tts:
                    texts.append(text_tts)
        
        narration_text = " ".join(texts)
        
        if not narration_text:
            print(f"⚠️  Scene {scene_id}: No narration text, skipping generators")
            continue
        
        # 1. Generate narration_summary (meaning-lock)
        try:
            summary = _generate_deterministic_summary_v27(narration_text)
            scene["narration_summary"] = summary
            print(f"✅ Scene {scene_id}: Generated summary")
        except Exception as e:
            print(f"⚠️  Scene {scene_id}: Summary generation failed: {e}")
        
        # 2. Generate keywords (with guardrails)
        try:
            keywords = _generate_deterministic_keywords_v27(narration_text, episode_anchor_hints=episode_anchor_hints)
            scene["keywords"] = keywords
            print(f"✅ Scene {scene_id}: Generated {len(keywords)} keywords")
        except Exception as e:
            print(f"⚠️  Scene {scene_id}: Keywords generation failed: {e}")
        
        # 3. Generate search_queries (with templates + guardrails)
        try:
            # First generate queries deterministically
            # NOTE: _generate_deterministic_queries_v27 accepts episode_anchor_hints for its internal logic
            # But we use episode_topic (from metadata) for guardrails validation
            raw_queries = _generate_deterministic_queries_v27(narration_text, i, episode_anchor_hints=episode_anchor_hints)
            
            # Then apply guardrails for validation/refinement
            if not QUERY_GUARDRAILS_AVAILABLE:
                raise RuntimeError(
                    "QUERY_GUARDRAILS_UNAVAILABLE: Query guardrails module not loaded. "
                    "Cannot proceed with query generation without validation. "
                    "Check import errors at startup."
                )
            
            shot_types = scene.get("shot_strategy", {}).get("shot_types", [])
            
            # Use episode_topic from PRIMARY GATE (metadata), not episode_anchor_hints
            validated_queries, diagnostics = validate_and_fix_queries(
                raw_queries,
                narration_text,
                shot_types=shot_types,
                episode_topic=episode_topic,  # From metadata, validated at start
                min_valid_queries=5,
                max_regen_attempts=2,
                verbose=False
            )
            
            scene["search_queries"] = validated_queries
            scene["_query_diagnostics"] = diagnostics
            
            if diagnostics.get('low_coverage'):
                print(f"⚠️  Scene {scene_id}: LOW COVERAGE - only {diagnostics['final_count']}/5 valid queries")
            else:
                print(f"✅ Scene {scene_id}: Generated {len(validated_queries)} queries (validated)")
                
        except Exception as e:
            print(f"⚠️  Scene {scene_id}: Queries generation failed: {e}")
            raise  # Re-raise to fail loudly
        
        # 4. Fix shot_strategy
        try:
            _fix_shot_strategy_v27(scene, narration_text)
            print(f"✅ Scene {scene_id}: Fixed shot_strategy")
        except Exception as e:
            print(f"⚠️  Scene {scene_id}: shot_strategy fix failed: {e}")

    # 5. Recompute timings deterministically from narration text (critical for VO sync)
    try:
        _recompute_scene_timings_v27(scenes, narration_blocks, words_per_minute=150)
        print("✅ Timings recomputed from narration word counts")
    except Exception as e:
        # This MUST be extremely robust; if it fails, validator will fail-stop anyway.
        print(f"⚠️  Timing recomputation failed: {e}")
    
    print(f"✅ Deterministic generators applied to all scenes")
    
    # ========================================================================
    # VERSION LOCK VERIFICATION: Ensure version was NOT modified
    # ========================================================================
    final_version = None
    try:
        if "shot_plan" in result and isinstance(result["shot_plan"], dict):
            final_version = result["shot_plan"].get("version")
        
        if original_version != final_version:
            # CRITICAL ERROR: Version was modified during postprocessing!
            print(f"❌ FDA_POSTPROCESS_VERSION_CHANGED {{episode_id: '{episode_id}', original: '{original_version}', final: '{final_version}'}}")
            # RESTORE original version (defensive fix)
            result["shot_plan"]["version"] = original_version
            print(f"🔧 FDA_VERSION_RESTORED {{episode_id: '{episode_id}', restored_to: '{original_version}'}}")
    except Exception as e:
        print(f"⚠️  Version lock verification failed: {e}")
    
    return result


def validate_fda_hard_v27(
    shot_plan_wrapper: Dict[str, Any],
    tts_ready_package: Dict[str, Any],
    episode_id: Optional[str] = None,
) -> None:
    """
    FDA v2.7 HARD VALIDATOR - strict production gate with NO fallbacks.
    
    If validation fails, raises RuntimeError with FDA_VALIDATION_FAILED prefix
    and includes first ~5 violations in the message.
    
    This validator MUST pass before asset_resolver can start.
    
    Checks (per spec):
    - shot_plan.version == "fda_v2.7"
    - shot_plan.source == "tts_ready_package"
    - NO extra top-level fields (total_duration_sec, total_scenes, etc.)
    - scenes cover all narration_block_ids exactly once, in order
    - start_sec/end_sec are int, no gaps/overlaps, min 2 seconds, first scene starts at 0
    - narration_summary: exactly 1 sentence, no ';', ends with one '.', no fragments like "began his ."
    - keywords: exactly 8 items; 2–5 words each; no forbidden tokens; >=3 contain physical object type
    - search_queries: exactly 5 per scene; each 5–9 words; forbidden starts; no "He"/"They" inside;
      contains >=1 required anchor; contains exactly 1 object type (from exact list)
    - shot_strategy.source_preference == ["archive_org"]
    """
    violations: List[Dict[str, Any]] = []
    
    # Basic structure check
    if not isinstance(shot_plan_wrapper, dict) or not isinstance(shot_plan_wrapper.get("shot_plan"), dict):
        violations.append({
            "type": "INVALID_WRAPPER",
            "message": "Expected wrapper {'shot_plan': {...}}",
        })
        raise RuntimeError(f"FDA_VALIDATION_FAILED: {json.dumps({'episode_id': episode_id, 'violations': violations[:5]}, ensure_ascii=False)}")
    
    shot_plan = shot_plan_wrapper["shot_plan"]
    
    # 1. VERSION CHECK
    version = shot_plan.get("version", "")
    
    # ========================================================================
    # DIAGNOSTIC LOG: Validator expected vs actual version
    # ========================================================================
    print(f"🔍 FDA_DIAGNOSTIC {{episode_id: '{episode_id}', stage: 'validator', expected_version: '{FDA_V27_VERSION}', actual_version: '{version}'}}")
    
    if version != FDA_V27_VERSION:
        violations.append({
            "type": "VERSION_MISMATCH",
            "message": f"Expected version '{FDA_V27_VERSION}', got '{version}'",
            "expected": FDA_V27_VERSION,
            "actual": version,
        })
    
    # 1a. SOURCE CHECK
    source = shot_plan.get("source", "")
    if source != "tts_ready_package":
        violations.append({
            "type": "SOURCE_MISMATCH",
            "message": f"Expected source 'tts_ready_package', got '{source}'",
            "expected": "tts_ready_package",
            "actual": source,
        })
    
    # 1b. NO EXTRA TOP-LEVEL FIELDS
    allowed_top_level_keys = {"version", "source", "assumptions", "scenes"}
    extra_keys = set(shot_plan.keys()) - allowed_top_level_keys
    if extra_keys:
        violations.append({
            "type": "EXTRA_TOP_LEVEL_FIELDS",
            "message": f"shot_plan contains forbidden top-level fields: {list(extra_keys)}",
            "extra_fields": list(extra_keys),
            "allowed_fields": list(allowed_top_level_keys),
        })
    
    # Get narration blocks for coverage check
    if not isinstance(tts_ready_package, dict):
        violations.append({
            "type": "INVALID_TTS_PACKAGE",
            "message": "tts_ready_package must be a dict",
        })
        raise RuntimeError(f"FDA_VALIDATION_FAILED: {json.dumps({'episode_id': episode_id, 'violations': violations[:5]}, ensure_ascii=False)}")
    
    nb_raw = tts_ready_package.get("narration_blocks", [])
    if not isinstance(nb_raw, list) or not nb_raw:
        violations.append({
            "type": "MISSING_NARRATION_BLOCKS",
            "message": "tts_ready_package.narration_blocks[] is required",
        })
    
    expected_block_ids = []
    for b in nb_raw:
        if isinstance(b, dict):
            bid = str(b.get("block_id") or "").strip()
            if bid:
                expected_block_ids.append(bid)
    nb_dict = {str(b.get("block_id") or "").strip(): b for b in nb_raw if isinstance(b, dict) and str(b.get("block_id") or "").strip()}
    
    scenes = shot_plan.get("scenes", [])
    if not isinstance(scenes, list) or not scenes:
        violations.append({
            "type": "EMPTY_SCENES",
            "message": "shot_plan.scenes must be a non-empty list",
        })
        raise RuntimeError(f"FDA_VALIDATION_FAILED: {json.dumps({'episode_id': episode_id, 'violations': violations[:5]}, ensure_ascii=False)}")
    
    # 2. COVERAGE CHECK - all block_ids exactly once, in order
    used_block_ids = []
    for scene in scenes:
        if isinstance(scene, dict):
            block_ids = scene.get("narration_block_ids", [])
            if isinstance(block_ids, list):
                used_block_ids.extend([str(bid).strip() for bid in block_ids if str(bid).strip()])
    
    if used_block_ids != expected_block_ids:
        missing = [bid for bid in expected_block_ids if bid not in set(used_block_ids)]
        extra = [bid for bid in used_block_ids if bid not in set(expected_block_ids)]
        duplicates = [bid for bid in set(used_block_ids) if used_block_ids.count(bid) > 1]
        
        violations.append({
            "type": "COVERAGE_MISMATCH",
            "message": f"Block IDs mismatch: expected {len(expected_block_ids)}, got {len(used_block_ids)}",
            "missing": missing[:5],
            "extra": extra[:5],
            "duplicates": duplicates[:5],
            "order_match": used_block_ids == expected_block_ids if len(used_block_ids) == len(expected_block_ids) else False,
        })
    
    # Episode Anchor Lock (computed once for the episode)
    # Include BOTH narration anchors AND episode_topic anchors
    episode_anchor_terms = _extract_episode_anchor_terms_v27(tts_ready_package)
    
    # CRITICAL: Also include anchors from episode_metadata.topic
    # Query guardrails use episode_topic as anchor source, so validator must accept those too
    try:
        episode_metadata = tts_ready_package.get("episode_metadata", {})
        topic_str = str(episode_metadata.get("topic") or "").strip()
        if topic_str:
            topic_anchors = _extract_anchor_terms_from_text_v27(topic_str, max_terms=16)
            episode_anchor_terms = topic_anchors + episode_anchor_terms
    except Exception:
        pass  # Non-fatal if topic extraction fails
    
    # Normalize + de-dupe + prefer longer phrases for matching
    _seen_anchor = set()
    episode_anchor_terms_norm: List[str] = []
    for t in episode_anchor_terms:
        s = str(t or "").strip()
        if not s:
            continue
        low = s.lower()
        if low in _seen_anchor:
            continue
        _seen_anchor.add(low)
        episode_anchor_terms_norm.append(s)
    episode_anchor_terms_norm.sort(key=lambda x: (len(x.split()), len(x)), reverse=True)
    episode_anchor_terms_set = {t.lower() for t in episode_anchor_terms_norm}

    # Collect stats for quality log
    total_query_words = 0
    total_queries = 0
    anchor_lock_violations = 0
    
    # Per-scene validation
    for si, scene in enumerate(scenes):
        if not isinstance(scene, dict):
            violations.append({
                "type": "SCENE_NOT_DICT",
                "scene_index": si,
                "message": f"Scene {si} is not a dict",
            })
            continue
        
        scene_id = scene.get("scene_id", f"sc_{si:04d}")
        
        # 3. TIMING CHECK - start_sec/end_sec must be int, no gaps/overlaps, min 2 sec
        start_sec = scene.get("start_sec")
        end_sec = scene.get("end_sec")
        
        # Must be integers (not floats)
        if not isinstance(start_sec, int):
            violations.append({
                "type": "TIMING_NOT_INT",
                "scene_id": scene_id,
                "field": "start_sec",
                "value": start_sec,
                "value_type": type(start_sec).__name__,
                "message": f"Scene {scene_id}: start_sec must be int, got {type(start_sec).__name__}",
            })
        
        if not isinstance(end_sec, int):
            violations.append({
                "type": "TIMING_NOT_INT",
                "scene_id": scene_id,
                "field": "end_sec",
                "value": end_sec,
                "value_type": type(end_sec).__name__,
                "message": f"Scene {scene_id}: end_sec must be int, got {type(end_sec).__name__}",
            })
        
        # First scene must start at 0
        if si == 0 and isinstance(start_sec, int) and start_sec != 0:
            violations.append({
                "type": "TIMING_FIRST_SCENE_NOT_ZERO",
                "scene_id": scene_id,
                "start_sec": start_sec,
                "message": f"First scene must start at 0, got {start_sec}",
            })
        
        # Duration check (min 2 seconds)
        if isinstance(start_sec, (int, float)) and isinstance(end_sec, (int, float)):
            duration = end_sec - start_sec
            if duration < 2:
                violations.append({
                    "type": "TIMING_TOO_SHORT",
                    "scene_id": scene_id,
                    "duration": duration,
                    "message": f"Scene {scene_id}: duration {duration}s < 2s minimum",
                })
            # Realism check: duration should roughly match narration word_count-based estimate.
            # Prevents pathological "2s per block" outputs that pass continuity but break VO sync.
            try:
                bids = scene.get("narration_block_ids", [])
                if not isinstance(bids, list):
                    bids = []
                expected_dur = 0
                for bid in bids:
                    b = nb_dict.get(str(bid).strip()) or {}
                    txt = b.get("text_tts") or ""
                    sec = estimate_speech_duration_seconds_int(txt, words_per_minute=150, min_seconds=2)
                    if sec <= 0:
                        sec = 3
                    expected_dur += sec
                # Allow tiny drift (rounding / edge cases), but not orders of magnitude.
                if expected_dur >= 4 and abs(int(duration) - int(expected_dur)) > 2:
                    violations.append({
                        "type": "TIMING_VO_MISMATCH",
                        "scene_id": scene_id,
                        "expected_duration_sec": expected_dur,
                        "actual_duration_sec": duration,
                        "message": f"Scene {scene_id}: duration {duration}s does not match VO estimate {expected_dur}s (±2s)",
                    })
            except Exception:
                # Never crash validator for this check; other timing gates still apply.
                pass
            
            # Check gaps/overlaps with previous scene
            if si > 0:
                prev_scene = scenes[si - 1]
                if isinstance(prev_scene, dict):
                    prev_end = prev_scene.get("end_sec")
                    if isinstance(prev_end, (int, float)) and isinstance(start_sec, (int, float)):
                        if start_sec != prev_end:
                            if start_sec > prev_end:
                                violations.append({
                                    "type": "TIMING_GAP",
                                    "scene_id": scene_id,
                                    "prev_end": prev_end,
                                    "start": start_sec,
                                    "gap": start_sec - prev_end,
                                    "message": f"Scene {scene_id}: gap of {start_sec - prev_end}s after previous scene",
                                })
                            else:
                                violations.append({
                                    "type": "TIMING_OVERLAP",
                                    "scene_id": scene_id,
                                    "prev_end": prev_end,
                                    "start": start_sec,
                                    "overlap": prev_end - start_sec,
                                    "message": f"Scene {scene_id}: overlap of {prev_end - start_sec}s with previous scene",
                                })
        
        # 4. NARRATION_SUMMARY CHECK
        narration_summary = scene.get("narration_summary", "")
        is_valid_summary, summary_reason = _is_valid_narration_summary_v27(narration_summary)
        if not is_valid_summary:
            violations.append({
                "type": "INVALID_NARRATION_SUMMARY",
                "scene_id": scene_id,
                "reason": summary_reason,
                "summary_preview": narration_summary[:80] if narration_summary else "(empty)",
                "message": f"Scene {scene_id}: narration_summary invalid - {summary_reason}",
            })
        
        # 5. KEYWORDS CHECK - exactly 8 items, 2-5 words each, no forbidden tokens, >=3 with physical object
        keywords = scene.get("keywords", [])
        if not isinstance(keywords, list):
            keywords = []
        
        # Exactly 8 keywords
        if len(keywords) != 8:
            violations.append({
                "type": "KEYWORDS_COUNT",
                "scene_id": scene_id,
                "expected": 8,
                "actual": len(keywords),
                "message": f"Scene {scene_id}: expected 8 keywords, got {len(keywords)}",
            })
        
        physical_object_count = 0
        for ki, kw in enumerate(keywords):
            kw_str = str(kw or "").strip()
            word_count = _count_words(kw_str)
            
            # 2-5 words
            if word_count < 2 or word_count > 5:
                violations.append({
                    "type": "KEYWORD_WORD_COUNT",
                    "scene_id": scene_id,
                    "keyword_index": ki,
                    "keyword": kw_str[:40],
                    "word_count": word_count,
                    "message": f"Scene {scene_id} keyword[{ki}]: '{kw_str[:30]}' has {word_count} words (need 2-5)",
                })
            
            # No forbidden tokens
            forbidden_found = _has_forbidden_token(kw_str, FDA_V27_FORBIDDEN_KEYWORD_TOKENS)
            if forbidden_found:
                violations.append({
                    "type": "KEYWORD_FORBIDDEN_TOKEN",
                    "scene_id": scene_id,
                    "keyword_index": ki,
                    "keyword": kw_str[:40],
                    "forbidden_token": forbidden_found,
                    "message": f"Scene {scene_id} keyword[{ki}]: contains forbidden token '{forbidden_found}'",
                })
            
            # Check for physical object type
            if _contains_object_type(kw_str, FDA_V27_PHYSICAL_OBJECT_TYPES):
                physical_object_count += 1
        
        # At least 3 keywords with physical object
        if physical_object_count < 3:
            violations.append({
                "type": "KEYWORDS_PHYSICAL_OBJECTS",
                "scene_id": scene_id,
                "required": 3,
                "actual": physical_object_count,
                "message": f"Scene {scene_id}: only {physical_object_count}/3 keywords contain physical object type",
            })
        
        # 6. SEARCH_QUERIES CHECK - exactly 5, 5-9 words each, proper structure
        search_queries = scene.get("search_queries", [])
        if not isinstance(search_queries, list):
            search_queries = []
        
        # Exactly 5 queries
        if len(search_queries) != 5:
            violations.append({
                "type": "QUERIES_COUNT",
                "scene_id": scene_id,
                "expected": 5,
                "actual": len(search_queries),
                "message": f"Scene {scene_id}: expected 5 search_queries, got {len(search_queries)}",
            })
        
        for qi, query in enumerate(search_queries):
            query_str = str(query or "").strip()
            word_count = _count_words(query_str)
            total_query_words += word_count
            total_queries += 1
            
            # 5-9 words
            if word_count < 5 or word_count > 9:
                violations.append({
                    "type": "QUERY_WORD_COUNT",
                    "scene_id": scene_id,
                    "query_index": qi,
                    "query": query_str[:60],
                    "word_count": word_count,
                    "message": f"Scene {scene_id} query[{qi}]: '{query_str[:40]}' has {word_count} words (need 5-9)",
                })
            
            # Check start word
            first_word = query_str.split()[0].lower() if query_str.split() else ""
            if first_word in FDA_V27_FORBIDDEN_QUERY_STARTS:
                violations.append({
                    "type": "QUERY_FORBIDDEN_START",
                    "scene_id": scene_id,
                    "query_index": qi,
                    "query": query_str[:60],
                    "start_word": first_word,
                    "message": f"Scene {scene_id} query[{qi}]: starts with forbidden '{first_word}'",
                })
            
            # Check for forbidden pronoun anchors anywhere inside (standalone tokens)
            words_in_query = [re.sub(r"[^\w]", "", w.lower()) for w in query_str.split()]
            for bad in FDA_V27_FORBIDDEN_PRONOUN_ANCHORS:
                if bad in words_in_query:
                    violations.append({
                        "type": "QUERY_PRONOUN_ANCHOR",
                        "scene_id": scene_id,
                        "query_index": qi,
                        "query": query_str[:60],
                        "pronoun": bad,
                        "message": f"Scene {scene_id} query[{qi}]: contains forbidden pronoun anchor '{bad}'",
                    })
                    break
            
            # Check for exactly 1 object type
            object_type_count = _count_object_types(query_str, FDA_V27_QUERY_OBJECT_TYPES)
            if object_type_count != 1:
                violations.append({
                    "type": "QUERY_OBJECT_TYPE_COUNT",
                    "scene_id": scene_id,
                    "query_index": qi,
                    "query": query_str[:60],
                    "object_type_count": object_type_count,
                    "message": f"Scene {scene_id} query[{qi}]: has {object_type_count} object types (need exactly 1)",
                })
            
            # Episode Anchor Lock:
            # (1) each query must contain >=1 anchor extracted from the episode narration
            # (2) queries must NOT introduce new anchors not present in the episode
            query_lower = query_str.lower()

            has_episode_anchor = False
            if episode_anchor_terms_norm:
                for a in episode_anchor_terms_norm:
                    pat = r"\b" + re.escape(a.lower()) + r"\b"
                    if re.search(pat, query_lower):
                        has_episode_anchor = True
                        break
            else:
                # Degenerate fallback: require at least some anchor-ish signal in the query.
                has_episode_anchor = len(_extract_anchor_terms_from_text_v27(query_str, max_terms=8)) > 0

            if not has_episode_anchor:
                violations.append({
                    "type": "QUERY_MISSING_EPISODE_ANCHOR",
                    "scene_id": scene_id,
                    "query_index": qi,
                    "query": query_str[:80],
                    "message": f"Scene {scene_id} query[{qi}]: missing episode anchor (Episode Anchor Lock)",
                })
                anchor_lock_violations += 1

            # No off-topic anchors: extract anchor-like terms from the query and ensure they exist in episode anchors.
            if episode_anchor_terms_set:
                query_terms = _extract_anchor_terms_from_text_v27(query_str, max_terms=12)
                for t in query_terms:
                    tl = str(t or "").strip().lower()
                    if not tl:
                        continue
                    if tl in _V27_ANCHOR_STOPWORDS:
                        continue
                    if tl not in episode_anchor_terms_set:
                        violations.append({
                            "type": "QUERY_ANCHOR_NOT_IN_EPISODE",
                            "scene_id": scene_id,
                            "query_index": qi,
                            "query": query_str[:80],
                            "offending_anchor": t,
                            "message": f"Scene {scene_id} query[{qi}]: anchor '{t}' not present in episode narration (off-topic contamination)",
                        })
                        anchor_lock_violations += 1
                        break
        
        # DEBUG LOG for queries
        print(f"FDA_QUERY_SET {{scene_id: {scene_id}, queries: {json.dumps(search_queries, ensure_ascii=False)}}}")
        
        # 7. SHOT_STRATEGY CHECK - source_preference must be ["archive_org"], max 2-3 shot_types
        shot_strategy = scene.get("shot_strategy", {})
        if isinstance(shot_strategy, dict):
            source_pref = shot_strategy.get("source_preference", [])
            # Must be exactly ["archive_org"]
            if source_pref != ["archive_org"]:
                violations.append({
                    "type": "SHOT_STRATEGY_SOURCE_PREFERENCE",
                    "scene_id": scene_id,
                    "expected": ["archive_org"],
                    "actual": source_pref,
                    "message": f"Scene {scene_id}: source_preference must be ['archive_org'], got {source_pref}",
                })
            
            # shot_types should be max 2-3 types
            shot_types = shot_strategy.get("shot_types", [])
            if isinstance(shot_types, list) and len(shot_types) > 3:
                violations.append({
                    "type": "SHOT_STRATEGY_TOO_MANY_TYPES",
                    "scene_id": scene_id,
                    "max_allowed": 3,
                    "actual": len(shot_types),
                    "shot_types": shot_types,
                    "message": f"Scene {scene_id}: shot_types has {len(shot_types)} types (max 3 recommended)",
                })
            # shot_types MUST be from allowlist (enum gate) — otherwise downstream schema/asset_resolver can fail.
            if isinstance(shot_types, list):
                invalid = [st for st in shot_types if not isinstance(st, str) or st not in ALLOWED_SHOT_TYPES]
                if invalid:
                    violations.append({
                        "type": "SHOT_STRATEGY_INVALID_SHOT_TYPES",
                        "scene_id": scene_id,
                        "invalid": invalid,
                        "allowed": ALLOWED_SHOT_TYPES,
                        "message": f"Scene {scene_id}: invalid shot_types {invalid} (allowed: {ALLOWED_SHOT_TYPES})",
                    })
        
        # DEBUG LOG for scene validation
        print(f"FDA_SCENE_VALIDATION {{scene_id: {scene_id}, ok: {len([v for v in violations if v.get('scene_id') == scene_id]) == 0}, violations: {len([v for v in violations if v.get('scene_id') == scene_id])}}}")
    
    # Log quality summary
    avg_query_words = total_query_words / total_queries if total_queries > 0 else 0
    quality_summary = {
        "episode_id": episode_id,
        "total_scenes": len(scenes),
        "total_queries": total_queries,
        "avg_query_words": round(avg_query_words, 1),
        "episode_anchor_terms_count": len(episode_anchor_terms_norm),
        "anchor_lock_violations": anchor_lock_violations,
        "violations_count": len(violations),
    }
    print(f"FDA_V27_QUALITY_SUMMARY {json.dumps(quality_summary, ensure_ascii=False)}")
    
    # If any violations, fail hard
    if violations:
        error_payload = {
            "episode_id": episode_id,
            "error": "FDA_VALIDATION_FAILED",
            "total_violations": len(violations),
            "violations": violations[:5],  # First 5 only
        }
        raise RuntimeError(f"FDA_VALIDATION_FAILED: {json.dumps(error_payload, ensure_ascii=False)}")
    
    print(f"✅ FDA_V27_HARD_VALIDATOR PASSED: {len(scenes)} scenes, {total_queries} queries, anchor_lock_violations={anchor_lock_violations}")


# ============================================================================
# PUBLIC API (pro integration do pipeline)
# ============================================================================

def run_fda_llm(
    script_state: Dict[str, Any],
    provider_api_keys: Dict[str, str],
    config: Optional[Dict[str, Any]] = None,
    repair_hint: Optional[str] = None,
    attempt: int = 1,
) -> Tuple[Dict[str, Any], str, Dict[str, Any]]:
    """
    Hlavní entry point pro LLM-assisted FDA.
    
    Args:
        script_state: script_state obsahující tts_ready_package
        provider_api_keys: dict s API klíči (openai, openrouter)
        config: optional config (provider, model, temperature, prompt_template)
    
    Returns:
        (raw_llm_json, raw_llm_output_text, metadata)
    
    Raises:
        ValueError: pokud chybí požadovaná data
        RuntimeError: pokud LLM call selže
    """
    # Default config
    cfg = {
        "provider": "openrouter",
        "model": "openai/gpt-4o-mini",
        "temperature": 0.2,
        "prompt_template": None,
    }
    if config:
        cfg.update(config)
    
    # Extrakce tts_ready_package
    tts_pkg = script_state.get("tts_ready_package")
    if not tts_pkg:
        raise ValueError("FDA_INPUT_MISSING: script_state.tts_ready_package is missing")
    
    # Extrakce narration_blocks
    narration_blocks = None
    
    episode_id = script_state.get("episode_id", None)
    
    if "narration_blocks" in tts_pkg:
        narration_blocks = tts_pkg["narration_blocks"]
    elif "tts_segments" in tts_pkg:
        # Převeď tts_segments na narration_blocks
        narration_blocks = []
        for seg in tts_pkg["tts_segments"]:
            # HOTFIX: text_tts-only, žádný fallback na text
            text_tts = seg.get("tts_formatted_text")
            if not text_tts or not isinstance(text_tts, str) or not text_tts.strip():
                block_id = seg.get("block_id", seg.get("segment_id", "unknown"))
                has_text = "text" in seg
                text_type = type(seg.get("text")).__name__ if has_text else "N/A"
                text_len = len(str(seg.get("text", ""))) if has_text else 0
                
                diagnostic = {
                    "episode_id": episode_id,
                    "block_id": block_id,
                    "has_text_field": has_text,
                    "text_type": text_type,
                    "text_length": text_len,
                    "tts_formatted_text_present": "tts_formatted_text" in seg,
                    "tts_formatted_text_type": type(seg.get("tts_formatted_text")).__name__ if "tts_formatted_text" in seg else "N/A",
                }
                raise RuntimeError(
                    f"FDA_TEXT_TTS_MISSING: tts_segment {block_id} nemá validní tts_formatted_text. "
                    f"Diagnostic: {diagnostic}"
                )
            
            narration_blocks.append({
                "block_id": seg.get("block_id", seg.get("segment_id", "")),
                "text_tts": text_tts,
                "claim_ids": [],
            })
    
    if not narration_blocks or not isinstance(narration_blocks, list):
        raise ValueError("FDA_INPUT_MISSING: narration_blocks[] not found in tts_ready_package")
    
    # Vytvoř prompt (s episode_id pro diagnostiku)
    prompt = cfg.get("prompt_template") or _prompt_footage_director(narration_blocks, episode_id=episode_id)

    # HARD COVERAGE GUARD (dynamic, applies even when prompt_template is provided):
    # LLM MUST include ALL block_ids exactly once, in the same order.
    ordered_block_ids = [str(b.get("block_id") or "").strip() for b in narration_blocks if isinstance(b, dict) and str(b.get("block_id") or "").strip()]
    coverage_guard = (
        "HARD COVERAGE GUARD (must obey):\n"
        "- You MUST use EVERY block_id from the input exactly once across all scenes.\n"
        "- You MUST preserve the exact order of block_ids (no reordering).\n"
        "- You MUST NOT merge or rename IDs (e.g., b_0007 is NOT a substitute for b_0007a+b_0007b).\n"
        "- Before output: concatenate all scenes[].narration_block_ids into one list and compare it to EXPECTED_BLOCK_IDS.\n"
        "  If there is any mismatch (missing/extra/duplicate/order), FIX your JSON before returning.\n\n"
        f"EXPECTED_BLOCK_IDS (ORDERED): {json.dumps(ordered_block_ids, ensure_ascii=False)}\n\n"
    )
    generic_ban_guard = (
        "HARD KEYWORDS/QUERIES BAN (must obey):\n"
        "- keywords/search_queries MUST be concrete and visually grounded.\n"
        "- NEVER use generic filler terms (even if they sound 'documentary').\n"
        f"  BANNED_TERMS: {json.dumps(GENERIC_FILLER_BLACKLIST, ensure_ascii=False)}\n"
        "- Also avoid meta-writing terms like: \"overview\", \"narrative\", \"stages\", \"strategy\".\n"
        "- Before output: scan every keyword/query and rewrite anything that matches banned terms.\n\n"
    )

    # HARD ANCHOR TERMS GUARD:
    # Beat-lock requires >=2 anchored terms in keywords and >=1 anchored query in search_queries.
    # Provide an explicit, per-block allowlist of anchor terms derived from the actual text_tts.
    anchor_terms_map = {}
    try:
        for b in narration_blocks:
            if not isinstance(b, dict):
                continue
            bid = str(b.get("block_id") or "").strip()
            txt = b.get("text_tts")
            if not bid or not isinstance(txt, str) or not txt.strip():
                continue
            terms = extract_anchor_terms_from_text(txt)
            # Keep it compact and high-signal
            anchor_terms_map[bid] = terms[:16]
    except Exception:
        anchor_terms_map = {}

    anchor_guard = (
        "HARD ANCHOR TERMS GUARD (must obey):\n"
        "- For each scene, your keywords MUST include at least 2 EXACT anchored terms that appear verbatim in the narration text.\n"
        "- Do NOT use synonyms. Use exact words/phrases present in narration.\n"
        "- To make this easy: use only terms from ANCHOR_TERMS_PER_BLOCK_ID for that scene’s narration_block_ids.\n"
        "- At least 2 keywords must be SINGLE-WORD tokens that appear literally in narration text.\n"
        "- For search_queries: at least 1 query must include at least 1 exact anchor term from narration.\n\n"
        f"ANCHOR_TERMS_PER_BLOCK_ID (derived from text_tts): {json.dumps(anchor_terms_map, ensure_ascii=False)}\n\n"
    )

    # Provide a conservative allowed pool for keywords to reduce generic filler leaks.
    # (Use verbatim anchor terms + known concrete visual nouns.)
    allowed_pool = []
    try:
        for terms in anchor_terms_map.values():
            if isinstance(terms, list):
                allowed_pool.extend([t for t in terms if isinstance(t, str) and t.strip()])
        allowed_pool.extend([n for n in CONCRETE_VISUAL_NOUNS if isinstance(n, str) and n.strip()])
        # de-dupe while preserving order
        seen = set()
        allowed_pool_uniq = []
        for t in allowed_pool:
            tl = t.lower()
            if tl in seen:
                continue
            seen.add(tl)
            allowed_pool_uniq.append(t)
        allowed_pool = allowed_pool_uniq[:120]
    except Exception:
        allowed_pool = []

    pool_guard = (
        "HARD KEYWORD POOL (must obey):\n"
        "- All keywords MUST be chosen from ALLOWED_KEYWORD_POOL.\n"
        "- If you cannot find enough, pick more terms from narration text (verbatim).\n"
        f"ALLOWED_KEYWORD_POOL: {json.dumps(allowed_pool, ensure_ascii=False)}\n\n"
    )

    repair_section = ""
    if repair_hint:
        repair_section = (
            "REPAIR MODE (must obey):\n"
            "- Your previous output was rejected by deterministic validation.\n"
            "- You MUST fix the issue described in REPAIR_HINT and return a fully compliant JSON.\n"
            f"REPAIR_HINT: {repair_hint}\n\n"
        )

    prompt = coverage_guard + anchor_guard + pool_guard + generic_ban_guard + repair_section + prompt
    
    # LLM call
    from script_pipeline import _llm_chat_json_raw
    
    provider = cfg["provider"].strip().lower()
    model = cfg["model"].strip()
    api_key = provider_api_keys.get(provider, "").strip()
    
    if not api_key:
        raise RuntimeError(f"Chybí API key pro provider '{provider}' (FDA)")
    
    raw_text, parsed, meta = _llm_chat_json_raw(
        provider=provider,
        prompt=prompt,
        api_key=api_key,
        model=model,
        temperature=float(cfg.get("temperature", 0.2)),
        timeout_s=600,
    )
    
    if parsed is None:
        fr = (meta or {}).get("finish_reason")
        src = (meta or {}).get("response_text_source")
        raise RuntimeError(f"FDA: LLM vrátil nevalidní JSON (source={src}, finish_reason={fr})")

    # Required tag: did this raw draft come from cache or a fresh LLM call?
    # run_fda_llm always performs a fresh LLM call.
    print(f"FDA_LLM_SOURCE episode_id={episode_id} source=fresh_llm")

    # ========================================================================
    # DIAGNOSTIC LOG: Raw LLM version (před sanitizerem a postprocessingem)
    # ========================================================================
    raw_llm_version = None
    try:
        if isinstance(parsed, dict):
            if "shot_plan" in parsed and isinstance(parsed["shot_plan"], dict):
                raw_llm_version = parsed["shot_plan"].get("version")
            elif "version" in parsed:
                raw_llm_version = parsed.get("version")
        print(f"🔍 FDA_DIAGNOSTIC {{episode_id: '{episode_id}', stage: 'raw_llm', version: '{raw_llm_version}'}}")
        # Required checkpoint tag (user request): include episode_id + raw_version + final_version (pending here)
        print(
            f"FDA_RAW_VERSION episode_id={episode_id} raw_version={raw_llm_version} final_version=PENDING"
        )
    except Exception:
        pass

    # ========================================================================
    # v2.7 HARD COERCION GATE (kill-switch)
    # Must be BEFORE sanitizer/deterministic generators and BEFORE validation.
    # ========================================================================
    try:
        coerce_fda_v27_version_inplace(parsed, episode_id=episode_id)
    except Exception:
        pass

    # ========================================================================
    # PRE-FDA SANITIZER (KRITICKÝ KROK: PŘED validací)
    # ========================================================================
    # Sanitizer odstraní abstraktní/generické výrazy z keywords/queries PŘED
    # validate_and_fix_shot_plan a validate_shot_plan_hard_gate.
    # Tím zajistíme, že FDA hard-gate NIKDY nepadne na FDA_GENERIC_FILLER_DETECTED.
    
    if PRE_FDA_SANITIZER_AVAILABLE:
        try:
            # Extrahuj shot_plan (může být wrapper nebo direct)
            shot_plan_to_sanitize = parsed
            if isinstance(parsed, dict) and "shot_plan" in parsed:
                shot_plan_to_sanitize = parsed["shot_plan"]
            
            # Sanitizuj shot_plan (deterministicky nahradí abstraktní → konkrétní)
            sanitized_shot_plan = sanitize_and_log(shot_plan_to_sanitize)
            
            # FIX: Obal zpět do wrapper formátu (pokud byl wrapper)
            # Zajisti že sanitized_shot_plan NENÍ double-wrapped
            if isinstance(parsed, dict) and "shot_plan" in parsed:
                # Pokud sanitized_shot_plan už obsahuje "shot_plan" key, extrahuj vnitřní
                if isinstance(sanitized_shot_plan, dict) and "shot_plan" in sanitized_shot_plan:
                    parsed["shot_plan"] = sanitized_shot_plan["shot_plan"]
                else:
                    parsed["shot_plan"] = sanitized_shot_plan
            else:
                parsed = sanitized_shot_plan
                
        except RuntimeError as e:
            # Sanitizer chyba je FATAL (žádné fallbacky)
            error_msg = str(e)
            if "FDA_SANITIZER_" in error_msg:
                # Re-raise s původním error kódem
                raise
            else:
                # Neočekávaná chyba v sanitizeru
                raise RuntimeError(f"FDA_SANITIZER_FAILED: Unexpected error: {error_msg}")
    else:
        # Sanitizer není dostupný - HARD FAIL (nemůžeme pokračovat bez něj)
        raise RuntimeError(
            "FDA_SANITIZER_UNAVAILABLE: Pre-FDA Sanitizer není dostupný, "
            "ale je POVINNÝ pro prevenci FDA_GENERIC_FILLER_DETECTED errors. "
            "Zkontroluj import pre_fda_sanitizer.py."
        )

    # ========================================================================
    # DIAGNOSTIC LOG: Version po sanitizeru (sanitizer NESMÍ měnit verzi)
    # ========================================================================
    postprocess_version_before = None
    try:
        if isinstance(parsed, dict):
            if "shot_plan" in parsed and isinstance(parsed["shot_plan"], dict):
                postprocess_version_before = parsed["shot_plan"].get("version")
            elif "version" in parsed:
                postprocess_version_before = parsed.get("version")
        print(f"🔍 FDA_DIAGNOSTIC {{episode_id: '{episode_id}', stage: 'post_sanitizer', version: '{postprocess_version_before}'}}")
    except Exception:
        pass

    # Apply deterministic generators (post-LLM processing)
    # This ensures all scenes have properly generated keywords, queries, summaries, and shot_strategy
    try:
        print("🔧 Applying deterministic generators to FDA output...")
        parsed = apply_deterministic_generators_v27(parsed, tts_pkg, episode_id)
        print("✅ Deterministic generators applied successfully")
    except Exception as e:
        print(f"⚠️  Deterministic generators failed: {e}")
        # Continue anyway - validators will catch issues
    
    # ========================================================================
    # AUTO-FIX COVERAGE ISSUES (CRITICAL)
    # ========================================================================
    # Pokud LLM vynechalo některé bloky, doplníme je automaticky PŘED validací
    try:
        print("🔧 Running validate_and_fix_shot_plan with auto_fix=True...")
        fixed_wrapper, fix_errors = validate_and_fix_shot_plan(
            raw_llm_output=parsed,
            tts_ready_package=tts_pkg,
            words_per_minute=150,
            auto_fix=True
        )
        if fix_errors:
            print(f"⚠️  FDA auto-fix applied: {len(fix_errors)} issues fixed")
            for err in fix_errors[:3]:
                print(f"    - {err}")
        parsed = fixed_wrapper
        print("✅ validate_and_fix_shot_plan completed")
    except Exception as e:
        # Coverage fix failed - tento error propagujeme
        print(f"❌ validate_and_fix_shot_plan failed: {e}")
        raise RuntimeError(f"FDA_AUTOFIX_FAILED: {str(e)}")
    
    # ========================================================================
    # DIAGNOSTIC LOG: Version po deterministic generators
    # ========================================================================
    postprocess_version_after = None
    try:
        if isinstance(parsed, dict):
            if "shot_plan" in parsed and isinstance(parsed["shot_plan"], dict):
                postprocess_version_after = parsed["shot_plan"].get("version")
            elif "version" in parsed:
                postprocess_version_after = parsed.get("version")
        print(f"🔍 FDA_DIAGNOSTIC {{episode_id: '{episode_id}', stage: 'post_deterministic_gen', version: '{postprocess_version_after}'}}")
        
        # CRITICAL CHECK: Pokud se verze změnila v postprocessingu → WARNING
        if raw_llm_version != postprocess_version_after:
            print(f"⚠️  FDA_VERSION_CHANGED_IN_POSTPROCESS {{episode_id: '{episode_id}', raw_llm_version: '{raw_llm_version}', postprocess_version: '{postprocess_version_after}'}}")
    except Exception:
        pass
    
    # Metadata pro audit
    metadata = {
        "provider": provider,
        "model": model,
        "temperature": cfg.get("temperature", 0.2),
        "timestamp": _now_iso(),
        "attempt": int(attempt),
        "prompt_used": prompt[:500] + "..." if len(prompt) > 500 else prompt,
        "sanitizer_applied": PRE_FDA_SANITIZER_AVAILABLE,
        "deterministic_generators_applied": True,
    }
    # propagate raw version for downstream checkpoint logging (script_pipeline)
    try:
        metadata["raw_llm_version"] = raw_llm_version
    except Exception:
        pass
    if meta:
        metadata["llm_meta"] = meta
    
    return parsed, raw_text, metadata


# ============================================================================
# ScenePlan v3 (LLM output) - best effort, no strict counted constraints
# ============================================================================

def _prompt_sceneplan_v3(narration_blocks: List[Dict[str, Any]], episode_id: Optional[str] = None) -> str:
    """
    ScenePlan v3 prompt: creative planning only.
    No counted constraints (keywords_count/query_count/word_count/object_type_count).
    Compiler will generate canonical ShotPlan v3 deterministically.
    """
    # Compact input (avoid token blow-up)
    lines: List[str] = []
    for i, b in enumerate(narration_blocks[:30], start=1):
        bid = str(b.get("block_id") or f"b_{i:04d}").strip()
        txt = str(b.get("text_tts") or "").strip()
        if len(txt) > 180:
            txt = txt[:180] + "…"
        lines.append(f"- {bid}: {txt}")
    if len(narration_blocks) > 30:
        lines.append(f"- ... (+{len(narration_blocks) - 30} more blocks)")

    return f"""
Return exactly ONE JSON object. No markdown. No extra keys.

Schema: ScenePlan v3
{{
  "version": "{SCENEPLAN_V3_VERSION}",
  "scenes": [
    {{
      "scene_id": "sc_0001",
      "narration_block_ids": ["b_0001", "b_0002"],
      "emotion": "neutral",
      "shot_types": ["maps_context", "archival_documents"],
      "cut_rhythm": "medium",
      "source_preference": "archive_org",
      "focus_entities": ["Napoleon", "Moscow", "1812"]
    }}
  ]
}}

Allowed enums (best-effort):
- emotion: {json.dumps(ALLOWED_EMOTIONS)}
- cut_rhythm: {json.dumps(ALLOWED_CUT_RHYTHMS)}
- shot_types: {json.dumps(ALLOWED_SHOT_TYPES)}

Notes:
- narration_block_ids may be partial; the deterministic compiler will repair coverage.
- focus_entities is optional.
- Prefer archive_org sources.

Episode: {episode_id or "unknown"}
Narration blocks:
{chr(10).join(lines)}
""".strip()


def run_sceneplan_llm(
    script_state: Dict[str, Any],
    provider_api_keys: Dict[str, str],
    config: Optional[Dict[str, Any]] = None,
) -> Tuple[Dict[str, Any], str, Dict[str, Any]]:
    """
    Best-effort LLM call producing ScenePlan v3 (not ShotPlan).
    No retries, no strict validators, no sanitizer hard-dependency.
    """
    cfg = {
        "provider": "openrouter",
        "model": "openai/gpt-4o-mini",
        "temperature": 0.2,
        "prompt_template": None,
    }
    if isinstance(config, dict):
        cfg.update(config)

    tts_pkg = script_state.get("tts_ready_package")
    if not isinstance(tts_pkg, dict):
        raise ValueError("FDA_INPUT_MISSING: script_state.tts_ready_package is missing")

    episode_id = script_state.get("episode_id") or tts_pkg.get("episode_id")

    # Tolerant extraction for v3 (legacy v2.7 extraction may hard-fail on missing text_tts).
    from visual_planning_v3 import extract_narration_blocks
    narration_blocks = extract_narration_blocks(tts_pkg)
    if not narration_blocks:
        raise ValueError("FDA_INPUT_MISSING: narration_blocks[] not found in tts_ready_package")

    prompt = cfg.get("prompt_template") or _prompt_sceneplan_v3(narration_blocks, episode_id=episode_id)

    from script_pipeline import _llm_chat_json_raw
    provider = str(cfg.get("provider") or "").strip().lower() or "openrouter"
    model = str(cfg.get("model") or "").strip() or "openai/gpt-4o-mini"
    api_key = str((provider_api_keys or {}).get(provider) or "").strip()

    if not api_key:
        raise RuntimeError(f"FDA_LLM_SKIPPED_NO_API_KEY: missing api key for provider '{provider}'")

    raw_text, parsed, meta = _llm_chat_json_raw(
        provider=provider,
        prompt=prompt,
        api_key=api_key,
        model=model,
        temperature=float(cfg.get("temperature", 0.2)),
        timeout_s=600,
    )

    if parsed is None:
        fr = (meta or {}).get("finish_reason")
        src = (meta or {}).get("response_text_source")
        raise RuntimeError(f"FDA_SCENEPLAN_PARSE_FAIL: LLM returned invalid JSON (source={src}, finish_reason={fr})")

    metadata = {
        "provider": provider,
        "model": model,
        "temperature": cfg.get("temperature", 0.2),
        "timestamp": _now_iso(),
        "prompt_used": prompt[:500] + "..." if len(prompt) > 500 else prompt,
    }
    if meta:
        metadata["llm_meta"] = meta

    return parsed, raw_text, metadata


def run_fda_standalone(
    tts_ready_package: Dict[str, Any],
    provider_api_keys: Dict[str, str],
    config: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Standalone verze FDA pro endpoint testing.
    
    Args:
        tts_ready_package: Přímo tts_ready_package nebo dict s narration_blocks
        provider_api_keys: dict s API klíči
        config: optional config
    
    Returns:
        shot_plan dict
    """
    # v3 behavior: LLM -> ScenePlan (best-effort) -> deterministic compiler -> ShotPlan v3
    fake_state = {
        "tts_ready_package": tts_ready_package,
        "episode_id": tts_ready_package.get("episode_id") if isinstance(tts_ready_package, dict) else None,
    }
    raw_sceneplan = None
    try:
        raw_sceneplan, _raw_text, _meta = run_sceneplan_llm(fake_state, provider_api_keys, config)
    except Exception:
        raw_sceneplan = None

    from visual_planning_v3 import coerce_sceneplan_v3, compile_shotplan_v3, validate_shotplan_v3_minimal
    sceneplan, _w1 = coerce_sceneplan_v3(raw_sceneplan, tts_ready_package)
    wrapper, _w2 = compile_shotplan_v3(tts_ready_package, sceneplan, words_per_minute=150)
    validate_shotplan_v3_minimal(wrapper, tts_ready_package, episode_id=fake_state.get("episode_id"))
    return wrapper["shot_plan"]
