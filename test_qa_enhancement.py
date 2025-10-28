#!/usr/bin/env python3
"""
Quick test script for Q&A enhancement
Tests entity detection and Context Provider integration
"""

import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from modules.context_provider import ContextProvider
from utils.llm_client_enhanced import LLMClient

def test_entity_detection():
    """Test entity detection in questions"""
    print("=" * 60)
    print("Testing Entity Detection")
    print("=" * 60)

    test_questions = [
        "what business is anthropic in",
        "explain how openai makes money",
        "what technology does google use",
        "how does claude work"
    ]

    company_keywords = ['公司', 'company', 'business', '业务', '商业模式', '收入', '创始']
    common_companies = ['anthropic', 'openai', 'google', 'deepmind', 'meta', 'microsoft']

    for question in test_questions:
        question_lower = question.lower()
        asks_about_company = any(kw in question_lower for kw in company_keywords)

        entities = set()
        for company in common_companies:
            if company in question_lower:
                entities.add(company.title())

        print(f"\nQuestion: {question}")
        print(f"  Asks about company: {asks_about_company}")
        print(f"  Entities found: {entities}")


def test_context_provider():
    """Test Context Provider integration"""
    print("\n" + "=" * 60)
    print("Testing Context Provider")
    print("=" * 60)

    try:
        llm_client = LLMClient()
        context_provider = ContextProvider(llm_client=llm_client)

        # Test company context
        print("\n[Test 1] Getting Anthropic company context...")
        company_ctx = context_provider.get_company_context("Anthropic")
        if company_ctx:
            print(f"✓ Background: {company_ctx.get('background', 'N/A')[:100]}...")
            print(f"✓ Business Model: {company_ctx.get('business_model', 'N/A')[:100]}...")
        else:
            print("✗ No context returned")

        # Test cache stats
        print("\n[Test 2] Checking cache stats...")
        stats = context_provider.get_cache_stats()
        print(f"✓ Cached companies: {stats.get('cached_companies', 0)}")
        print(f"✓ Cached technologies: {stats.get('cached_technologies', 0)}")
        print(f"✓ Cache path: {stats.get('cache_path', 'N/A')}")

    except Exception as e:
        print(f"✗ Error: {e}")


def test_enrichment_logic():
    """Test the enrichment routing logic"""
    print("\n" + "=" * 60)
    print("Testing Enrichment Routing Logic")
    print("=" * 60)

    test_cases = [
        {
            "question": "what business is anthropic in",
            "expected_company": True,
            "expected_tech": False,
            "expected_detail": False
        },
        {
            "question": "explain how claude works in detail",
            "expected_company": False,
            "expected_tech": False,
            "expected_detail": True
        },
        {
            "question": "what is anthropic's technology",
            "expected_company": False,
            "expected_tech": True,
            "expected_detail": False
        }
    ]

    company_keywords = ['公司', 'company', 'business', '业务', '商业模式', '收入', '创始']
    tech_keywords = ['技术', 'technology', 'principle', '原理', 'how does', '如何工作', '实现']
    detail_keywords = ['详细', 'detail', 'explain', '解释', 'how', '为什么', 'why']

    for test in test_cases:
        question = test["question"]
        question_lower = question.lower()

        asks_about_company = any(kw in question_lower for kw in company_keywords)
        asks_about_tech = any(kw in question_lower for kw in tech_keywords)
        asks_for_details = any(kw in question_lower for kw in detail_keywords)

        print(f"\nQuestion: {question}")
        print(f"  Company: {asks_about_company} (expected: {test['expected_company']})")
        print(f"  Tech: {asks_about_tech} (expected: {test['expected_tech']})")
        print(f"  Detail: {asks_for_details} (expected: {test['expected_detail']})")

        # Validate
        match = (
            asks_about_company == test['expected_company'] and
            asks_about_tech == test['expected_tech'] and
            asks_for_details == test['expected_detail']
        )
        print(f"  Result: {'✓ PASS' if match else '✗ FAIL'}")


if __name__ == "__main__":
    print("\n🔍 Q&A Enhancement Test Suite\n")

    test_entity_detection()
    test_context_provider()
    test_enrichment_logic()

    print("\n" + "=" * 60)
    print("✅ All tests completed!")
    print("=" * 60 + "\n")
