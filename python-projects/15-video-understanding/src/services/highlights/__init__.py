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
from src.services.highlights.highlight_detector import (
    HighlightDetector,
    Highlight,
    HighlightCollection,
    HighlightType,
    detect_highlights,
)

__all__ = [
    'ImportanceScorer',
    'ImportanceFactors',
    'ScoringWeights',
    'SceneImportanceScore',
    'score_scene_importance',
    'HighlightDetector',
    'Highlight',
    'HighlightCollection',
    'HighlightType',
    'detect_highlights',
]
