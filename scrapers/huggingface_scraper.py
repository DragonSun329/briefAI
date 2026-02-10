"""
HuggingFace Trending Scraper

Scrapes trending models and spaces from HuggingFace Hub.
These represent technical significance - developer/researcher adoption.

Data collected:
- Models: name, downloads, likes, task type, author, tags
- Spaces: name, likes, sdk, author, hardware

Output: data/alternative_signals/huggingface_trending_YYYY-MM-DD.json
"""

import requests
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field, asdict
from datetime import date, datetime
from pathlib import Path
import json
import time


@dataclass
class HFModel:
    """HuggingFace model data."""
    model_id: str                    # e.g., "meta-llama/Llama-3.1-8B"
    author: str                      # e.g., "meta-llama"
    name: str                        # e.g., "Llama-3.1-8B"
    downloads: int = 0               # All-time downloads
    downloads_month: int = 0         # Last 30 days
    likes: int = 0
    task: Optional[str] = None       # e.g., "text-generation"
    tags: List[str] = field(default_factory=list)
    library: Optional[str] = None    # e.g., "transformers"
    created_at: Optional[str] = None
    last_modified: Optional[str] = None
    private: bool = False


@dataclass
class HFSpace:
    """HuggingFace space (demo app) data."""
    space_id: str                    # e.g., "stabilityai/stable-diffusion"
    author: str
    name: str
    likes: int = 0
    sdk: Optional[str] = None        # "gradio", "streamlit", "docker"
    hardware: Optional[str] = None   # "cpu-basic", "t4-medium", etc.
    tags: List[str] = field(default_factory=list)
    created_at: Optional[str] = None
    last_modified: Optional[str] = None


@dataclass
class TrendingSignal:
    """Unified signal format for storage."""
    name: str
    source_type: str = "huggingface"
    signal_type: str = "trending"
    entity_type: str = "technology"   # models/spaces are technologies
    description: Optional[str] = None
    url: str = ""
    category: str = ""               # "models" or "spaces"
    metrics: Dict[str, Any] = field(default_factory=dict)
    author: Optional[str] = None
    date_observed: str = field(default_factory=lambda: date.today().isoformat())


class HuggingFaceScraper:
    """
    Scraper for HuggingFace Hub trending content.

    Uses the HuggingFace Hub API which is free and doesn't require auth
    for public data.
    """

    BASE_URL = "https://huggingface.co/api"

    def __init__(self, api_token: Optional[str] = None):
        """
        Initialize scraper.

        Args:
            api_token: Optional HF API token for higher rate limits
        """
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (compatible; BriefAI/1.0)"
        })
        if api_token:
            self.session.headers["Authorization"] = f"Bearer {api_token}"

    def get_trending_models(
        self,
        limit: int = 100,
        task: Optional[str] = None,
        sort: str = "downloads",
        direction: int = -1
    ) -> List[HFModel]:
        """
        Fetch trending/popular models from HuggingFace.

        Args:
            limit: Max number of models to fetch
            task: Filter by task (e.g., "text-generation", "image-classification")
            sort: Sort field ("downloads", "likes", "lastModified")
            direction: -1 for descending, 1 for ascending
        """
        models = []

        params = {
            "limit": min(limit, 100),  # API max is 100 per request
            "sort": sort,
            "direction": direction,
            "full": "true",  # Get full model info
        }

        if task:
            params["filter"] = task

        try:
            print(f"Fetching top {limit} models (sorted by {sort})...")

            # Paginate if needed
            offset = 0
            while len(models) < limit:
                params["offset"] = offset

                response = self.session.get(
                    f"{self.BASE_URL}/models",
                    params=params,
                    timeout=30
                )
                response.raise_for_status()
                data = response.json()

                if not data:
                    break

                for item in data:
                    model = HFModel(
                        model_id=item.get("id", ""),
                        author=item.get("author", item.get("id", "").split("/")[0] if "/" in item.get("id", "") else ""),
                        name=item.get("id", "").split("/")[-1] if "/" in item.get("id", "") else item.get("id", ""),
                        downloads=item.get("downloads", 0),
                        downloads_month=item.get("downloadsAllTime", item.get("downloads", 0)),
                        likes=item.get("likes", 0),
                        task=item.get("pipeline_tag"),
                        tags=item.get("tags", []),
                        library=item.get("library_name"),
                        created_at=item.get("createdAt"),
                        last_modified=item.get("lastModified"),
                        private=item.get("private", False),
                    )
                    models.append(model)

                offset += len(data)

                if len(data) < params["limit"]:
                    break

                time.sleep(0.5)  # Rate limiting

            print(f"  Found {len(models)} models")
            return models[:limit]

        except requests.RequestException as e:
            print(f"  Error fetching models: {e}")
            return models

    def get_trending_spaces(
        self,
        limit: int = 100,
        sort: str = "likes",
        direction: int = -1
    ) -> List[HFSpace]:
        """
        Fetch trending/popular spaces from HuggingFace.

        Args:
            limit: Max number of spaces to fetch
            sort: Sort field ("likes", "lastModified")
            direction: -1 for descending
        """
        spaces = []

        params = {
            "limit": min(limit, 100),
            "sort": sort,
            "direction": direction,
            "full": "true",
        }

        try:
            print(f"Fetching top {limit} spaces (sorted by {sort})...")

            offset = 0
            while len(spaces) < limit:
                params["offset"] = offset

                response = self.session.get(
                    f"{self.BASE_URL}/spaces",
                    params=params,
                    timeout=30
                )
                response.raise_for_status()
                data = response.json()

                if not data:
                    break

                for item in data:
                    space = HFSpace(
                        space_id=item.get("id", ""),
                        author=item.get("author", item.get("id", "").split("/")[0] if "/" in item.get("id", "") else ""),
                        name=item.get("id", "").split("/")[-1] if "/" in item.get("id", "") else item.get("id", ""),
                        likes=item.get("likes", 0),
                        sdk=item.get("sdk"),
                        hardware=item.get("runtime", {}).get("hardware") if item.get("runtime") else None,
                        tags=item.get("tags", []),
                        created_at=item.get("createdAt"),
                        last_modified=item.get("lastModified"),
                    )
                    spaces.append(space)

                offset += len(data)

                if len(data) < params["limit"]:
                    break

                time.sleep(0.5)

            print(f"  Found {len(spaces)} spaces")
            return spaces[:limit]

        except requests.RequestException as e:
            print(f"  Error fetching spaces: {e}")
            return spaces

    def get_models_by_task(self, tasks: List[str], limit_per_task: int = 50) -> Dict[str, List[HFModel]]:
        """
        Fetch top models for specific AI tasks.

        Args:
            tasks: List of tasks like ["text-generation", "image-to-text"]
            limit_per_task: Max models per task
        """
        results = {}

        for task in tasks:
            print(f"\nFetching models for task: {task}")
            models = self.get_trending_models(limit=limit_per_task, task=task)
            results[task] = models
            time.sleep(1)

        return results

    def run(self, save: bool = True) -> Dict[str, Any]:
        """
        Run the scraper and return results.
        
        Args:
            save: Whether to save results to file
            
        Returns:
            Dictionary with scraped data and signals
        """
        from datetime import date
        from pathlib import Path
        import json
        
        output_dir = Path(__file__).parent.parent / "data" / "alternative_signals"
        
        print("Fetching trending models...")
        models = self.get_trending_models(limit=100, sort="downloads")
        
        # Also get by likes
        print("Fetching most-liked models...")
        liked_models = self.get_trending_models(limit=50, sort="likes")
        
        # Merge and dedupe
        seen_ids = {m.model_id for m in models}
        for m in liked_models:
            if m.model_id not in seen_ids:
                models.append(m)
                seen_ids.add(m.model_id)
        
        print(f"Total unique models: {len(models)}")
        
        # Fetch spaces
        print("Fetching trending spaces...")
        spaces = self.get_trending_spaces(limit=100, sort="likes")
        
        # Convert to signals
        signals = convert_to_signals(models, spaces)
        
        result = {
            "source": "huggingface",
            "scraped_at": datetime.now().isoformat(),
            "total_models": len(models),
            "total_spaces": len(spaces),
            "total_signals": len(signals),
            "signals": [asdict(s) for s in signals],
        }
        
        if save:
            output_dir.mkdir(parents=True, exist_ok=True)
            today = date.today().isoformat()
            output_file = output_dir / f"huggingface_trending_{today}.json"
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(result, f, indent=2, ensure_ascii=False)
            print(f"Saved to {output_file}")
        
        return result


def convert_to_signals(
    models: List[HFModel],
    spaces: List[HFSpace]
) -> List[TrendingSignal]:
    """Convert HF data to unified TrendingSignal format."""
    signals = []

    # Convert models
    for model in models:
        signal = TrendingSignal(
            name=model.model_id,
            source_type="huggingface",
            signal_type="trending_model",
            entity_type="technology",
            description=f"{model.task or 'AI'} model by {model.author}",
            url=f"https://huggingface.co/{model.model_id}",
            category=f"HuggingFace/models/{model.task or 'other'}",
            author=model.author,
            metrics={
                "downloads": model.downloads,
                "downloads_month": model.downloads_month,
                "likes": model.likes,
                "task": model.task,
                "library": model.library,
                "tags": model.tags[:5],  # Top 5 tags
            }
        )
        signals.append(signal)

    # Convert spaces
    for space in spaces:
        signal = TrendingSignal(
            name=space.space_id,
            source_type="huggingface",
            signal_type="trending_space",
            entity_type="technology",
            description=f"{space.sdk or 'Demo'} space by {space.author}",
            url=f"https://huggingface.co/spaces/{space.space_id}",
            category=f"HuggingFace/spaces/{space.sdk or 'other'}",
            author=space.author,
            metrics={
                "likes": space.likes,
                "sdk": space.sdk,
                "hardware": space.hardware,
                "tags": space.tags[:5],
            }
        )
        signals.append(signal)

    return signals


def save_signals(signals: List[TrendingSignal], output_dir: Path) -> Path:
    """Save signals to JSON file."""
    output_dir.mkdir(parents=True, exist_ok=True)

    today = date.today().isoformat()
    output_file = output_dir / f"huggingface_trending_{today}.json"

    data = [asdict(s) for s in signals]

    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

    return output_file


def main():
    """Main scraper workflow."""
    print("=" * 60)
    print("HUGGINGFACE TRENDING SCRAPER")
    print("=" * 60)
    print()

    output_dir = Path(__file__).parent.parent / "data" / "alternative_signals"

    scraper = HuggingFaceScraper()

    # Fetch trending models (by downloads)
    print("=" * 60)
    print("FETCHING TRENDING MODELS")
    print("=" * 60)
    models = scraper.get_trending_models(limit=100, sort="downloads")

    # Also get by likes (different signal - community appreciation vs raw usage)
    print("\nFetching most-liked models...")
    liked_models = scraper.get_trending_models(limit=50, sort="likes")

    # Merge and dedupe
    seen_ids = {m.model_id for m in models}
    for m in liked_models:
        if m.model_id not in seen_ids:
            models.append(m)
            seen_ids.add(m.model_id)

    print(f"\nTotal unique models: {len(models)}")

    # Fetch trending spaces
    print("\n" + "=" * 60)
    print("FETCHING TRENDING SPACES")
    print("=" * 60)
    spaces = scraper.get_trending_spaces(limit=100, sort="likes")

    # Convert to signals
    print("\n" + "=" * 60)
    print("CONVERTING TO SIGNALS")
    print("=" * 60)
    signals = convert_to_signals(models, spaces)
    print(f"Total signals: {len(signals)}")

    # Save
    output_file = save_signals(signals, output_dir)
    print(f"\nSaved to: {output_file}")

    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"Models scraped: {len(models)}")
    print(f"Spaces scraped: {len(spaces)}")
    print(f"Total signals: {len(signals)}")

    # Top models by downloads
    print("\nTop 10 Models (by downloads):")
    top_models = sorted(models, key=lambda m: m.downloads, reverse=True)[:10]
    for i, m in enumerate(top_models, 1):
        downloads_str = f"{m.downloads:,}" if m.downloads else "N/A"
        print(f"  {i}. {m.model_id} ({downloads_str} downloads)")

    # Top spaces by likes
    print("\nTop 10 Spaces (by likes):")
    top_spaces = sorted(spaces, key=lambda s: s.likes, reverse=True)[:10]
    for i, s in enumerate(top_spaces, 1):
        print(f"  {i}. {s.space_id} ({s.likes} likes)")


if __name__ == "__main__":
    main()
