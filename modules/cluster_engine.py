from __future__ import annotations

from typing import List
from utils.schemas import RiskSignal, Cluster
from sentence_transformers import SentenceTransformer
from sklearn.cluster import DBSCAN
import numpy as np
import uuid


class ClusterEngine:
    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        self.model = SentenceTransformer(model_name)

    def cluster_signals(self, signals: List[RiskSignal]) -> List[Cluster]:
        if not signals:
            return []
        texts = [s.title or (s.summary or "") for s in signals]
        embeddings = self.model.encode(texts, normalize_embeddings=True)
        clustering = DBSCAN(eps=0.25, min_samples=2, metric="cosine").fit(embeddings)
        labels = clustering.labels_

        clusters: List[Cluster] = []
        for label in set(labels):
            if label == -1:
                continue
            member_idx = np.where(labels == label)[0].tolist()
            member_ids = [signals[i].id for i in member_idx]
            centroid = np.mean(embeddings[member_idx], axis=0)
            # Simple label: top title
            label_text = signals[member_idx[0]].title
            clusters.append(
                Cluster(
                    id=str(uuid.uuid4()),
                    label=label_text,
                    member_signal_ids=member_ids,
                    theme_keywords=[],
                    centroid_ref=None,
                )
            )
        return clusters













