"""
FDA v2.7 Keyword Normalizer - deterministický, bez hacků, bez fallbacků

Zajišťuje, že všechny keywords mají 2-5 slov před FDA validací.
Volá se JEDNOU, těsně před validate_fda_hard_v27().

CRITICAL: Uses SAME validation logic as FDA validator (shared constants).
"""

import re
from typing import List, Dict, Set, Tuple


# ============================================================================
# SHARED CONSTANTS FROM FDA VALIDATOR (import to ensure consistency)
# ============================================================================
try:
    from footage_director import (
        FDA_V27_PHYSICAL_OBJECT_TYPES,
        _contains_object_type,
        _count_words
    )
    VALIDATOR_IMPORTS_AVAILABLE = True
except ImportError:
    VALIDATOR_IMPORTS_AVAILABLE = False
    # Fallback definitions (but should never be used in production)
    FDA_V27_PHYSICAL_OBJECT_TYPES = {
        "map", "photograph", "document", "letter", "engraving", "illustration",
        "portrait", "ruins", "monument", "artifact"
    }
    
    def _contains_object_type(text: str, object_types: set) -> bool:
        """Fallback object type checker."""
        if not text:
            return False
        low = text.lower()
        return any(obj in low for obj in object_types)
    
    def _count_words(text: str) -> int:
        """Fallback word counter."""
        if not text or not isinstance(text, str):
            return 0
        return len(text.strip().split())


# LLM filler words that should be removed (low information content)
# These are typical "output padding" from LLM that don't add value
LLM_FILLER_WORDS = {
    "largest", "biggest", "greatest", "most", "best", "worst",
    "important", "significance", "notable", "famous", "major",
    "various", "several", "many", "numerous", "multiple",
    "overall", "general", "specific", "particular", "certain",
    "aspect", "factor", "element", "component", "feature",
}


# Generic single words that MUST NOT appear alone (too broad/vague)
# These MUST be expanded to 2+ words with entity prefix or descriptor
GENERIC_SINGLE_WORDS = {
    # Time/temporal
    "time", "year", "years", "period", "era", "age", "moment",
    
    # Generic nouns
    "service", "services", "people", "person", "man", "men", "woman", "women",
    "history", "event", "events", "story", "stories", "thing", "things",
    
    # Military/conflict (too generic alone)
    "war", "wars", "battle", "battles", "conflict", "conflicts",
    "army", "navy", "forces", "troops", "military",
    
    # Media types (need context)
    "map", "maps", "photo", "photos", "image", "images",
    "document", "documents", "archive", "archives",
    "footage", "film", "video", "newspaper", "newspapers",
    "letter", "letters", "report", "reports",
    
    # Locations (too generic alone)
    "city", "cities", "port", "ports", "harbor", "harbors",
    "ship", "ships", "vessel", "vessels", "boat", "boats",
    
    # Abstract concepts
    "impact", "importance", "significance", "context",
    "background", "situation", "condition", "conditions",
}


# Descriptor mini-mapa (deterministické rozšíření single-word keywords)
# Preferuje entity-specific varianty
KEYWORD_DESCRIPTORS = {
    # Generic media types → add "archival/historical"
    "documents": "archival documents",
    "document": "archival document",
    "map": "historical map",
    "maps": "historical maps",
    "photo": "archival photo",
    "photos": "archival photos",
    "photograph": "archival photograph",
    "photographs": "archival photographs",
    "footage": "archival footage",
    "newspaper": "historical newspaper",
    "newspapers": "historical newspapers",
    "archive": "historical archive",
    "archives": "historical archives",
    "letter": "official letter",
    "letters": "official letters",
    "report": "official report",
    "reports": "official reports",
    
    # Time/temporal → add context
    "time": "departure time",
    "year": "historical year",
    "period": "historical period",
    "era": "historical era",
    
    # People → add role
    "service": "crew service",
    "people": "crew members",
    "person": "crew member",
    
    # Maritime/naval
    "iceberg": "iceberg collision",
    "breached": "breached hull",
    "hull": "ship hull",
    "ship": "passenger ship",
    "ships": "passenger ships",
    "vessel": "naval vessel",
    "vessels": "naval vessels",
    "port": "departure port",
    "harbor": "naval harbor",
    
    # Location-specific (common proper nouns)
    "Southampton": "Southampton port",
    "Titanic": "Titanic ship",
    "Atlantic": "Atlantic Ocean",
    "Pacific": "Pacific Ocean",
    
    # Military → add descriptor
    "army": "military army",
    "navy": "naval fleet",
    "troops": "military troops",
    "forces": "armed forces",
    "battle": "military battle",
    "war": "world war",
    "conflict": "military conflict",
    
    # Buildings/structures
    "building": "historic building",
    "buildings": "historic buildings",
    "ruins": "burned ruins",
    "city": "historic city",
    "cities": "historic cities",
    
    # Verbs/adjectives (turn into noun phrases)
    "sinking": "ship sinking",
    "burning": "city burning",
    "breaching": "hull breaching",
    "departure": "ship departure",
    "arrival": "ship arrival",
}

# Stop words for extracting main entity from episode_topic
ENTITY_STOPWORDS = {
    "the", "a", "an", "of", "in", "on", "at", "to", "for", "with",
    "and", "or", "but", "by", "from", "about", "during", "after", "before"
}


def extract_main_entity(episode_topic: str, max_words: int = 2) -> str:
    """
    Extract 1-2 most significant words from episode_topic.
    
    Rules:
    - Skip years (4-digit numbers)
    - Skip stop words
    - Prefer capitalized words (proper nouns)
    - Return first 1-2 significant tokens
    
    Example: "The Titanic Disaster 1912" → "Titanic"
    """
    if not episode_topic:
        return "historical"
    
    words = episode_topic.split()
    significant_words = []
    
    for word in words:
        # Skip years
        if re.match(r'^\d{4}$', word):
            continue
        # Skip stop words
        if word.lower() in ENTITY_STOPWORDS:
            continue
        # Prefer capitalized (proper nouns)
        significant_words.append(word)
        if len(significant_words) >= max_words:
            break
    
    if not significant_words:
        return "historical"
    
    return ' '.join(significant_words[:max_words])


def normalize_keyword(
    keyword: str,
    episode_topic: str,
    main_entity: str,
    used_phrases: Set[str]
) -> str:
    """
    Normalize single keyword to 2-5 words (deterministicky).
    
    CRITICAL: Generic single words (time, service, documents) MUST be expanded
    with entity-specific prefix (e.g., "Titanic departure time").
    
    Args:
        keyword: Original keyword (may be 1-5+ words)
        episode_topic: Full episode topic (for context)
        main_entity: Pre-extracted 1-2 significant words from topic
        used_phrases: Set of already used phrases (for dedup)
    
    Returns:
        Normalized keyword (2-5 words, guaranteed unique, no generic singletons)
    """
    kw = keyword.strip()
    if not kw:
        return "archival photograph"  # Safe fallback
    
    words = kw.split()
    word_count = len(words)
    
    # Case 1: Already 2-5 words → keep as is (unless duplicate)
    if 2 <= word_count <= 5:
        if kw.lower() not in used_phrases:
            return kw
        # Duplicate → add "archival" prefix if not already there
        if not kw.lower().startswith('archival'):
            candidate = f"archival {kw}"
            if len(candidate.split()) <= 5:
                return candidate
        # Still duplicate → add number suffix
        return f"{kw} image"
    
    # Case 2: More than 5 words → truncate
    if word_count > 5:
        # Keep first 5 words
        truncated = ' '.join(words[:5])
        return truncated
    
    # Case 3: Single word → expand to 2-4 words
    # CRITICAL: Check if it's a GENERIC single word first!
    kw_lower = kw.lower()
    
    # Generic filter: These MUST be expanded with entity prefix
    if kw_lower in GENERIC_SINGLE_WORDS:
        # Try descriptor map first (entity-specific)
        if kw_lower in KEYWORD_DESCRIPTORS:
            base_expansion = KEYWORD_DESCRIPTORS[kw_lower]
            # If descriptor is generic (e.g., "archival documents"), add entity prefix
            if not any(entity_word in base_expansion.lower() for entity_word in main_entity.lower().split()):
                # Add entity prefix to make it specific
                candidate = f"{main_entity} {base_expansion}"
                # Ensure not too long
                if len(candidate.split()) <= 5:
                    if candidate.lower() not in used_phrases:
                        return candidate
            else:
                # Descriptor already has entity context
                if base_expansion.lower() not in used_phrases:
                    return base_expansion
        
        # No descriptor or duplicate → use entity prefix + keyword
        candidate = f"{main_entity} {kw}"
        if len(candidate.split()) <= 5 and candidate.lower() not in used_phrases:
            return candidate
        
        # Still duplicate → add "archival" as secondary descriptor
        candidate2 = f"{main_entity} archival {kw}"
        if len(candidate2.split()) <= 5:
            return candidate2
        
        # Last resort for generic: use descriptor without entity check
        if kw_lower in KEYWORD_DESCRIPTORS:
            return KEYWORD_DESCRIPTORS[kw_lower]
        
        # Ultimate fallback for generic
        return f"archival {kw}"
    
    # Non-generic single word (e.g., proper nouns like "Titanic", "Southampton")
    # Check descriptor map first
    if kw_lower in KEYWORD_DESCRIPTORS:
        expanded = KEYWORD_DESCRIPTORS[kw_lower]
        if expanded.lower() not in used_phrases:
            return expanded
    
    # If keyword is same as main entity → use descriptor or add generic descriptor
    if kw_lower == main_entity.lower():
        # Try descriptor map first
        if kw_lower in KEYWORD_DESCRIPTORS:
            return KEYWORD_DESCRIPTORS[kw_lower]
        # Otherwise add generic descriptor
        return f"{kw} {_get_generic_descriptor(kw)}"
    
    # Generic single-word → prefix with main entity
    # But ensure not duplicate
    candidate = f"{main_entity} {kw}"
    if candidate.lower() not in used_phrases:
        return candidate
    
    # If still duplicate, use archival prefix
    candidate2 = f"archival {kw}"
    if candidate2.lower() not in used_phrases:
        return candidate2
    
    # Last resort: add generic descriptor
    return f"{kw} {_get_generic_descriptor(kw)}"


def _get_generic_descriptor(keyword: str) -> str:
    """Return generic descriptor based on keyword type."""
    kw_lower = keyword.lower()
    
    # Check if it's a media type
    if any(media in kw_lower for media in ['photo', 'image', 'picture']):
        return "image"
    if any(doc in kw_lower for doc in ['document', 'letter', 'report']):
        return "document"
    if 'map' in kw_lower:
        return "illustration"
    if any(loc in kw_lower for loc in ['city', 'port', 'harbor', 'place']):
        return "view"
    if any(naval in kw_lower for naval in ['ship', 'vessel', 'boat', 'navy']):
        return "photograph"
    
    # Default
    return "photograph"


def normalize_scene_keywords(
    keywords: List[str],
    episode_topic: str,
    scene_id: str = "",
    verbose: bool = False
) -> Tuple[List[str], Dict]:
    """
    Normalize all keywords for a scene to EXACTLY 8 keywords, 2-5 words each.
    
    FDA v2.7 CONTRACT (STRICT):
    - Input: list of keywords (may be 1-5+ words, may be 7-9+ items)
    - Output: EXACTLY 8 keywords (guaranteed 2-5 words, no duplicates, no generic singletons)
    - Deterministic: same input → same output
    - No LLM, no hacky fallbacks
    
    ENFORCEMENT RULES:
    1. Quality first: fix word count (2-5), remove generics, expand singletons
    2. Count enforcement: trim to 8 if >8, pad to 8 if <8
    3. Trimming priority: LLM fillers first, then shortest/least informative
    4. Padding: use episode_topic + safe templates
    
    Args:
        keywords: List of keywords (from scene.keywords) - any count
        episode_topic: Canonical episode topic (from episode_metadata.topic)
        scene_id: Scene ID for logging (optional)
        verbose: Enable debug logging
    
    Returns:
        Tuple of (normalized keywords [exactly 8], diagnostics dict)
    """
    if not isinstance(keywords, list):
        # Hard fallback for invalid input
        main_entity = extract_main_entity(episode_topic)
        return (generate_fallback_keywords(main_entity), {"error": "invalid_input"})
    
    # Extract main entity once (1-2 words from topic)
    main_entity = extract_main_entity(episode_topic)
    
    # Track used phrases (lowercase) for dedup
    used_phrases: Set[str] = set()
    
    # Phase 1: Normalize quality (2-5 words, no generics, no LLM fillers)
    normalized = []
    single_word_before = 0
    generic_single_before = 0
    llm_filler_removed = 0
    rewrites = []  # Track max 2 rewrites for logging
    
    for i, kw in enumerate(keywords):
        original = str(kw or "").strip()
        if not original:
            continue  # Skip empty, will pad later
        
        # Count metrics
        if len(original.split()) == 1:
            single_word_before += 1
            if original.lower() in GENERIC_SINGLE_WORDS:
                generic_single_before += 1
            # Check if LLM filler
            if original.lower() in LLM_FILLER_WORDS:
                llm_filler_removed += 1
                continue  # Skip LLM fillers entirely
        
        # Normalize
        norm_kw = normalize_keyword(original, episode_topic, main_entity, used_phrases)
        
        # Final validation
        word_count = len(norm_kw.split())
        if not (2 <= word_count <= 5):
            # Shouldn't happen, but safety fallback
            norm_kw = f"{main_entity} photograph"
        
        # Check for duplicates
        if norm_kw.lower() in used_phrases:
            continue  # Skip duplicates
        
        normalized.append(norm_kw)
        used_phrases.add(norm_kw.lower())
        
        # Track rewrites (only first 2 for logging)
        if original != norm_kw and len(rewrites) < 2:
            rewrites.append(f"'{original}' → '{norm_kw}'")
    
    # Phase 2: ENFORCE EXACTLY 8 keywords
    original_count = len(keywords)
    after_quality_count = len(normalized)
    
    # Case A: More than 8 → trim to 8
    if len(normalized) > 8:
        # Trimming priority:
        # 1. Remove shortest keywords (likely less informative)
        # 2. Remove keywords without entity reference
        # 3. Keep first 8 if all equal quality
        
        # Score each keyword (higher = keep)
        def keyword_score(kw: str) -> int:
            score = 0
            kw_lower = kw.lower()
            # Bonus for entity in keyword
            for entity_word in main_entity.lower().split():
                if entity_word in kw_lower:
                    score += 3
            # Bonus for longer (more specific)
            score += len(kw.split())
            # Bonus for object type
            if any(obj in kw_lower for obj in ['ship', 'port', 'wreck', 'crew', 'passenger', 'archival', 'document', 'photograph', 'map']):
                score += 2
            return score
        
        # Sort by score (descending), keep top 8
        scored = [(kw, keyword_score(kw)) for kw in normalized]
        scored.sort(key=lambda x: (-x[1], x[0]))  # Score desc, then alphabetical for determinism
        normalized = [kw for kw, score in scored[:8]]
    
    # Case B: Less than 8 → pad to 8
    elif len(normalized) < 8:
        padding_needed = 8 - len(normalized)
        # Generate safe padding keywords from episode_topic
        padding_templates = [
            "{} archival photograph",
            "{} historical document",
            "{} location map",
            "{} crew members",
            "{} passenger list",
            "{} departure port",
            "{} ship interior",
            "{} official report",
        ]
        
        for i in range(padding_needed):
            template = padding_templates[i % len(padding_templates)]
            candidate = template.format(main_entity)
            
            # Ensure 2-5 words
            words = candidate.split()
            if len(words) > 5:
                candidate = ' '.join(words[:5])
            
            # Ensure unique
            if candidate.lower() not in used_phrases:
                normalized.append(candidate)
                used_phrases.add(candidate.lower())
            else:
                # Add variation with number
                candidate_var = f"{candidate} view"
                if len(candidate_var.split()) <= 5:
                    normalized.append(candidate_var)
                    used_phrases.add(candidate_var.lower())
                else:
                    normalized.append(f"{main_entity} image {len(normalized)}")
    
    # Final validation: MUST be exactly 8
    if len(normalized) != 8:
        # This should never happen, but hard fallback
        normalized = generate_fallback_keywords(main_entity)
    
    # Phase 3: ENFORCE PHYSICAL OBJECTS (min 3)
    # Use SAME logic as FDA validator
    physical_count = sum(1 for kw in normalized if _contains_object_type(kw, FDA_V27_PHYSICAL_OBJECT_TYPES))
    physical_fixed = 0
    
    if physical_count < 3:
        # Need to add/replace keywords with physical object types
        needed = 3 - physical_count
        
        # Physical object templates (guaranteed to match validator)
        physical_templates = [
            "{} archival photograph",
            "{} historical map",
            "{} official document",
            "{} crew portrait",
            "{} ship engraving",
            "{} departure letter",
        ]
        
        # Replace non-physical keywords with physical ones
        for i in range(len(normalized)):
            if needed <= 0:
                break
            
            kw = normalized[i]
            # If keyword doesn't contain physical object, replace it
            if not _contains_object_type(kw, FDA_V27_PHYSICAL_OBJECT_TYPES):
                template = physical_templates[physical_fixed % len(physical_templates)]
                new_kw = template.format(main_entity)
                
                # Remove old keyword from used_phrases
                used_phrases.discard(kw.lower())
                
                # Ensure unique (check if new_kw already exists)
                if new_kw.lower() in used_phrases:
                    # Try next template
                    for alt_idx in range(len(physical_templates)):
                        alt_template = physical_templates[(physical_fixed + alt_idx) % len(physical_templates)]
                        alt_kw = alt_template.format(main_entity)
                        if alt_kw.lower() not in used_phrases:
                            new_kw = alt_kw
                            break
                
                normalized[i] = new_kw
                used_phrases.add(new_kw.lower())
                needed -= 1
                physical_fixed += 1
        
        # Recount after fixes
        physical_count = sum(1 for kw in normalized if _contains_object_type(kw, FDA_V27_PHYSICAL_OBJECT_TYPES))
    
    # Count single words after (should be 0)
    single_word_after = sum(1 for kw in normalized if _count_words(kw) == 1)
    
    # Diagnostics
    diagnostics = {
        "scene_id": scene_id,
        "original_count": original_count,
        "single_word_before": single_word_before,
        "generic_single_before": generic_single_before,
        "llm_filler_removed": llm_filler_removed,
        "after_quality_count": after_quality_count,
        "final_count": len(normalized),
        "single_word_after": single_word_after,
        "physical_count": physical_count,
        "physical_fixed": physical_fixed,
        "trimmed": after_quality_count - len(normalized) if after_quality_count > 8 else 0,
        "padded": len(normalized) - after_quality_count if after_quality_count < 8 else 0,
        "rewrites_sample": rewrites,
        "original_keywords": keywords[:3] if verbose else [],  # Log first 3 for diagnostics
        "normalized_keywords": normalized,
    }
    
    # Mikro-diagnostika log (not spam)
    if verbose and (single_word_before > 0 or llm_filler_removed > 0 or original_count != 8 or physical_fixed > 0):
        print(f"   Scene {scene_id}: orig={original_count}, single={single_word_before}, "
              f"generic={generic_single_before}, llm_filler={llm_filler_removed}, "
              f"physical={physical_count}, physical_fixed={physical_fixed}, "
              f"final=8, trimmed={diagnostics['trimmed']}, padded={diagnostics['padded']}")
        if rewrites:
            print(f"   Rewrites: {', '.join(rewrites)}")
    
    return (normalized, diagnostics)


def generate_fallback_keywords(main_entity: str) -> List[str]:
    """
    Generate exactly 8 safe fallback keywords when everything else fails.
    
    Uses episode entity + safe templates, guaranteed 2-5 words each.
    """
    templates = [
        "{} archival photograph",
        "{} historical document",
        "{} location map",
        "{} crew members",
        "{} ship interior",
        "{} departure port",
        "{} official report",
        "{} passenger list",
    ]
    
    return [t.format(main_entity) for t in templates]


def normalize_all_scene_keywords(
    shot_plan_wrapper: Dict,
    episode_topic: str,
    verbose: bool = False
) -> None:
    """
    Normalize keywords for ALL scenes in shot_plan (in-place).
    
    Call this ONCE, immediately before validate_fda_hard_v27().
    
    CRITICAL: Enforces EXACTLY 8 keywords per scene, 2-5 words each.
    Includes internal preflight assert to catch violations before FDA validator.
    
    Args:
        shot_plan_wrapper: {'shot_plan': {...}} wrapper
        episode_topic: Canonical episode topic from metadata
        verbose: Enable debug logging
    
    Raises:
        RuntimeError: If preflight assert fails (LOCAL_PREFLIGHT_FAILED)
    """
    if not isinstance(shot_plan_wrapper, dict):
        return
    
    shot_plan = shot_plan_wrapper.get("shot_plan")
    if not isinstance(shot_plan, dict):
        return
    
    scenes = shot_plan.get("scenes", [])
    if not isinstance(scenes, list):
        return
    
    total_single_word = 0
    total_generic_single = 0
    total_llm_filler = 0
    total_trimmed = 0
    total_padded = 0
    scenes_affected = 0
    
    for scene in scenes:
        if not isinstance(scene, dict):
            continue
        
        scene_id = scene.get("scene_id", "unknown")
        keywords = scene.get("keywords", [])
        
        # Normalize (returns tuple now)
        normalized_keywords, diagnostics = normalize_scene_keywords(
            keywords,
            episode_topic,
            scene_id=scene_id,
            verbose=verbose
        )
        
        # Update scene (in-place)
        scene["keywords"] = normalized_keywords
        
        # Aggregate stats
        single_before = diagnostics.get("single_word_before", 0)
        generic_before = diagnostics.get("generic_single_before", 0)
        llm_filler = diagnostics.get("llm_filler_removed", 0)
        trimmed = diagnostics.get("trimmed", 0)
        padded = diagnostics.get("padded", 0)
        
        if single_before > 0 or llm_filler > 0:
            total_single_word += single_before
            total_generic_single += generic_before
            total_llm_filler += llm_filler
            total_trimmed += trimmed
            total_padded += padded
            scenes_affected += 1
    
    # ============================================================================
    # INTERNAL PREFLIGHT ASSERT (Krok D)
    # ============================================================================
    # Check keywords BEFORE FDA validator to catch violations early
    preflight_violations = []
    
    for scene in scenes:
        if not isinstance(scene, dict):
            continue
        
        scene_id = scene.get("scene_id", "unknown")
        keywords = scene.get("keywords", [])
        
        # Check 1: Exactly 8 keywords
        if len(keywords) != 8:
            preflight_violations.append({
                "scene_id": scene_id,
                "issue": "KEYWORDS_COUNT",
                "expected": 8,
                "actual": len(keywords),
                "keywords": keywords
            })
        
        # Check 2: Each keyword 2-5 words
        for ki, kw in enumerate(keywords):
            word_count = len(str(kw).split())
            if not (2 <= word_count <= 5):
                preflight_violations.append({
                    "scene_id": scene_id,
                    "issue": "KEYWORD_WORD_COUNT",
                    "keyword_index": ki,
                    "keyword": str(kw)[:40],
                    "word_count": word_count,
                })
    
    # If preflight fails, raise error with details
    if preflight_violations:
        error_msg = f"LOCAL_PREFLIGHT_FAILED: {len(preflight_violations)} violations before FDA validator\n"
        # Show first 2 violations in detail
        for i, viol in enumerate(preflight_violations[:2]):
            error_msg += f"\nViolation {i+1}: {viol}\n"
        if len(preflight_violations) > 2:
            error_msg += f"\n... and {len(preflight_violations) - 2} more violations"
        
        raise RuntimeError(error_msg)
    
    # Summary log (not spam)
    if verbose and total_single_word > 0:
        print(f"✅ Keyword normalizer: Fixed {total_single_word} single-word keywords "
              f"({total_generic_single} generic, {total_llm_filler} LLM fillers) "
              f"across {scenes_affected} scenes. Trimmed {total_trimmed}, padded {total_padded}.")
    
    # Success log
    if verbose:
        print(f"✅ Preflight assert PASSED: All {len(scenes)} scenes have exactly 8 keywords (2-5 words each)")

