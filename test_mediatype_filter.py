#!/usr/bin/env python3
"""
Test Archive.org Mediatype Filter - Phase 1
Quick validation that mediatype filter works correctly.
"""

import sys
import os

# Add backend to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'backend'))

from video_sources import ArchiveOrgSource
from archive_asset_resolver import ArchiveAssetResolver

def test_video_source_filter():
    """Test ArchiveOrgSource mediatype filter (VIDEO context)"""
    print("=" * 60)
    print("TEST 1: ArchiveOrgSource (VIDEO context)")
    print("=" * 60)
    
    source = ArchiveOrgSource(verbose=True)
    
    # Test query that historically returns mixed results
    query = "Michael Jackson 2009"
    results = source.search(query, max_results=10)
    
    print(f"\n✅ Returned {len(results)} results")
    print("\nTop 10 results:")
    for i, item in enumerate(results[:10], 1):
        print(f"{i}. [{item.get('mediatype', 'N/A')}] {item.get('item_id', 'N/A')}")
        print(f"   Title: {item.get('title', 'N/A')[:80]}")
        if 'collection' in item and item['collection']:
            print(f"   Collection: {item['collection'][:60]}")
        print()
    
    # Validation
    errors = []
    for item in results:
        mediatype = item.get('mediatype', '')
        if not mediatype:
            errors.append(f"Missing mediatype: {item.get('item_id')}")
        elif mediatype not in ('movies', 'movingimage'):
            errors.append(f"Wrong mediatype '{mediatype}': {item.get('item_id')}")
    
    if errors:
        print("❌ VALIDATION FAILED:")
        for err in errors:
            print(f"  - {err}")
        return False
    else:
        print("✅ VALIDATION PASSED: All results have correct mediatype")
        return True

def test_aar_image_filter():
    """Test AAR mediatype filter (IMAGE context)"""
    print("\n" + "=" * 60)
    print("TEST 2: ArchiveAssetResolver (IMAGE context)")
    print("=" * 60)
    
    cache_dir = "/tmp/aar_test_cache"
    os.makedirs(cache_dir, exist_ok=True)
    
    resolver = ArchiveAssetResolver(cache_dir, verbose=True)
    
    # Test image search
    query = "Michael Jackson 2009"
    results = resolver.search_archive_org(
        query,
        max_results=10,
        mediatype_filter="image",
        media_label="image"
    )
    
    print(f"\n✅ Returned {len(results)} results")
    print("\nTop 10 results:")
    for i, item in enumerate(results[:10], 1):
        print(f"{i}. [{item.get('mediatype', 'N/A')}] {item.get('archive_item_id', 'N/A')}")
        print(f"   Title: {item.get('title', 'N/A')[:80]}")
        print()
    
    # Validation
    errors = []
    for item in results:
        mediatype = item.get('mediatype', '')
        if not mediatype:
            errors.append(f"Missing mediatype: {item.get('archive_item_id')}")
        elif mediatype != 'image':
            errors.append(f"Wrong mediatype '{mediatype}': {item.get('archive_item_id')}")
    
    if errors:
        print("❌ VALIDATION FAILED:")
        for err in errors:
            print(f"  - {err}")
        return False
    else:
        print("✅ VALIDATION PASSED: All results have correct mediatype")
        return True

if __name__ == "__main__":
    print("Archive.org Mediatype Filter - Phase 1 Test\n")
    
    test1_pass = test_video_source_filter()
    test2_pass = test_aar_image_filter()
    
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"Test 1 (VIDEO context): {'✅ PASS' if test1_pass else '❌ FAIL'}")
    print(f"Test 2 (IMAGE context): {'✅ PASS' if test2_pass else '❌ FAIL'}")
    
    if test1_pass and test2_pass:
        print("\n✅ ALL TESTS PASSED")
        sys.exit(0)
    else:
        print("\n❌ SOME TESTS FAILED")
        sys.exit(1)


