"""
Chinese AI Company Funding Lookup
Fetches funding data from web sources for key Chinese AI companies.
"""

import json
import time
import re
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional
import requests

# Key Chinese AI companies to research
CN_AI_COMPANIES = [
    # LLM Foundation Models
    {"name": "DeepSeek", "cn_name": "深度求索", "category": "llm"},
    {"name": "Moonshot AI", "cn_name": "月之暗面", "alt_names": ["Kimi"], "category": "llm"},
    {"name": "Zhipu AI", "cn_name": "智谱AI", "alt_names": ["GLM", "ChatGLM"], "category": "llm"},
    {"name": "Baichuan AI", "cn_name": "百川智能", "category": "llm"},
    {"name": "MiniMax", "cn_name": "MiniMax", "category": "llm"},
    {"name": "01.AI", "cn_name": "零一万物", "alt_names": ["Yi"], "category": "llm"},
    {"name": "Stepfun", "cn_name": "阶跃星辰", "category": "llm"},

    # Big Tech AI
    {"name": "Baidu", "cn_name": "百度", "alt_names": ["Ernie", "文心一言"], "category": "bigtech"},
    {"name": "Alibaba Cloud", "cn_name": "阿里云", "alt_names": ["Tongyi", "通义千问"], "category": "bigtech"},
    {"name": "Tencent", "cn_name": "腾讯", "alt_names": ["Hunyuan", "混元"], "category": "bigtech"},
    {"name": "ByteDance", "cn_name": "字节跳动", "alt_names": ["Doubao", "豆包"], "category": "bigtech"},
    {"name": "Huawei", "cn_name": "华为", "alt_names": ["Pangu", "盘古"], "category": "bigtech"},

    # AI Chips
    {"name": "Cambricon", "cn_name": "寒武纪", "category": "chips"},
    {"name": "Horizon Robotics", "cn_name": "地平线", "category": "chips"},
    {"name": "Biren Technology", "cn_name": "壁仞科技", "category": "chips"},
    {"name": "Moore Threads", "cn_name": "摩尔线程", "category": "chips"},
    {"name": "Enflame", "cn_name": "燧原科技", "category": "chips"},

    # AI Vision / Robotics
    {"name": "SenseTime", "cn_name": "商汤科技", "category": "vision"},
    {"name": "Megvii", "cn_name": "旷视科技", "alt_names": ["Face++"], "category": "vision"},
    {"name": "CloudWalk", "cn_name": "云从科技", "category": "vision"},
    {"name": "Yitu Technology", "cn_name": "依图科技", "category": "vision"},
    {"name": "Unitree Robotics", "cn_name": "宇树科技", "category": "robotics"},
    {"name": "Agility Robotics China", "cn_name": "灵动科技", "category": "robotics"},

    # AI Healthcare
    {"name": "iFlytek", "cn_name": "科大讯飞", "category": "enterprise"},
    {"name": "Fourth Paradigm", "cn_name": "第四范式", "category": "enterprise"},
]


def search_crunchbase_web(company_name: str) -> Optional[Dict]:
    """Search Crunchbase for company funding info via web."""
    try:
        # Use DuckDuckGo to find Crunchbase page
        search_url = f"https://html.duckduckgo.com/html/?q=site:crunchbase.com+{company_name}+funding"
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        resp = requests.get(search_url, headers=headers, timeout=10)

        # Extract Crunchbase URL from results
        cb_match = re.search(r'https://www\.crunchbase\.com/organization/([a-z0-9-]+)', resp.text)
        if cb_match:
            return {"crunchbase_url": cb_match.group(0), "slug": cb_match.group(1)}
    except Exception as e:
        print(f"  Crunchbase search error for {company_name}: {e}")
    return None


def search_tracxn(company_name: str) -> Optional[Dict]:
    """Search Tracxn for funding info."""
    try:
        search_url = f"https://tracxn.com/d/companies/{company_name.lower().replace(' ', '-')}"
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        resp = requests.get(search_url, headers=headers, timeout=10)

        if resp.status_code == 200:
            # Try to extract funding from page
            funding_match = re.search(r'Total Funding[:\s]*\$?([\d.]+)\s*(M|B|Million|Billion)', resp.text, re.I)
            if funding_match:
                amount = float(funding_match.group(1))
                unit = funding_match.group(2).upper()
                if 'B' in unit:
                    amount *= 1000
                return {"total_funding_usd_m": amount, "source": "tracxn"}
    except Exception as e:
        print(f"  Tracxn error for {company_name}: {e}")
    return None


def search_pitchbook_summary(company_name: str) -> Optional[Dict]:
    """Try to get basic info from PitchBook public summaries."""
    try:
        search_url = f"https://html.duckduckgo.com/html/?q=site:pitchbook.com+{company_name}+total+funding"
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        resp = requests.get(search_url, headers=headers, timeout=10)

        # Look for funding amounts in snippets
        funding_match = re.search(r'\$?([\d.]+)\s*(M|B|Million|Billion)\s*(?:total|raised|funding)', resp.text, re.I)
        if funding_match:
            amount = float(funding_match.group(1))
            unit = funding_match.group(2).upper()
            if 'B' in unit:
                amount *= 1000
            return {"total_funding_usd_m": amount, "source": "pitchbook_snippet"}
    except Exception as e:
        print(f"  PitchBook error for {company_name}: {e}")
    return None


def search_36kr_itjuzi(company_cn_name: str) -> Optional[Dict]:
    """Search Chinese funding databases (36Kr/ITJuzi)."""
    try:
        # ITJuzi search
        search_url = f"https://html.duckduckgo.com/html/?q=site:itjuzi.com+{company_cn_name}+融资"
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
        resp = requests.get(search_url, headers=headers, timeout=10)

        # Look for funding amounts in Chinese format
        # Pattern: 数字 + 亿/万 + 美元/人民币
        funding_match = re.search(r'([\d.]+)\s*(亿|万)\s*(美元|人民币|元|USD)', resp.text)
        if funding_match:
            amount = float(funding_match.group(1))
            unit = funding_match.group(2)
            currency = funding_match.group(3)

            # Convert to millions USD
            if unit == '亿':
                amount *= 100  # 100 million
            elif unit == '万':
                amount *= 0.01  # 10,000

            if currency in ['人民币', '元']:
                amount /= 7.2  # Approximate CNY to USD

            return {"total_funding_usd_m": amount, "source": "itjuzi", "currency_note": currency}
    except Exception as e:
        print(f"  ITJuzi error for {company_cn_name}: {e}")
    return None


def lookup_company_funding(company: Dict) -> Dict:
    """Look up funding for a single company from multiple sources."""
    result = {
        "name": company["name"],
        "cn_name": company.get("cn_name"),
        "category": company.get("category"),
        "funding_sources": [],
        "best_estimate_usd_m": None,
    }

    print(f"\nSearching: {company['name']} ({company.get('cn_name', '')})")

    # Try Crunchbase
    cb_result = search_crunchbase_web(company["name"])
    if cb_result:
        result["crunchbase_url"] = cb_result.get("crunchbase_url")
        result["funding_sources"].append({"source": "crunchbase", "data": cb_result})
        print(f"  Found Crunchbase: {cb_result.get('crunchbase_url')}")

    time.sleep(0.5)  # Rate limiting

    # Try Tracxn
    tracxn_result = search_tracxn(company["name"])
    if tracxn_result:
        result["funding_sources"].append(tracxn_result)
        if tracxn_result.get("total_funding_usd_m"):
            result["best_estimate_usd_m"] = tracxn_result["total_funding_usd_m"]
            print(f"  Tracxn funding: ${tracxn_result['total_funding_usd_m']}M")

    time.sleep(0.5)

    # Try PitchBook snippets
    pb_result = search_pitchbook_summary(company["name"])
    if pb_result:
        result["funding_sources"].append(pb_result)
        if not result["best_estimate_usd_m"] and pb_result.get("total_funding_usd_m"):
            result["best_estimate_usd_m"] = pb_result["total_funding_usd_m"]
            print(f"  PitchBook snippet: ${pb_result['total_funding_usd_m']}M")

    time.sleep(0.5)

    # Try Chinese sources if we have Chinese name
    if company.get("cn_name"):
        cn_result = search_36kr_itjuzi(company["cn_name"])
        if cn_result:
            result["funding_sources"].append(cn_result)
            if not result["best_estimate_usd_m"] and cn_result.get("total_funding_usd_m"):
                result["best_estimate_usd_m"] = cn_result["total_funding_usd_m"]
                print(f"  ITJuzi funding: ${cn_result['total_funding_usd_m']:.1f}M")

    return result


def main():
    """Run funding lookup for all CN AI companies."""
    print("=" * 60)
    print("Chinese AI Company Funding Lookup")
    print(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("=" * 60)

    results = []

    for company in CN_AI_COMPANIES:
        result = lookup_company_funding(company)
        results.append(result)
        time.sleep(1)  # Be nice to servers

    # Save results
    output_dir = Path("data/alternative_signals")
    output_dir.mkdir(parents=True, exist_ok=True)

    output_file = output_dir / f"cn_ai_funding_{datetime.now().strftime('%Y-%m-%d')}.json"
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump({
            "scraped_at": datetime.now().isoformat(),
            "total_companies": len(results),
            "companies": results
        }, f, indent=2, ensure_ascii=False)

    print("\n" + "=" * 60)
    print("RESULTS SUMMARY")
    print("=" * 60)

    # Print summary table
    print(f"\n{'Company':<25} {'Chinese':<12} {'Category':<10} {'Funding (USD M)':<15}")
    print("-" * 70)

    for r in sorted(results, key=lambda x: x.get("best_estimate_usd_m") or 0, reverse=True):
        funding = f"${r['best_estimate_usd_m']:.0f}M" if r.get("best_estimate_usd_m") else "Unknown"
        print(f"{r['name']:<25} {r.get('cn_name', ''):<12} {r.get('category', ''):<10} {funding:<15}")

    print(f"\nResults saved to: {output_file}")
    return results


if __name__ == "__main__":
    main()
