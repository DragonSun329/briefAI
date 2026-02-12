"""
Delta Detector - Find genuinely new content using embeddings.

Compares today's stories/narratives to yesterday's, filters semantic duplicates.
"""

import json
from pathlib import Path
from datetime import datetime, timedelta
from typing import List, Dict, Tuple, Optional
import numpy as np
from sentence_transformers import SentenceTransformer
from loguru import logger


class DeltaDetector:
    """Detect genuinely new content by comparing to previous day."""
    
    def __init__(self, similarity_threshold: float = 0.75):
        self.threshold = similarity_threshold
        self.model = SentenceTransformer('all-MiniLM-L6-v2')
        logger.info(f"DeltaDetector initialized (threshold={similarity_threshold})")
    
    def _get_embeddings(self, texts: List[str]) -> np.ndarray:
        """Get embeddings for a list of texts."""
        if not texts:
            return np.array([])
        return self.model.encode(texts, show_progress_bar=False)
    
    def _cosine_similarity(self, a: np.ndarray, b: np.ndarray) -> float:
        """Compute cosine similarity between two vectors."""
        norm_a = np.linalg.norm(a)
        norm_b = np.linalg.norm(b)
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return float(np.dot(a, b) / (norm_a * norm_b))
    
    def find_novel_stories(
        self, 
        today_stories: List[Dict], 
        yesterday_stories: List[Dict],
        title_key: str = 'title'
    ) -> Tuple[List[Dict], List[Dict]]:
        """
        Find stories that are genuinely new (not semantic duplicates).
        
        Returns:
            (novel_stories, duplicate_stories)
        """
        if not yesterday_stories:
            return today_stories, []
        
        # Get titles
        today_titles = [s.get(title_key, '') for s in today_stories]
        yesterday_titles = [s.get(title_key, '') for s in yesterday_stories]
        
        # Get embeddings
        today_emb = self._get_embeddings(today_titles)
        yesterday_emb = self._get_embeddings(yesterday_titles)
        
        if len(today_emb) == 0:
            return [], []
        
        novel = []
        duplicates = []
        
        for i, story in enumerate(today_stories):
            # Find max similarity to any yesterday story
            max_sim = 0.0
            for j in range(len(yesterday_emb)):
                sim = self._cosine_similarity(today_emb[i], yesterday_emb[j])
                max_sim = max(max_sim, sim)
            
            if max_sim < self.threshold:
                novel.append(story)
            else:
                story['_duplicate_score'] = max_sim
                duplicates.append(story)
        
        logger.info(f"Delta detection: {len(novel)} novel, {len(duplicates)} duplicates")
        return novel, duplicates
    
    def compare_briefs(
        self,
        today_brief: str,
        yesterday_brief: str,
        chunk_size: int = 200
    ) -> Dict:
        """
        Compare two briefs and find novel sections.
        
        Returns dict with:
            - similarity: overall similarity score
            - novel_chunks: sections that are new
        """
        # Simple chunking by sentences/paragraphs
        def chunk_text(text: str) -> List[str]:
            # Split by double newlines or sentences
            chunks = []
            for para in text.split('\n\n'):
                para = para.strip()
                if len(para) > chunk_size:
                    # Split long paragraphs
                    sentences = para.replace('. ', '.\n').split('\n')
                    chunks.extend([s.strip() for s in sentences if s.strip()])
                elif para:
                    chunks.append(para)
            return chunks
        
        today_chunks = chunk_text(today_brief)
        yesterday_chunks = chunk_text(yesterday_brief)
        
        if not yesterday_chunks:
            return {'similarity': 0.0, 'novel_chunks': today_chunks}
        
        today_emb = self._get_embeddings(today_chunks)
        yesterday_emb = self._get_embeddings(yesterday_chunks)
        
        # Overall similarity (average of best matches)
        similarities = []
        novel_chunks = []
        
        for i, chunk in enumerate(today_chunks):
            max_sim = max(
                self._cosine_similarity(today_emb[i], yesterday_emb[j])
                for j in range(len(yesterday_emb))
            )
            similarities.append(max_sim)
            if max_sim < self.threshold:
                novel_chunks.append(chunk)
        
        return {
            'similarity': float(np.mean(similarities)) if similarities else 0.0,
            'novel_chunks': novel_chunks,
            'total_chunks': len(today_chunks),
            'novel_count': len(novel_chunks)
        }


def detect_stale_stories(data_dir: str = "data/news_signals") -> Dict:
    """
    Compare today's scraped stories to yesterday's.
    
    Returns report on what's novel vs duplicate.
    """
    data_path = Path(data_dir)
    today = datetime.now().strftime("%Y-%m-%d")
    yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    
    detector = DeltaDetector()
    report = {'date': today, 'sources': {}}
    
    # Find today's files
    for today_file in data_path.glob(f"*_{today}.json"):
        source_name = today_file.stem.replace(f"_{today}", "")
        yesterday_file = data_path / f"{source_name}_{yesterday}.json"
        
        try:
            with open(today_file, encoding='utf-8') as f:
                today_data = json.load(f)
            
            # Handle different structures
            if 'stories' in today_data:
                today_stories = today_data['stories']
            elif 'articles' in today_data:
                today_stories = today_data['articles']
            elif isinstance(today_data, list):
                today_stories = today_data
            else:
                continue
            
            yesterday_stories = []
            if yesterday_file.exists():
                with open(yesterday_file, encoding='utf-8') as f:
                    yesterday_data = json.load(f)
                if 'stories' in yesterday_data:
                    yesterday_stories = yesterday_data['stories']
                elif 'articles' in yesterday_data:
                    yesterday_stories = yesterday_data['articles']
                elif isinstance(yesterday_data, list):
                    yesterday_stories = yesterday_data
            
            novel, dupes = detector.find_novel_stories(today_stories, yesterday_stories)
            
            report['sources'][source_name] = {
                'total': len(today_stories),
                'novel': len(novel),
                'duplicate': len(dupes),
                'novelty_rate': len(novel) / max(1, len(today_stories))
            }
            
        except Exception as e:
            logger.warning(f"Failed to process {source_name}: {e}")
    
    return report


if __name__ == "__main__":
    report = detect_stale_stories()
    print(json.dumps(report, indent=2))
