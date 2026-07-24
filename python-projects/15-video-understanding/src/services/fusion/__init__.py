"""
Multi-modal fusion services
Combine visual, audio, and textual information
"""

from src.services.fusion.temporal_aligner import (
    TemporalAligner,
    AlignedSegment,
    AlignmentResult,
    align_transcript_with_scenes,
)
from src.services.fusion.visual_audio_fuser import (
    VisualAudioFuser,
    FusionWeights,
    FusedScene,
    fuse_visual_audio_context,
)
from src.services.fusion.context_aggregator import (
    ContextAggregator,
    SceneContext,
    VideoContext,
    aggregate_scene_context,
)
from src.services.fusion.timeline_builder import (
    TimelineBuilder,
    TimelineEvent,
    TimelineSegment,
    VideoTimeline,
    build_video_timeline,
)

__all__ = [
    'TemporalAligner',
    'AlignedSegment',
    'AlignmentResult',
    'align_transcript_with_scenes',
    'VisualAudioFuser',
    'FusionWeights',
    'FusedScene',
    'fuse_visual_audio_context',
    'ContextAggregator',
    'SceneContext',
    'VideoContext',
    'aggregate_scene_context',
    'TimelineBuilder',
    'TimelineEvent',
    'TimelineSegment',
    'VideoTimeline',
    'build_video_timeline',
]
