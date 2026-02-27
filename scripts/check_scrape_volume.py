import json, os
from pathlib import Path

dirs = [
    ('alternative_signals', 'data/alternative_signals'),
    ('market_signals', 'data/market_signals'),
    ('market_correlations', 'data/market_correlations'),
    ('news_signals', 'data/news_signals'),
    ('newsletter_signals', 'data/newsletter_signals'),
    ('insider_signals', 'data/insider_signals'),
    ('earnings_signals', 'data/earnings_signals'),
    ('job_signals', 'data/job_signals'),
    ('social_signals', 'data/social_signals'),
    ('financial_signals', 'data/financial_signals'),
    ('app_signals', 'data/app_signals'),
    ('paper_signals', 'data/paper_signals'),
    ('product_signals', 'data/product_signals'),
    ('package_signals', 'data/package_signals'),
    ('salary_signals', 'data/salary_signals'),
    ('glassdoor_signals', 'data/glassdoor_signals'),
    ('vertical_signals', 'data/vertical_signals'),
    ('policy_signals', 'data/policy_signals'),
    ('deep_research', 'data/deep_research'),
]

dates = ['2026-02-24', '2026-02-25', '2026-02-26']

for d in dates:
    print(f'\n{"="*60}')
    print(f'  {d}')
    print(f'{"="*60}')
    total_files = 0
    total_items = 0
    for name, path in dirs:
        p = Path(path)
        if not p.exists():
            continue
        for f in sorted(p.glob(f'*{d}*')):
            total_files += 1
            try:
                data = json.load(open(f, encoding='utf-8'))
                if isinstance(data, list):
                    count = len(data)
                elif isinstance(data, dict):
                    count = 0
                    for k in data:
                        v = data[k]
                        if isinstance(v, list):
                            count += len(v)
                        elif isinstance(v, dict) and k not in ('metadata', 'summary', 'config', 'scrape_info'):
                            count += len(v)
                else:
                    count = 0
                print(f'  {f.name:50s} {count:>6}')
                total_items += count
            except:
                print(f'  {f.name:50s}  ERROR')
    print(f'  {"---":50s} ------')
    print(f'  {"TOTAL":50s} {total_items:>6} items in {total_files} files')
