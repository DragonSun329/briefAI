import json

with open('data/review_signals/reviews_2026-01-28.json', encoding='utf-8') as f:
    data = json.load(f)

for app in data['apps']:
    print('=' * 60)
    print(f"{app['app_name']} ({app['company']})")
    print(f"Rating: {app['current_rating']}* ({app['total_reviews']:,} reviews)")
    print()
    
    a = app['analysis']
    
    print('PROS:')
    for p in a.get('pros', [])[:4]:
        print(f'  + {p}')
    
    print()
    print('CONS:')
    for c in a.get('cons', [])[:4]:
        print(f'  - {c}')
    
    print()
    print('FEATURE REQUESTS:')
    for fr in a.get('feature_requests', [])[:3]:
        print(f'  > {fr}')
    
    print()
    sent = a.get('sentiment_summary', 'N/A')
    print(f"SENTIMENT: {sent[:200]}...")
    print()
