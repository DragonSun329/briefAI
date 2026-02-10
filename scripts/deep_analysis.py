"""Deep analysis of briefAI data quality."""
import sqlite3
from pathlib import Path
from datetime import datetime, timedelta
import json
from collections import Counter

DATA_DIR = Path(__file__).parent.parent / "data"

def analyze_trend_radar():
    """Analyze trend_radar.db for issues."""
    print("\n" + "="*60)
    print("TREND RADAR ANALYSIS")
    print("="*60)
    
    conn = sqlite3.connect(DATA_DIR / "trend_radar.db")
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    # Check companies without observations
    cursor.execute("""
        SELECT COUNT(*) FROM companies c 
        LEFT JOIN observations o ON c.id = o.company_id 
        WHERE o.id IS NULL
    """)
    orphan_companies = cursor.fetchone()[0]
    print(f"\nCompanies without observations: {orphan_companies}")
    
    # Check observation age distribution
    cursor.execute("""
        SELECT 
            CASE 
                WHEN last_seen >= date('now', '-7 days') THEN 'last_7_days'
                WHEN last_seen >= date('now', '-30 days') THEN 'last_30_days'
                WHEN last_seen >= date('now', '-90 days') THEN 'last_90_days'
                ELSE 'older'
            END as age_bucket,
            COUNT(*) as count
        FROM observations
        GROUP BY age_bucket
    """)
    print("\nObservation freshness:")
    for row in cursor.fetchall():
        print(f"  {row['age_bucket']}: {row['count']}")
    
    # Check conviction scores
    cursor.execute("SELECT * FROM conviction_scores ORDER BY conviction_score DESC")
    scores = cursor.fetchall()
    print(f"\nConviction scores: {len(scores)} entities")
    for s in scores[:5]:
        print(f"  {s['entity_name']}: {s['conviction_score']:.2f} (tech={s['technical_velocity_score']:.2f}, commercial={s['commercial_maturity_score']:.2f})")
    
    # Check source coverage
    cursor.execute("""
        SELECT s.name, COUNT(o.id) as obs_count
        FROM sources s
        LEFT JOIN observations o ON s.id = o.source_id
        GROUP BY s.id
        ORDER BY obs_count DESC
    """)
    print("\nSource coverage:")
    for row in cursor.fetchall():
        print(f"  {row['name']}: {row['obs_count']} observations")
    
    conn.close()

def analyze_signals_db():
    """Analyze signals.db for data quality."""
    print("\n" + "="*60)
    print("SIGNALS DB ANALYSIS")
    print("="*60)
    
    conn = sqlite3.connect(DATA_DIR / "signals.db")
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    # Entity type distribution
    cursor.execute("""
        SELECT entity_type, COUNT(*) as count
        FROM entities
        GROUP BY entity_type
        ORDER BY count DESC
    """)
    print("\nEntity types:")
    for row in cursor.fetchall():
        print(f"  {row['entity_type'] or 'unknown'}: {row['count']}")
    
    # Signal category distribution
    cursor.execute("""
        SELECT category, COUNT(*) as count, AVG(score) as avg_score
        FROM signal_scores
        GROUP BY category
        ORDER BY count DESC
    """)
    print("\nSignal categories:")
    for row in cursor.fetchall():
        avg = row['avg_score'] or 0
        print(f"  {row['category']}: {row['count']} obs, avg_score={avg:.2f}")
    
    # Entities with highest scores
    cursor.execute("""
        SELECT entity_name, entity_type, 
               technical_score, company_score, financial_score,
               (COALESCE(technical_score, 0) + COALESCE(company_score, 0) + COALESCE(financial_score, 0)) / 3.0 as combined
        FROM signal_profiles
        ORDER BY combined DESC
        LIMIT 10
    """)
    print("\nTop entities by combined score:")
    for row in cursor.fetchall():
        tech = row['technical_score'] or 0
        company = row['company_score'] or 0
        financial = row['financial_score'] or 0
        print(f"  {row['entity_name']} ({row['entity_type']}): tech={tech:.1f}, company={company:.1f}, financial={financial:.1f}")
    
    # Divergences (interesting!)
    cursor.execute("""
        SELECT entity_name, divergence_type, 
               high_signal_category, high_signal_score,
               low_signal_category, low_signal_score
        FROM signal_divergences
        ORDER BY (high_signal_score - low_signal_score) DESC
        LIMIT 10
    """)
    print("\nTop divergences (mismatches between signal types):")
    for row in cursor.fetchall():
        gap = row['high_signal_score'] - row['low_signal_score']
        print(f"  {row['entity_name']}: {row['high_signal_category']}={row['high_signal_score']:.1f} vs {row['low_signal_category']}={row['low_signal_score']:.1f} (gap={gap:.1f})")
    
    conn.close()

def analyze_stale_signals():
    """Find stale alternative signals that need refresh."""
    print("\n" + "="*60)
    print("STALE SIGNALS (>7 days old)")
    print("="*60)
    
    signals_dir = DATA_DIR / "alternative_signals"
    today = datetime.now().date()
    stale = []
    
    for f in signals_dir.glob("*.json"):
        parts = f.stem.rsplit("_", 1)
        if len(parts) == 2:
            signal_type = parts[0]
            date_str = parts[1]
            try:
                file_date = datetime.strptime(date_str, "%Y-%m-%d").date()
                days_old = (today - file_date).days
                if days_old > 7:
                    stale.append((signal_type, date_str, days_old))
            except ValueError:
                pass
    
    stale.sort(key=lambda x: -x[2])
    for signal_type, date_str, days_old in stale:
        print(f"  {signal_type}: {days_old} days old (last: {date_str})")

def analyze_report_quality():
    """Check report quality and content."""
    print("\n" + "="*60)
    print("REPORT QUALITY CHECK")
    print("="*60)
    
    reports_dir = DATA_DIR / "reports"
    issues = []
    
    for report in sorted(reports_dir.glob("*.md"), reverse=True)[:5]:
        content = report.read_text(encoding='utf-8')
        
        # Check for common issues
        problems = []
        
        # Empty sections
        if "暂无" in content or "No articles" in content.lower():
            problems.append("has empty sections")
        
        # Very short
        if len(content) < 2000:
            problems.append("very short (<2KB)")
        
        # Missing categories
        if "##" not in content:
            problems.append("no section headers")
        
        # Count articles
        article_count = content.count("###") or content.count("**")
        if article_count < 3:
            problems.append(f"only {article_count} articles")
        
        status = "✅" if not problems else "⚠️"
        print(f"\n{status} {report.name}")
        if problems:
            for p in problems:
                print(f"   - {p}")
        else:
            print(f"   {len(content)/1024:.1f}KB, ~{article_count} articles")

def main():
    print("BRIEFAI DEEP ANALYSIS")
    print(f"Run at: {datetime.now().isoformat()}")
    
    analyze_trend_radar()
    analyze_signals_db()
    analyze_stale_signals()
    analyze_report_quality()
    
    print("\n" + "="*60)
    print("ANALYSIS COMPLETE")
    print("="*60)

if __name__ == "__main__":
    main()
