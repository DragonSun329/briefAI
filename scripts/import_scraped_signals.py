# -*- coding: utf-8 -*-
"""Import scraped signals from today into briefAI database."""

import sys
import json
from pathlib import Path
from datetime import datetime, timezone
import uuid

sys.path.insert(0, str(Path(__file__).parent.parent))

from utils.signal_store import SignalStore
from utils.signal_models import EntityType, SignalCategory, SignalObservation, SignalScore


def import_tech_news(store: SignalStore, date_str: str):
    """Import tech news signals."""
    print("Importing tech news signals...")
    
    news_file = Path(f"data/news_signals/tech_news_{date_str}.json")
    if not news_file.exists():
        print(f"  File not found: {news_file}")
        return 0
    
    with open(news_file, encoding="utf-8") as f:
        data = json.load(f)
    
    added = 0
    skipped = 0
    
    for article in data["articles"][:50]:  # Top 50
        # Extract entities from article
        entities = extract_entities_from_title(article["title"])
        
        for entity_name in entities:
            try:
                entity = store.get_or_create_entity(
                    name=entity_name,
                    entity_type=EntityType.COMPANY
                )
                
                obs = SignalObservation(
                    id=str(uuid.uuid4()),
                    entity_id=entity.id,
                    source_id=f"news_{article['source_id']}",
                    category=SignalCategory.MEDIA_SENTIMENT,
                    observed_at=datetime.now(timezone.utc),
                    data_timestamp=datetime.now(timezone.utc),
                    raw_value=5.0 + (article["ai_relevance_score"] * 4),
                    raw_value_unit="relevance",
                    raw_data={
                        "source": article["source"],
                        "headline": article["title"],
                        "url": article["url"],
                        "ai_relevance": article["ai_relevance_score"],
                        "signal_type": "news_coverage",
                    },
                    confidence=min(0.6 + article["ai_relevance_score"] * 0.3, 0.95),
                )
                
                result = store.add_observation(obs)
                if result:
                    added += 1
                    store.add_score(SignalScore(
                        id=str(uuid.uuid4()),
                        observation_id=obs.id,
                        entity_id=entity.id,
                        source_id=f"news_{article['source_id']}",
                        category=SignalCategory.MEDIA_SENTIMENT,
                        score=(5.0 + article["ai_relevance_score"] * 4) * 10,
                    ))
                else:
                    skipped += 1
            except Exception as e:
                print(f"    Error: {e}")
    
    print(f"  Tech news: {added} imported, {skipped} deduped")
    return added


def import_newsletters(store: SignalStore, date_str: str):
    """Import newsletter signals."""
    print("Importing newsletter signals...")
    
    news_file = Path(f"data/newsletter_signals/newsletters_{date_str}.json")
    if not news_file.exists():
        print(f"  File not found: {news_file}")
        return 0
    
    with open(news_file, encoding="utf-8") as f:
        data = json.load(f)
    
    added = 0
    skipped = 0
    
    for post in data["posts"][:50]:
        try:
            entity_name = post["author"] if post["author"] != "Community" else post["source"]
            entity = store.get_or_create_entity(
                name=entity_name,
                entity_type=EntityType.PERSON if post["author"] != "Community" else EntityType.COMPANY
            )
            
            influence = post.get("influence_score", 0.7)
            
            obs = SignalObservation(
                id=str(uuid.uuid4()),
                entity_id=entity.id,
                source_id=f"newsletter_{post['source_id']}",
                category=SignalCategory.MEDIA_SENTIMENT,
                observed_at=datetime.now(timezone.utc),
                data_timestamp=datetime.now(timezone.utc),
                raw_value=5.0 + influence * 4,
                raw_value_unit="influence",
                raw_data={
                    "source": post["source"],
                    "headline": post["title"],
                    "url": post["url"],
                    "author": post["author"],
                    "influence_score": influence,
                    "signal_type": "thought_leadership",
                },
                confidence=0.7 + influence * 0.2,
            )
            
            result = store.add_observation(obs)
            if result:
                added += 1
                store.add_score(SignalScore(
                    id=str(uuid.uuid4()),
                    observation_id=obs.id,
                    entity_id=entity.id,
                    source_id=f"newsletter_{post['source_id']}",
                    category=SignalCategory.MEDIA_SENTIMENT,
                    score=(5.0 + influence * 4) * 10,
                ))
            else:
                skipped += 1
        except Exception as e:
            print(f"    Error: {e}")
    
    print(f"  Newsletters: {added} imported, {skipped} deduped")
    return added


def extract_entities_from_title(title: str):
    """Extract company/product entities from title."""
    known_entities = [
        "OpenAI", "Anthropic", "Google", "Meta", "Microsoft", "NVIDIA",
        "AMD", "Apple", "Amazon", "Tesla", "Palantir", "Snowflake",
        "DeepMind", "Stability AI", "Midjourney", "Hugging Face",
        "Databricks", "Scale AI", "Cohere", "AI21", "Inflection",
        "xAI", "Mistral", "Perplexity", "Character.AI",
        "ChatGPT", "Claude", "Gemini", "GPT-4", "GPT-5", "Llama",
        "Copilot", "Bard", "Grok", "DeepSeek",
    ]
    
    found = []
    title_lower = title.lower()
    
    for entity in known_entities:
        if entity.lower() in title_lower:
            found.append(entity)
    
    return found if found else ["AI Industry"]


def main():
    """Import all scraped signals."""
    print("=" * 60)
    print("IMPORTING SCRAPED SIGNALS TO BRIEFAI")
    print("=" * 60)
    
    store = SignalStore()
    date_str = datetime.now().strftime("%Y-%m-%d")
    
    total = 0
    total += import_tech_news(store, date_str)
    total += import_newsletters(store, date_str)
    
    print("\n" + "=" * 60)
    print(f"Total signals imported: {total}")
    print("Run `python scripts/rebuild_profiles.py` to update radar.")


if __name__ == "__main__":
    main()
