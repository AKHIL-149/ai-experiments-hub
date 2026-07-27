"""
Highlight detection and generation services
Identify and create video highlights
"""

from src.services.highlights.importance_scorer import (
    ImportanceScorer,
    ImportanceFactors,
    ScoringWeights,
    SceneImportanceScore,
    score_scene_importance,
)

__all__ = [
    'ImportanceScorer',
    'ImportanceFactors',
    'ScoringWeights',
    'SceneImportanceScore',
    'score_scene_importance',
]
