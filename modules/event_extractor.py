"""
Event Extractor Module - Pipeline Integration

Integrates business event detection into the news pipeline.
Hooks into the article processing flow after entity extraction.

Usage:
    from modules.event_extractor import EventExtractor
    
    extractor = EventExtractor()
    events = extractor.process_articles(articles)
"""

from datetime import datetime
from typing import List, Dict, Any, Optional, Tuple
from pathlib import Path
from loguru import logger

from utils.event_models import (
    BusinessEvent, BusinessEventType, EventConfidence, EventTimeline
)
from utils.event_detector import EventDetector, detect_events_batch
from utils.event_store import BusinessEventStore


class EventExtractor:
    """
    Pipeline module for extracting business events from articles.
    
    Integrates with the news evaluation pipeline to detect,
    deduplicate, and store business events.
    """
    
    def __init__(
        self,
        llm_client=None,
        db_path: Optional[str] = None,
        enable_storage: bool = True,
        enable_llm: bool = True,
        min_confidence: float = 0.2
    ):
        """
        Initialize event extractor.
        
        Args:
            llm_client: LLM client for complex extraction
            db_path: Path to events database
            enable_storage: Whether to persist events
            enable_llm: Whether to use LLM for extraction
            min_confidence: Minimum confidence to keep events
        """
        self.llm_client = llm_client
        self.enable_storage = enable_storage
        self.min_confidence = min_confidence
        
        # Initialize detector
        self.detector = EventDetector(
            llm_client=llm_client if enable_llm else None,
            use_llm_fallback=enable_llm
        )
        
        # Initialize store
        self.store = BusinessEventStore(db_path) if enable_storage else None
        
        # Cache for deduplication within session
        self._session_events: List[BusinessEvent] = []
        
        logger.info(
            f"EventExtractor initialized (storage={enable_storage}, llm={enable_llm})"
        )
    
    def process_articles(
        self,
        articles: List[Dict[str, Any]],
        deduplicate: bool = True
    ) -> List[BusinessEvent]:
        """
        Process a batch of articles to extract events.
        
        This is the main pipeline integration point.
        
        Args:
            articles: List of article dictionaries
            deduplicate: Whether to deduplicate against existing events
        
        Returns:
            List of detected events
        """
        if not articles:
            return []
        
        logger.info(f"Processing {len(articles)} articles for events...")
        
        # Get existing events for deduplication
        existing_events = []
        if deduplicate and self.store:
            # Get recent events for dedup
            existing_events = self.store.get_recent_events(days=14, limit=500)
        
        # Also include session events
        existing_events.extend(self._session_events)
        
        # Batch detection
        events, stats = detect_events_batch(
            articles=articles,
            llm_client=self.llm_client,
            existing_events=existing_events
        )
        
        # Filter by confidence
        events = [e for e in events if e.confidence_score >= self.min_confidence]
        
        # Add to session cache
        self._session_events.extend(events)
        
        # Persist to database
        if self.store and events:
            saved = self.store.save_events_batch(events)
            logger.info(f"Saved {saved} events to database")
        
        # Log summary
        self._log_extraction_summary(events, stats)
        
        return events
    
    def process_single_article(
        self,
        article: Dict[str, Any]
    ) -> List[BusinessEvent]:
        """
        Process a single article for events.
        
        Args:
            article: Article dictionary
        
        Returns:
            List of detected events
        """
        return self.process_articles([article])
    
    def extract_events_from_text(
        self,
        title: str,
        content: str,
        source: str = "unknown",
        url: str = "",
        published_date: Optional[str] = None
    ) -> List[BusinessEvent]:
        """
        Extract events from raw text.
        
        Convenience method for ad-hoc extraction.
        
        Args:
            title: Article title
            content: Article content
            source: Source name
            url: Article URL
            published_date: Publication date
        
        Returns:
            List of detected events
        """
        article = {
            "title": title,
            "content": content,
            "source": source,
            "url": url,
            "published_date": published_date,
            "credibility_score": 7,  # Default medium
            "searchable_entities": {},
        }
        
        # Use entity extractor if available
        try:
            from utils.entity_extractor import EntityExtractor
            entity_extractor = EntityExtractor(llm_client=self.llm_client)
            entities = entity_extractor.extract_entities(content)
            article["searchable_entities"] = entities
        except ImportError:
            pass
        
        return self.process_single_article(article)
    
    def get_events_for_article(
        self,
        article: Dict[str, Any]
    ) -> List[BusinessEvent]:
        """
        Get events associated with an article (without detection).
        
        Looks up events by content similarity.
        
        Args:
            article: Article dictionary
        
        Returns:
            List of associated events
        """
        if not self.store:
            return []
        
        # Search by title
        title = article.get("title", "")
        if title:
            return self.store.search_events(title[:100], limit=10)
        
        return []
    
    def enrich_articles_with_events(
        self,
        articles: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Enrich articles with detected events.
        
        Adds 'detected_events' field to each article.
        
        Args:
            articles: List of article dictionaries
        
        Returns:
            Articles with 'detected_events' field added
        """
        # Process all articles
        all_events = self.process_articles(articles)
        
        # Build mapping from article to events
        # (Simple approach: match by headline overlap)
        for article in articles:
            article_events = []
            title = article.get("title", "").lower()
            
            for event in all_events:
                # Check if event headline overlaps with article title
                if any(word in event.headline.lower() for word in title.split() if len(word) > 4):
                    article_events.append(event.to_dict())
            
            article["detected_events"] = article_events
        
        return articles
    
    def get_entity_events(
        self,
        entity_name: str,
        event_types: Optional[List[BusinessEventType]] = None,
        days: int = 90
    ) -> List[BusinessEvent]:
        """
        Get events for a specific entity.
        
        Args:
            entity_name: Entity name to search for
            event_types: Optional filter by event types
            days: Number of days to look back
        
        Returns:
            List of events
        """
        if not self.store:
            return []
        
        entity_id = entity_name.lower().replace(" ", "_")
        events = self.store.get_events_by_entity(entity_id, limit=100)
        
        # Filter by type if specified
        if event_types:
            events = [e for e in events if e.event_type in event_types]
        
        # Filter by date
        from datetime import timedelta
        cutoff = datetime.utcnow() - timedelta(days=days)
        events = [e for e in events if (e.event_date or e.first_reported) >= cutoff]
        
        return events
    
    def get_entity_timeline(
        self,
        entity_name: str,
        days: int = 365
    ) -> EventTimeline:
        """
        Get event timeline for an entity.
        
        Args:
            entity_name: Entity name
            days: Number of days to include
        
        Returns:
            EventTimeline object
        """
        if not self.store:
            return EventTimeline(
                entity_id=entity_name.lower().replace(" ", "_"),
                entity_name=entity_name
            )
        
        entity_id = entity_name.lower().replace(" ", "_")
        return self.store.get_entity_timeline(entity_id, days)
    
    def get_recent_funding(self, days: int = 30, limit: int = 20) -> List[BusinessEvent]:
        """Get recent funding events."""
        if not self.store:
            return []
        return self.store.get_events_by_type(
            BusinessEventType.FUNDING_ROUND, days=days, limit=limit
        )
    
    def get_recent_acquisitions(self, days: int = 30, limit: int = 20) -> List[BusinessEvent]:
        """Get recent acquisition events."""
        if not self.store:
            return []
        return self.store.get_events_by_type(
            BusinessEventType.ACQUISITION, days=days, limit=limit
        )
    
    def get_recent_product_launches(self, days: int = 30, limit: int = 20) -> List[BusinessEvent]:
        """Get recent product launch events."""
        if not self.store:
            return []
        return self.store.get_events_by_type(
            BusinessEventType.PRODUCT_LAUNCH, days=days, limit=limit
        )
    
    def detect_causal_chains(self, entity_name: str) -> List[List[BusinessEvent]]:
        """
        Detect causal event chains for an entity.
        
        Args:
            entity_name: Entity to analyze
        
        Returns:
            List of causal chains
        """
        if not self.store:
            return []
        
        entity_id = entity_name.lower().replace(" ", "_")
        return self.store.detect_causal_chains(entity_id)
    
    def get_stats(self) -> Dict[str, Any]:
        """Get event extraction statistics."""
        stats = {
            "session_events": len(self._session_events),
            "by_type": {},
        }
        
        for event in self._session_events:
            event_type = event.event_type.value
            stats["by_type"][event_type] = stats["by_type"].get(event_type, 0) + 1
        
        if self.store:
            db_stats = self.store.get_stats()
            stats["database"] = db_stats
        
        return stats
    
    def clear_session_cache(self) -> None:
        """Clear the session event cache."""
        self._session_events = []
    
    def _log_extraction_summary(
        self,
        events: List[BusinessEvent],
        stats: Dict[str, Any]
    ) -> None:
        """Log a summary of extraction results."""
        if not events:
            logger.info("No events detected in this batch")
            return
        
        # Count by type
        by_type = {}
        for event in events:
            t = event.event_type.value
            by_type[t] = by_type.get(t, 0) + 1
        
        type_summary = ", ".join(f"{t}: {c}" for t, c in sorted(by_type.items()))
        
        # Count high confidence
        high_conf = sum(1 for e in events if e.confidence == EventConfidence.HIGH)
        
        logger.info(
            f"Extracted {len(events)} events: {type_summary} "
            f"(high confidence: {high_conf})"
        )


def integrate_with_news_evaluator(
    news_evaluator,
    event_extractor: Optional[EventExtractor] = None,
    llm_client=None
) -> None:
    """
    Integrate event extraction with NewsEvaluator.
    
    Monkey-patches the evaluate_articles method to include event detection.
    
    Args:
        news_evaluator: NewsEvaluator instance to patch
        event_extractor: EventExtractor to use (creates new if None)
        llm_client: LLM client for extraction
    """
    if event_extractor is None:
        event_extractor = EventExtractor(llm_client=llm_client)
    
    # Store original method
    original_evaluate = news_evaluator.evaluate_articles
    
    def evaluate_with_events(articles, categories, **kwargs):
        # First, run event extraction
        events = event_extractor.process_articles(articles)
        
        # Add events to articles
        for article in articles:
            article_events = []
            title = article.get("title", "").lower()
            
            for event in events:
                if any(word in event.headline.lower() for word in title.split() if len(word) > 4):
                    article_events.append(event.to_dict())
            
            article["detected_events"] = article_events
        
        # Then run original evaluation
        return original_evaluate(articles, categories, **kwargs)
    
    news_evaluator.evaluate_articles = evaluate_with_events
    news_evaluator._event_extractor = event_extractor
    
    logger.info("Event extraction integrated with NewsEvaluator")


# Convenience function for standalone use
def extract_events(
    articles: List[Dict[str, Any]],
    llm_client=None,
    save_to_db: bool = True
) -> Tuple[List[BusinessEvent], Dict[str, Any]]:
    """
    Convenience function to extract events from articles.
    
    Args:
        articles: List of article dictionaries
        llm_client: Optional LLM client
        save_to_db: Whether to save to database
    
    Returns:
        Tuple of (events, stats)
    """
    extractor = EventExtractor(
        llm_client=llm_client,
        enable_storage=save_to_db,
        enable_llm=llm_client is not None
    )
    
    events = extractor.process_articles(articles)
    stats = extractor.get_stats()
    
    return events, stats


if __name__ == "__main__":
    # Demo usage
    sample_articles = [
        {
            "title": "OpenAI raises $6 billion in funding round led by Thrive Capital",
            "content": "OpenAI has raised $6 billion in a new funding round led by Thrive Capital, "
                       "valuing the company at $157 billion. Microsoft, NVIDIA, and SoftBank also participated.",
            "source": "TechCrunch",
            "url": "https://techcrunch.com/openai-funding",
            "published_date": "2024-10-01",
            "credibility_score": 9,
        },
        {
            "title": "Anthropic launches Claude 3.5 Sonnet with improved reasoning capabilities",
            "content": "Anthropic today announced the release of Claude 3.5 Sonnet, featuring "
                       "significantly improved reasoning and coding capabilities. The model is now available via API.",
            "source": "VentureBeat",
            "url": "https://venturebeat.com/anthropic-claude",
            "published_date": "2024-10-01",
            "credibility_score": 8,
        },
        {
            "title": "Meta acquires AI startup Character.AI for $2.5 billion",
            "content": "Meta has acquired AI chatbot startup Character.AI in a deal worth $2.5 billion. "
                       "The acquisition will strengthen Meta's AI research capabilities.",
            "source": "Bloomberg",
            "url": "https://bloomberg.com/meta-character",
            "published_date": "2024-10-01",
            "credibility_score": 9,
        },
    ]
    
    extractor = EventExtractor(enable_storage=False, enable_llm=False)
    events = extractor.process_articles(sample_articles)
    
    print(f"\nDetected {len(events)} events:")
    for event in events:
        print(f"\n{event.event_type.value.upper()}: {event.headline}")
        print(f"  Entity: {event.entity_name}")
        print(f"  Confidence: {event.confidence.value} ({event.confidence_score:.2f})")
        print(f"  Sources: {event.source_count}")
        
        if event.funding_details:
            fd = event.funding_details
            print(f"  Funding: ${fd.amount_usd:,.0f}" if fd.amount_usd else "")
            print(f"  Stage: {fd.stage.value}")
