import tempfile


def test_aar_anchor_match_rejects_modern_when_strong_scene_anchors_present():
    """
    Regression: beat-level text can be generic ("Russian sabotage") and previously allowed modern items.
    With strong scene anchors present (Napoleon/Moscow/1812), we must NOT pass on generic-only matches.
    """
    from archive_asset_resolver import ArchiveAssetResolver

    with tempfile.TemporaryDirectory() as td:
        r = ArchiveAssetResolver(cache_dir=td, throttle_delay_sec=0.0, verbose=False)

        # Modern-ish asset haystack (no Napoleon/Moscow/1812)
        haystack = r._normalize_text("MoD Russia August 14th 2023 1700hrs")
        narration = r._normalize_text("Fires were attributed to Russian sabotage during the occupation.")

        keywords = [
            "russian",
            "sabotage",
            "occupation",
            # Strong anchors from scene context:
            "napoleon",
            "moscow",
            "1812",
        ]

        ok, details = r._check_anchor_match_v2(haystack, narration, keywords, query_used="russian sabotage")
        assert ok is False, details
        assert details.get("mode") == "strong_anchors"


def test_aar_anchor_match_accepts_when_multiple_strong_anchors_match():
    from archive_asset_resolver import ArchiveAssetResolver

    with tempfile.TemporaryDirectory() as td:
        r = ArchiveAssetResolver(cache_dir=td, throttle_delay_sec=0.0, verbose=False)

        haystack = r._normalize_text("Napoleon Moscow 1812 documentary")
        narration = r._normalize_text("Napoleon waited in ruined Moscow in 1812.")
        keywords = ["napoleon", "moscow", "1812", "ruins", "documents"]

        ok, details = r._check_anchor_match_v2(haystack, narration, keywords, query_used="napoleon moscow 1812")
        assert ok is True, details
        assert details.get("mode") == "strong_anchors"


def test_aar_anchor_match_allows_weak_only_when_no_strong_exists():
    from archive_asset_resolver import ArchiveAssetResolver

    with tempfile.TemporaryDirectory() as td:
        r = ArchiveAssetResolver(cache_dir=td, throttle_delay_sec=0.0, verbose=False)

        haystack = r._normalize_text("russian sabotage report occupation")
        narration = r._normalize_text("Russian sabotage occurred.")
        keywords = ["russian", "sabotage"]

        ok, details = r._check_anchor_match_v2(haystack, narration, keywords, query_used="russian sabotage")
        # Policy hardening: weak anchors alone are NOT sufficient (prevents off-topic contamination).
        assert ok is False, details
        assert details.get("mode") in ("weak_anchors_only_insufficient", "no_anchor_match")


