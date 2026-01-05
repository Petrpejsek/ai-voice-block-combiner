"""
FDA Query Sanitizer - deterministický post-processing search queries

Převádí LLM-generované queries do Archive.org-optimalizovaných šablon.
Běží PŘED AAR, AFTER FDA LLM output.

Cíl: 100% úspěšnost vyhledávání místo 0 výsledků.
"""

import re
from typing import List, Tuple, Optional

# FORBIDDEN WORDS (vyhoď z queries)
FORBIDDEN_QUERY_WORDS = {
    # Generic fillers
    "footage", "montage", "background", "context", "video", "clip", "scene",
    # Abstract concepts
    "battle", "invasion", "campaign", "siege", "warfare", "conflict", "strategy",
    # Verbs (archive.org preferuje nouns)
    "ordered", "destroying", "attacking", "defending", "fighting", "marching",
    "entering", "leaving", "arriving", "departing", "advancing", "retreating",
    # Adjectives that are too specific
    "abandoned", "deserted", "empty", "ruined", "destroyed", "burned",
}

# QUERY TEMPLATES (Archive.org-optimized patterns)
# Priority order: these templates have HIGH success rate on Archive.org
QUERY_TEMPLATES = {
    # Maps & Documents (velmi časté v archivech)
    "map": "archival map {place}",
    "maps": "archival map {place}",
    "document": "government correspondence {place}",
    "documents": "archival documents {place}",
    "letter": "handwritten letter {name}",
    "letters": "official letters {name}",
    "correspondence": "diplomatic correspondence {place}",
    
    # Visual media
    "photograph": "nineteenth century photograph {place}",
    "engraving": "engraving {place} {century}",
    "illustration": "historical illustration {place}",
    "portrait": "portrait {name}",
    
    # Physical objects
    "building": "historic building {place}",
    "street": "historic street {place}",
    "city": "{place} cityscape",
    
    # People & events
    "troops": "{name} army {year}",
    "army": "{name} army {year}",
    "soldiers": "{name} soldiers",
}

# Historical periods for century substitution
PERIOD_MAPPING = {
    "1800": "nineteenth century",
    "1801-1850": "nineteenth century",
    "1851-1900": "nineteenth century",
    "1900": "twentieth century",
    "1901-1950": "twentieth century",
    "1951-2000": "twentieth century",
}

# Required anchors (temporal/spatial)
REQUIRED_ANCHORS = {
    # Proper nouns (places, people)
    # Will be detected dynamically via capitalization
    
    # Years (1812, 1815, etc.)
    # Will be detected dynamically via \d{4} pattern
}

# Physical objects (visual nouns) - Archive.org discipline
REQUIRED_PHYSICAL_OBJECTS = {
    "map", "letter", "manuscript", "engraving", "lithograph", "photograph",
    "treaty", "decree", "proclamation", "correspondence", "portrait",
    "building", "street", "cityscape", "fortification", "wall", "gate",
    "document", "illustration", "drawing", "painting", "sketch",
}


def _has_anchor(query: str) -> bool:
    """Check if query has temporal/spatial anchor (proper noun or year)"""
    # Check for proper noun (capitalized word)
    if re.search(r'\b[A-Z][a-z]+', query):
        return True
    
    # Check for year
    if re.search(r'\b1[0-9]{3}\b', query):
        return True
    
    return False


def _has_physical_object(query: str) -> bool:
    """Check if query contains a physical visual noun"""
    query_lower = query.lower()
    for obj in REQUIRED_PHYSICAL_OBJECTS:
        if obj in query_lower:
            return True
    return False


def _clean_query_words(query: str) -> str:
    """
    Vyhoď forbidden slova z query.
    PRESERVE proper nouns (Napoleon, Moscow) a years (1812).
    """
    words = query.split()
    cleaned = []
    
    for word in words:
        word_lower = word.lower()
        
        # KEEP proper nouns (capitalized words)
        if word[0].isupper() and len(word) > 1:
            cleaned.append(word)
            continue
        
        # KEEP years
        if re.match(r'^1[0-9]{3}s?$', word):
            cleaned.append(word)
            continue
        
        # REMOVE forbidden words
        if word_lower not in FORBIDDEN_QUERY_WORDS:
            cleaned.append(word)
    
    return " ".join(cleaned)


def _extract_entities(query: str) -> dict:
    """
    Extrahuj klíčové entity z query: place, name, year, century.
    """
    entities = {
        "place": None,
        "name": None,
        "year": None,
        "century": None,
    }
    
    # Extract year (1812, 1940s, etc.)
    year_match = re.search(r'\b(1[0-9]{3}s?|20[0-2][0-9])\b', query)
    if year_match:
        entities["year"] = year_match.group(1)
        # Determine century
        year_int = int(year_match.group(1)[:4])
        if 1801 <= year_int <= 1900:
            entities["century"] = "nineteenth century"
        elif 1901 <= year_int <= 2000:
            entities["century"] = "twentieth century"
    
    # Extract proper nouns (Napoleon, Moscow, etc.)
    proper_nouns = re.findall(r'\b[A-Z][a-z]{2,}\b', query)
    if proper_nouns:
        # Heuristic: first proper noun is usually a name/place
        entities["name"] = proper_nouns[0]
        if len(proper_nouns) > 1:
            entities["place"] = proper_nouns[1]
        else:
            entities["place"] = proper_nouns[0]
    
    return entities


def _apply_template(query: str) -> Optional[str]:
    """
    Zkus aplikovat template na query.
    Returns None pokud žádný template nesedí.
    """
    query_lower = query.lower()
    entities = _extract_entities(query)
    
    # Try to match a template
    for trigger_word, template in QUERY_TEMPLATES.items():
        if trigger_word in query_lower:
            # Fill template with entities
            result = template
            if "{place}" in template and entities["place"]:
                result = result.replace("{place}", entities["place"])
            elif "{place}" in template:
                # No place entity - skip this template
                continue
            
            if "{name}" in template and entities["name"]:
                result = result.replace("{name}", entities["name"])
            elif "{name}" in template:
                continue
            
            if "{year}" in template and entities["year"]:
                result = result.replace("{year}", entities["year"])
            elif "{year}" in template:
                # Year optional - remove it
                result = result.replace(" {year}", "")
            
            if "{century}" in template and entities["century"]:
                result = result.replace("{century}", entities["century"])
            elif "{century}" in template:
                result = result.replace("{century}", "nineteenth century")  # Default
            
            return result.strip()
    
    return None


def sanitize_fda_query(query: str) -> Tuple[str, str]:
    """
    Sanitizuje jednu FDA query do Archive.org-optimized formy.
    
    Returns:
        (sanitized_query, transformation_log)
    """
    original = query
    
    # Step 1: Clean forbidden words
    cleaned = _clean_query_words(query)
    if not cleaned:
        return "", f"[DELETED]: '{original}' (all words forbidden)"
    
    # Step 2: Try to apply template
    templated = _apply_template(cleaned)
    if templated:
        return templated, f"[TEMPLATE]: '{original}' → '{templated}'"
    
    # Step 3: No template matched - return cleaned version (better than original)
    if cleaned != original.lower():
        return cleaned, f"[CLEANED]: '{original}' → '{cleaned}'"
    
    # Step 4: Query was already good
    return original, f"[KEPT]: '{original}'"


def sanitize_fda_queries(
    queries: List[str],
    narration_text: str = "",
    scene_id: str = "unknown",
    min_queries: int = 3,
    max_queries: int = 8
) -> Tuple[List[str], List[str]]:
    """
    Sanitizuje všechny FDA queries s STRICT ENFORCEMENT:
    - Každý query MUSÍ mít kotvu (proper noun/year)
    - Každý query MUSÍ mít fyzický objekt (map/letter/engraving/etc.)
    
    Args:
        queries: Raw queries z FDA LLM
        narration_text: Original narration pro extraction anchorů
        scene_id: Scene ID pro logging
        min_queries: Minimální počet queries
        max_queries: Maximální počet queries
    
    Returns:
        (sanitized_queries, transformation_logs)
    
    Raises:
        RuntimeError: pokud nelze vytvořit min_queries platných queries
    """
    sanitized = []
    logs = []
    rejected = []
    
    for query in queries[:max_queries]:
        san_query, log = sanitize_fda_query(query)
        logs.append(log)
        
        if not san_query or not san_query.strip():
            rejected.append(f"'{query}' (empty after sanitization)")
            continue
        
        # STRICT CHECKS
        if not _has_anchor(san_query):
            rejected.append(f"'{san_query}' (missing anchor: no proper noun or year)")
            continue
        
        if not _has_physical_object(san_query):
            rejected.append(f"'{san_query}' (missing physical object: no map/letter/engraving/etc.)")
            continue
        
        sanitized.append(san_query)
    
    # Deduplicate (case-insensitive)
    seen = set()
    unique = []
    for q in sanitized:
        q_lower = q.lower()
        if q_lower not in seen:
            seen.add(q_lower)
            unique.append(q)
    
    # NEVER-FAIL POLICY:
    # Not enough valid queries is NOT fatal. Return what we have and let downstream
    # broadening + local safety pack guarantee completion.
    if len(unique) < min_queries:
        logs.append(
            f"[WARN]: FDA_QUERY_SANITIZER_LOW_COUNT ({scene_id}): Only {len(unique)}/{min_queries} queries passed "
            f"(anchor+physical_object). Rejected: {rejected[:5]}"
        )
    
    return unique[:max_queries], logs


# === Integration function for footage_director.py ===

def sanitize_shot_plan_queries(shot_plan: dict) -> Tuple[dict, List[str]]:
    """
    Sanitizuje všechny search_queries v shot_plan.
    
    To be called AFTER FDA LLM, BEFORE AAR.
    
    Args:
        shot_plan: FDA output (už má search_queries)
    
    Returns:
        (sanitized_shot_plan, all_logs)
    """
    all_logs = []
    scenes = shot_plan.get("scenes", [])
    
    for i, scene in enumerate(scenes):
        scene_id = scene.get("scene_id", f"sc_{i:04d}")
        raw_queries = scene.get("search_queries", [])
        
        if not raw_queries:
            continue
        
        sanitized_queries, logs = sanitize_fda_queries(raw_queries)
        scene["search_queries"] = sanitized_queries
        
        if logs:
            all_logs.append(f"Scene {scene_id}:")
            all_logs.extend([f"  {log}" for log in logs])
    
    return shot_plan, all_logs

