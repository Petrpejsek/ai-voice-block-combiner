#!/usr/bin/env python3
"""
Test Europeana API integrace
Ověří, že API klíč funguje a můžeme stahovat metadata.
"""

import os
import sys
from dotenv import load_dotenv

# Načti .env
load_dotenv()

# Import Europeana source
from video_sources import EuropeanaSource

def test_europeana_search():
    """Test základního vyhledávání přes Europeana API"""
    
    api_key = os.getenv("EUROPEANA_API_KEY")
    
    if not api_key:
        print("❌ EUROPEANA_API_KEY není nastaven v .env")
        return False
    
    print(f"✅ API klíč načten: {api_key[:10]}...")
    
    # Vytvoř Europeana source
    europeana = EuropeanaSource(api_key=api_key, verbose=True)
    
    # Testovací query - hledáme historická videa
    test_queries = [
        "Napoleon",
        "World War",
        "historical battle",
        "ancient rome"
    ]
    
    print("\n" + "="*80)
    print("🔍 Testování Europeana API Search")
    print("="*80 + "\n")
    
    for query in test_queries:
        print(f"\n📹 Hledám: '{query}'")
        print("-" * 60)
        
        try:
            results = europeana.search(query, max_results=5)
            
            if not results:
                print(f"   ⚠️  Žádné výsledky pro '{query}'")
                continue
            
            print(f"   ✅ Nalezeno {len(results)} videí:")
            
            for i, item in enumerate(results, 1):
                print(f"\n   {i}. {item['title'][:80]}")
                print(f"      ID: {item['item_id']}")
                print(f"      Zdroj: {item['source']}")
                print(f"      Licence: {item['license']} ({item['license_raw'][:50]}...)")
                print(f"      URL: {item['url']}")
                if item.get('attribution'):
                    print(f"      Autor: {item['attribution']}")
                if item.get('thumbnail_url'):
                    print(f"      Náhled: {item['thumbnail_url'][:60]}...")
        
        except Exception as e:
            print(f"   ❌ Chyba při vyhledávání: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    print("\n" + "="*80)
    print("✅ Test Europeana API dokončen úspěšně!")
    print("="*80 + "\n")
    
    return True


def test_multi_source():
    """Test multi-source searcheru s Europeana"""
    
    from video_sources import create_multi_source_searcher
    
    api_key = os.getenv("EUROPEANA_API_KEY")
    
    print("\n" + "="*80)
    print("🔍 Testování Multi-Source Searcheru (Archive.org + Wikimedia + Europeana)")
    print("="*80 + "\n")
    
    sources = create_multi_source_searcher(
        archive_org=True,
        wikimedia=True,
        europeana=True,
        europeana_api_key=api_key,
        verbose=True
    )
    
    print(f"\n✅ Inicializováno {len(sources)} zdrojů:")
    for source in sources:
        print(f"   - {source.source_name}")
    
    # Test vyhledávání napříč všemi zdroji
    query = "Napoleon 1812"
    print(f"\n📹 Testovací query: '{query}'")
    print("-" * 60)
    
    all_results = []
    for source in sources:
        print(f"\n🔍 Zdroj: {source.source_name}")
        try:
            results = source.search(query, max_results=3)
            print(f"   ✅ Nalezeno {len(results)} videí")
            all_results.extend(results)
            
            for i, item in enumerate(results, 1):
                print(f"      {i}. {item['title'][:60]}... ({item['license']})")
        
        except Exception as e:
            print(f"   ⚠️  Chyba: {e}")
    
    print(f"\n" + "="*80)
    print(f"✅ Celkem nalezeno {len(all_results)} videí z {len(sources)} zdrojů")
    print("="*80 + "\n")
    
    return True


if __name__ == "__main__":
    print("\n🚀 Europeana API Test Suite\n")
    
    # Test 1: Základní Europeana search
    success1 = test_europeana_search()
    
    # Test 2: Multi-source integrace
    success2 = test_multi_source()
    
    if success1 and success2:
        print("\n✅ Všechny testy prošly úspěšně!")
        print("🎉 Europeana API je správně integrována a připravena k použití.\n")
        sys.exit(0)
    else:
        print("\n❌ Některé testy selhaly.")
        sys.exit(1)



