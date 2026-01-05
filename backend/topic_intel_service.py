"""
Topic Intelligence Service - USA/EN focus

Main orchestration service for topic research pipeline:
1. Seed collection (YouTube mostPopular + static list)
2. LLM topic expansion (GPT-4o)
3. Signal fetching (parallel)
4. Scoring and ranking
5. Top N selection

Fully isolated from episode pipeline.
"""

import os
import json
import time
import uuid
import requests
import re
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed

from gpt_utils import call_openai
from topic_intel_providers import (
    GoogleTrendsProvider,
    WikipediaPageviewsProvider,
    YouTubeSignalsProvider
)


def call_openai_openrouter(prompt: str, model: str = "openai/gpt-4o", temperature: float = 0.7) -> dict:
    """
    Call OpenRouter API (compatible interface with call_openai).
    
    Args:
        prompt: The prompt text
        model: OpenRouter model name (e.g., 'openai/gpt-4o', 'anthropic/claude-3.5-sonnet')
        temperature: Temperature (0.0-2.0)
    
    Returns:
        dict: Response with 'content' or 'error'
    """
    try:
        api_key = os.getenv('OPENROUTER_API_KEY')
        if not api_key:
            return {"error": "OpenRouter API key not configured"}
        
        url = "https://openrouter.ai/api/v1/chat/completions"
        
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
            "HTTP-Referer": "https://github.com/your-repo",  # Optional
            "X-Title": "Topic Intelligence Assistant"  # Optional
        }
        
        data = {
            "model": model,
            "messages": [
                {
                    "role": "system",
                    "content": "You are a professional documentary researcher. Always return valid JSON in the requested format."
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            "temperature": temperature
        }
        
        response = requests.post(url, headers=headers, json=data, timeout=120)
        response.raise_for_status()
        
        result = response.json()
        content = result.get('choices', [{}])[0].get('message', {}).get('content', '')
        
        return {"content": content}
        
    except Exception as e:
        return {"error": str(e)}


# Historical documentary archetypes (optimized for retention)
ARCHETYPES = [
    "Final Days / Last Hours",
    "Betrayal & Power",
    "Forbidden / Hidden History",
    "Disaster as Thriller",
    "Trial / Execution / Scandal",
    "Mystery / Vanished",
    "War Turning Points",
    "Empire Collapse",
    "Genius vs. System",
    "Plagues & Panic",
    "Conspiracy (Evidence-based)",
    "Survival Stories"
]

# Static seed list (fallback when YouTube API not available)
STATIC_SEED_TOPICS = [
    "The Fall of the Berlin Wall",
    "Assassination of Julius Caesar",
    "Discovery of Tutankhamun's Tomb",
    "The Salem Witch Trials",
    "Mount Vesuvius Eruption Pompeii",
    "The Titanic Disaster",
    "D-Day Normandy Invasion",
    "The Great Fire of London",
    "The Space Race Apollo 11",
    "The Black Death Plague",
    "The French Revolution",
    "The Mystery of Atlantis",
    "Escape from Alcatraz",
    "The Hindenburg Disaster",
    "The Boston Tea Party",
    "The Lost Colony of Roanoke",
    "The Chernobyl Nuclear Disaster",
    "The Wright Brothers First Flight",
    "The Gunpowder Plot",
    "The Last Days of Napoleon",
    "The Sinking of the Lusitania",
    "The Battle of Thermopylae",
    "The Discovery of Penicillin",
    "The Moon Landing Conspiracy",
    "The Triangle Shirtwaist Factory Fire",
    "The Reign of Cleopatra",
    "The Viking Voyages to America",
    "The Roswell UFO Incident",
    "The Assassination of Abraham Lincoln",
    "The Terracotta Army Discovery"
]


class TopicIntelService:
    """
    Main service for Topic Intelligence Assistant.
    Orchestrates the entire research pipeline.
    """
    
    def __init__(self, verbose: bool = False):
        self.verbose = verbose
        
        # Initialize providers
        self.google_trends = GoogleTrendsProvider(verbose=verbose)
        self.wikipedia = WikipediaPageviewsProvider(verbose=verbose)
        
        # YouTube provider loads key lazily (from env / backend/.env) so it works as soon as configured
        self.youtube = YouTubeSignalsProvider(api_key=None, verbose=verbose)
        
        # Max candidates to process (performance guard)
        self.max_candidates = 200
        
        # Load profiles
        self.profiles = self._load_profiles()

    def _tokenize(self, text: str) -> List[str]:
        return re.findall(r"[a-z0-9]+", (text or "").lower())

    def _candidate_signature(self, topic: str) -> str:
        """
        Stable signature for deduping topics.
        """
        toks = self._tokenize(topic)
        # remove trivial stopwords
        stop = {"the", "a", "an", "of", "and", "in", "to", "for", "on", "at", "with", "from", "by"}
        toks = [t for t in toks if t not in stop]
        return " ".join(toks[:12]).strip()

    def _profile_match(self, profile: Dict[str, Any], candidate: Dict[str, Any]) -> bool:
        """
        Server-side enforcement so LLM can't drift off-topic.
        - avoid_topics: hard blacklist (reject)
        - must_fit_topics: at least one phrase must match (token-subset match)
        """
        topic = candidate.get("topic", "") or ""
        angle = candidate.get("suggested_angle", "") or ""
        why = candidate.get("why_now_draft", "") or ""
        combined = f"{topic} {angle} {why}".lower()
        combined_tokens = set(self._tokenize(combined))

        # Hard blacklist
        for bad in profile.get("avoid_topics", []) or []:
            if bad and str(bad).lower() in combined:
                return False

        must_fit = profile.get("must_fit_topics", []) or []
        if must_fit:
            for phrase in must_fit:
                ptoks = [t for t in self._tokenize(str(phrase)) if t]
                if ptoks and set(ptoks).issubset(combined_tokens):
                    return True
            # If none matched, reject
            return False

        return True

    def _filter_and_dedupe_candidates(self, candidates: List[Dict[str, Any]], profile: Dict[str, Any], target_count: int) -> List[Dict[str, Any]]:
        """
        Remove duplicates + enforce channel profile constraints.
        If filtering is too strict (returns too few), relax must_fit but still enforce hard blacklist.
        """
        seen = set()
        kept: List[Dict[str, Any]] = []
        rejected_hard = 0
        rejected_fit = 0

        for c in candidates:
            topic = (c.get("topic") or "").strip()
            if not topic:
                continue
            sig = self._candidate_signature(topic)
            if not sig or sig in seen:
                continue
            # Hard blacklist + must_fit enforcement
            if not self._profile_match(profile, c):
                # Track which gate failed (best effort)
                combined = f"{topic} {c.get('suggested_angle','')} {c.get('why_now_draft','')}".lower()
                hard = False
                for bad in profile.get("avoid_topics", []) or []:
                    if bad and str(bad).lower() in combined:
                        hard = True
                        break
                if hard:
                    rejected_hard += 1
                else:
                    rejected_fit += 1
                continue

            seen.add(sig)
            kept.append(c)

        # If too strict, relax must_fit but keep hard blacklist
        if len(kept) < max(5, min(target_count, 20)):
            relaxed: List[Dict[str, Any]] = []
            seen2 = set(seen)
            for c in candidates:
                topic = (c.get("topic") or "").strip()
                if not topic:
                    continue
                sig = self._candidate_signature(topic)
                if not sig or sig in seen2:
                    continue
                combined = f"{topic} {c.get('suggested_angle','')} {c.get('why_now_draft','')}".lower()
                hard_blocked = False
                for bad in profile.get("avoid_topics", []) or []:
                    if bad and str(bad).lower() in combined:
                        hard_blocked = True
                        break
                if hard_blocked:
                    continue
                seen2.add(sig)
                relaxed.append(c)
                if len(kept) + len(relaxed) >= target_count * 3:
                    break
            kept.extend(relaxed)

        if self.verbose:
            print(f"   🧹 Candidate cleanup: kept={len(kept)} rejected_fit={rejected_fit} rejected_hard={rejected_hard}")
        return kept
    
    def _load_profiles(self) -> Dict[str, Dict[str, Any]]:
        """Load channel profiles from JSON file"""
        try:
            profiles_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'topic_intel_profiles.json')
            if not os.path.exists(profiles_path):
                return self._get_default_profiles()
            
            with open(profiles_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # Convert list to dict keyed by id
            profiles_dict = {}
            for profile in data.get('profiles', []):
                profiles_dict[profile['id']] = profile
            
            return profiles_dict
        except Exception as e:
            if self.verbose:
                print(f"⚠️  Failed to load profiles: {e}, using defaults")
            return self._get_default_profiles()
    
    def _get_default_profiles(self) -> Dict[str, Dict[str, Any]]:
        """Fallback default profiles"""
        return {
            'us_history_docs': {
                'id': 'us_history_docs',
                'name': 'US History Docs',
                'locale': 'US',
                'language': 'en-US',
                'content_type': 'history_docs',
                'must_fit_topics': ['turning points', 'empires', 'betrayals', 'disasters', 'trials', 'mysteries'],
                'must_avoid_topics': ['graphic gore', 'extremist propaganda'],
                'style_notes': 'Documentary style with thriller/mystery framing.',
                'archetype_weights': dict.fromkeys(ARCHETYPES, 0.8),
                'avoid_topics': []
            },
            'us_true_crime': {
                'id': 'us_true_crime',
                'name': 'US True Crime',
                'locale': 'US',
                'language': 'en-US',
                'content_type': 'true_crime',
                'must_fit_topics': ['investigations', 'timelines', 'courtroom', 'disappearances'],
                'must_avoid_topics': ['explicit gore', 'victim-blaming'],
                'style_notes': 'True crime documentary with investigative approach.',
                'archetype_weights': dict.fromkeys(ARCHETYPES, 0.7),
                'avoid_topics': []
            }
        }
    
    def _call_llm_openrouter(self, prompt: str, model: str, temperature: float) -> dict:
        """Wrapper to call OpenRouter"""
        return call_openai_openrouter(prompt, model, temperature)
    
    def research(self, count: int, window_days: int, profile_id: str, locale: str, language: str, 
                 llm_provider: str = 'openrouter', llm_model: str = 'openai/gpt-4o', 
                 llm_temperature: float = 0.7, llm_custom_prompt: Optional[str] = None,
                 recommendation_mode: str = 'momentum') -> Dict[str, Any]:
        """
        Execute full topic research pipeline.
        
        Args:
            count: Number of top recommendations to return (5-50)
            window_days: Time window for signals (7, 30)
            profile_id: Channel profile ID (e.g., 'us_history_docs')
            locale: Locale code (e.g., 'US')
            language: Language code (e.g., 'en-US')
            llm_provider: LLM provider ('openrouter' only for now)
            llm_model: Model name (e.g., 'openai/gpt-4o')
            llm_temperature: Temperature (0.0-2.0)
            llm_custom_prompt: Optional custom prompt instructions
            recommendation_mode: 'momentum', 'balanced', or 'evergreen'
        
        Returns:
            {
                'request_id': str,
                'generated_at': str (ISO),
                'items': List[TopicIdea],
                'other_ideas': List[TopicIdea],
                'stats': {...}
            }
        """
        request_id = f"ti_{uuid.uuid4().hex[:12]}"
        start_time = time.time()
        
        # Load profile
        profile = self.profiles.get(profile_id)
        if not profile:
            if self.verbose:
                print(f"⚠️  Profile {profile_id} not found, using default")
            profile = self.profiles.get('us_history_docs', list(self.profiles.values())[0])
        
        if self.verbose:
            print(f"\n{'='*60}")
            print(f"🔬 Topic Intelligence Research: {request_id}")
            print(f"   Profile: {profile['name']} ({profile_id})")
            print(f"   Count: {count}, Window: {window_days}d, Locale: {locale}")
            print(f"   Mode: {recommendation_mode.upper()}")
            print(f"   LLM: {llm_provider}/{llm_model}, Temp: {llm_temperature}")
            print(f"{'='*60}\n")
        
        # Step 1: Seed collection
        seeds = self._collect_seeds(locale)
        if self.verbose:
            print(f"✅ Collected {len(seeds)} seed topics")
        
        # Step 2: Topic expansion (with profile)
        expansion_count = min(count * 4, self.max_candidates)  # 4x candidates
        candidates = self._expand_topics(seeds, expansion_count, profile, 
                                        llm_provider, llm_model, llm_temperature, llm_custom_prompt)
        # Server-side cleanup: enforce profile + dedupe so output is on-topic
        candidates = self._filter_and_dedupe_candidates(candidates, profile, target_count=expansion_count)
        if self.verbose:
            print(f"✅ Expanded to {len(candidates)} candidate topics")
        
        # Step 3: Signal fetching (parallel)
        candidates_with_signals = self._fetch_signals_batch(candidates, window_days, locale)
        if self.verbose:
            print(f"✅ Fetched signals for {len(candidates_with_signals)} candidates")
        
        # Step 4: Scoring and ranking (with mode-specific weights)
        scored_candidates = self._score_candidates(candidates_with_signals, recommendation_mode)
        if self.verbose:
            print(f"✅ Scored {len(scored_candidates)} candidates")
        
        # Step 5: Apply gate filters and split TOP / Other Ideas
        top_recommendations, other_ideas = self._apply_gates_and_split(scored_candidates, count, recommendation_mode)
        if self.verbose:
            print(f"✅ TOP recommendations: {len(top_recommendations)}")
            print(f"   Other ideas: {len(other_ideas)}")
        
        elapsed = time.time() - start_time
        
        return {
            'request_id': request_id,
            'generated_at': datetime.now(timezone.utc).isoformat(),
            'locale': locale,
            'language': language,
            'recommendation_mode': recommendation_mode,
            'items': top_recommendations,
            'other_ideas': other_ideas,
            'stats': {
                'seeds_collected': len(seeds),
                'candidates_generated': len(candidates),
                'candidates_scored': len(scored_candidates),
                'top_recommendations': len(top_recommendations),
                'other_ideas': len(other_ideas),
                'elapsed_seconds': round(elapsed, 2),
                'provider_stats': {
                    'google_trends': {
                        'requests': self.google_trends.request_count,
                        'cache_hits': self.google_trends.cache_hit_count
                    },
                    'wikipedia': {
                        'requests': self.wikipedia.request_count,
                        'cache_hits': self.wikipedia.cache_hit_count
                    },
                    'youtube': {
                        'requests': self.youtube.request_count,
                        'cache_hits': self.youtube.cache_hit_count
                    }
                }
            }
        }
    
    def _collect_seeds(self, locale: str) -> List[str]:
        """
        Collect seed topics from YouTube mostPopular + static list.
        """
        seeds = []
        
        # Try YouTube mostPopular first
        try:
            youtube_titles = self.youtube.get_most_popular_videos(locale=locale, max_results=30)
            if youtube_titles:
                seeds.extend(youtube_titles)
                if self.verbose:
                    print(f"   📺 YouTube: {len(youtube_titles)} popular titles")
        except Exception as e:
            if self.verbose:
                print(f"   ⚠️  YouTube seed failed: {e}")
        
        # Always add static seeds (diversity)
        seeds.extend(STATIC_SEED_TOPICS)
        if self.verbose:
            print(f"   📚 Static: {len(STATIC_SEED_TOPICS)} curated topics")
        
        # Deduplicate and return
        unique_seeds = list(dict.fromkeys(seeds))  # Preserve order
        return unique_seeds[:50]  # Cap at 50 seeds
    
    def _expand_topics(self, seeds: List[str], count: int, profile: Dict[str, Any],
                       llm_provider: str = 'openrouter', llm_model: str = 'openai/gpt-4o',
                       llm_temperature: float = 0.7, llm_custom_prompt: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Use LLM to expand seeds into candidate topics with channel profile.
        
        Returns:
            [{'topic': str, 'suggested_angle': str, 'why_now_draft': str}, ...]
        """
        # Prepare prompt
        seeds_sample = seeds[:20]  # Use up to 20 seeds for context
        archetypes_str = "\n".join(f"- {a}" for a in ARCHETYPES)
        seeds_str = "\n".join(f"- {s}" for s in seeds_sample)
        
        # CHANNEL PROFILE BLOCK (as instructed)
        must_fit = ", ".join(profile.get('must_fit_topics', []))
        must_avoid = ", ".join(profile.get('must_avoid_topics', []))
        avoid_topics_hard = json.dumps(profile.get('avoid_topics', []))
        archetype_weights = json.dumps(profile.get('archetype_weights', {}), indent=2)
        
        profile_block = f"""
**CHANNEL PROFILE:**
- Name: {profile.get('name', 'Unknown')}
- Audience: {profile.get('locale', 'US')}
- Language: {profile.get('language', 'en-US')}
- Content type: {profile.get('content_type', 'general')}
- Must-fit topics: {must_fit}
- Must-avoid topics: {must_avoid}
- Style notes: {profile.get('style_notes', 'N/A')}
- Archetype weights (0-1): {archetype_weights}
- Hard blacklist (avoid_topics): {avoid_topics_hard}
"""
        
        # Base prompt
        prompt = f"""You are a topic researcher for a documentary YouTube channel.

{profile_block}

**Current Trending Seeds ({profile.get('locale', 'US')}):**
{seeds_str}

**Available Archetypes (retention-optimized):**
{archetypes_str}

**Task:** Generate {count} compelling documentary topic ideas that FIT THE CHANNEL PROFILE.

**CRITICAL REQUIREMENTS:**
1. ALL topics MUST fit the "Must-fit topics" list
2. NEVER suggest topics from "Must-avoid topics" or "Hard blacklist"
3. Follow the style notes exactly
4. Prefer archetypes with higher weights (closer to 1.0)
5. Focus on {profile.get('content_type', 'documentary')} content
6. Clickable titles (not academic)

**FARM BRIEF REQUIREMENTS (CRITICAL):**
Each topic MUST include `farm_brief_en` (1-3 sentences, max 450 characters):
- Hook/Promise: One strong opening claim that explains WHY viewers should watch
- Exactly 3 beats: Three specific, concrete story elements to cover (e.g., "the decisive mistake", "the hidden informant", "the courtroom turning point")
- Style/Pacing hint: Brief phrase about tone (e.g., "thriller pacing", "evidence-aware", "minute-by-minute")
- Written to be pasted directly into production farm as the topic brief
- Safe for monetization (no graphic details)
- FORBIDDEN: Generic phrases without content like "explore the story", "dive into...", "uncover the mystery" UNLESS they include the 3 specific beats
- Example structure: "[Hook]. We examine [beat 1], [beat 2], and [beat 3]. [Pacing/style note]."

**CZECH LANGUAGE FIELDS (CRITICAL):**
Each topic MUST also include:
- `recommendation_summary_cs`: 1 sentence in Czech explaining why to make this topic (human-readable)
- `opportunity_bullets_cs`: 2-3 short bullet points in Czech (advantages)
- `risk_bullets_cs`: 1-3 short bullet points in Czech (risks/cautions)"""

        # Add custom prompt if provided
        if llm_custom_prompt and llm_custom_prompt.strip():
            prompt += f"\n\n**Additional Instructions:**\n{llm_custom_prompt.strip()}"
        
        prompt += f"""

**Output Format:**
```json
[
  {{
    "topic": "The Last 48 Hours of Anne Boleyn",
    "suggested_angle": "Minute-by-minute thriller: courtroom to scaffold",
    "why_now_draft": "Tudor history trending on Netflix, female power narratives resonate",
    "farm_brief_en": "The queen who changed history had 48 hours between verdict and execution. We examine her final trial power moves, the secret message to her daughter, and why her last words on the scaffold terrified King Henry. Thriller pacing, evidence-based.",
    "recommendation_summary_cs": "Doporučujeme díky nízké konkurenci, silnému zájmu o Tudorovce a perfektnímu thriller framingu.",
    "opportunity_bullets_cs": [
      "Nízká YouTube konkurence (5 nových videí/měsíc)",
      "Vysoký zájem na Wikipedii (200k+ views týdně)",
      "Perfektní pro thriller/drama archetyp"
    ],
    "risk_bullets_cs": [
      "Potřebuje vizuálně silný obal aby se odlišilo",
      "Nutné citlivé zacházení s popravou"
    ]
  }},
  ...
]
```

Generate exactly {count} topics as a JSON array. ALL fields (including farm_brief_en with EXACTLY 3 beats and Czech fields) are REQUIRED. No additional text."""

        try:
            # Use OpenRouter via call_openai_openrouter helper
            response = self._call_llm_openrouter(prompt, llm_model, llm_temperature)
            
            if 'error' in response:
                if self.verbose:
                    print(f"   ⚠️  LLM error: {response['error']}")
                return []
            
            # Parse response
            content = response.get('content', '')
            
            # Extract JSON from markdown code blocks if present
            if '```json' in content:
                content = content.split('```json')[1].split('```')[0].strip()
            elif '```' in content:
                content = content.split('```')[1].split('```')[0].strip()
            
            candidates = json.loads(content)
            
            # Validate structure - CHECK FOR REQUIRED NEW FIELDS
            validated = []
            for c in candidates:
                if isinstance(c, dict) and 'topic' in c:
                    # Check for required new fields
                    if not c.get('farm_brief_en'):
                        raise ValueError(f"PROMPT_MISMATCH: Missing 'farm_brief_en' field for topic '{c.get('topic')}'")
                    if not c.get('recommendation_summary_cs'):
                        raise ValueError(f"PROMPT_MISMATCH: Missing 'recommendation_summary_cs' field for topic '{c.get('topic')}'")
                    if not c.get('opportunity_bullets_cs'):
                        raise ValueError(f"PROMPT_MISMATCH: Missing 'opportunity_bullets_cs' field for topic '{c.get('topic')}'")
                    if not c.get('risk_bullets_cs'):
                        raise ValueError(f"PROMPT_MISMATCH: Missing 'risk_bullets_cs' field for topic '{c.get('topic')}'")
                    
                    validated.append({
                        'topic': c.get('topic', '').strip(),
                        'suggested_angle': c.get('suggested_angle', '').strip(),
                        'why_now_draft': c.get('why_now_draft', '').strip(),
                        'farm_brief_en': c.get('farm_brief_en', '').strip(),
                        'recommendation_summary_cs': c.get('recommendation_summary_cs', '').strip(),
                        'opportunity_bullets_cs': c.get('opportunity_bullets_cs', []),
                        'risk_bullets_cs': c.get('risk_bullets_cs', [])
                    })
            
            if not validated:
                raise ValueError("PROMPT_MISMATCH: No valid candidates with required fields returned by LLM")
            
            return validated[:self.max_candidates]
            
        except ValueError as ve:
            # Propagate PROMPT_MISMATCH errors
            if 'PROMPT_MISMATCH' in str(ve):
                raise ve
            raise
        except Exception as e:
            if self.verbose:
                print(f"   ⚠️  Topic expansion failed: {e}")
            raise ValueError(f"PROMPT_MISMATCH or JSON parsing error: {e}")
    
    def _fetch_signals_batch(self, candidates: List[Dict[str, Any]], window_days: int, locale: str) -> List[Dict[str, Any]]:
        """
        Fetch signals for all candidates in parallel.
        """
        results = []
        
        def fetch_for_candidate(candidate: Dict[str, Any]) -> Dict[str, Any]:
            """Fetch all signals for one candidate"""
            topic = candidate['topic']
            
            # Fetch all three signals
            google_signal = self.google_trends.fetch(topic, window_days, locale)
            wikipedia_signal = self.wikipedia.fetch(topic, window_days, locale)
            youtube_signal = self.youtube.fetch(topic, window_days, locale)
            
            # Attach signals to candidate
            candidate['signals'] = {
                'google_trends': google_signal,
                'wikipedia': wikipedia_signal,
                'youtube': youtube_signal
            }
            
            return candidate
        
        # Parallel execution with thread pool
        if not candidates:
            return results  # Return empty list if no candidates
        
        max_workers = max(1, min(10, len(candidates)))  # Min 1, max 10 concurrent threads
        
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(fetch_for_candidate, c): c for c in candidates}
            
            for future in as_completed(futures):
                try:
                    result = future.result(timeout=30)
                    results.append(result)
                except Exception as e:
                    candidate = futures[future]
                    if self.verbose:
                        print(f"   ⚠️  Signal fetch failed for '{candidate['topic']}': {e}")
                    # Still include candidate with error signals
                    candidate['signals'] = {
                        'google_trends': {'status': 'error', 'score': 0, 'note': 'Fetch failed', 'metadata': {}},
                        'wikipedia': {'status': 'error', 'score': 0, 'note': 'Fetch failed', 'metadata': {}},
                        'youtube': {'status': 'error', 'score': 0, 'note': 'Fetch failed', 'metadata': {}}
                    }
                    results.append(candidate)
        
        return results
    
    def _score_candidates(self, candidates: List[Dict[str, Any]], recommendation_mode: str = 'momentum') -> List[Dict[str, Any]]:
        """
        Score candidates based on signals and archetype fit.
        Scoring weights vary by recommendation_mode.
        
        Modes:
        - momentum: 55% trend, 25% baseline, 20% competition
        - balanced: 35% baseline, 35% competition, 30% trend  
        - evergreen: 55% competition, 35% baseline, 10% trend
        """
        scored = []
        
        for candidate in candidates:
            signals = candidate.get('signals', {})
            
            # Extract signal scores
            trends_signal = signals.get('google_trends', {})
            wiki_signal = signals.get('wikipedia', {})
            youtube_signal = signals.get('youtube', {})
            
            wiki_metadata = wiki_signal.get('metadata', {})
            wiki_views = wiki_metadata.get('total_views', 0)
            wiki_delta_pct = wiki_metadata.get('delta_pct', 0)
            
            trends_score = trends_signal.get('score', 0)
            trends_available = trends_signal.get('status') == 'ok'
            wiki_score = wiki_signal.get('score', 0)
            youtube_score = youtube_signal.get('score', 0)
            
            yt_metadata = youtube_signal.get('metadata', {})
            yt_recent_count = yt_metadata.get('recent_videos_count', 0)
            yt_dominated = yt_metadata.get('dominated_by_large_channels', False)
            
            # Calculate baseline score (Wikipedia views)
            baseline_score = wiki_score
            
            # Calculate trend score
            if trends_available and trends_score > 0:
                trend_score = trends_score * 0.4 + (50 + wiki_delta_pct * 2) * 0.6  # Convert delta% to 0-100 scale
            else:
                # Trend score based on wiki delta only
                trend_score = max(0, min(100, 50 + wiki_delta_pct * 2))  # -25% = 0, 0% = 50, +25% = 100
            
            # Competition score (inverse)
            competition_score = youtube_score
            
            # Retention fit (heuristic: check for archetype keywords)
            retention_score = self._calculate_retention_fit(candidate)
            
            # Mode-specific weights
            if recommendation_mode == 'momentum':
                # Momentum: 55% trend, 25% baseline, 20% competition
                final_score = (
                    trend_score * 0.55 +
                    baseline_score * 0.25 +
                    competition_score * 0.20
                )
            elif recommendation_mode == 'evergreen':
                # Evergreen: 55% competition (low=good), 35% baseline, 10% trend
                final_score = (
                    competition_score * 0.55 +
                    baseline_score * 0.35 +
                    trend_score * 0.10
                )
            else:  # balanced
                # Balanced: 35% baseline, 35% competition, 30% trend
                final_score = (
                    baseline_score * 0.35 +
                    competition_score * 0.35 +
                    trend_score * 0.30
                )
            
            # Apply penalties
            # Crash penalty (wiki_delta <= -30%)
            if wiki_delta_pct <= -30:
                if recommendation_mode == 'momentum':
                    final_score -= 40  # Harsh in momentum
                elif recommendation_mode == 'balanced':
                    final_score -= 25
                else:  # evergreen
                    final_score -= 15  # Less harsh for evergreen
            
            # Mega channel dominance penalty
            if yt_dominated:
                final_score -= 15
            
            # Ensure score is in 0-100 range
            final_score = max(0, min(100, final_score))
            
            # Rating letter
            if final_score >= 90:
                rating = "A++"
            elif final_score >= 80:
                rating = "A"
            elif final_score >= 70:
                rating = "B"
            else:
                rating = "C"
            
            # Competition flags
            competition_flags = yt_metadata.get('competition_flags', [])
            
            # Store raw signal data for gate filtering
            raw_signal_data = {
                'wiki_views': wiki_views,
                'wiki_delta_pct': wiki_delta_pct,
                'yt_recent_count': yt_recent_count,
                'yt_dominated': yt_dominated
            }
            
            # Generate interpretations (deterministic, no LLM)
            wiki_interp = self._interpret_wikipedia(wiki_signal)
            yt_interp = self._interpret_youtube(youtube_signal)
            trends_interp = self._interpret_trends(trends_signal)
            
            # Generate recommendation summary
            recommendation_summary = self._generate_recommendation_summary(
                wiki_signal, youtube_signal, trends_signal, final_score
            )
            
            # Generate opportunity and risk bullets
            opportunity_bullets, risk_bullets = self._generate_opportunity_risk(
                wiki_signal, youtube_signal, trends_signal, candidate
            )
            
            # Build scored candidate
            scored_candidate = {
                'topic': candidate['topic'],
                'rating_letter': rating,
                'score_total': int(final_score),
                'score_breakdown': {
                    'baseline': int(baseline_score),
                    'trend': int(trend_score),
                    'competition': int(competition_score)
                },
                '_raw_signal_data': raw_signal_data,  # For gate filtering
                'recommendation_summary': recommendation_summary,
                'hook_angle': candidate.get('suggested_angle', ''),
                'why_now': candidate.get('why_now_draft', ''),
                'opportunity_bullets': opportunity_bullets,
                'risk_bullets': risk_bullets,
                # NEW: Czech fields from LLM
                'recommendation_summary_cs': candidate.get('recommendation_summary_cs', 'N/A'),
                'opportunity_bullets_cs': candidate.get('opportunity_bullets_cs', []),
                'risk_bullets_cs': candidate.get('risk_bullets_cs', []),
                # NEW: Farm brief (EN) for clipboard
                'farm_brief_en': candidate.get('farm_brief_en', ''),
                'signals': {
                    'google_trends': {
                        'status': trends_signal.get('status'),
                        'score': int(trends_score),
                        'note': trends_signal.get('note', ''),
                        'label': trends_interp['label'],
                        'trend_label': trends_interp['trend_label'],
                        'interpretation': trends_interp['interpretation']
                    },
                    'wikipedia': {
                        'status': wiki_signal.get('status'),
                        'score': int(wiki_score),
                        'note': wiki_signal.get('note', ''),
                        'page_title': wiki_signal.get('metadata', {}).get('page_title'),
                        'delta_pct': wiki_signal.get('metadata', {}).get('delta_pct'),
                        'label': wiki_interp['label'],
                        'trend_label': wiki_interp['trend_label'],
                        'interpretation': wiki_interp['interpretation'],
                        'verdict_cs': wiki_interp['verdict_cs'],
                        'interpretation_cs': wiki_interp['interpretation_cs']
                    },
                    'youtube': {
                        'status': youtube_signal.get('status'),
                        'score': int(youtube_score),
                        'note': youtube_signal.get('note', ''),
                        'recent_videos_count': yt_metadata.get('recent_videos_count'),
                        'dominated_by_large_channels': yt_metadata.get('dominated_by_large_channels', False),
                        'label': yt_interp['label'],
                        'trend_label': yt_interp['trend_label'],
                        'interpretation': yt_interp['interpretation'],
                        'verdict_cs': yt_interp['verdict_cs'],
                        'interpretation_cs': yt_interp['interpretation_cs']
                    }
                },
                'competition_flags': competition_flags,
                'sources': self._collect_sources(signals)
            }
            
            scored.append(scored_candidate)
        
        return scored
    
    def _calculate_retention_fit(self, candidate: Dict[str, Any]) -> int:
        """
        Calculate retention fit based on archetype keywords.
        Heuristic: check if topic/angle mentions archetype keywords.
        """
        topic = candidate.get('topic', '').lower()
        angle = candidate.get('suggested_angle', '').lower()
        combined = f"{topic} {angle}"
        
        # Keyword matches
        score = 50  # Base score
        
        # High-retention keywords
        thriller_keywords = ['last', 'final', 'hours', 'days', 'betrayal', 'conspiracy', 'mystery', 'vanished', 'disaster', 'trial', 'execution', 'scandal', 'forbidden', 'hidden', 'untold']
        matches = sum(1 for kw in thriller_keywords if kw in combined)
        
        score += min(50, matches * 10)  # Up to +50 for keyword matches
        
        return min(100, score)
    
    def _refine_why_now(self, candidate: Dict[str, Any], wiki_signal: Dict[str, Any]) -> str:
        """
        Refine 'why_now' based on actual signal data.
        """
        draft = candidate.get('why_now_draft', '')
        
        # If Wikipedia shows strong growth, emphasize it
        wiki_meta = wiki_signal.get('metadata', {})
        delta = wiki_meta.get('delta_pct', 0)
        
        if delta > 20:
            return f"Surging interest ({delta:+.0f}% Wikipedia growth). {draft}"
        elif delta > 5:
            return f"Growing momentum in search. {draft}"
        else:
            return draft if draft else "Timeless topic with proven appeal"
    
    def _collect_sources(self, signals: Dict[str, Any]) -> List[str]:
        """
        Collect source URLs from signals.
        """
        sources = []
        
        # Wikipedia URL
        wiki_meta = signals.get('wikipedia', {}).get('metadata', {})
        wiki_url = wiki_meta.get('url')
        if wiki_url:
            sources.append(wiki_url)
        
        return sources
    
    def _select_top_n(self, scored_candidates: List[Dict[str, Any]], n: int) -> List[Dict[str, Any]]:
        """
        Select top N candidates by score.
        """
        # Sort by score descending
        sorted_candidates = sorted(scored_candidates, key=lambda x: x['score_total'], reverse=True)
        
        # Return top N
        return sorted_candidates[:n]
    
    # =========================================================================
    # DETERMINISTIC INTERPRETATION METHODS (no LLM calls)
    # =========================================================================
    
    def _interpret_wikipedia(self, signal: Dict[str, Any]) -> Dict[str, str]:
        """
        Generate human-readable interpretation for Wikipedia signal.
        Includes Czech verdict and interpretation.
        """
        status = signal.get('status', 'no_data')
        metadata = signal.get('metadata', {})
        
        if status != 'ok':
            return {
                'label': 'No data available',
                'trend_label': '',
                'interpretation': 'Wikipedia data not available for this topic.',
                'verdict_cs': 'Neznámé ❓',
                'interpretation_cs': 'Wikipedia data nejsou dostupná pro toto téma.'
            }
        
        total_views = metadata.get('total_views', 0)
        delta_pct = metadata.get('delta_pct', 0)
        page_title = metadata.get('page_title', 'Unknown')
        
        # Format views label
        if total_views >= 1000000:
            views_str = f"{total_views/1000000:.1f}M"
        elif total_views >= 1000:
            views_str = f"{total_views/1000:.1f}k"
        else:
            views_str = str(total_views)
        
        label = f"Baseline interest: {views_str} views"
        
        # Trend label
        if delta_pct > 0:
            trend_label = f"Trend: up {delta_pct:+.0f}%"
        elif delta_pct < 0:
            trend_label = f"Trend: down {delta_pct:.0f}%"
        else:
            trend_label = "Trend: stable"
        
        # Determine baseline level
        if total_views >= 30000:
            baseline = 'high'
        elif total_views >= 10000:
            baseline = 'medium'
        else:
            baseline = 'low'
        
        # Determine trend direction
        if delta_pct >= 10:
            trend = 'up'
        elif delta_pct <= -10:
            trend = 'down'
        else:
            trend = 'flat'
        
        # Czech verdict + interpretation (deterministic logic)
        verdict_cs = ''
        interpretation_cs = ''
        
        if baseline == 'high':
            if trend == 'down':
                verdict_cs = 'Silné ✅'
                interpretation_cs = f"Zájem je pořád vysoký ({views_str}/7 dní), jen teď krátkodobě klesá — evergreen téma, stačí fresh angle."
            else:  # flat or up
                verdict_cs = 'Silné ✅'
                if trend == 'up':
                    interpretation_cs = f"Vysoký a rostoucí zájem ({views_str}/7 dní) — dobré načasování."
                else:
                    interpretation_cs = f"Vysoký a stabilní zájem ({views_str}/7 dní) — dobré načasování."
        
        elif baseline == 'medium':
            if trend == 'down':
                verdict_cs = 'OK ⚠️'
                interpretation_cs = f"Střední zájem ({views_str}/7 dní) a klesá — doporučeno, pokud dáme ostřejší hook a unikátní úhel."
            elif trend == 'flat':
                verdict_cs = 'OK ⚠️'
                interpretation_cs = f"Střední stabilní zájem ({views_str}/7 dní) — funguje, když bude balení (thumbnail/hook) silné."
            else:  # up
                verdict_cs = 'Silné ✅'
                interpretation_cs = f"Střední zájem roste ({views_str}/7 dní) — dobrá šance chytit momentum."
        
        else:  # low baseline
            if trend == 'up':
                verdict_cs = 'OK ⚠️'
                interpretation_cs = f"Nízký baseline ({views_str}/7 dní), ale roste — může být early trend, potřebuje výborné balení."
            else:  # down or flat
                verdict_cs = 'Slabé ❌'
                interpretation_cs = f"Nízký zájem ({views_str}/7 dní) bez růstu — spíš slabší volba, leda s výrazným reframem."
        
        # EN interpretation (keep existing logic for backwards compatibility)
        if total_views >= 50000:  # High baseline
            if delta_pct > 20:
                interpretation = "Strong baseline + rising interest—ideal timing to publish now."
            elif delta_pct > 0:
                interpretation = "High baseline with growing interest—solid evergreen potential."
            elif delta_pct > -20:
                interpretation = "Strong baseline interest despite cooling trend—good evergreen topic."
            else:
                interpretation = "High baseline but declining fast—consider a fresh angle to revive interest."
        elif total_views >= 10000:  # Medium baseline
            if delta_pct > 20:
                interpretation = "Moderate baseline + surging interest—good timing window."
            elif delta_pct > 0:
                interpretation = "Decent baseline with positive momentum."
            else:
                interpretation = "Moderate interest—may need a stronger hook or unique angle."
        else:  # Low baseline
            if delta_pct > 50:
                interpretation = "Low baseline but spiking interest—emerging topic worth watching."
            elif delta_pct > 0:
                interpretation = "Low baseline but growing—niche topic with dedicated audience."
            else:
                interpretation = "Low baseline interest—needs exceptional packaging to attract viewers."
        
        return {
            'label': label,
            'trend_label': trend_label,
            'interpretation': interpretation,
            'verdict_cs': verdict_cs,
            'interpretation_cs': interpretation_cs
        }
    
    def _interpret_youtube(self, signal: Dict[str, Any]) -> Dict[str, str]:
        """
        Generate human-readable interpretation for YouTube signal.
        Includes Czech verdict and interpretation.
        """
        status = signal.get('status', 'no_data')
        metadata = signal.get('metadata', {})
        
        if status != 'ok':
            return {
                'label': 'No data available',
                'trend_label': '',
                'interpretation': 'YouTube competition data not available.',
                'verdict_cs': 'Neznámé ❓',
                'interpretation_cs': 'YouTube data nejsou dostupná.'
            }
        
        recent_count = metadata.get('recent_videos_count', 0)
        dominated = metadata.get('dominated_by_large_channels', False)
        competition_level = metadata.get('competition_level', 'Unknown')
        
        # Competition label
        if recent_count == 0:
            label = "Competition: none (0 recent videos)"
        elif recent_count <= 5:
            label = f"Competition: very low ({recent_count} recent videos)"
        elif recent_count <= 20:
            label = f"Competition: low ({recent_count} recent videos)"
        elif recent_count <= 50:
            label = f"Competition: moderate ({recent_count} recent videos)"
        else:
            label = f"Competition: high ({recent_count}+ recent videos)"
        
        # Freshness label
        if recent_count <= 5:
            trend_label = "Freshness: wide open—few recent uploads"
        elif recent_count <= 20:
            trend_label = "Freshness: room to compete"
        else:
            trend_label = "Freshness: crowded—many recent uploads"
        
        # Czech verdict + interpretation (deterministic)
        verdict_cs = ''
        interpretation_cs = ''
        
        if recent_count <= 3:  # Very low
            verdict_cs = 'Silné ✅'
            interpretation_cs = f"Konkurence je nízká ({recent_count} videí/7 dní) — velký prostor prorazit, když bude dobrý thumbnail + hook."
        elif recent_count <= 15:  # Low
            verdict_cs = 'Silné ✅'
            interpretation_cs = f"Konkurence je nízká ({recent_count} videí/7 dní) — velký prostor prorazit, když bude dobrý thumbnail + hook."
        elif recent_count <= 40:  # Medium
            verdict_cs = 'OK ⚠️'
            interpretation_cs = f"Konkurence je střední ({recent_count} videí/7 dní) — vyhraje unikátní angle a lepší balení než průměr."
        else:  # High
            verdict_cs = 'Slabé ❌'
            interpretation_cs = f"Téma je přeplněné ({recent_count} videí/7 dní) — bez extrémně unikátního úhlu bude těžké vyhrát."
        
        # Add mega channel warning if applicable
        if dominated and recent_count <= 40:
            interpretation_cs += " Pozor: dominují velké kanály — bude těžší získat doporučování."
        
        # EN interpretation (keep existing logic for backwards compatibility)
        if recent_count <= 5:
            if dominated:
                interpretation = "Very low competition but dominated by big channels—unique angle needed to stand out."
            else:
                interpretation = "Wide open opportunity—very few recent videos, high chance to rank if hook is strong."
        elif recent_count <= 20:
            if dominated:
                interpretation = "Low competition but big channels present—differentiation is key."
            else:
                interpretation = "Good opportunity—low competition with room to rank in recommendations."
        elif recent_count <= 50:
            if dominated:
                interpretation = "Moderate competition with big players—needs exceptional packaging to compete."
            else:
                interpretation = "Moderate competition—a strong thumbnail and hook can still break through."
        else:
            if dominated:
                interpretation = "Crowded and dominated by mega-channels—very hard to break in without unique angle."
            else:
                interpretation = "Crowded topic—needs a truly unique angle and exceptional packaging."
        
        return {
            'label': label,
            'trend_label': trend_label,
            'interpretation': interpretation,
            'verdict_cs': verdict_cs,
            'interpretation_cs': interpretation_cs
        }
    
    def _interpret_trends(self, signal: Dict[str, Any]) -> Dict[str, str]:
        """
        Generate human-readable interpretation for Google Trends signal.
        """
        status = signal.get('status', 'no_data')
        
        if status != 'ok':
            return {
                'label': 'Not configured',
                'trend_label': '',
                'interpretation': 'Google Trends signal not available yet; recommendation relies on Wikipedia + YouTube data.',
                'verdict_cs': 'N/A',
                'interpretation_cs': 'Google Trends zatím není dostupné.'
            }
        
        # When implemented, add proper interpretation here
        score = signal.get('score', 0)
        return {
            'label': f'Search interest: {score}/100',
            'trend_label': 'Trend data available',
            'interpretation': 'Google Trends data available for this topic.',
            'verdict_cs': 'N/A',
            'interpretation_cs': 'Google Trends data jsou dostupná.'
        }
    
    def _generate_recommendation_summary(self, wiki_signal: Dict[str, Any], 
                                         yt_signal: Dict[str, Any],
                                         trends_signal: Dict[str, Any],
                                         final_score: float) -> str:
        """
        Generate a one-sentence recommendation summary based on signals.
        """
        reasons = []
        
        # Wikipedia assessment
        wiki_status = wiki_signal.get('status', 'no_data')
        if wiki_status == 'ok':
            wiki_meta = wiki_signal.get('metadata', {})
            views = wiki_meta.get('total_views', 0)
            delta = wiki_meta.get('delta_pct', 0)
            
            if views >= 50000:
                reasons.append("strong baseline interest")
            elif views >= 10000:
                reasons.append("moderate baseline interest")
            
            if delta > 20:
                reasons.append("rising search interest")
            elif delta > 0:
                reasons.append("positive momentum")
        
        # YouTube assessment
        yt_status = yt_signal.get('status', 'no_data')
        if yt_status == 'ok':
            yt_meta = yt_signal.get('metadata', {})
            count = yt_meta.get('recent_videos_count', 0)
            dominated = yt_meta.get('dominated_by_large_channels', False)
            
            if count <= 5:
                reasons.append("very low competition")
            elif count <= 20:
                reasons.append("low competition")
            
            if not dominated and count <= 20:
                reasons.append("no mega-channel dominance")
        
        # Build summary
        if not reasons:
            if final_score >= 50:
                return "Recommended based on channel profile fit and archetype match."
            else:
                return "Limited signal data available; recommendation based on profile fit."
        
        reasons_str = " + ".join(reasons)
        return f"Recommended because: {reasons_str}."
    
    def _generate_opportunity_risk(self, wiki_signal: Dict[str, Any],
                                   yt_signal: Dict[str, Any], 
                                   trends_signal: Dict[str, Any],
                                   candidate: Dict[str, Any]) -> tuple:
        """
        Generate opportunity and risk bullet points.
        Returns: (opportunity_bullets, risk_bullets)
        """
        opportunities = []
        risks = []
        
        # Wikipedia-based
        wiki_status = wiki_signal.get('status', 'no_data')
        if wiki_status == 'ok':
            wiki_meta = wiki_signal.get('metadata', {})
            views = wiki_meta.get('total_views', 0)
            delta = wiki_meta.get('delta_pct', 0)
            
            if views >= 50000:
                opportunities.append("High baseline interest—proven audience exists")
            elif views >= 10000:
                opportunities.append("Moderate existing audience to tap into")
            else:
                risks.append("Low baseline interest—may need broader appeal")
            
            if delta > 20:
                opportunities.append("Rising interest—good timing window")
            elif delta < -20:
                risks.append("Declining interest—consider fresh angle")
        else:
            risks.append("No Wikipedia data—harder to validate demand")
        
        # YouTube-based
        yt_status = yt_signal.get('status', 'no_data')
        if yt_status == 'ok':
            yt_meta = yt_signal.get('metadata', {})
            count = yt_meta.get('recent_videos_count', 0)
            dominated = yt_meta.get('dominated_by_large_channels', False)
            
            if count <= 5:
                opportunities.append("Very low competition—easy to rank")
            elif count <= 20:
                opportunities.append("Low competition—good chance to rank")
            elif count > 50:
                risks.append("Crowded topic—needs unique angle")
            
            if dominated:
                risks.append("Dominated by big channels—harder to break in")
            elif count <= 20:
                opportunities.append("No mega-channel dominance")
        else:
            risks.append("No YouTube data—competition unknown")
        
        # Profile fit
        topic = candidate.get('topic', '')
        angle = candidate.get('suggested_angle', '')
        if any(kw in topic.lower() or kw in angle.lower() for kw in ['mystery', 'disappear', 'vanish', 'trial', 'scandal']):
            opportunities.append("Strong retention archetype match")
        
        # Limit bullets
        opportunities = opportunities[:3]
        risks = risks[:3]
        
        # Ensure at least one of each if possible
        if not opportunities:
            opportunities.append("Fits channel profile")
        if not risks:
            risks.append("No major risks identified")
        
        return opportunities, risks
    
    # =========================================================================
    # GATE FILTERING & MODE-SPECIFIC LOGIC
    # =========================================================================
    
    def _apply_gates_and_split(self, scored_candidates: List[Dict[str, Any]], 
                                count: int, mode: str) -> tuple:
        """
        Apply gate filters based on recommendation mode and split into TOP / Other Ideas.
        
        Args:
            scored_candidates: All scored candidates
            count: Requested number of TOP recommendations
            mode: 'momentum', 'balanced', or 'evergreen'
        
        Returns:
            (top_recommendations, other_ideas)
        """
        top_passed = []
        other = []
        
        for candidate in scored_candidates:
            raw = candidate.get('_raw_signal_data', {})
            wiki_views = raw.get('wiki_views', 0)
            wiki_delta_pct = raw.get('wiki_delta_pct', 0)
            yt_recent = raw.get('yt_recent_count', 0)
            yt_dominated = raw.get('yt_dominated', False)
            
            # Categorize
            wiki_baseline = 'high' if wiki_views >= 30000 else 'medium' if wiki_views >= 10000 else 'low'
            wiki_trend = 'up' if wiki_delta_pct >= 10 else 'flat' if wiki_delta_pct > -10 else 'crash' if wiki_delta_pct <= -30 else 'down'
            yt_competition = 'very_low' if yt_recent <= 3 else 'low' if yt_recent <= 15 else 'medium' if yt_recent <= 40 else 'high'
            
            # Apply gate logic
            passed_gate = False
            gate_reason = ''
            
            if mode == 'momentum':
                # Gate A: wiki_trend Up + wiki_views Medium/High + yt_competition not High
                if wiki_trend == 'up' and wiki_baseline in ['medium', 'high'] and yt_competition != 'high':
                    passed_gate = True
                    gate_reason = 'MOMENTUM_A'
                # Gate B: wiki_trend Flat + wiki_views High + yt_competition Low/Very Low
                elif wiki_trend == 'flat' and wiki_baseline == 'high' and yt_competition in ['low', 'very_low']:
                    passed_gate = True
                    gate_reason = 'MOMENTUM_B'
                # Gate C: yt_competition Very Low + wiki_views Medium+ + wiki_trend not Crash
                elif yt_competition == 'very_low' and wiki_baseline in ['medium', 'high'] and wiki_trend != 'crash':
                    passed_gate = True
                    gate_reason = 'MOMENTUM_C'
                
                # Hard rejects for momentum
                if wiki_trend == 'crash':
                    passed_gate = False
                    gate_reason = 'REJECTED_CRASH'
                if yt_competition == 'high' and wiki_trend != 'up':
                    passed_gate = False
                    gate_reason = 'REJECTED_HIGH_COMP'
                if yt_dominated and wiki_trend != 'up':
                    passed_gate = False
                    gate_reason = 'REJECTED_DOMINATED'
            
            elif mode == 'balanced':
                # Gate A: wiki_views High + yt_competition Low/Very Low
                if wiki_baseline == 'high' and yt_competition in ['low', 'very_low']:
                    passed_gate = True
                    gate_reason = 'BALANCED_A'
                # Gate B: wiki_trend Up + wiki_views Medium+
                elif wiki_trend == 'up' and wiki_baseline in ['medium', 'high']:
                    passed_gate = True
                    gate_reason = 'BALANCED_B'
                # Gate C: yt_competition Very Low + wiki_views Medium+
                elif yt_competition == 'very_low' and wiki_baseline in ['medium', 'high']:
                    passed_gate = True
                    gate_reason = 'BALANCED_C'
                
                # Hard reject for balanced
                if wiki_trend == 'crash' and wiki_baseline != 'high':
                    passed_gate = False
                    gate_reason = 'REJECTED_CRASH'
            
            else:  # evergreen
                # Gate A: yt_competition Low/Very Low + wiki_views Medium+
                if yt_competition in ['low', 'very_low'] and wiki_baseline in ['medium', 'high']:
                    passed_gate = True
                    gate_reason = 'EVERGREEN_A'
                # Gate B: wiki_views High + yt_competition not High
                elif wiki_baseline == 'high' and yt_competition != 'high':
                    passed_gate = True
                    gate_reason = 'EVERGREEN_B'
                
                # Hard reject for evergreen
                if wiki_baseline == 'low' and yt_competition != 'very_low':
                    passed_gate = False
                    gate_reason = 'REJECTED_LOW_BASELINE'
            
            # Store gate metadata
            candidate['_gate_passed'] = passed_gate
            candidate['_gate_reason'] = gate_reason
            candidate['_mode_tag'] = mode.upper()
            
            if passed_gate:
                top_passed.append(candidate)
            else:
                other.append(candidate)
        
        # Sort both lists by score
        top_passed.sort(key=lambda x: x['score_total'], reverse=True)
        other.sort(key=lambda x: x['score_total'], reverse=True)
        
        # If TOP has fewer than requested, fill from other (with lower threshold)
        if len(top_passed) < count:
            needed = count - len(top_passed)
            print(f"⚠️  Gate passed only {len(top_passed)}/{count} - doplňování z Other...")
            
            # FIX: Snížený threshold z 50 na 30, aby systém dokázal vrátit požadovaný počet
            # Pokud ani to nestačí, bereme všechny zbývající (seřazené od nejlepšího)
            fillable = [c for c in other if c['score_total'] >= 30]
            if len(fillable) < needed:
                print(f"   Threshold 30+ má jen {len(fillable)} kandidátů, bereme všechny z Other")
                # Pokud stále nemáme dost, přidáme i ty s nejnižším score
                fillable = other  # Už jsou seřazené od nejvyššího score
            
            actually_added = min(len(fillable), needed)
            top_passed.extend(fillable[:needed])
            other = [c for c in other if c not in top_passed]
            print(f"   ✅ Doplněno {actually_added} kandidátů (finální TOP: {len(top_passed)})")
            
            if len(top_passed) < count:
                print(f"   ⚠️  WARNING: Nedostatek kandidátů! Požadováno {count}, dostupných pouze {len(top_passed)}")
                print(f"      Zvažte snížení počtu nebo změnu recommendation_mode")

        
        # Limit TOP to requested count
        top_recommendations = top_passed[:count]
        
        # Final validation - pokud stále nemáme požadovaný počet
        if len(top_recommendations) < count:
            print(f"   ⚠️  NEDOSTATEK KANDIDÁTŮ: Vráceno {len(top_recommendations)}/{count} doporučení")
            print(f"      Důvod: Nedostatek high-quality kandidátů po filtrování")
        
        # Clean up internal fields before returning
        for item in top_recommendations + other:
            item.pop('_raw_signal_data', None)
        
        return top_recommendations, other


