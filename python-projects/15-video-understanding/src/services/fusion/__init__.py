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

__all__ = [
    'TemporalAligner',
    'AlignedSegment',
    'AlignmentResult',
    'align_transcript_with_scenes',
]
