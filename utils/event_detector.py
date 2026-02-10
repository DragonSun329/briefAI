"""
Event Detection Engine

Detects business events from news articles using:
1. Pattern matching on headlines and content
2. LLM-based extraction for complex events
3. Confidence scoring based on source quality

Handles deduplication of events across multiple sources.
"""

import re
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple
from loguru import logger
from difflib import SequenceMatcher

from utils.event_models import (
    BusinessEvent, BusinessEventType, EventConfidence, EventSource,
    FundingDetails, FundingStage, AcquisitionDetails, ProductLaunchDetails,
    LeadershipChangeDetails, PartnershipDetails, LayoffDetails
)


class EventDetector:
    """
    Detects business events from news articles.
    
    Uses a combination of regex pattern matching and LLM-based extraction.
    """
    
    def __init__(
        self, 
        llm_client=None,
        patterns_path: Optional[str] = None,
        use_llm_fallback: bool = True
    ):
        """
        Initialize event detector.
        
        Args:
            llm_client: LLM client for complex extraction
            patterns_path: Path to event_patterns.json
            use_llm_fallback: Use LLM for complex events
        """
        self.llm_client = llm_client
        self.use_llm_fallback = use_llm_fallback
        
        # Load patterns
        if patterns_path is None:
            patterns_path = Path(__file__).parent.parent / "config" / "event_patterns.json"
        
        self.patterns = self._load_patterns(patterns_path)
        self._compile_patterns()
        
        logger.info(f"EventDetector initialized (LLM fallback: {use_llm_fallback})")
    
    def _load_patterns(self, path: Path) -> Dict:
        """Load event patterns from JSON."""
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"Failed to load event patterns: {e}")
            return {"event_types": {}}
    
    def _compile_patterns(self) -> None:
        """Pre-compile regex patterns for efficiency."""
        self.compiled_patterns = {}
        
        for event_type, config in self.patterns.get("event_types", {}).items():
            if not config.get("enabled", True):
                continue
            
            self.compiled_patterns[event_type] = {
                "headline": [],
                "content": [],
            }
            
            # Compile headline patterns
            for pattern in config.get("headline_patterns", []):
                try:
                    self.compiled_patterns[event_type]["headline"].append(
                        re.compile(pattern, re.IGNORECASE)
                    )
                except re.error as e:
                    logger.warning(f"Invalid pattern '{pattern}': {e}")
            
            # Compile content patterns
            for pattern in config.get("content_patterns", []):
                try:
                    self.compiled_patterns[event_type]["content"].append(
                        re.compile(pattern, re.IGNORECASE)
                    )
                except re.error as e:
                    logger.warning(f"Invalid pattern '{pattern}': {e}")
    
    def detect_events(
        self,
        article: Dict[str, Any],
        existing_events: Optional[List[BusinessEvent]] = None
    ) -> List[BusinessEvent]:
        """
        Detect business events from an article.
        
        Args:
            article: Article dictionary with title, content, source, etc.
            existing_events: Existing events for deduplication
        
        Returns:
            List of detected BusinessEvent objects
        """
        title = article.get("title", "")
        content = article.get("content", "") or article.get("paraphrased_content", "")
        source = article.get("source", "unknown")
        url = article.get("url", "")
        published = article.get("published_date")
        credibility = article.get("credibility_score", 7) / 10.0
        
        # Extract entities from article
        entities = article.get("searchable_entities", {})
        companies = entities.get("companies", [])
        
        detected_events = []
        
        # Try pattern-based detection first
        for event_type, patterns in self.compiled_patterns.items():
            # Check headline patterns
            headline_matches = self._check_patterns(title, patterns["headline"])
            content_matches = self._check_patterns(content[:2000], patterns["content"])
            
            if headline_matches:
                # Strong signal - headline match
                event = self._extract_event(
                    event_type=BusinessEventType(event_type),
                    article=article,
                    headline_match=headline_matches[0],
                    companies=companies,
                    confidence_boost=0.2
                )
                if event:
                    detected_events.append(event)
            
            elif content_matches and len(content_matches) >= 2:
                # Weaker signal - multiple content matches
                event = self._extract_event(
                    event_type=BusinessEventType(event_type),
                    article=article,
                    headline_match=None,
                    companies=companies,
                    confidence_boost=0.0
                )
                if event:
                    detected_events.append(event)
        
        # Use LLM for complex extraction if needed
        if self.use_llm_fallback and self.llm_client:
            if not detected_events:
                # No events found by patterns, try LLM
                llm_events = self._detect_with_llm(article)
                detected_events.extend(llm_events)
            else:
                # Enrich detected events with LLM details
                for event in detected_events:
                    self._enrich_event_with_llm(event, article)
        
        # Add source to all events
        source_obj = EventSource(
            source_id=source.lower().replace(" ", "_"),
            source_name=source,
            source_url=url,
            source_credibility=credibility,
            published_at=self._parse_date(published) if published else datetime.utcnow(),
            excerpt=title,
        )
        
        for event in detected_events:
            event.add_source(source_obj)
        
        # Deduplicate against existing events
        if existing_events:
            detected_events = self._deduplicate_events(detected_events, existing_events)
        
        logger.debug(f"Detected {len(detected_events)} events from '{title[:50]}...'")
        
        return detected_events
    
    def _check_patterns(
        self, 
        text: str, 
        patterns: List[re.Pattern]
    ) -> List[re.Match]:
        """Check text against compiled patterns."""
        matches = []
        for pattern in patterns:
            match = pattern.search(text)
            if match:
                matches.append(match)
        return matches
    
    def _extract_event(
        self,
        event_type: BusinessEventType,
        article: Dict[str, Any],
        headline_match: Optional[re.Match],
        companies: List[str],
        confidence_boost: float = 0.0
    ) -> Optional[BusinessEvent]:
        """
        Extract event details from article.
        
        Args:
            event_type: Type of event detected
            article: Article dictionary
            headline_match: Regex match from headline
            companies: List of companies mentioned
            confidence_boost: Additional confidence from strong match
        
        Returns:
            BusinessEvent or None if extraction fails
        """
        title = article.get("title", "")
        content = article.get("content", "") or article.get("paraphrased_content", "")
        
        # Determine primary entity
        entity_name = ""
        if companies:
            entity_name = companies[0]
        elif headline_match:
            # Try to extract entity from match
            groups = headline_match.groups()
            if groups:
                entity_name = groups[0] if groups[0] else ""
        
        if not entity_name:
            # Try to find company in title
            known_companies = self.patterns.get("entity_extraction", {}).get("ai_companies", [])
            for company in known_companies:
                if company.lower() in title.lower():
                    entity_name = company
                    break
        
        if not entity_name:
            # For Chinese articles, try to extract entity from beginning of title
            # Common pattern: "Company完成融资" or "Company发布产品"
            import re
            chinese_company_match = re.match(r'^([^\s完成发布宣布获得推出]{2,15})', title)
            if chinese_company_match and any(ord(c) > 0x4E00 for c in chinese_company_match.group(1)):
                entity_name = chinese_company_match.group(1)
        
        if not entity_name:
            logger.debug(f"No entity found for {event_type} in '{title[:50]}'")
            return None
        
        # Create base event
        event = BusinessEvent(
            event_type=event_type,
            entity_name=entity_name,
            entity_id=entity_name.lower().replace(" ", "_"),
            headline=title,
            summary=content[:300] if content else title,
            event_date=self._parse_date(article.get("published_date")),
            related_entity_names=companies[1:] if len(companies) > 1 else [],
        )
        
        # Extract type-specific details
        if event_type == BusinessEventType.FUNDING_ROUND:
            event.funding_details = self._extract_funding_details(title, content)
        
        elif event_type == BusinessEventType.ACQUISITION:
            event.acquisition_details = self._extract_acquisition_details(title, content, companies)
        
        elif event_type == BusinessEventType.PRODUCT_LAUNCH:
            event.product_details = self._extract_product_details(title, content)
        
        elif event_type == BusinessEventType.LEADERSHIP_CHANGE:
            event.leadership_details = self._extract_leadership_details(title, content)
        
        elif event_type == BusinessEventType.PARTNERSHIP:
            event.partnership_details = self._extract_partnership_details(title, content, companies)
        
        elif event_type == BusinessEventType.LAYOFF:
            event.layoff_details = self._extract_layoff_details(title, content)
        
        # Set initial confidence
        base_confidence = 0.3 if headline_match else 0.2
        event.confidence_score = min(1.0, base_confidence + confidence_boost)
        
        # Recompute content hash with details
        event.content_hash = event.compute_content_hash()
        
        return event
    
    def _extract_funding_details(
        self, 
        title: str, 
        content: str
    ) -> FundingDetails:
        """Extract funding round details."""
        text = f"{title} {content}"
        
        details = FundingDetails()
        
        # Extract amount
        amount_config = self.patterns.get("event_types", {}).get(
            "funding_round", {}
        ).get("amount_extraction", {})
        
        for pattern in amount_config.get("patterns", []):
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                try:
                    amount = float(match.group(1).replace(",", ""))
                    unit = match.group(2).lower() if len(match.groups()) > 1 else ""
                    
                    multiplier = amount_config.get("multipliers", {}).get(unit, 1)
                    details.amount_usd = amount * multiplier
                    break
                except (ValueError, IndexError):
                    continue
        
        # Extract stage
        stage_patterns = self.patterns.get("event_types", {}).get(
            "funding_round", {}
        ).get("stage_patterns", {})
        
        for stage, keywords in stage_patterns.items():
            for keyword in keywords:
                if keyword.lower() in text.lower():
                    details.stage = FundingStage(stage)
                    break
        
        # Extract investors (basic)
        investor_match = re.search(r"led by ([A-Z][\w\s&]+?)(?:,|\.|and|with)", text)
        if investor_match:
            details.lead_investors = [investor_match.group(1).strip()]
        
        return details
    
    def _extract_acquisition_details(
        self, 
        title: str, 
        content: str,
        companies: List[str]
    ) -> AcquisitionDetails:
        """Extract acquisition details."""
        text = f"{title} {content}"
        
        details = AcquisitionDetails()
        
        # Pattern: X acquires Y
        match = re.search(
            r"([A-Z][\w\s]+?)\s+(?:acquires?|to acquire|buying|to buy)\s+([A-Z][\w\s]+?)(?:\s+for|\s+in|,|\.)", 
            text
        )
        if match:
            details.acquirer_name = match.group(1).strip()
            details.target_name = match.group(2).strip()
        
        # Pattern: Y acquired by X
        if not details.acquirer_name:
            match = re.search(
                r"([A-Z][\w\s]+?)\s+(?:acquired|bought)\s+by\s+([A-Z][\w\s]+?)(?:\s+for|,|\.)",
                text
            )
            if match:
                details.target_name = match.group(1).strip()
                details.acquirer_name = match.group(2).strip()
        
        # Fall back to company list
        if not details.acquirer_name and len(companies) >= 2:
            details.acquirer_name = companies[0]
            details.target_name = companies[1]
        
        # Extract deal value
        value_match = re.search(
            r"(?:deal|transaction|acquisition)\s+(?:valued?|worth)\s+(?:at\s+)?\$?([\d,\.]+)\s*(billion|million|B|M)",
            text, re.IGNORECASE
        )
        if value_match:
            try:
                amount = float(value_match.group(1).replace(",", ""))
                unit = value_match.group(2).lower()
                multiplier = {"billion": 1e9, "million": 1e6, "b": 1e9, "m": 1e6}.get(unit, 1)
                details.deal_value_usd = amount * multiplier
            except ValueError:
                pass
        
        # Check if rumored
        if any(word in text.lower() for word in ["rumor", "reportedly", "exploring", "in talks"]):
            details.is_rumored = True
        
        return details
    
    def _extract_product_details(
        self, 
        title: str, 
        content: str
    ) -> ProductLaunchDetails:
        """Extract product launch details."""
        text = f"{title} {content}"
        
        details = ProductLaunchDetails()
        
        # Extract product name from common patterns
        patterns = [
            r"(?:launches?|announces?|introduces?|unveils?|releases?)\s+([A-Z][\w\s\d\.\-]+?)(?:\s*,|\s+with|\s+for|,|\.)",
            r"([A-Z][\w\d\.\-]+)\s+(?:is now available|now available|in beta|launched)",
        ]
        
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                details.product_name = match.group(1).strip()
                break
        
        # Detect model names
        model_patterns = self.patterns.get("event_types", {}).get(
            "product_launch", {}
        ).get("model_patterns", [])
        
        for pattern in model_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                if not details.product_name:
                    details.product_name = match.group(0)
                details.product_type = "model"
                break
        
        # Detect beta/early access
        if any(word in text.lower() for word in ["beta", "early access", "preview"]):
            details.is_beta = True
        
        # Detect open source
        if any(word in text.lower() for word in ["open source", "open-source", "openly available"]):
            details.is_open_source = True
        
        return details
    
    def _extract_leadership_details(
        self, 
        title: str, 
        content: str
    ) -> LeadershipChangeDetails:
        """Extract leadership change details."""
        text = f"{title} {content}"
        
        details = LeadershipChangeDetails()
        
        # Role patterns
        roles = ["CEO", "CTO", "CFO", "COO", "CPO", "CMO", "President", "Chairman", "Chairwoman"]
        
        # Pattern: Person joins/hired as Role
        for role in roles:
            match = re.search(
                rf"([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)\s+(?:joins?|hired|appointed|named)\s+(?:as\s+)?(?:new\s+)?{role}",
                text
            )
            if match:
                details.person_name = match.group(1).strip()
                details.new_role = role
                details.change_type = "hired"
                break
        
        # Pattern: Role steps down/departs
        if not details.person_name:
            for role in roles:
                match = re.search(
                    rf"([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)(?:,\s+)?(?:the\s+)?{role}(?:,)?\s+(?:steps?\s+down|resigns?|departs?|leaves?|exits?)",
                    text
                )
                if match:
                    details.person_name = match.group(1).strip()
                    details.old_role = role
                    details.change_type = "departed"
                    break
        
        # Check for founder
        if "founder" in text.lower() or "co-founder" in text.lower():
            details.is_founder = True
        
        return details
    
    def _extract_partnership_details(
        self, 
        title: str, 
        content: str,
        companies: List[str]
    ) -> PartnershipDetails:
        """Extract partnership details."""
        text = f"{title} {content}"
        
        details = PartnershipDetails()
        details.partner_names = companies[:4]  # Limit to 4 partners
        
        # Detect partnership type
        if "strategic" in text.lower():
            details.partnership_type = "strategic"
        elif "technology" in text.lower() or "technical" in text.lower():
            details.partnership_type = "technology"
        elif "distribution" in text.lower():
            details.partnership_type = "distribution"
        elif "investment" in text.lower():
            details.partnership_type = "investment"
        
        return details
    
    def _extract_layoff_details(
        self, 
        title: str, 
        content: str
    ) -> LayoffDetails:
        """Extract layoff details."""
        text = f"{title} {content}"
        
        details = LayoffDetails()
        
        # Extract headcount
        count_match = re.search(
            r"(?:lay(?:s|ing)?\s+off|cut(?:s|ting)?|reduc(?:es?|ing))\s+(?:about\s+|around\s+|approximately\s+)?([\d,]+)\s*(?:employees?|workers?|jobs?|people|staff)",
            text, re.IGNORECASE
        )
        if count_match:
            try:
                details.headcount = int(count_match.group(1).replace(",", ""))
            except ValueError:
                pass
        
        # Extract percentage
        pct_match = re.search(
            r"(\d+)\s*%\s*(?:of\s+)?(?:its\s+)?(?:workforce|staff|employees)",
            text, re.IGNORECASE
        )
        if pct_match:
            try:
                details.percentage = float(pct_match.group(1))
            except ValueError:
                pass
        
        # Extract reason
        reason_keywords = {
            "restructuring": "restructuring",
            "cost cutting": "cost reduction",
            "downturn": "market conditions",
            "efficiency": "efficiency",
            "reorganization": "reorganization",
        }
        
        for keyword, reason in reason_keywords.items():
            if keyword in text.lower():
                details.reason = reason
                break
        
        return details
    
    def _detect_with_llm(
        self, 
        article: Dict[str, Any]
    ) -> List[BusinessEvent]:
        """
        Use LLM to detect events when pattern matching fails.
        
        Returns list of detected events.
        """
        if not self.llm_client:
            return []
        
        title = article.get("title", "")
        content = article.get("content", "") or article.get("paraphrased_content", "")
        
        system_prompt = """You are an expert at identifying business events from news articles.

Extract business events from the given article. Focus on these event types:
- FUNDING_ROUND: Investment rounds, funding announcements
- ACQUISITION: Company acquisitions, mergers
- PRODUCT_LAUNCH: New product or model releases
- PARTNERSHIP: Strategic partnerships, collaborations
- LEADERSHIP_CHANGE: Executive hires, departures, promotions
- IPO: Public offerings, SPAC mergers
- LAYOFF: Workforce reductions
- PIVOT: Business model changes
- REGULATORY: Government/regulatory actions
- EXPANSION: Geographic or market expansion
- LEGAL: Lawsuits, IP disputes
- SHUTDOWN: Company closures

Return JSON array. For each event found:
{
  "event_type": "FUNDING_ROUND|ACQUISITION|...",
  "entity_name": "Company name",
  "headline": "One line summary",
  "event_date": "YYYY-MM-DD or null",
  "details": {
    // Type-specific fields
    // FUNDING_ROUND: amount_usd, stage, lead_investors
    // ACQUISITION: acquirer, target, deal_value
    // PRODUCT_LAUNCH: product_name, is_beta
    // etc.
  },
  "confidence": "high|medium|low"
}

Return [] if no clear business events found. Only return events you're confident about."""

        user_message = f"""Article:

Title: {title}

Content:
{content[:3000]}

Extract any business events from this article as JSON array:"""

        try:
            response = self.llm_client.chat_structured(
                system_prompt=system_prompt,
                user_message=user_message,
                temperature=0.1
            )
            
            events = []
            
            # Handle both list and dict responses
            if isinstance(response, dict):
                response = [response] if response.get("event_type") else []
            
            for event_data in response:
                try:
                    event_type = BusinessEventType(event_data.get("event_type", "").lower())
                    
                    event = BusinessEvent(
                        event_type=event_type,
                        entity_name=event_data.get("entity_name", ""),
                        entity_id=event_data.get("entity_name", "").lower().replace(" ", "_"),
                        headline=event_data.get("headline", title),
                        summary=event_data.get("headline", ""),
                        details=event_data.get("details", {}),
                    )
                    
                    # Parse date
                    if event_data.get("event_date"):
                        event.event_date = self._parse_date(event_data["event_date"])
                    
                    # Set confidence
                    conf_map = {"high": 0.8, "medium": 0.5, "low": 0.3}
                    event.confidence_score = conf_map.get(
                        event_data.get("confidence", "medium"), 0.5
                    )
                    
                    # Extract type-specific details from LLM response
                    details = event_data.get("details", {})
                    
                    if event_type == BusinessEventType.FUNDING_ROUND:
                        event.funding_details = FundingDetails(
                            amount_usd=details.get("amount_usd"),
                            stage=FundingStage(details.get("stage", "unknown").lower().replace(" ", "_")),
                            lead_investors=details.get("lead_investors", []),
                        )
                    
                    elif event_type == BusinessEventType.ACQUISITION:
                        event.acquisition_details = AcquisitionDetails(
                            acquirer_name=details.get("acquirer", ""),
                            target_name=details.get("target", ""),
                            deal_value_usd=details.get("deal_value"),
                        )
                    
                    elif event_type == BusinessEventType.PRODUCT_LAUNCH:
                        event.product_details = ProductLaunchDetails(
                            product_name=details.get("product_name", ""),
                            is_beta=details.get("is_beta", False),
                        )
                    
                    events.append(event)
                    
                except (ValueError, KeyError) as e:
                    logger.debug(f"Failed to parse LLM event: {e}")
                    continue
            
            return events
            
        except Exception as e:
            logger.error(f"LLM event detection failed: {e}")
            return []
    
    def _enrich_event_with_llm(
        self, 
        event: BusinessEvent, 
        article: Dict[str, Any]
    ) -> None:
        """
        Use LLM to enrich an event with additional details.
        
        Modifies event in place.
        """
        if not self.llm_client:
            return
        
        # Only enrich if we're missing key details
        if event.event_type == BusinessEventType.FUNDING_ROUND:
            if event.funding_details and event.funding_details.amount_usd:
                return  # Already have details
        elif event.event_type == BusinessEventType.ACQUISITION:
            if event.acquisition_details and event.acquisition_details.acquirer_name:
                return
        else:
            return  # Only enrich funding and acquisition for now
        
        # Similar to _detect_with_llm but focused on single event type
        # Implementation would go here but skipping for efficiency
        pass
    
    def _deduplicate_events(
        self,
        new_events: List[BusinessEvent],
        existing_events: List[BusinessEvent]
    ) -> List[BusinessEvent]:
        """
        Deduplicate new events against existing ones.
        
        If duplicate found, merges into existing event.
        Returns only truly new events.
        """
        unique_events = []
        
        for new_event in new_events:
            is_duplicate = False
            
            for existing in existing_events:
                if new_event.is_similar_to(existing):
                    # Merge into existing event
                    existing.merge_with(new_event)
                    is_duplicate = True
                    logger.debug(
                        f"Merged duplicate event: {new_event.headline[:50]} -> {existing.event_id}"
                    )
                    break
            
            if not is_duplicate:
                unique_events.append(new_event)
        
        return unique_events
    
    def _parse_date(self, date_str: Any) -> Optional[datetime]:
        """Parse date string to datetime."""
        if not date_str:
            return None
        
        if isinstance(date_str, datetime):
            return date_str
        
        date_str = str(date_str)
        
        formats = [
            "%Y-%m-%d",
            "%Y-%m-%dT%H:%M:%S",
            "%Y-%m-%dT%H:%M:%SZ",
            "%Y-%m-%dT%H:%M:%S.%f",
            "%Y-%m-%dT%H:%M:%S.%fZ",
            "%B %d, %Y",
            "%b %d, %Y",
            "%d %B %Y",
            "%d %b %Y",
        ]
        
        for fmt in formats:
            try:
                return datetime.strptime(date_str.split("+")[0].split("Z")[0], fmt)
            except ValueError:
                continue
        
        return None
    
    def get_source_credibility(self, source_name: str) -> float:
        """
        Get credibility score for a source.
        
        Based on source_credibility config in patterns.
        """
        source_lower = source_name.lower().replace(" ", "")
        cred_config = self.patterns.get("source_credibility", {})
        
        for tier, config in cred_config.items():
            if tier == "default":
                continue
            sources = config.get("sources", [])
            if any(s in source_lower for s in sources):
                return config.get("score", 0.7)
        
        return cred_config.get("default", {}).get("score", 0.7)


def detect_events_batch(
    articles: List[Dict[str, Any]],
    llm_client=None,
    existing_events: Optional[List[BusinessEvent]] = None
) -> Tuple[List[BusinessEvent], Dict[str, Any]]:
    """
    Detect events from a batch of articles.
    
    Handles deduplication across the batch.
    
    Args:
        articles: List of article dictionaries
        llm_client: Optional LLM client
        existing_events: Existing events for dedup
    
    Returns:
        Tuple of (events list, stats dict)
    """
    detector = EventDetector(llm_client=llm_client)
    
    all_events = existing_events or []
    new_events = []
    stats = {
        "articles_processed": 0,
        "events_detected": 0,
        "events_merged": 0,
        "by_type": {},
    }
    
    for article in articles:
        stats["articles_processed"] += 1
        
        events = detector.detect_events(article, existing_events=all_events)
        
        for event in events:
            stats["events_detected"] += 1
            
            # Track by type
            event_type = event.event_type.value
            stats["by_type"][event_type] = stats["by_type"].get(event_type, 0) + 1
            
            # Check for merge with batch events
            merged = False
            for existing in new_events:
                if event.is_similar_to(existing):
                    existing.merge_with(event)
                    stats["events_merged"] += 1
                    merged = True
                    break
            
            if not merged:
                new_events.append(event)
                all_events.append(event)
    
    logger.info(
        f"Batch detection: {stats['articles_processed']} articles → "
        f"{len(new_events)} unique events ({stats['events_merged']} merged)"
    )
    
    return new_events, stats
