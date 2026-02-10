"""
Basic Usage Examples for briefAI Python SDK

This file demonstrates common use cases for the briefAI API.
"""

from briefai_client import BriefAIClient, QueryBuilder, create_client


def example_search_entities():
    """Example: Search for entities by name."""
    client = create_client(api_key="your_api_key")
    
    # Search for companies related to "openai"
    entities, pagination = client.entities.search(
        query="openai",
        entity_type="company",
        limit=10
    )
    
    print(f"Found {pagination.total} entities:")
    for entity in entities:
        print(f"  - {entity.name} ({entity.entity_type})")
        if entity.description:
            print(f"    {entity.description[:100]}...")


def example_signal_history():
    """Example: Get signal history for an entity."""
    client = create_client(api_key="your_api_key")
    
    # Get 30 days of technical signals for OpenAI
    signals, pagination = client.signals.history(
        entity_id="openai",
        category="technical",
        days=30,
        limit=100
    )
    
    print(f"Signal history for OpenAI (technical):")
    for signal in signals[:5]:  # Show first 5
        print(f"  - Score: {signal.score:.2f}, Date: {signal.created_at}")
        if signal.score_delta_7d:
            print(f"    7-day change: {signal.score_delta_7d:+.2f}")


def example_entity_profile():
    """Example: Get composite signal profile for an entity."""
    client = create_client(api_key="your_api_key")
    
    # Get OpenAI's signal profile
    profile = client.entities.profile("openai")
    
    print(f"Signal Profile for {profile.entity_name}:")
    print(f"  Composite Score: {profile.composite_score:.2f}")
    print(f"  Technical:  {profile.technical_score or 'N/A'}")
    print(f"  Company:    {profile.company_score or 'N/A'}")
    print(f"  Financial:  {profile.financial_score or 'N/A'}")
    print(f"  Product:    {profile.product_score or 'N/A'}")
    print(f"  Media:      {profile.media_score or 'N/A'}")
    print(f"  7-day Momentum: {profile.momentum_7d or 'N/A'}")


def example_divergences():
    """Example: Find investment opportunities from divergences."""
    client = create_client(api_key="your_api_key")
    
    # Get opportunity divergences (high technical, low financial)
    divergences, pagination = client.divergences.active(
        interpretation="opportunity",
        min_magnitude=30,
        limit=10
    )
    
    print(f"Found {pagination.total} opportunity divergences:")
    for div in divergences:
        print(f"\n  {div.entity_name}:")
        print(f"    High: {div.high_signal_category} ({div.high_signal_score:.1f})")
        print(f"    Low:  {div.low_signal_category} ({div.low_signal_score:.1f})")
        print(f"    Magnitude: {div.divergence_magnitude:.1f}")
        print(f"    Confidence: {div.confidence:.0%}")
        if div.interpretation_rationale:
            print(f"    Rationale: {div.interpretation_rationale}")


def example_export_csv():
    """Example: Export signals to CSV."""
    client = create_client(api_key="your_api_key")
    
    # Export technical signals from the last month
    csv_data = client.export.signals(
        format="csv",
        start_date="2025-01-01",
        categories=["technical", "financial"],
        min_score=50,
        limit=5000
    )
    
    # Save to file
    with open("signals_export.csv", "wb") as f:
        f.write(csv_data)
    
    print("Exported to signals_export.csv")


def example_async_export():
    """Example: Create async export job for large datasets."""
    client = create_client(api_key="your_api_key")
    
    # Create export job
    job = client.export.create_job(
        export_type="signals",
        format="parquet",
        start_date="2024-01-01",
        end_date="2025-01-01",
        compress=True
    )
    
    print(f"Created job: {job.job_id}")
    print(f"Status: {job.status}")
    
    # Wait for completion
    completed_job = client.export.wait_for_job(job.job_id, timeout=300)
    
    print(f"Job completed! Rows: {completed_job.row_count}")
    print(f"File size: {completed_job.file_size_bytes} bytes")
    
    # Download
    data = client.export.download_job(job.job_id)
    with open("large_export.parquet.gz", "wb") as f:
        f.write(data)


def example_query_builder():
    """Example: Use query builder for complex queries (Premium)."""
    client = create_client(api_key="your_premium_key")
    
    # Build a complex query
    query = (QueryBuilder("signals")
        .select("entity_id", "entity_name", "score", "category", "created_at")
        .where("category", "IN", ["technical", "financial"])
        .where("score", ">=", 70)
        .or_where("entity_name", "LIKE", "%OpenAI%")
        .or_where("entity_name", "LIKE", "%Anthropic%")
        .date_range("2025-01-01", "2025-06-01")
        .min_confidence(0.8)
        .order_by("score", desc=True)
        .limit(100)
        .build())
    
    # Execute
    result = client.query.execute(query)
    
    print(f"Query returned {result['total_rows']} rows")
    print(f"Execution time: {result['execution_time_ms']:.2f}ms")
    
    for row in result["rows"][:5]:
        print(f"  {row['entity_name']}: {row['score']:.1f} ({row['category']})")


def example_rate_limits():
    """Example: Handle rate limits properly."""
    client = create_client(
        api_key="your_api_key",
        retry_on_rate_limit=True,  # Auto-retry when rate limited
        max_retries=3
    )
    
    # Make a request
    entities, _ = client.entities.search("ai")
    
    # Check rate limit status
    if client.rate_limit:
        print(f"Tier: {client.rate_limit.tier}")
        print(f"Remaining: {client.rate_limit.remaining_minute}/{client.rate_limit.limit_per_minute}")
        print(f"Resets at: {client.rate_limit.reset_at}")


def main():
    """Run all examples."""
    print("=" * 60)
    print("briefAI SDK Examples")
    print("=" * 60)
    
    # Note: These examples require a valid API key
    # Uncomment to run:
    
    # example_search_entities()
    # example_signal_history()
    # example_entity_profile()
    # example_divergences()
    # example_export_csv()
    # example_async_export()
    # example_query_builder()
    # example_rate_limits()
    
    print("\nTo run examples, uncomment the function calls and provide your API key.")


if __name__ == "__main__":
    main()
