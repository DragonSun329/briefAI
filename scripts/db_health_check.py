"""Quick database health check script."""
import sqlite3
from pathlib import Path
from datetime import datetime
import json

DATA_DIR = Path(__file__).parent.parent / "data"

def check_db(db_path):
    """Check a single database."""
    print(f"\n{'='*60}")
    print(f"DATABASE: {db_path.name}")
    print('='*60)
    
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Get tables
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [t[0] for t in cursor.fetchall()]
        print(f"Tables: {tables}")
        
        for table in tables:
            cursor.execute(f"SELECT COUNT(*) FROM {table}")
            count = cursor.fetchone()[0]
            
            # Get sample and schema
            cursor.execute(f"PRAGMA table_info({table})")
            columns = [c[1] for c in cursor.fetchall()]
            
            print(f"\n  {table}: {count} rows")
            print(f"    Columns: {columns[:8]}{'...' if len(columns) > 8 else ''}")
            
            # Check for recent data
            date_cols = [c for c in columns if 'date' in c.lower() or 'time' in c.lower() or 'created' in c.lower()]
            if date_cols and count > 0:
                try:
                    cursor.execute(f"SELECT MAX({date_cols[0]}) FROM {table}")
                    latest = cursor.fetchone()[0]
                    print(f"    Latest ({date_cols[0]}): {latest}")
                except:
                    pass
        
        conn.close()
    except Exception as e:
        print(f"  ERROR: {e}")

def check_reports():
    """Check recent reports."""
    print(f"\n{'='*60}")
    print("RECENT REPORTS")
    print('='*60)
    
    reports_dir = DATA_DIR / "reports"
    if reports_dir.exists():
        reports = sorted(reports_dir.glob("*.md"), key=lambda x: x.stat().st_mtime, reverse=True)[:10]
        for r in reports:
            size = r.stat().st_size
            mtime = datetime.fromtimestamp(r.stat().st_mtime).strftime("%Y-%m-%d %H:%M")
            print(f"  {r.name}: {size/1024:.1f}KB ({mtime})")
    else:
        print("  No reports directory")

def check_cache():
    """Check cache status."""
    print(f"\n{'='*60}")
    print("CACHE STATUS")
    print('='*60)
    
    cache_dir = DATA_DIR / "cache"
    if cache_dir.exists():
        cache_files = list(cache_dir.rglob("*"))
        files_only = [f for f in cache_files if f.is_file()]
        total_size = sum(f.stat().st_size for f in files_only)
        print(f"  Total files: {len(files_only)}")
        print(f"  Total size: {total_size/1024/1024:.1f}MB")
        
        # Check pipeline contexts
        contexts_dir = cache_dir / "pipeline_contexts"
        if contexts_dir.exists():
            contexts = list(contexts_dir.glob("*.json"))
            print(f"  Pipeline contexts: {len(contexts)}")
            for c in sorted(contexts, reverse=True)[:5]:
                print(f"    - {c.name}")
    else:
        print("  No cache directory")

def check_alternative_signals():
    """Check alternative signals freshness."""
    print(f"\n{'='*60}")
    print("ALTERNATIVE SIGNALS FRESHNESS")
    print('='*60)
    
    signals_dir = DATA_DIR / "alternative_signals"
    if signals_dir.exists():
        # Group by type
        by_type = {}
        for f in signals_dir.glob("*.json"):
            parts = f.stem.rsplit("_", 1)
            if len(parts) == 2:
                signal_type = parts[0]
                date = parts[1]
                if signal_type not in by_type:
                    by_type[signal_type] = []
                by_type[signal_type].append(date)
        
        for signal_type, dates in sorted(by_type.items()):
            dates.sort(reverse=True)
            latest = dates[0] if dates else "none"
            count = len(dates)
            print(f"  {signal_type}: {count} files, latest={latest}")
    else:
        print("  No alternative_signals directory")

def main():
    print("BRIEFAI HEALTH CHECK")
    print(f"Run at: {datetime.now().isoformat()}")
    
    # Check databases
    for db_file in DATA_DIR.glob("*.db"):
        check_db(db_file)
    
    check_reports()
    check_cache()
    check_alternative_signals()
    
    print("\n" + "="*60)
    print("DONE")
    print("="*60)

if __name__ == "__main__":
    main()
