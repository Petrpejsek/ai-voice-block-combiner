"""
Query Guardrails - Systematic query validation and refinement

PROBLEM: LLM sometimes generates ambiguous/too-broad queries → search returns irrelevant results
(bands, games, memes, wrong meanings of words)

SOLUTION: 3 guardrails that every query must pass:
1. ANCHOR: Every query must have temporal/spatial anchor (person/place/year/event)
2. MEDIA INTENT: Every query must have media token (photo/archival/map/document)
3. NO ULTRA-WIDE: Ban queries without anchor or with noise terms (band/game/meme)

INTEGRATION: Called AFTER query generation, BEFORE sending to archive search
"""

import re
from typing import List, Dict, Tuple, Optional, Any


# ============================================================================
# GUARDRAIL 1: ANCHOR DETECTION
# ============================================================================

def extract_anchors_from_text(text: str) -> List[str]:
    """
    Extract candidate anchors from beat text.
    
    Anchors = proper nouns, quoted names, capitalized phrases, years
    
    Returns:
        List of anchor candidates (most specific first)
    """
    anchors = []
    
    # 1. Extract years (1812, 1940s, etc.)
    years = re.findall(r'\b(1[0-9]{3}s?|20[0-2][0-9])\b', text)
    anchors.extend(years)
    
    # 2. Extract quoted names/phrases
    quoted = re.findall(r'"([^"]{3,40})"', text)
    anchors.extend(quoted)
    
    # 3. Extract proper nouns (capitalized words, 3+ chars)
    proper_nouns = re.findall(r'\b([A-Z][a-z]{2,}(?:\s+[A-Z][a-z]{2,})?)\b', text)
    # Filter out common words at start of sentences
    stopwords = {'The', 'This', 'That', 'These', 'Those', 'He', 'She', 'They', 'It', 'A', 'An', 'Following', 'Soon', 'After', 'Before', 'During', 'While'}
    proper_nouns = [pn for pn in proper_nouns if pn not in stopwords]
    anchors.extend(proper_nouns)
    
    # 4. Extract multi-word capitalized phrases (e.g., "World War II", "American Civil War")
    cap_phrases = re.findall(r'\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,3})\b', text)
    # Filter already captured
    cap_phrases = [cp for cp in cap_phrases if cp not in anchors]
    anchors.extend(cap_phrases)
    
    # Deduplicate while preserving order
    seen = set()
    unique_anchors = []
    for a in anchors:
        a_lower = a.lower()
        if a_lower not in seen and len(a.strip()) >= 3:
            seen.add(a_lower)
            unique_anchors.append(a.strip())
    
    return unique_anchors


# Broad epoch/era terms that are NOT valid anchors (even if capitalized)
# These need to be supplemented with specific entities
BROAD_EPOCH_TERMS = {
    'world war one', 'world war two', 'world war i', 'world war ii', 'wwi', 'wwii',
    'cold war', 'vietnam war', 'korean war', 'civil war', 'revolutionary war',
    'great war', 'great depression', 'industrial revolution',
    'middle ages', 'renaissance', 'dark ages', 'iron age', 'bronze age',
    'ancient rome', 'ancient greece', 'ancient egypt',  # Too broad without specific person/event
}

# Broad organizational names that are NOT valid anchors
BROAD_ORGANIZATIONS = {
    'united states navy', 'us navy', 'royal navy', 'british army',
    'united states air force', 'us air force', 'royal air force',
    'united states army', 'us army',
    'marines', 'marine corps',
    'nato', 'united nations', 'un',
}


def has_anchor(query: str) -> bool:
    """
    Check if query contains a VALID anchor.
    
    CRITICAL: Year alone is NOT sufficient anchor!
    CRITICAL: Broad epoch/org names are NOT sufficient anchors!
    
    Anchor = ONE of:
    1. Specific entity: Person/Ship/Battle/Location name (not broad org)
    2. Multi-word phrase that is NOT in broad_epoch_terms
    3. Specific quoted phrase
    
    Year can SUPPLEMENT anchor but never BE the only anchor.
    Broad terms like "World War One" or "United States Navy" are NOT anchors.
    """
    query_lower = query.lower()
    
    # Check if query contains broad epoch/org terms - these are NOT valid anchors
    for broad_term in BROAD_EPOCH_TERMS | BROAD_ORGANIZATIONS:
        if broad_term in query_lower:
            # This is a broad term - check if there's ALSO a specific entity
            # Extract all capitalized words that are NOT part of the broad term
            words_in_broad = set(broad_term.split())
            all_caps_words = re.findall(r'\b([A-Z][a-z]{2,})\b', query)
            specific_caps = [w for w in all_caps_words if w.lower() not in words_in_broad]
            
            if specific_caps:
                # Has specific entity beyond the broad term - OK
                return True
            else:
                # Only has broad term - NOT valid anchor
                return False
    
    # Check for proper noun (entity: person/place/event, 3+ chars)
    if re.search(r'\b[A-Z][a-z]{2,}', query):
        return True
    
    # Check for multi-word capitalized phrase (2-4 words)
    if re.search(r'\b[A-Z][a-z]+\s+[A-Z][a-z]+', query):
        return True
    
    # Check for quoted phrase (specific reference)
    if re.search(r'"[^"]{3,}"', query):
        return True
    
    # Year ALONE is NOT valid anchor - if we only find year, reject
    has_year = bool(re.search(r'\b(1[0-9]{3}s?|20[0-2][0-9])\b', query))
    has_entity = bool(re.search(r'\b[A-Z][a-z]{2,}', query))
    
    # If query has year but no entity, it's NOT anchored
    if has_year and not has_entity:
        return False
    
    return False


def get_anchor_from_query(query: str) -> Optional[str]:
    """
    Extract the primary anchor from a query.
    
    Priority: Multi-word entity > Single entity > Year (only if entity present)
    """
    # Try multi-word proper noun FIRST (highest priority)
    multi_match = re.search(r'\b([A-Z][a-z]+\s+[A-Z][a-z]+)', query)
    if multi_match:
        return multi_match.group(1)
    
    # Try single proper noun (entity)
    single_match = re.search(r'\b([A-Z][a-z]{2,})', query)
    if single_match:
        entity = single_match.group(1)
        # Check if there's also a year - combine them
        year_match = re.search(r'\b(1[0-9]{3}s?|20[0-2][0-9])\b', query)
        if year_match:
            return f"{entity} {year_match.group(1)}"
        return entity
    
    # No entity found - year alone is NOT valid anchor
    return None


# ============================================================================
# GUARDRAIL 2: MEDIA INTENT TOKENS
# ============================================================================

# Whitelist of media intent tokens
MEDIA_INTENT_TOKENS = {
    'photo', 'photograph', 'photography',
    'archival', 'archive', 'archived',
    'newspaper', 'newsreel',
    'map', 'maps', 'mapping',
    'document', 'documents', 'documentation',
    'report', 'reports', 'reporting',
    'manuscript', 'manuscripts',
    'engraving', 'engravings',
    'illustration', 'illustrations',
    'print', 'prints', 'printed',
    'lithograph', 'lithographs',
    'drawing', 'drawings',
    'sketch', 'sketches',
    'letter', 'letters', 'correspondence',
    'portrait', 'portraits',
    'footage', 'film',  # For video queries
    # FDA v2.7 object types used in shot plans (must be treated as valid visual intent)
    'ruins',
}


def has_media_intent(query: str) -> bool:
    """Check if query contains a media intent token."""
    query_lower = query.lower()
    return any(token in query_lower for token in MEDIA_INTENT_TOKENS)


def get_media_intent_from_query(query: str) -> Optional[str]:
    """Extract the media intent token from query."""
    query_lower = query.lower()
    for token in MEDIA_INTENT_TOKENS:
        if token in query_lower:
            return token
    return None


def add_media_intent_token(query: str, shot_type: Optional[str] = None) -> str:
    """
    Add appropriate media intent token based on shot type.
    
    Preference:
    - map shot → map
    - document shot → document/report
    - general → archival photo
    """
    if shot_type:
        shot_lower = shot_type.lower()
        if 'map' in shot_lower:
            return f"{query} map"
        elif 'document' in shot_lower:
            return f"{query} document"
        elif 'photo' in shot_lower or 'portrait' in shot_lower:
            return f"{query} photograph"
    
    # Default: archival photo
    return f"{query} archival photograph"


# ============================================================================
# GUARDRAIL 3: NOISE TERM STOPLIST
# ============================================================================

# Noise terms that historically pull irrelevant results
# CRITICAL: These must be checked in CONTEXT to avoid false positives
NOISE_STOPLIST = {
    # Entertainment (standalone or with modern context)
    'band', 'bands', 'album', 'albums', 'song', 'songs', 'lyrics',
    'soundtrack', 'soundtracks', 'remix', 'remixes',
    'concert', 'concerts', 'tour', 'tours',
    
    # Games (standalone)
    'game', 'games', 'gaming', 'gameplay', 'playthrough',
    'video game', 'videogame', 'board game',
    
    # Internet culture
    'meme', 'memes', 'viral', 'trending', 'challenge',
    'webm', 'gif', 'gifs', 'reaction',
    
    # Modern media
    'youtube', 'tiktok', 'instagram', 'twitter', 'facebook',
    'podcast', 'podcasts', 'stream', 'streaming',
    
    # Generic/ambiguous
    'compilation', 'montage', 'highlights', 'recap',
    'trailer', 'teaser', 'preview', 'promo',
}

# Legitimate historical contexts that override stoplist
# Format: (term, legitimate_context_words)
LEGITIMATE_CONTEXTS = {
    'game': ['olympic', 'olympics', 'ancient', 'arena', 'gladiator', 'hunt', 'hunting'],
    'games': ['olympic', 'olympics', 'ancient', 'arena', 'gladiator'],
    'band': ['armband', 'headband', 'elastic', 'rubber'],  # Physical band objects
}


def has_noise_terms(query: str) -> bool:
    """
    Check if query contains noise terms from stoplist.
    
    CRITICAL: Check context to avoid false positives!
    "Olympic Games" is legitimate, "games compilation" is noise.
    """
    query_lower = query.lower()
    
    for noise in NOISE_STOPLIST:
        if noise not in query_lower:
            continue
            
        # Found potential noise term - check if it's legitimate
        if noise in LEGITIMATE_CONTEXTS:
            # Check if ANY legitimate context word is present
            is_legitimate = False
            for context_word in LEGITIMATE_CONTEXTS[noise]:
                if context_word in query_lower:
                    is_legitimate = True
                    break
            
            if is_legitimate:
                # This is legitimate usage - skip this noise term
                continue
        
        # No legitimate context found - this IS noise
        return True
    
    return False


def get_noise_terms_from_query(query: str) -> List[str]:
    """Return list of noise terms found in query."""
    query_lower = query.lower()
    found = []
    for noise in NOISE_STOPLIST:
        if noise in query_lower:
            found.append(noise)
    return found


def is_too_short(query: str, min_meaningful_words: int = 3) -> bool:
    """
    Check if query is too short after filtering noise.
    
    Args:
        query: Query string
        min_meaningful_words: Minimum number of meaningful words
    
    Returns:
        True if query is too short
    """
    # Remove media intent tokens (they don't count as content)
    words = query.lower().split()
    meaningful_words = [
        w for w in words
        if w not in MEDIA_INTENT_TOKENS
        and w not in {'the', 'a', 'an', 'of', 'in', 'on', 'at', 'to', 'for', 'with'}
    ]
    return len(meaningful_words) < min_meaningful_words


# ============================================================================
# FDA-COMPATIBLE VALIDATION (Pre-FDA Sanitizer alignment)
# ============================================================================

# Forbidden start words (FDA v2.7 validator alignment)
# Source-of-truth in validator: `footage_director.FDA_V27_FORBIDDEN_QUERY_STARTS`.
# We mirror it here to keep query guardrails FDA-compatible.
FDA_FORBIDDEN_START_WORDS = {
    # temporal / discourse starters
    "following", "upon", "soon", "although",
    # pronouns
    "he", "she", "they", "it",
    # demonstratives / articles
    "this", "these", "that", "those",
    "the", "a", "an",
    # keep older discourse words too (harmless + useful)
    "however", "despite", "nevertheless", "meanwhile",
    "furthermore", "moreover", "additionally", "consequently",
    "therefore", "thus", "hence", "accordingly",
}


def _derive_episode_anchor_from_topic(episode_topic: str) -> str:
    """
    Derive a short, FDA-safe anchor phrase from canonical episode_topic.
    This is deterministic (no narration heuristics) and prevents anchors like
    "The ..." which violate FDA forbidden-start rules.
    """
    if not episode_topic or not isinstance(episode_topic, str):
        return "historical"
    # Tokenize (keep apostrophes/hyphens in names)
    tokens = re.findall(r"[0-9A-Za-zÀ-ž]+(?:[-'][0-9A-Za-zÀ-ž]+)*", episode_topic.strip())
    # Drop leading forbidden start words
    while tokens and tokens[0].lower() in FDA_FORBIDDEN_START_WORDS:
        tokens = tokens[1:]
    # Drop leading years (never a sole anchor)
    while tokens and re.match(r"^\d{4}$", tokens[0]):
        tokens = tokens[1:]
    if not tokens:
        return "historical"
    # Keep 1-3 tokens (short anchor phrase)
    return " ".join(tokens[:3]).strip()

def has_forbidden_start_word(query: str) -> bool:
    """Check if query starts with forbidden word (FDA compatibility)."""
    first_word = query.strip().split()[0].lower() if query.strip() else ""
    return first_word in FDA_FORBIDDEN_START_WORDS


def has_duplicate_words(query: str) -> bool:
    """Check for duplicate consecutive words (bug detector)."""
    words = query.lower().split()
    for i in range(len(words) - 1):
        if words[i] == words[i + 1]:
            return True
    return False


def validate_fda_word_count(query: str) -> bool:
    """
    Validate query has 5-9 words (FDA requirement).
    
    Counts all words including articles/prepositions for FDA compatibility.
    """
    words = query.strip().split()
    word_count = len(words)
    return 5 <= word_count <= 9


def is_fda_compatible(query: str) -> Tuple[bool, List[str]]:
    """
    Check if query is compatible with FDA validator.
    
    FDA Requirements:
    - 5-9 words total
    - No forbidden start words
    - No duplicate consecutive words
    
    Returns:
        (is_compatible, list_of_violations)
    """
    violations = []
    
    # Check word count
    if not validate_fda_word_count(query):
        word_count = len(query.strip().split())
        violations.append(f"FDA_WORD_COUNT ({word_count} words, need 5-9)")
    
    # Check forbidden start
    if has_forbidden_start_word(query):
        first_word = query.strip().split()[0] if query.strip() else ""
        violations.append(f"FDA_FORBIDDEN_START ({first_word})")
    
    # Check duplicates
    if has_duplicate_words(query):
        violations.append("FDA_DUPLICATE_WORDS")
    
    return (len(violations) == 0, violations)


# ============================================================================
# COMBINED VALIDATION
# ============================================================================

def validate_query(
    query: str,
    beat_text: Optional[str] = None,
    shot_type: Optional[str] = None,
    available_anchors: Optional[List[str]] = None
) -> Tuple[bool, List[str], Dict[str, Any]]:
    """
    Validate a single query against all 3 guardrails.
    
    Args:
        query: Query string to validate
        beat_text: Original beat text (for anchor extraction fallback)
        shot_type: Shot type (for media intent suggestion)
        available_anchors: Pre-extracted anchors from beat
    
    Returns:
        (is_valid, reasons, metadata)
        - is_valid: True if query passes all guardrails
        - reasons: List of rejection reasons (empty if valid)
        - metadata: Dict with diagnostic info
    """
    reasons = []
    metadata = {
        'has_anchor': False,
        'anchor': None,
        'has_media_intent': False,
        'media_intent': None,
        'has_noise': False,
        'noise_terms': [],
        'too_short': False,
    }
    
    # Guardrail 1: ANCHOR
    if not has_anchor(query):
        reasons.append('NO_ANCHOR')
    else:
        metadata['has_anchor'] = True
        metadata['anchor'] = get_anchor_from_query(query)
    
    # Guardrail 2: MEDIA INTENT
    if not has_media_intent(query):
        reasons.append('NO_MEDIA_INTENT')
    else:
        metadata['has_media_intent'] = True
        metadata['media_intent'] = get_media_intent_from_query(query)
    
    # Guardrail 3: NOISE & WIDTH
    if has_noise_terms(query):
        reasons.append('STOPLIST_HIT')
        metadata['has_noise'] = True
        metadata['noise_terms'] = get_noise_terms_from_query(query)
    
    if is_too_short(query, min_meaningful_words=3):  # Keep original guardrail at 3
        reasons.append('TOO_SHORT')
        metadata['too_short'] = True
    
    # FDA COMPATIBILITY CHECK (additional layer)
    is_fda_ok, fda_violations = is_fda_compatible(query)
    if not is_fda_ok:
        reasons.extend(fda_violations)
        metadata['fda_violations'] = fda_violations
    
    is_valid = len(reasons) == 0
    return is_valid, reasons, metadata


# ============================================================================
# QUERY REFINEMENT & REGENERATION
# ============================================================================

def refine_query(
    query: str,
    beat_text: str,
    available_anchors: List[str],
    shot_type: Optional[str] = None,
    episode_topic: Optional[str] = None
) -> str:
    """
    Attempt to fix an invalid query.
    
    Strategy:
    1. Add anchor if missing (from available_anchors)
    2. Add media intent if missing (based on shot_type)
    3. Remove noise terms if present
    4. Ensure FDA compatibility (5-9 words, no forbidden starts, no duplicates)
    
    Returns:
        Refined query string
    """
    refined = query.strip()
    
    # Remove noise terms first
    if has_noise_terms(refined):
        noise_terms = get_noise_terms_from_query(refined)
        for noise in noise_terms:
            # Remove noise term (case-insensitive)
            refined = re.sub(rf'\b{re.escape(noise)}\b', '', refined, flags=re.IGNORECASE)
        refined = re.sub(r'\s+', ' ', refined).strip()
    
    # Remove forbidden start words
    first_word = refined.split()[0].lower() if refined.split() else ""
    if first_word in FDA_FORBIDDEN_START_WORDS:
        words = refined.split()
        refined = ' '.join(words[1:]) if len(words) > 1 else ""
    
    # Remove duplicate consecutive words
    words = refined.split()
    deduped = []
    prev_word = None
    for word in words:
        if word.lower() != (prev_word or "").lower():
            deduped.append(word)
            prev_word = word
    refined = ' '.join(deduped)
    
    # Add anchor if missing
    if not has_anchor(refined) and available_anchors:
        # Prefer first anchor (usually most specific)
        anchor = available_anchors[0]
        # CRITICAL: Strip leading articles to avoid FDA_FORBIDDEN_START
        for prefix in ["The ", "the ", "A ", "a ", "An ", "an "]:
            if anchor.startswith(prefix):
                anchor = anchor[len(prefix):]
                break
        refined = f"{anchor} {refined}"
    
    # Add media intent if missing
    if not has_media_intent(refined):
        refined = add_media_intent_token(refined, shot_type)
    
    # Clean up multiple spaces
    refined = re.sub(r'\s+', ' ', refined).strip()
    
    # Ensure FDA word count (5-9 words)
    # If too short, pad with descriptive words from beat_text
    words = refined.split()
    if len(words) < 5 and beat_text:
        # Extract 1-2 more keywords from beat (filter out duplicates)
        existing_words_lower = {w.lower() for w in words}
        beat_words = [
            w for w in beat_text.lower().split()
            if len(w) > 4 and w.isalpha() and w not in existing_words_lower
        ]
        for beat_word in beat_words[:3]:  # Try up to 3 words
            if len(words) >= 5:
                break
            # Insert before media intent token (last 1-2 words usually)
            if words and any(words[-1] == token or words[-2:] == ['archival', 'photograph'] for token in ['map', 'document', 'photo', 'photograph']):
                # Find media intent position
                if words[-2:] == ['archival', 'photograph']:
                    words.insert(-2, beat_word)
                else:
                    words.insert(-1, beat_word)
            else:
                words.append(beat_word)
        refined = ' '.join(words)
    
    # If too long, truncate to 9 words (keep anchor + media intent)
    words = refined.split()
    if len(words) > 9:
        # Keep first 7 words + last media intent token if present
        if words[-1] in MEDIA_INTENT_TOKENS or words[-2:] == ['archival', 'photograph']:
            refined = ' '.join(words[:7] + words[-2:])
        else:
            refined = ' '.join(words[:9])
    
    return refined


def generate_safe_query(
    beat_text: str,
    available_anchors: List[str],
    shot_type: Optional[str] = None,
    episode_topic: Optional[str] = None
) -> str:
    """
    Generate a safe FDA-compatible fallback query using template.
    
    Template: "{ANCHOR} {keywords} {media_intent}" with 5-9 words total
    
    Args:
        beat_text: Beat text to extract keywords from
        available_anchors: List of available anchors
        shot_type: Optional shot type for media intent
        episode_topic: Optional episode topic for context
    
    Returns:
        Safe query string (5-9 words, FDA-compatible)
    """
    # Pick best anchor: prefer extracted anchors, otherwise derive from episode_topic.
    anchor = available_anchors[0] if available_anchors else _derive_episode_anchor_from_topic(str(episode_topic or ""))
    
    # CRITICAL: Strip leading articles to avoid FDA_FORBIDDEN_START
    for prefix in ["The ", "the ", "A ", "a ", "An ", "an "]:
        if anchor.startswith(prefix):
            anchor = anchor[len(prefix):]
            break
    
    anchor_lower = anchor.lower()
    
    # Extract 2-3 keywords from beat (nouns, not too generic)
    # CRITICAL: Filter out keywords that duplicate the anchor
    generic_stopwords = {
        'history', 'event', 'situation', 'conflict', 'thing', 'background',
        'context', 'footage', 'montage', 'impact', 'support', 'importance',
        'although', 'however', 'despite'  # Also filter forbidden start words
    }
    
    words = beat_text.lower().split()
    keywords = []
    for word in words:
        # Skip if word is part of anchor (avoid "Titanic titanic" duplicates)
        if anchor_lower in word or word in anchor_lower:
            continue
        if (len(word) > 4 and
            word not in generic_stopwords and
            word.isalpha() and  # Only alphabetic words
            not word.startswith(('follow', 'soon', 'after', 'before')) and
            len(keywords) < 3):  # Extract up to 3 keywords
            keywords.append(word)
    
    # Build media token
    if shot_type and 'map' in shot_type.lower():
        media_token = "map"
    elif shot_type and 'document' in shot_type.lower():
        media_token = "document"
    else:
        media_token = "archival photograph"
    
    # Assemble query with target word count 5-7
    parts = [anchor]
    
    # Add keywords to reach 5-7 words (accounting for media_token)
    media_words = media_token.split()
    current_word_count = len(parts) + len(media_words)
    target_min = 5
    target_max = 7
    
    # Add keywords until we reach target range
    for keyword in keywords:
        if current_word_count < target_max:
            parts.append(keyword)
            current_word_count += 1
        else:
            break
    
    # Add media intent
    parts.append(media_token)
    
    query = ' '.join(parts)

    # Ensure FDA forbidden-start rule (defensive; anchor should already be safe).
    if has_forbidden_start_word(query):
        ws = query.split()
        query = " ".join(ws[1:]).strip() if len(ws) > 1 else ""
    
    # Final validation: ensure 5-9 words
    word_count = len(query.split())
    if word_count < 5:
        # Pad with "historical" or "period"
        parts.insert(-1, "historical")
        query = ' '.join(parts)
    elif word_count > 9:
        # Truncate (keep anchor + 2 keywords + media)
        words = query.split()
        query = ' '.join(words[:7] + [media_token])
    
    return query


# ============================================================================
# BATCH VALIDATION & REGENERATION
# ============================================================================

def validate_and_fix_queries(
    queries: List[str],
    beat_text: str,
    shot_types: Optional[List[str]] = None,
    episode_topic: Optional[str] = None,
    min_valid_queries: int = 6,
    max_regen_attempts: int = 2,
    verbose: bool = True
) -> Tuple[List[str], Dict[str, Any]]:
    """
    Validate and fix a batch of queries with regeneration logic.
    
    Strategy:
    1. Validate all queries
    2. Try to refine invalid ones (1 attempt)
    3. If still < min_valid_queries, regenerate missing ones (max 2 attempts)
    4. Mark beat as "low_coverage" if still insufficient
    
    Args:
        queries: List of generated queries
        beat_text: Original beat text
        shot_types: List of shot types (for media intent)
        episode_topic: Episode topic (for anchor fallback)
        min_valid_queries: Minimum required valid queries
        max_regen_attempts: Maximum regeneration attempts
        verbose: Print diagnostic info
    
    Returns:
        (valid_queries, diagnostics)
    """
    diagnostics = {
        'original_count': len(queries),
        'valid_count': 0,
        'invalid_count': 0,
        'refined_count': 0,
        'regenerated_count': 0,
        'rejection_reasons': {},
        'final_count': 0,
        'low_coverage': False,
    }
    
    # Extract anchors from beat text (once)
    available_anchors = extract_anchors_from_text(beat_text)
    
    # CRITICAL: episode_topic is REQUIRED for valid anchoring
    # Cannot rely solely on beat text (may be generic)
    if not episode_topic or not episode_topic.strip():
        raise ValueError(
            "EPISODE_TOPIC_REQUIRED: episode_topic parameter is required for query validation. "
            "Cannot generate anchored queries without episode context. "
            "Provide episode_metadata['title'] or ['topic']."
        )
    
    # Add episode topic as anchor source (derived FDA-safe anchor, not full topic paragraph)
    available_anchors.append(_derive_episode_anchor_from_topic(episode_topic.strip()))
    
    shot_type = shot_types[0] if shot_types else None
    
    # Phase 1: Validate original queries
    valid_queries = []
    invalid_queries = []
    
    for query in queries:
        is_valid, reasons, metadata = validate_query(
            query, beat_text, shot_type, available_anchors
        )
        
        if is_valid:
            valid_queries.append(query)
            diagnostics['valid_count'] += 1
        else:
            invalid_queries.append((query, reasons, metadata))
            diagnostics['invalid_count'] += 1
            
            # Track rejection reasons
            for reason in reasons:
                diagnostics['rejection_reasons'][reason] = \
                    diagnostics['rejection_reasons'].get(reason, 0) + 1
    
    if verbose:
        print(f"   Query validation: {diagnostics['valid_count']}/{len(queries)} valid")
        if diagnostics['rejection_reasons']:
            print(f"   Rejection reasons: {diagnostics['rejection_reasons']}")
    
    # Phase 2: NO REFINEMENT - deterministický generátor musí produkovat validní queries
    # Pouze logujeme invalid queries pro debugging
    if invalid_queries and verbose:
        for query, reasons, metadata in invalid_queries:
            print(f"   ✗ Invalid (not refining): '{query}' (reasons: {reasons})")
    
    # Phase 3: NO REGENERATION - žádné fallbacky
    # Deterministický generátor (`_generate_deterministic_queries_v27`) je zodpovědný
    # za produkci přesně 5 validních queries. Pokud selže, FDA validator to zachytí.
    
    # Phase 4: VALIDATION ONLY - NO FALLBACKS
    # Deterministický generátor MUSÍ produkovat 5 validních queries
    # Query guardrails pouze validují, NEREGENERUJÍ
    target_count = 5
    
    # Trim to exactly 5 if more
    if len(valid_queries) > target_count:
        valid_queries = valid_queries[:target_count]
        if verbose:
            print(f"   Trimmed to {target_count} queries")
    
    # If less than 5: mark as low_coverage (NO PADDING - deterministic generator must fix this)
    if len(valid_queries) < target_count:
        diagnostics['low_coverage'] = True
        if verbose:
            print(f"   ⚠️  LOW COVERAGE: Only {len(valid_queries)}/{target_count} valid queries (NO FALLBACK)")
        # Return what we have - FDA validator will catch this and fail loudly
    
    diagnostics['final_count'] = len(valid_queries)
    
    return valid_queries, diagnostics


# ============================================================================
# INTEGRATION HELPERS
# ============================================================================

def validate_scene_queries(
    scene: Dict[str, Any],
    episode_topic: Optional[str] = None,
    min_valid_queries: int = 6,
    verbose: bool = True
) -> Dict[str, Any]:
    """
    Validate and fix queries for a single scene from shot plan.
    
    Modifies scene in-place: scene['search_queries'] updated with valid queries.
    
    Args:
        scene: Scene dict with 'search_queries', 'narration_text', 'shot_types'
        episode_topic: Episode topic for fallback anchors
        min_valid_queries: Minimum required valid queries
        verbose: Print diagnostic info
    
    Returns:
        Diagnostics dict
    """
    queries = scene.get('search_queries', [])
    narration_text = scene.get('narration_text', '')
    shot_types = scene.get('shot_types', [])
    scene_id = scene.get('scene_id', 'unknown')
    
    if not queries:
        if verbose:
            print(f"Scene {scene_id}: No queries to validate")
        return {'final_count': 0, 'low_coverage': True}
    
    if verbose:
        print(f"\nScene {scene_id}: Validating {len(queries)} queries")
    
    valid_queries, diagnostics = validate_and_fix_queries(
        queries,
        narration_text,
        shot_types=shot_types,
        episode_topic=episode_topic,
        min_valid_queries=min_valid_queries,
        verbose=verbose
    )
    
    # Update scene with valid queries
    scene['search_queries'] = valid_queries
    scene['_query_diagnostics'] = diagnostics
    
    return diagnostics


def validate_shot_plan_queries(
    shot_plan: Dict[str, Any],
    episode_topic: Optional[str] = None,
    min_valid_queries: int = 6,
    verbose: bool = True
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """
    Validate and fix all queries in a shot plan.
    
    Args:
        shot_plan: Shot plan dict with 'scenes' list
        episode_topic: Episode topic for fallback anchors
        min_valid_queries: Minimum required valid queries per scene
        verbose: Print diagnostic info
    
    Returns:
        (updated_shot_plan, overall_diagnostics)
    """
    scenes = shot_plan.get('scenes', [])
    
    overall_diagnostics = {
        'total_scenes': len(scenes),
        'scenes_with_low_coverage': 0,
        'total_original_queries': 0,
        'total_final_queries': 0,
        'total_refined': 0,
        'total_regenerated': 0,
        'rejection_reasons_summary': {},
    }
    
    for scene in scenes:
        scene_diag = validate_scene_queries(scene, episode_topic, min_valid_queries, verbose)
        
        # Aggregate stats
        overall_diagnostics['total_original_queries'] += scene_diag.get('original_count', 0)
        overall_diagnostics['total_final_queries'] += scene_diag.get('final_count', 0)
        overall_diagnostics['total_refined'] += scene_diag.get('refined_count', 0)
        overall_diagnostics['total_regenerated'] += scene_diag.get('regenerated_count', 0)
        
        if scene_diag.get('low_coverage'):
            overall_diagnostics['scenes_with_low_coverage'] += 1
        
        # Aggregate rejection reasons
        for reason, count in scene_diag.get('rejection_reasons', {}).items():
            overall_diagnostics['rejection_reasons_summary'][reason] = \
                overall_diagnostics['rejection_reasons_summary'].get(reason, 0) + count
    
    if verbose:
        print("\n" + "="*60)
        print("QUERY VALIDATION SUMMARY")
        print("="*60)
        print(f"Total scenes: {overall_diagnostics['total_scenes']}")
        print(f"Total original queries: {overall_diagnostics['total_original_queries']}")
        print(f"Total final queries: {overall_diagnostics['total_final_queries']}")
        print(f"Total refined: {overall_diagnostics['total_refined']}")
        print(f"Total regenerated: {overall_diagnostics['total_regenerated']}")
        print(f"Scenes with low coverage: {overall_diagnostics['scenes_with_low_coverage']}")
        if overall_diagnostics['rejection_reasons_summary']:
            print(f"Rejection reasons: {overall_diagnostics['rejection_reasons_summary']}")
        print("="*60)
    
    return shot_plan, overall_diagnostics

