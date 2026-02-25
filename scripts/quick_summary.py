import json
mc = json.load(open('data/market_correlations/market_news_2026-02-24.json', encoding='utf-8'))
print("SECTOR PERFORMANCE:")
for s, v in mc.get('sector_performance', {}).items():
    print(f"  {s}: {v:.1f}%")
movers = mc.get('movers', [])
print(f"\nTotal movers: {len(movers)}")
strong = sum(1 for m in movers if m.get('explanation_strength') == 'strong')
unexpl = sum(1 for m in movers if m.get('explanation_strength') == 'unexplained')
print(f"Strong: {strong}, Unexplained: {unexpl}")
print("\nTOP MOVERS:")
for m in sorted(movers, key=lambda x: abs(x.get('day_change_pct', 0)), reverse=True)[:15]:
    t = m['ticker']
    chg = m.get('day_change_pct', 0)
    exp = m.get('explanation_strength', '?')
    arts = m.get('matched_articles', [])
    best = arts[0]['title'][:70] if arts else 'none'
    ta = m.get('technical_signals', [])
    ta_str = ', '.join(ta[:3]) if ta else ''
    print(f"  {t:5s} {chg:+7.1f}%  [{exp:11s}]  {best}  |{ta_str}")
