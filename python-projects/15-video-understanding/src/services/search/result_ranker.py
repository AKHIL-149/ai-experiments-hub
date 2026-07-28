"""
Search result ranker for combining and reranking results
Combine multiple signals (visual, text, temporal) for better ranking
"""

import logging
from typing import List, Optional, Dict, Any
from dataclasses import dataclass
import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class RankingConfig:
    """Configuration for result ranking"""
    # Signal weights
    visual_weight: float = 0.4
    text_weight: float = 0.4
    temporal_weight: float = 0.1
    recency_weight: float = 0.1

    # LLM reranking
    use_llm_reranking: bool = False
    rerank_top_k: int = 20  # Rerank only top results

    # Diversity
    enforce_diversity: bool = True
    min_temporal_gap: float = 5.0  # Seconds between results
    max_same_video: int = 5  # Max results from same video

    # Normalization
    normalize_scores: bool = True


class SearchResultRanker:
    """
    Rank and combine search results from multiple sources
    Use weighted scoring and optional LLM reranking
    """

    def __init__(
        self,
        llm_client=None,
        default_config: Optional[RankingConfig] = None,
    ):
        """
        Initialize search result ranker

        Args:
            llm_client: Optional LLM client for reranking
            default_config: Default ranking configuration
        """
        self.llm_client = llm_client
        self.default_config = default_config or RankingConfig()

        logger.info("Initialized SearchResultRanker")

    def rank_combined_results(
        self,
        query: str,
        visual_results: List[Any] = None,
        text_results: List[Any] = None,
        config: Optional[RankingConfig] = None,
    ) -> List[Any]:
        """
        Rank combined results from visual and text search

        Args:
            query: Search query
            visual_results: Results from frame search
            text_results: Results from transcript search
            config: Ranking configuration

        Returns:
            Ranked list of results
        """
        config = config or self.default_config

        logger.info(
            f"Ranking combined results: "
            f"{len(visual_results or [])} visual, {len(text_results or [])} text"
        )

        # Combine results
        combined = self._combine_results(
            visual_results or [],
            text_results or [],
        )

        # Calculate composite scores
        ranked = self._calculate_composite_scores(combined, config)

        # Apply diversity if requested
        if config.enforce_diversity:
            ranked = self._enforce_diversity(ranked, config)

        # LLM reranking if requested
        if config.use_llm_reranking and self.llm_client:
            ranked = self._llm_rerank(
                query=query,
                results=ranked,
                top_k=config.rerank_top_k,
            )

        # Sort by final score
        ranked = sorted(
            ranked,
            key=lambda r: r.get("final_score", 0.0),
            reverse=True,
        )

        # Update ranks
        for i, result in enumerate(ranked, 1):
            result["rank"] = i

        logger.info(f"Ranked {len(ranked)} combined results")

        return ranked

    def rank_multimodal_results(
        self,
        query: str,
        results: List[Any],
        config: Optional[RankingConfig] = None,
    ) -> List[Any]:
        """
        Rank results that already have multiple modality scores

        Args:
            query: Search query
            results: Results with visual_similarity and text_similarity
            config: Ranking configuration

        Returns:
            Ranked results
        """
        config = config or self.default_config

        logger.info(f"Ranking {len(results)} multimodal results")

        # Calculate composite scores
        ranked = []

        for result in results:
            visual_score = result.get("visual_similarity", 0.0)
            text_score = result.get("text_similarity", 0.0)

            # Calculate weighted score
            composite_score = (
                visual_score * config.visual_weight +
                text_score * config.text_weight
            )

            # Add temporal factor
            if "timestamp" in result:
                temporal_factor = self._calculate_temporal_factor(result)
                composite_score += temporal_factor * config.temporal_weight

            result["composite_score"] = composite_score
            result["final_score"] = composite_score
            ranked.append(result)

        # Apply diversity
        if config.enforce_diversity:
            ranked = self._enforce_diversity(ranked, config)

        # LLM reranking
        if config.use_llm_reranking and self.llm_client:
            ranked = self._llm_rerank(
                query=query,
                results=ranked,
                top_k=config.rerank_top_k,
            )

        # Sort by final score
        ranked = sorted(
            ranked,
            key=lambda r: r.get("final_score", 0.0),
            reverse=True,
        )

        # Update ranks
        for i, result in enumerate(ranked, 1):
            result["rank"] = i

        logger.info(f"Ranked {len(ranked)} multimodal results")

        return ranked

    def _combine_results(
        self,
        visual_results: List[Any],
        text_results: List[Any],
    ) -> List[Dict[str, Any]]:
        """Combine visual and text results"""
        combined = []

        # Add visual results
        for result in visual_results:
            combined_result = {
                "type": "visual",
                "result": result,
                "video_id": getattr(result, "video_id", ""),
                "timestamp": getattr(result, "timestamp", 0.0),
                "visual_similarity": getattr(result, "similarity_score", 0.0),
                "text_similarity": 0.0,
            }
            combined.append(combined_result)

        # Add text results
        for result in text_results:
            combined_result = {
                "type": "text",
                "result": result,
                "video_id": getattr(result, "video_id", ""),
                "timestamp": getattr(result, "timestamp", 0.0),
                "visual_similarity": 0.0,
                "text_similarity": getattr(result, "similarity_score", 0.0),
            }
            combined.append(combined_result)

        # Merge results with same video+timestamp
        merged = self._merge_same_timestamp(combined)

        return merged

    def _merge_same_timestamp(
        self,
        results: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Merge results from same video and timestamp"""
        merged_map: Dict[str, Dict[str, Any]] = {}

        for result in results:
            key = f"{result['video_id']}_{result['timestamp']:.1f}"

            if key in merged_map:
                # Merge scores
                existing = merged_map[key]
                existing["visual_similarity"] = max(
                    existing["visual_similarity"],
                    result["visual_similarity"],
                )
                existing["text_similarity"] = max(
                    existing["text_similarity"],
                    result["text_similarity"],
                )
                existing["type"] = "multimodal"
            else:
                merged_map[key] = result.copy()

        return list(merged_map.values())

    def _calculate_composite_scores(
        self,
        results: List[Dict[str, Any]],
        config: RankingConfig,
    ) -> List[Dict[str, Any]]:
        """Calculate composite scores for results"""
        for result in results:
            visual_score = result.get("visual_similarity", 0.0)
            text_score = result.get("text_similarity", 0.0)

            # Weighted combination
            composite_score = (
                visual_score * config.visual_weight +
                text_score * config.text_weight
            )

            # Add temporal factor
            temporal_factor = self._calculate_temporal_factor(result)
            composite_score += temporal_factor * config.temporal_weight

            # Add recency factor
            recency_factor = self._calculate_recency_factor(result)
            composite_score += recency_factor * config.recency_weight

            result["composite_score"] = composite_score
            result["final_score"] = composite_score

        # Normalize scores if requested
        if config.normalize_scores:
            results = self._normalize_scores(results)

        return results

    def _calculate_temporal_factor(
        self,
        result: Dict[str, Any],
    ) -> float:
        """Calculate temporal importance factor"""
        # Could consider position in video, etc.
        # For now, return neutral
        return 0.5

    def _calculate_recency_factor(
        self,
        result: Dict[str, Any],
    ) -> float:
        """Calculate recency factor"""
        # Could prefer recent results for trending queries
        # For now, return neutral
        return 0.5

    def _normalize_scores(
        self,
        results: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Normalize final scores to 0-1 range"""
        if not results:
            return results

        scores = [r.get("final_score", 0.0) for r in results]
        min_score = min(scores)
        max_score = max(scores)

        if max_score - min_score < 1e-6:
            return results

        for result in results:
            score = result.get("final_score", 0.0)
            normalized = (score - min_score) / (max_score - min_score)
            result["final_score"] = normalized

        return results

    def _enforce_diversity(
        self,
        results: List[Dict[str, Any]],
        config: RankingConfig,
    ) -> List[Dict[str, Any]]:
        """Enforce diversity in results"""
        if not results:
            return results

        # Track selected by video
        video_counts: Dict[str, int] = {}
        diverse_results = []

        # Sort by score first
        sorted_results = sorted(
            results,
            key=lambda r: r.get("final_score", 0.0),
            reverse=True,
        )

        for result in sorted_results:
            video_id = result.get("video_id", "")

            # Check video limit
            if video_counts.get(video_id, 0) >= config.max_same_video:
                continue

            # Check temporal diversity
            too_close = False
            if config.min_temporal_gap > 0:
                for selected in diverse_results:
                    if selected.get("video_id") == video_id:
                        gap = abs(
                            selected.get("timestamp", 0.0) -
                            result.get("timestamp", 0.0)
                        )
                        if gap < config.min_temporal_gap:
                            too_close = True
                            break

            if not too_close:
                diverse_results.append(result)
                video_counts[video_id] = video_counts.get(video_id, 0) + 1

        logger.info(
            f"Enforced diversity: {len(results)} -> {len(diverse_results)} results"
        )

        return diverse_results

    def _llm_rerank(
        self,
        query: str,
        results: List[Dict[str, Any]],
        top_k: int,
    ) -> List[Dict[str, Any]]:
        """Rerank top results using LLM"""
        if not self.llm_client or not results:
            return results

        # Select top_k for reranking
        top_results = sorted(
            results,
            key=lambda r: r.get("final_score", 0.0),
            reverse=True,
        )[:top_k]

        remaining_results = results[top_k:]

        logger.info(f"LLM reranking top {len(top_results)} results")

        # Build reranking prompt
        result_descriptions = []
        for i, result in enumerate(top_results):
            result_obj = result.get("result")
            if hasattr(result_obj, "text"):
                desc = f"{i+1}. {result_obj.text[:200]}"
            elif hasattr(result_obj, "description"):
                desc = f"{i+1}. {result_obj.description[:200]}"
            else:
                desc = f"{i+1}. Result {i+1}"
            result_descriptions.append(desc)

        prompt = f"""Query: {query}

Results to rank:
{chr(10).join(result_descriptions)}

Please rank these results by relevance to the query.
Return only the numbers in order of relevance (most relevant first).
Format: 1,3,2,5,4,..."""

        try:
            response = self.llm_client.generate(
                prompt=prompt,
                max_tokens=100,
                temperature=0.0,
            )

            # Parse ranking
            ranking_text = response.get("text", "")
            ranking = self._parse_ranking(ranking_text, len(top_results))

            # Reorder results
            reranked = []
            for rank_idx in ranking:
                if 0 <= rank_idx < len(top_results):
                    result = top_results[rank_idx]
                    # Boost score based on LLM ranking
                    boost = (len(ranking) - ranking.index(rank_idx)) / len(ranking)
                    result["final_score"] = result.get("final_score", 0.0) + boost * 0.2
                    reranked.append(result)

            # Add remaining results
            reranked.extend(remaining_results)

            logger.info(f"LLM reranked {len(reranked)} results")

            return reranked

        except Exception as e:
            logger.warning(f"LLM reranking failed: {e}, using original ranking")
            return results

    def _parse_ranking(
        self,
        ranking_text: str,
        num_results: int,
    ) -> List[int]:
        """Parse LLM ranking output"""
        try:
            # Extract numbers
            import re
            numbers = re.findall(r'\d+', ranking_text)
            ranking = [int(n) - 1 for n in numbers if 1 <= int(n) <= num_results]

            # Add missing indices
            for i in range(num_results):
                if i not in ranking:
                    ranking.append(i)

            return ranking[:num_results]

        except Exception as e:
            logger.warning(f"Failed to parse ranking: {e}")
            return list(range(num_results))

    def boost_results_by_importance(
        self,
        results: List[Dict[str, Any]],
        importance_scores: Dict[str, float],
    ) -> List[Dict[str, Any]]:
        """
        Boost results based on external importance scores

        Args:
            results: Search results
            importance_scores: Map of result_id to importance score

        Returns:
            Boosted results
        """
        for result in results:
            result_obj = result.get("result")
            result_id = getattr(result_obj, "result_id", None) or getattr(result_obj, "frame_id", None)

            if result_id and result_id in importance_scores:
                importance = importance_scores[result_id]
                current_score = result.get("final_score", 0.0)
                # Boost by importance (weighted 20%)
                result["final_score"] = current_score * 0.8 + importance * 0.2

        return results

    def filter_by_confidence(
        self,
        results: List[Dict[str, Any]],
        min_confidence: float = 0.5,
    ) -> List[Dict[str, Any]]:
        """Filter results by minimum confidence score"""
        filtered = [
            r for r in results
            if r.get("final_score", 0.0) >= min_confidence
        ]

        logger.info(
            f"Filtered by confidence: {len(results)} -> {len(filtered)} results"
        )

        return filtered


def rank_search_results(
    query: str,
    visual_results: List[Any] = None,
    text_results: List[Any] = None,
    llm_client=None,
    config: Optional[RankingConfig] = None,
) -> List[Any]:
    """
    Convenience function to rank search results

    Args:
        query: Search query
        visual_results: Visual search results
        text_results: Text search results
        llm_client: Optional LLM client
        config: Ranking configuration

    Returns:
        Ranked results
    """
    ranker = SearchResultRanker(
        llm_client=llm_client,
        default_config=config,
    )

    return ranker.rank_combined_results(
        query=query,
        visual_results=visual_results,
        text_results=text_results,
        config=config,
    )
