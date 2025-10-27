"""
Entity Extractor Utility - spaCy Primary + Claude Fallback

Extracts named entities (companies, models, topics, people) from text.
- Primary: spaCy NER (instant, free, local)
- Fallback: Claude LLM if spaCy confidence < 0.7
- Merges results when using fallback for maximum coverage

This is the foundation for future chatbot semantic search.
"""

import re
import json
from typing import Dict, List, Set, Any, Optional, Tuple
from loguru import logger

try:
    import spacy
    SPACY_AVAILABLE = True
except ImportError:
    SPACY_AVAILABLE = False
    logger.warning("spaCy not installed. Install with: pip install spacy")
    logger.warning("Then download models: python -m spacy download en_core_web_md")

from utils.llm_client_enhanced import LLMClient


class EntityExtractor:
    """Extracts and normalizes entities from article text using spaCy + Claude fallback"""

    def __init__(self, llm_client: LLMClient = None, checkpoint_manager: Optional[Any] = None):
        """
        Initialize entity extractor

        Args:
            llm_client: LLM client instance (creates new if None)
            checkpoint_manager: Optional checkpoint manager for saving results
        """
        self.llm_client = llm_client or LLMClient()
        self.checkpoint_manager = checkpoint_manager

        # Initialize spaCy if available
        self.nlp = None
        if SPACY_AVAILABLE:
            try:
                self.nlp = spacy.load("en_core_web_md")
                logger.info("spaCy NER model loaded (en_core_web_md)")
            except OSError:
                logger.warning("spaCy model not found. Download with:")
                logger.warning("python -m spacy download en_core_web_md")
                SPACY_AVAILABLE = False

        # Build normalization maps for common entities
        self._build_normalization_maps()

        logger.info(f"Entity extractor initialized (spaCy: {SPACY_AVAILABLE})")

    def _build_normalization_maps(self):
        """Build maps for entity normalization (aliases)"""

        # Common company name variations
        self.company_aliases = {
            'openai': ['open ai', 'open-ai', 'open.ai'],
            'anthropic': ['anthropic ai'],
            'google': ['google ai', 'deepmind'],
            'meta': ['facebook'],
            'microsoft': ['microsoft ai'],
        }

        # Common model name variations
        self.model_aliases = {
            'gpt-4': ['gpt4', 'gpt 4', 'gpt4-turbo'],
            'gpt-3.5': ['gpt3.5', 'gpt 3.5'],
            'claude': ['claude ai'],
            'claude 3.5': ['claude 3.5 sonnet', 'claude 3.5 opus'],
            'llama': ['llama 2', 'llama2', 'llama 3'],
            'gemini': ['bard'],
        }

        # Build reverse lookup (alias -> canonical)
        self.alias_to_canonical = {}
        for canonical, aliases in self.company_aliases.items():
            self.alias_to_canonical[canonical] = canonical
            for alias in aliases:
                self.alias_to_canonical[alias] = canonical

        for canonical, aliases in self.model_aliases.items():
            self.alias_to_canonical[canonical] = canonical
            for alias in aliases:
                self.alias_to_canonical[alias] = canonical

    def extract_entities(
        self,
        text: str,
        article_id: Optional[str] = None,
        article_data: Optional[Dict[str, Any]] = None,
        original_text: Optional[str] = None
    ) -> Dict[str, List[str]]:
        """
        Extract entities from text using spaCy primary + Claude fallback

        Args:
            text: Paraphrased text to extract entities from (~500-700 chars)
            article_id: Optional article ID for checkpointing
            article_data: Optional article data to save in checkpoint
            original_text: Optional original article content for fallback verification

        Returns:
            Dictionary with entity categories:
            {
                "companies": ["OpenAI", "Anthropic"],
                "models": ["GPT-4", "Claude"],
                "topics": ["AI Safety", "LLM Performance"],
                "business_models": ["Subscription", "API pricing"],
                "people": ["Sam Altman"]
            }
        """
        # Try spaCy extraction first (fast, free)
        spacy_entities, spacy_confidence = self._extract_with_spacy(text)

        # If spaCy confidence is low, use Claude and merge results
        if spacy_confidence < 0.7:
            logger.debug(f"spaCy confidence low ({spacy_confidence:.2f}), using Claude fallback")

            claude_entities = self._extract_with_claude(
                text=text,
                original_text=original_text,
                use_original_if_needed=True
            )

            # Merge spaCy + Claude results
            entities = self._merge_entities(spacy_entities, claude_entities)
            extraction_method = "claude_fallback"
        else:
            entities = spacy_entities
            extraction_method = "spacy"

        # Normalize extracted entities
        entities = self._normalize_entities(entities)

        # Log and checkpoint
        if self.checkpoint_manager and article_id and article_data:
            self.checkpoint_manager.save_article_entities(
                article_id,
                article_data,
                entities,
                provider_used=extraction_method
            )
            logger.debug(
                f"[{extraction_method.upper()}] Article {article_id}: "
                f"{sum(len(v) for v in entities.values())} entities"
            )
        else:
            logger.debug(f"Extracted {sum(len(v) for v in entities.values())} entities ({extraction_method})")

        return entities

    def _extract_with_spacy(self, text: str) -> Tuple[Dict[str, List[str]], float]:
        """
        Extract entities using spaCy NER

        Args:
            text: Text to extract from

        Returns:
            Tuple of (entities_dict, confidence_score)
        """
        if not SPACY_AVAILABLE or not self.nlp:
            return self._empty_entities(), 0.0

        try:
            doc = self.nlp(text[:2000])  # Limit to 2000 chars for speed

            entities = {
                "companies": [],
                "models": [],
                "topics": [],
                "business_models": [],
                "people": []
            }

            # Extract using spaCy NER labels
            for ent in doc.ents:
                text_lower = ent.text.lower()

                # Companies / ORG
                if ent.label_ in ['ORG', 'PRODUCT']:
                    if ent.text not in entities["companies"]:
                        entities["companies"].append(ent.text)

                # People / PERSON
                elif ent.label_ == 'PERSON':
                    if ent.text not in entities["people"]:
                        entities["people"].append(ent.text)

            # Post-process: Identify models and topics from noun chunks
            for chunk in doc.noun_chunks:
                chunk_lower = chunk.text.lower()

                # Detect models (contains: gpt, claude, llama, bert, gemini, etc.)
                model_keywords = ['gpt', 'claude', 'llama', 'bert', 'gemini', 'palm', 'alpaca', 'mistral']
                if any(kw in chunk_lower for kw in model_keywords):
                    if chunk.text not in entities["models"]:
                        entities["models"].append(chunk.text)

                # Detect business models (subscription, pricing, api, licensing, etc.)
                business_keywords = ['subscription', 'pricing', 'api', 'licensing', 'free tier', 'enterprise', 'saas', 'aaa', 'profit']
                if any(kw in chunk_lower for kw in business_keywords):
                    if chunk.text not in entities["business_models"]:
                        entities["business_models"].append(chunk.text)

                # Detect topics (safety, performance, reasoning, benchmarks, etc.)
                topic_keywords = ['safety', 'performance', 'reasoning', 'benchmark', 'accuracy', 'latency', 'cost', 'reliability']
                if any(kw in chunk_lower for kw in topic_keywords):
                    if chunk.text not in entities["topics"]:
                        entities["topics"].append(chunk.text)

            # Calculate confidence based on entity count
            total_entities = sum(len(v) for v in entities.values())
            confidence = min(1.0, total_entities / 8.0)  # Max confidence at 8+ entities

            return entities, confidence

        except Exception as e:
            logger.error(f"spaCy extraction error: {e}")
            return self._empty_entities(), 0.0

    def _extract_with_claude(
        self,
        text: str,
        original_text: Optional[str] = None,
        use_original_if_needed: bool = False
    ) -> Dict[str, List[str]]:
        """
        Extract entities using Claude LLM (fallback)

        Args:
            text: Paraphrased text (primary)
            original_text: Original article content (for fallback check)
            use_original_if_needed: If True, also check original text for additional entities

        Returns:
            Dictionary of extracted entities
        """
        try:
            # Start with paraphrased text
            extraction_text = text[:2000]

            # If original available and flagged, use first 2000 chars of original too
            additional_context = ""
            if use_original_if_needed and original_text:
                original_snippet = original_text[:1500]
                additional_context = f"\n\n**Additional context from original source:**\n{original_snippet}"

            system_prompt = self._build_claude_extraction_prompt()
            user_message = f"""Extract entities from this article paraphrase:

{extraction_text}{additional_context}

Return JSON format with extracted entities."""

            response = self.llm_client.chat_structured(
                system_prompt=system_prompt,
                user_message=user_message,
                temperature=0.1  # Low temp for consistent extraction
            )

            # Parse response
            if isinstance(response, dict):
                entities = response
            else:
                # Try to parse as JSON
                entities = json.loads(str(response))

            # Ensure all keys exist
            for key in ["companies", "models", "topics", "business_models", "people"]:
                if key not in entities:
                    entities[key] = []

            return entities

        except Exception as e:
            logger.error(f"Claude extraction fallback error: {e}")
            return self._empty_entities()

    def _merge_entities(
        self,
        entities1: Dict[str, List[str]],
        entities2: Dict[str, List[str]]
    ) -> Dict[str, List[str]]:
        """
        Merge two entity dictionaries, removing duplicates

        Args:
            entities1: First entity dictionary (spaCy results)
            entities2: Second entity dictionary (Claude results)

        Returns:
            Merged entity dictionary
        """
        merged = {}

        for key in ["companies", "models", "topics", "business_models", "people"]:
            list1 = entities1.get(key, [])
            list2 = entities2.get(key, [])

            # Combine and deduplicate (case-insensitive)
            combined = []
            seen = set()

            for entity in list1 + list2:
                entity_lower = entity.lower().strip()
                if entity_lower not in seen:
                    combined.append(entity)
                    seen.add(entity_lower)

            merged[key] = combined[:10]  # Limit to 10 per category

        return merged

    def _normalize_entities(self, entities: Dict[str, List[str]]) -> Dict[str, List[str]]:
        """
        Normalize extracted entities to canonical forms

        Args:
            entities: Raw extracted entities

        Returns:
            Normalized entities
        """
        normalized = {}

        for entity_type, entity_list in entities.items():
            normalized_list = []

            for entity in entity_list:
                if not entity:
                    continue

                # Normalize to canonical form
                canonical = self.normalize_entity(entity)
                if canonical and canonical not in normalized_list:
                    normalized_list.append(canonical)

            normalized[entity_type] = normalized_list[:10]  # Limit to 10 per category

        return normalized

    def normalize_entity(self, entity: str) -> str:
        """
        Normalize an entity to its canonical form

        Args:
            entity: Entity string to normalize

        Returns:
            Canonical form of entity
        """
        if not entity:
            return ""

        # Convert to lowercase for matching
        entity_lower = entity.lower().strip()

        # Remove extra punctuation and spaces
        entity_lower = re.sub(r'[^\w\s\-]', '', entity_lower)
        entity_lower = re.sub(r'\s+', ' ', entity_lower)

        # Look up in alias map
        if entity_lower in self.alias_to_canonical:
            return self.alias_to_canonical[entity_lower]

        # Return original if no alias found (with normalized spacing)
        return entity.strip()

    def calculate_similarity(
        self,
        entities1: Dict[str, List[str]],
        entities2: Dict[str, List[str]]
    ) -> float:
        """
        Calculate Jaccard similarity between two entity sets

        Args:
            entities1: First entity dictionary
            entities2: Second entity dictionary

        Returns:
            Similarity score between 0 and 1
        """
        # Combine all entities into sets
        set1 = set()
        set2 = set()

        for entity_type in entities1.keys():
            for entity in entities1.get(entity_type, []):
                set1.add(self.normalize_entity(entity).lower())
            for entity in entities2.get(entity_type, []):
                set2.add(self.normalize_entity(entity).lower())

        # Calculate Jaccard similarity
        if not set1 and not set2:
            return 0.0

        intersection = len(set1 & set2)
        union = len(set1 | set2)

        similarity = intersection / union if union > 0 else 0.0

        return similarity

    def extract_entities_batch(
        self,
        articles: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Extract entities from multiple articles

        Args:
            articles: List of article dictionaries (with paraphrased_content)

        Returns:
            Articles with 'searchable_entities' field added
        """
        logger.info(f"Extracting entities from {len(articles)} articles (spaCy + fallback)...")

        for i, article in enumerate(articles, 1):
            try:
                # Use paraphrased content as primary (already 500-700 chars, optimized)
                paraphrased_text = article.get('paraphrased_content', '')
                original_text = article.get('content', '')

                if not paraphrased_text:
                    logger.debug(f"Article {i}/{len(articles)}: No paraphrased content, skipping")
                    article['searchable_entities'] = self._empty_entities()
                    continue

                # Extract entities
                entities = self.extract_entities(
                    text=paraphrased_text,
                    original_text=original_text if original_text else None
                )

                article['searchable_entities'] = entities

                logger.debug(
                    f"Article {i}/{len(articles)}: {sum(len(v) for v in entities.values())} entities"
                )

            except Exception as e:
                logger.error(f"Failed to extract entities from article {i}: {e}")
                article['searchable_entities'] = self._empty_entities()

        logger.info("Entity extraction batch complete")
        return articles

    def _empty_entities(self) -> Dict[str, List[str]]:
        """Return empty entity dictionary"""
        return {
            "companies": [],
            "models": [],
            "topics": [],
            "business_models": [],
            "people": []
        }

    def _build_claude_extraction_prompt(self) -> str:
        """Build system prompt for Claude entity extraction"""
        return """You are an expert at extracting named entities from AI industry news.

Extract the following entity types from the given text:

1. **Companies** (AI companies, tech companies, startups, organizations)
   Examples: OpenAI, Anthropic, Google, Microsoft, Meta

2. **Models** (AI models, language models, products)
   Examples: GPT-4, Claude 3.5, Llama, Gemini, Mistral

3. **Topics** (AI research areas, capabilities, challenges)
   Examples: Reasoning, Safety, Performance, Benchmarks, Multimodal

4. **Business Models** (How companies make money, pricing models, licensing)
   Examples: API Pricing, Subscription, Enterprise Licensing, Free Tier

5. **People** (Founders, CEOs, researchers, notable figures)
   Examples: Sam Altman, Dario Amodei, Yann LeCun

Return ONLY valid JSON with these keys:
{
  "companies": ["company1", "company2"],
  "models": ["model1", "model2"],
  "topics": ["topic1", "topic2"],
  "business_models": ["model1", "model2"],
  "people": ["person1", "person2"]
}

Rules:
- Only extract entities that clearly appear in the text
- Keep original capitalization
- Maximum 10 entities per category
- Return empty arrays for missing categories
- Return ONLY the JSON, no other text"""
