import sqlite3, json, os, glob
from datetime import datetime, timedelta
from pathlib import Path

# === 1. CLEAN PREDICTIONS TABLE ===
print("=== CLEANING PREDICTIONS ===")
conn = sqlite3.connect("data/predictions.db")
c = conn.cursor()

# What's there
c.execute("SELECT prediction_type, predicted_outcome, COUNT(*) FROM predictions GROUP BY prediction_type, predicted_outcome")
for row in c.fetchall():
    print(f"  {row[0]}: {row[1][:50]} ({row[2]})")

c.execute("SELECT COUNT(*) FROM predictions WHERE status='pending'")
pending = c.fetchone()[0]
print(f"Pending: {pending}")

# Delete all the generic "bullish" predictions
c.execute("DELETE FROM predictions WHERE predicted_outcome = 'bullish'")
deleted = c.rowcount
print(f"Deleted {deleted} 'bullish' predictions")

# Check what's left
c.execute("SELECT COUNT(*) FROM predictions")
remaining = c.fetchone()[0]
c.execute("SELECT COUNT(*) FROM predictions WHERE status='pending'")
still_pending = c.fetchone()[0]
print(f"Remaining: {remaining} total, {still_pending} pending")

if still_pending > 0:
    c.execute("SELECT entity_name, predicted_outcome, confidence, status FROM predictions WHERE status='pending' LIMIT 10")
    for row in c.fetchall():
        print(f"  {row[0]}: {row[1][:60]} (conf={row[2]}, status={row[3]})")

conn.commit()
conn.close()

# === 2. CHECK ARTICLE DATA ===
print("\n=== ARTICLE DATA SCAN ===")
# Find today's scraped articles
data_dir = Path("data")
for pattern in ["articles_*.json", "scraped_*.json", "us_tech_news*.json", "alternative_signals/us_tech_news*.json", "alternative_signals/scraper_summary*.json"]:
    files = sorted(data_dir.glob(pattern), reverse=True)
    if files:
        for f in files[:3]:
            size = f.stat().st_size
            print(f"  {f.name}: {size/1024:.1f}KB")

# Check pipeline cache
cache_dir = data_dir / "cache"
if cache_dir.exists():
    for f in sorted(cache_dir.glob("*.json"), reverse=True)[:5]:
        print(f"  cache/{f.name}: {f.stat().st_size/1024:.1f}KB")

# Check alternative_signals for today's news
alt_dir = data_dir / "alternative_signals"
if alt_dir.exists():
    today = datetime.now().strftime("%Y-%m-%d")
    today_files = [f for f in alt_dir.glob(f"*{today.replace('-','')}*") if f.is_file()]
    print(f"\nToday's alt signal files: {len(today_files)}")
    for f in sorted(today_files):
        print(f"  {f.name}: {f.stat().st_size/1024:.1f}KB")
    
    # Check us_tech_news structure
    news_files = sorted(alt_dir.glob("us_tech_news_*.json"), reverse=True)
    if news_files:
        with open(news_files[0], "r", encoding="utf-8") as fh:
            news_data = json.load(fh)
        if isinstance(news_data, dict):
            print(f"\nus_tech_news structure: {list(news_data.keys())[:10]}")
            for k, v in list(news_data.items())[:2]:
                if isinstance(v, list):
                    print(f"  {k}: {len(v)} items")
                    if v:
                        print(f"    Sample keys: {list(v[0].keys())[:8]}")
                elif isinstance(v, dict):
                    print(f"  {k}: dict with {list(v.keys())[:5]}")
        elif isinstance(news_data, list):
            print(f"\nus_tech_news: {len(news_data)} items")
            if news_data:
                print(f"  Sample keys: {list(news_data[0].keys())[:8]}")

# === 3. CHECK HEATMAP VELOCITY DATA ===
print("\n=== VELOCITY CHECK ===")
import sys
sys.path.insert(0, ".")
from utils.entity_store import EntityStore
store = EntityStore()
for name in ["Meta", "OpenAI", "NVIDIA", "Snowflake", "Anthropic"]:
    vel = store.get_mention_velocity(name)
    print(f"  {name}: 7d={vel.get('count_7d', 0)}, 30d={vel.get('count_30d', 0)}, accel={vel.get('acceleration', 'N/A')}, diversity={vel.get('source_diversity', 0)}")
