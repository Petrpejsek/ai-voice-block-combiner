"""
Query Guardrails Utilities - Single entrypoint for episode_topic validation

KONTRAKT:
- KANONICKÝ zdroj: tts_ready_package["episode_metadata"]["topic"]
- title je jen UI label, NE fallback
- Pokud chybí → hard fail
"""

from typing import Dict, Any


def get_episode_topic_strict(tts_ready_package: Dict[str, Any]) -> str:
    """
    Single entrypoint pro získání episode_topic z tts_ready_package.
    
    KRITICKÉ PRAVIDLO:
    - Jediný validní zdroj: episode_metadata["topic"]
    - title je jen UI label, nepoužívá se pro queries
    - Žádné fallbacky, heuristiky, extraction z narration
    - Pokud topic chybí nebo je prázdný → hard fail
    
    Args:
        tts_ready_package: TTS ready package s episode_metadata
    
    Returns:
        str: Episode topic (non-empty, stripped)
    
    Raises:
        ValueError: Pokud topic chybí nebo je prázdný
    """
    if not isinstance(tts_ready_package, dict):
        raise ValueError(
            "INVALID_TTS_READY_PACKAGE: tts_ready_package must be dict. "
            f"Got: {type(tts_ready_package)}"
        )
    
    episode_metadata = tts_ready_package.get("episode_metadata")
    if not isinstance(episode_metadata, dict):
        raise ValueError(
            "EPISODE_METADATA_MISSING: tts_ready_package must contain 'episode_metadata' dict. "
            f"Got: {type(episode_metadata)}"
        )
    
    # SINGLE SOURCE: episode_metadata["topic"]
    topic = episode_metadata.get("topic")
    
    if not topic:
        raise ValueError(
            "EPISODE_TOPIC_MISSING: episode_metadata must contain non-empty 'topic' field. "
            "Cannot generate anchored queries without episode topic. "
            "title field is NOT used as fallback (UI label only)."
        )
    
    # Type cast and strip
    topic_str = str(topic).strip()
    
    if not topic_str:
        raise ValueError(
            "EPISODE_TOPIC_EMPTY: episode_metadata['topic'] is empty after stripping. "
            "Provide valid topic string."
        )
    
    return topic_str


