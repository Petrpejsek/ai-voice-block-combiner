#!/usr/bin/env python3
"""
Test script pro LLM-based Topic Relevance Validation (v14).

Ověřuje, že AAR správně odmítá off-topic kandidáty jako:
- "maxwell-chikumbutso-new-energy-zimbabwe" pro téma "Nikola Tesla"
- Africké zpravodajství pro téma o historických vynálezcích
"""

import os
import sys

# Přidej backend do path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Load environment variables from .env
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

from archive_asset_resolver import validate_candidates_topic_relevance


def test_topic_validation():
    """Test that off-topic candidates are correctly rejected."""
    
    # Mock candidates - mix of relevant and irrelevant
    # Each has thumbnail_url for Vision API analysis
    candidates = [
        {
            "archive_item_id": "archive_org:IlSegretoDiNikolaTeslaFilmCompletoInItalianoHQ",
            "title": "Il Segreto Di Nikola Tesla - Film Completo In Italiano",
            "description": "Documentary about Nikola Tesla's life and inventions.",
            "thumbnail_url": "https://archive.org/services/img/IlSegretoDiNikolaTeslaFilmCompletoInItalianoHQ",
            "query_used": "Nikola Tesla documentary"
        },
        {
            "archive_item_id": "archive_org:maxwell-chikumbutso-new-energy-zimbabwe",
            "title": "Maxwell Chikumbutso - New Energy Zimbabwe",
            "description": "News report about Zimbabwean inventor Maxwell Chikumbutso and his free energy claims. ZTN News coverage.",
            "thumbnail_url": "https://archive.org/services/img/maxwell-chikumbutso-new-energy-zimbabwe",
            "query_used": "Tesla free energy"
        },
        {
            "archive_item_id": "archive_org:Killuminati_The_Infomentary",
            "title": "Killuminati - The Infomentary",
            "description": "Conspiracy theory documentary about illuminati and secret societies.",
            "thumbnail_url": "https://archive.org/services/img/Killuminati_The_Infomentary",
            "query_used": "Tesla conspiracy"
        },
        {
            "archive_item_id": "archive_org:tesla-coil-experiments",
            "title": "Tesla Coil Experiments and Demonstrations",
            "description": "Historical footage of Tesla coil experiments and electrical demonstrations from early 1900s.",
            "thumbnail_url": "https://archive.org/services/img/tesla-coil-experiments",
            "query_used": "Tesla coil historical"
        },
        {
            "archive_item_id": "archive_org:elinor-wonders-why-s01e17",
            "title": "Elinor Wonders Why - Follow That Roly Poly",
            "description": "Children's animated educational series about nature and science.",
            "thumbnail_url": "https://archive.org/services/img/elinor-wonders-why-s-01-e-17-follow-that-roly-poly-rain-rain-dont-go-away",
            "query_used": "science electricity"
        }
    ]
    
    episode_topic = "Nikola Tesla - Life and Inventions"
    
    # Scene context - what the narrator is saying in this scene
    scene_context = {
        "narration_summary": "Nikola Tesla's revolutionary inventions changed the world. His work on alternating current and wireless transmission laid the foundation for modern electrical systems.",
        "search_queries": [
            "Nikola Tesla archive photograph",
            "Tesla laboratory experiments",
            "alternating current historical footage"
        ],
        "keywords": ["Tesla", "electricity", "invention", "AC current", "wireless"],
        "emotion": "inspirational"
    }
    
    print(f"🧪 Testing Topic Relevance Validation")
    print(f"   Episode Topic: '{episode_topic}'")
    print(f"   Scene Narration: '{scene_context['narration_summary'][:80]}...'")
    print(f"   Candidates: {len(candidates)}")
    print()
    
    # Check if API key is available (prefer OpenRouter)
    if not os.getenv("OPENROUTER_API_KEY") and not os.getenv("OPENAI_API_KEY"):
        print("❌ No API key set - skipping live test")
        print("   Set OPENROUTER_API_KEY or OPENAI_API_KEY environment variable to run this test")
        return False
    
    provider = "OpenRouter" if os.getenv("OPENROUTER_API_KEY") else "OpenAI"
    print(f"   Using provider: {provider}")
    
    relevant, rejected, report = validate_candidates_topic_relevance(
        candidates=candidates,
        episode_topic=episode_topic,
        scene_context=scene_context,
        max_candidates=10,
        verbose=True,
        use_vision=True,  # Enable thumbnail analysis
    )
    
    print()
    print("=" * 60)
    print("RESULTS:")
    print("=" * 60)
    print(f"✅ Relevant: {len(relevant)}")
    for r in relevant:
        print(f"   - {r.get('archive_item_id')}")
    
    print(f"\n❌ Rejected: {len(rejected)}")
    for r in rejected:
        reason = r.get("_topic_validation", {}).get("reason", "")
        print(f"   - {r.get('archive_item_id')}")
        print(f"     Reason: {reason}")
    
    print(f"\n📊 Validation Report:")
    for k, v in report.items():
        print(f"   {k}: {v}")
    
    # Assertions
    expected_rejected_ids = {
        "archive_org:maxwell-chikumbutso-new-energy-zimbabwe",
        "archive_org:Killuminati_The_Infomentary",
        "archive_org:elinor-wonders-why-s01e17"
    }
    
    expected_relevant_ids = {
        "archive_org:IlSegretoDiNikolaTeslaFilmCompletoInItalianoHQ",
        "archive_org:tesla-coil-experiments"
    }
    
    rejected_ids = {r.get("archive_item_id") for r in rejected}
    relevant_ids = {r.get("archive_item_id") for r in relevant}
    
    print()
    print("=" * 60)
    print("VALIDATION:")
    print("=" * 60)
    
    # Check Zimbabwe video was rejected
    zimbabwe_rejected = "archive_org:maxwell-chikumbutso-new-energy-zimbabwe" in rejected_ids
    print(f"✅ Zimbabwe 'free energy' video rejected: {zimbabwe_rejected}")
    
    # Check Tesla film was kept
    tesla_kept = "archive_org:IlSegretoDiNikolaTeslaFilmCompletoInItalianoHQ" in relevant_ids
    print(f"✅ Tesla documentary kept: {tesla_kept}")
    
    # Check Tesla coil experiments was kept
    coil_kept = "archive_org:tesla-coil-experiments" in relevant_ids
    print(f"✅ Tesla coil experiments kept: {coil_kept}")
    
    # Check children's show was rejected
    elinor_rejected = "archive_org:elinor-wonders-why-s01e17" in rejected_ids
    print(f"✅ Children's show rejected: {elinor_rejected}")
    
    success = zimbabwe_rejected and tesla_kept and coil_kept and elinor_rejected
    
    print()
    if success:
        print("🎉 ALL TESTS PASSED!")
    else:
        print("❌ SOME TESTS FAILED!")
    
    return success


if __name__ == "__main__":
    success = test_topic_validation()
    sys.exit(0 if success else 1)

