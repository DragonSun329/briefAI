"""
Bucket Tagger

Tags entities (repos, companies, models) to trend buckets using:
1. Keyword matching rules
2. GitHub topics / HuggingFace tasks
3. LLM-based classification for ambiguous cases

The bucket taxonomy represents AI trend themes that can be tracked
across different signal sources (GitHub, VC, SEC).
"""

import json
import re
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple, Set
from dataclasses import dataclass, field
from functools import lru_cache


@dataclass
class BucketMatch:
    """Result of matching an entity to buckets."""
    bucket_id: str
    bucket_name: str
    confidence: float  # 0-1
    match_reason: str  # "keyword", "topic", "task", "llm"
    matched_terms: List[str] = field(default_factory=list)


@dataclass
class TrendBucket:
    """A trend bucket/category for analysis."""
    id: str
    name: str
    description: str
    keywords: List[str]
    github_topics: List[str]
    hf_tasks: List[str]

    def __hash__(self):
        return hash(self.id)


class BucketTagger:
    """
    Tags entities to AI trend buckets.

    Usage:
        tagger = BucketTagger()
        matches = tagger.tag_entity(
            name="langchain",
            description="Building applications with LLMs",
            topics=["llm", "ai-agents"],
            entity_type="repo"
        )
    """

    def __init__(self, config_path: Optional[Path] = None, mapping_path: Optional[Path] = None):
        """
        Initialize tagger with bucket taxonomy.

        Args:
            config_path: Path to trend_buckets.json. Uses default if None.
            mapping_path: Path to company_bucket_mapping.json. Uses default if None.
        """
        if config_path is None:
            config_path = Path(__file__).parent.parent / "config" / "trend_buckets.json"
        if mapping_path is None:
            mapping_path = Path(__file__).parent.parent / "config" / "company_bucket_mapping.json"

        self.config_path = config_path
        self.mapping_path = mapping_path
        self.buckets: Dict[str, TrendBucket] = {}
        self._load_buckets()

        # Build reverse indices for fast lookup
        self._keyword_index: Dict[str, Set[str]] = {}  # keyword -> bucket_ids
        self._topic_index: Dict[str, Set[str]] = {}    # topic -> bucket_ids
        self._task_index: Dict[str, Set[str]] = {}     # task -> bucket_ids
        self._company_index: Dict[str, str] = {}       # normalized company name -> bucket_id
        self._build_indices()
        self._load_company_mapping()

    def _load_buckets(self):
        """Load bucket taxonomy from config."""
        with open(self.config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)

        for bucket_data in config.get("buckets", []):
            bucket = TrendBucket(
                id=bucket_data["id"],
                name=bucket_data["name"],
                description=bucket_data["description"],
                keywords=bucket_data.get("keywords", []),
                github_topics=bucket_data.get("github_topics", []),
                hf_tasks=bucket_data.get("hf_tasks", []),
            )
            self.buckets[bucket.id] = bucket

    def _build_indices(self):
        """Build reverse indices for fast matching."""
        for bucket_id, bucket in self.buckets.items():
            # Keyword index (lowercase, stemmed)
            for keyword in bucket.keywords:
                key = self._normalize_keyword(keyword)
                if key not in self._keyword_index:
                    self._keyword_index[key] = set()
                self._keyword_index[key].add(bucket_id)

            # GitHub topic index
            for topic in bucket.github_topics:
                key = topic.lower()
                if key not in self._topic_index:
                    self._topic_index[key] = set()
                self._topic_index[key].add(bucket_id)

            # HuggingFace task index
            for task in bucket.hf_tasks:
                key = task.lower()
                if key not in self._task_index:
                    self._task_index[key] = set()
                self._task_index[key].add(bucket_id)

    def _normalize_keyword(self, keyword: str) -> str:
        """Normalize keyword for matching."""
        return keyword.lower().strip()

    def _normalize_company_name(self, name: str) -> str:
        """Normalize company name for lookup."""
        # Remove common suffixes and normalize
        name = name.lower().strip()
        # Remove common company suffixes
        for suffix in [" ai", " inc", " inc.", " llc", " ltd", " corp", " labs"]:
            if name.endswith(suffix):
                name = name[:-len(suffix)]
        return name.strip()

    def _load_company_mapping(self):
        """Load company-to-bucket mapping from config."""
        if not self.mapping_path.exists():
            return

        try:
            with open(self.mapping_path, 'r', encoding='utf-8') as f:
                config = json.load(f)

            mappings = config.get("mappings", {})
            for bucket_id, companies in mappings.items():
                if bucket_id not in self.buckets:
                    continue
                for company in companies:
                    # Index both original and normalized names
                    normalized = self._normalize_company_name(company)
                    self._company_index[normalized] = bucket_id
                    # Also index exact lowercase match
                    self._company_index[company.lower()] = bucket_id
        except Exception as e:
            print(f"Warning: Could not load company mapping: {e}")

    def _lookup_company_mapping(self, name: str) -> Optional[str]:
        """Look up company in manual mapping, returns bucket_id if found."""
        # Try exact match first
        name_lower = name.lower()
        if name_lower in self._company_index:
            return self._company_index[name_lower]

        # Try normalized match
        normalized = self._normalize_company_name(name)
        if normalized in self._company_index:
            return self._company_index[normalized]

        return None

    def tag_entity(
        self,
        name: str,
        description: Optional[str] = None,
        topics: Optional[List[str]] = None,
        tasks: Optional[List[str]] = None,
        tags: Optional[List[str]] = None,
        entity_type: str = "unknown",
        max_buckets: int = 3,
        min_confidence: float = 0.3,
    ) -> List[BucketMatch]:
        """
        Tag an entity to trend buckets.

        Args:
            name: Entity name (repo name, company name, model name)
            description: Entity description or README excerpt
            topics: GitHub topics or similar categorization
            tasks: HuggingFace tasks
            tags: Additional tags/labels
            entity_type: "repo", "company", "model", "space"
            max_buckets: Maximum number of buckets to return
            min_confidence: Minimum confidence threshold

        Returns:
            List of BucketMatch objects, sorted by confidence
        """
        matches: Dict[str, BucketMatch] = {}

        # Combine text for keyword matching
        text_parts = [name]
        if description:
            text_parts.append(description)
        combined_text = " ".join(text_parts).lower()

        # 1. Match by GitHub topics (highest confidence for explicit categorization)
        if topics:
            for topic in topics:
                topic_lower = topic.lower()
                if topic_lower in self._topic_index:
                    for bucket_id in self._topic_index[topic_lower]:
                        self._add_match(
                            matches, bucket_id,
                            confidence=0.9,
                            reason="topic",
                            term=topic
                        )

        # 2. Match by HuggingFace tasks
        if tasks:
            for task in tasks:
                task_lower = task.lower()
                if task_lower in self._task_index:
                    for bucket_id in self._task_index[task_lower]:
                        self._add_match(
                            matches, bucket_id,
                            confidence=0.85,
                            reason="task",
                            term=task
                        )

        # 3. Match by keywords in name/description
        for keyword, bucket_ids in self._keyword_index.items():
            # Check for keyword match (word boundary aware)
            pattern = r'\b' + re.escape(keyword) + r'\b'
            if re.search(pattern, combined_text):
                for bucket_id in bucket_ids:
                    # Higher confidence for name matches
                    conf = 0.8 if keyword in name.lower() else 0.6
                    self._add_match(
                        matches, bucket_id,
                        confidence=conf,
                        reason="keyword",
                        term=keyword
                    )

        # 4. Match by tags
        if tags:
            for tag in tags:
                tag_lower = tag.lower()
                # Check if tag matches any keyword
                if tag_lower in self._keyword_index:
                    for bucket_id in self._keyword_index[tag_lower]:
                        self._add_match(
                            matches, bucket_id,
                            confidence=0.7,
                            reason="tag",
                            term=tag
                        )

        # 5. Fallback: Use manual company-to-bucket mapping (for companies without descriptions)
        if not matches and entity_type == "company":
            bucket_id = self._lookup_company_mapping(name)
            if bucket_id:
                self._add_match(
                    matches, bucket_id,
                    confidence=0.85,  # High confidence for manual mapping
                    reason="mapping",
                    term=name
                )

        # Filter and sort
        result = [
            m for m in matches.values()
            if m.confidence >= min_confidence
        ]
        result.sort(key=lambda x: x.confidence, reverse=True)

        return result[:max_buckets]

    def _add_match(
        self,
        matches: Dict[str, BucketMatch],
        bucket_id: str,
        confidence: float,
        reason: str,
        term: str
    ):
        """Add or update a bucket match."""
        bucket = self.buckets.get(bucket_id)
        if not bucket:
            return

        if bucket_id in matches:
            # Update existing match - increase confidence, add term
            existing = matches[bucket_id]
            # Boost confidence for multiple matches, cap at 0.95
            existing.confidence = min(0.95, existing.confidence + confidence * 0.2)
            if term not in existing.matched_terms:
                existing.matched_terms.append(term)
        else:
            matches[bucket_id] = BucketMatch(
                bucket_id=bucket_id,
                bucket_name=bucket.name,
                confidence=confidence,
                match_reason=reason,
                matched_terms=[term]
            )

    def tag_batch(
        self,
        entities: List[Dict[str, Any]],
        max_buckets: int = 3
    ) -> Dict[str, List[BucketMatch]]:
        """
        Tag multiple entities.

        Args:
            entities: List of dicts with keys: name, description, topics, tasks, tags

        Returns:
            Dict mapping entity name to list of BucketMatch
        """
        results = {}
        for entity in entities:
            name = entity.get("name", "")
            matches = self.tag_entity(
                name=name,
                description=entity.get("description"),
                topics=entity.get("topics"),
                tasks=entity.get("tasks"),
                tags=entity.get("tags"),
                entity_type=entity.get("entity_type", "unknown"),
                max_buckets=max_buckets
            )
            results[name] = matches
        return results

    def get_bucket(self, bucket_id: str) -> Optional[TrendBucket]:
        """Get bucket by ID."""
        return self.buckets.get(bucket_id)

    def get_all_buckets(self) -> List[TrendBucket]:
        """Get all buckets."""
        return list(self.buckets.values())

    def suggest_buckets_for_text(
        self,
        text: str,
        top_n: int = 5
    ) -> List[Tuple[str, float]]:
        """
        Suggest buckets based on free text (for search/discovery).

        Returns:
            List of (bucket_id, relevance_score) tuples
        """
        text_lower = text.lower()
        scores: Dict[str, float] = {}

        for keyword, bucket_ids in self._keyword_index.items():
            if keyword in text_lower:
                for bucket_id in bucket_ids:
                    scores[bucket_id] = scores.get(bucket_id, 0) + 1

        # Normalize by bucket keyword count
        for bucket_id in scores:
            bucket = self.buckets[bucket_id]
            scores[bucket_id] /= max(1, len(bucket.keywords) ** 0.5)

        sorted_scores = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        return sorted_scores[:top_n]


def tag_github_repo(repo_data: Dict[str, Any]) -> List[BucketMatch]:
    """
    Convenience function to tag a GitHub repo.

    Args:
        repo_data: Dict with name, description, topics, language, etc.
    """
    tagger = BucketTagger()
    return tagger.tag_entity(
        name=repo_data.get("name", ""),
        description=repo_data.get("description"),
        topics=repo_data.get("topics", []),
        entity_type="repo"
    )


def tag_huggingface_model(model_data: Dict[str, Any]) -> List[BucketMatch]:
    """
    Convenience function to tag a HuggingFace model.

    Args:
        model_data: Dict with name, task, tags, etc.
    """
    tagger = BucketTagger()

    # Extract task from metrics if available
    tasks = []
    task = model_data.get("task") or model_data.get("metrics", {}).get("task")
    if task:
        tasks.append(task)

    return tagger.tag_entity(
        name=model_data.get("name", model_data.get("model_id", "")),
        description=model_data.get("description"),
        tasks=tasks,
        tags=model_data.get("tags", model_data.get("metrics", {}).get("tags", [])),
        entity_type="model"
    )


def tag_company(company_data: Dict[str, Any]) -> List[BucketMatch]:
    """
    Convenience function to tag a company.

    Args:
        company_data: Dict with name, description, categories, etc.
    """
    tagger = BucketTagger()
    return tagger.tag_entity(
        name=company_data.get("name", ""),
        description=company_data.get("description"),
        tags=company_data.get("categories", []),
        entity_type="company"
    )


if __name__ == "__main__":
    # Test the tagger
    print("=" * 60)
    print("BUCKET TAGGER TEST")
    print("=" * 60)

    tagger = BucketTagger()
    print(f"Loaded {len(tagger.buckets)} buckets")
    print()

    # Test cases
    test_cases = [
        {
            "name": "langchain",
            "description": "Building applications with LLMs through composability",
            "topics": ["llm", "ai-agents", "langchain"],
            "entity_type": "repo"
        },
        {
            "name": "vllm",
            "description": "High-throughput and memory-efficient inference engine for LLMs",
            "topics": ["inference", "llm", "serving"],
            "entity_type": "repo"
        },
        {
            "name": "sentence-transformers/all-MiniLM-L6-v2",
            "description": "Sentence similarity model",
            "tasks": ["sentence-similarity"],
            "entity_type": "model"
        },
        {
            "name": "Anthropic",
            "description": "AI safety company building Claude",
            "tags": ["ai", "safety", "llm"],
            "entity_type": "company"
        },
        {
            "name": "Scale AI",
            "description": "Data labeling and AI infrastructure",
            "tags": ["data", "labeling", "ai"],
            "entity_type": "company"
        },
    ]

    for case in test_cases:
        print(f"Entity: {case['name']}")
        matches = tagger.tag_entity(**case)
        if matches:
            for m in matches:
                print(f"  -> {m.bucket_name} ({m.confidence:.0%}) via {m.match_reason}: {m.matched_terms}")
        else:
            print("  -> No matches")
        print()
