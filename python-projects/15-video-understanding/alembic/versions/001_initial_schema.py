"""Initial schema with all core tables

Revision ID: 001
Revises:
Create Date: 2024-01-15 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import JSON

# revision identifiers, used by Alembic.
revision: str = '001'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create all tables for the video understanding platform"""

    # Create videos table
    op.create_table(
        'videos',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('title', sa.String(length=500), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('source_type', sa.Enum('LOCAL', 'YOUTUBE', 'STREAM', name='sourcetype'), nullable=False),
        sa.Column('source_url', sa.String(length=1000), nullable=True),
        sa.Column('file_path', sa.String(length=1000), nullable=True),
        sa.Column('thumbnail_path', sa.String(length=1000), nullable=True),
        sa.Column('duration_seconds', sa.Float(), nullable=True),
        sa.Column('processing_status', sa.Enum('PENDING', 'DOWNLOADING', 'PROCESSING', 'COMPLETED', 'FAILED', name='videostatus'), nullable=False),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('metadata', JSON, nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.Column('processed_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_videos_id'), 'videos', ['id'], unique=False)
    op.create_index(op.f('ix_videos_title'), 'videos', ['title'], unique=False)
    op.create_index(op.f('ix_videos_source_type'), 'videos', ['source_type'], unique=False)
    op.create_index(op.f('ix_videos_processing_status'), 'videos', ['processing_status'], unique=False)
    op.create_index(op.f('ix_videos_created_at'), 'videos', ['created_at'], unique=False)

    # Create scenes table
    op.create_table(
        'scenes',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('video_id', sa.Integer(), nullable=False),
        sa.Column('scene_number', sa.Integer(), nullable=False),
        sa.Column('start_time', sa.Float(), nullable=False),
        sa.Column('end_time', sa.Float(), nullable=False),
        sa.Column('duration', sa.Float(), nullable=False),
        sa.Column('frame_count', sa.Integer(), nullable=False),
        sa.Column('keyframe_path', sa.String(length=1000), nullable=True),
        sa.Column('scene_type', sa.Enum('STATIC', 'MOTION', 'DIALOGUE', 'TRANSITION', 'ACTION', 'UNKNOWN', name='scenetype'), nullable=True),
        sa.Column('transition_type', sa.Enum('CUT', 'FADE', 'DISSOLVE', 'WIPE', 'UNKNOWN', name='transitiontype'), nullable=True),
        sa.Column('visual_embedding', JSON, nullable=True),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('metadata', JSON, nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['video_id'], ['videos.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_scenes_id'), 'scenes', ['id'], unique=False)
    op.create_index(op.f('ix_scenes_video_id'), 'scenes', ['video_id'], unique=False)
    op.create_index(op.f('ix_scenes_scene_number'), 'scenes', ['scene_number'], unique=False)
    op.create_index(op.f('ix_scenes_start_time'), 'scenes', ['start_time'], unique=False)
    op.create_index(op.f('ix_scenes_end_time'), 'scenes', ['end_time'], unique=False)
    op.create_index(op.f('ix_scenes_created_at'), 'scenes', ['created_at'], unique=False)

    # Create frames table
    op.create_table(
        'frames',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('video_id', sa.Integer(), nullable=False),
        sa.Column('scene_id', sa.Integer(), nullable=True),
        sa.Column('timestamp', sa.Float(), nullable=False),
        sa.Column('frame_number', sa.Integer(), nullable=False),
        sa.Column('file_path', sa.String(length=1000), nullable=True),
        sa.Column('is_keyframe', sa.Boolean(), nullable=True),
        sa.Column('frame_hash', sa.String(length=64), nullable=True),
        sa.Column('visual_features', JSON, nullable=True),
        sa.Column('ocr_text', sa.Text(), nullable=True),
        sa.Column('clip_embedding', JSON, nullable=True),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('objects_detected', JSON, nullable=True),
        sa.Column('faces_detected', JSON, nullable=True),
        sa.Column('metadata', JSON, nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['video_id'], ['videos.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['scene_id'], ['scenes.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_frames_id'), 'frames', ['id'], unique=False)
    op.create_index(op.f('ix_frames_video_id'), 'frames', ['video_id'], unique=False)
    op.create_index(op.f('ix_frames_scene_id'), 'frames', ['scene_id'], unique=False)
    op.create_index(op.f('ix_frames_timestamp'), 'frames', ['timestamp'], unique=False)
    op.create_index(op.f('ix_frames_frame_number'), 'frames', ['frame_number'], unique=False)
    op.create_index(op.f('ix_frames_is_keyframe'), 'frames', ['is_keyframe'], unique=False)
    op.create_index(op.f('ix_frames_frame_hash'), 'frames', ['frame_hash'], unique=False)
    op.create_index(op.f('ix_frames_created_at'), 'frames', ['created_at'], unique=False)

    # Create transcripts table
    op.create_table(
        'transcripts',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('video_id', sa.Integer(), nullable=False),
        sa.Column('scene_id', sa.Integer(), nullable=True),
        sa.Column('start_time', sa.Float(), nullable=False),
        sa.Column('end_time', sa.Float(), nullable=False),
        sa.Column('text', sa.Text(), nullable=False),
        sa.Column('speaker_id', sa.String(length=50), nullable=True),
        sa.Column('confidence', sa.Float(), nullable=True),
        sa.Column('language', sa.String(length=10), nullable=True),
        sa.Column('segment_type', sa.Enum('WORD', 'SENTENCE', 'PARAGRAPH', 'SPEAKER_TURN', name='segmenttype'), nullable=True),
        sa.Column('embedding', JSON, nullable=True),
        sa.Column('metadata', JSON, nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['video_id'], ['videos.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['scene_id'], ['scenes.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_transcripts_id'), 'transcripts', ['id'], unique=False)
    op.create_index(op.f('ix_transcripts_video_id'), 'transcripts', ['video_id'], unique=False)
    op.create_index(op.f('ix_transcripts_scene_id'), 'transcripts', ['scene_id'], unique=False)
    op.create_index(op.f('ix_transcripts_start_time'), 'transcripts', ['start_time'], unique=False)
    op.create_index(op.f('ix_transcripts_end_time'), 'transcripts', ['end_time'], unique=False)
    op.create_index(op.f('ix_transcripts_speaker_id'), 'transcripts', ['speaker_id'], unique=False)
    op.create_index(op.f('ix_transcripts_created_at'), 'transcripts', ['created_at'], unique=False)

    # Create summaries table
    op.create_table(
        'summaries',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('video_id', sa.Integer(), nullable=False),
        sa.Column('summary_type', sa.Enum('OVERALL', 'SCENE', 'CHAPTER', 'HIGHLIGHT', 'BRIEF', 'DETAILED', 'TECHNICAL', name='summarytype'), nullable=False),
        sa.Column('title', sa.String(length=500), nullable=True),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('timestamp_ranges', JSON, nullable=True),
        sa.Column('metadata', JSON, nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['video_id'], ['videos.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_summaries_id'), 'summaries', ['id'], unique=False)
    op.create_index(op.f('ix_summaries_video_id'), 'summaries', ['video_id'], unique=False)
    op.create_index(op.f('ix_summaries_summary_type'), 'summaries', ['summary_type'], unique=False)
    op.create_index(op.f('ix_summaries_created_at'), 'summaries', ['created_at'], unique=False)

    # Create highlights table
    op.create_table(
        'highlights',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('video_id', sa.Integer(), nullable=False),
        sa.Column('title', sa.String(length=500), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('start_time', sa.Float(), nullable=False),
        sa.Column('end_time', sa.Float(), nullable=False),
        sa.Column('importance_score', sa.Float(), nullable=False),
        sa.Column('highlight_type', sa.Enum('ACTION', 'DIALOGUE', 'KEY_MOMENT', 'EMOTIONAL', 'VISUAL', 'INFORMATIVE', 'TRANSITION', 'UNKNOWN', name='highlighttype'), nullable=False),
        sa.Column('clip_path', sa.String(length=1000), nullable=True),
        sa.Column('thumbnail_path', sa.String(length=1000), nullable=True),
        sa.Column('metadata', JSON, nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['video_id'], ['videos.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_highlights_id'), 'highlights', ['id'], unique=False)
    op.create_index(op.f('ix_highlights_video_id'), 'highlights', ['video_id'], unique=False)
    op.create_index(op.f('ix_highlights_start_time'), 'highlights', ['start_time'], unique=False)
    op.create_index(op.f('ix_highlights_end_time'), 'highlights', ['end_time'], unique=False)
    op.create_index(op.f('ix_highlights_importance_score'), 'highlights', ['importance_score'], unique=False)
    op.create_index(op.f('ix_highlights_highlight_type'), 'highlights', ['highlight_type'], unique=False)
    op.create_index(op.f('ix_highlights_created_at'), 'highlights', ['created_at'], unique=False)

    # Create video_embeddings table
    op.create_table(
        'video_embeddings',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('video_id', sa.Integer(), nullable=False),
        sa.Column('frame_id', sa.Integer(), nullable=True),
        sa.Column('scene_id', sa.Integer(), nullable=True),
        sa.Column('embedding_type', sa.Enum('CLIP_VISUAL', 'CLIP_TEXT', 'TEXT_SEMANTIC', 'AUDIO_FEATURE', 'MULTIMODAL', 'CUSTOM', name='embeddingtype'), nullable=False),
        sa.Column('embedding_vector', JSON, nullable=False),
        sa.Column('timestamp', sa.Float(), nullable=True),
        sa.Column('dimension', sa.Integer(), nullable=False),
        sa.Column('model_name', sa.String(length=100), nullable=True),
        sa.Column('metadata', JSON, nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['video_id'], ['videos.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['frame_id'], ['frames.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['scene_id'], ['scenes.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_video_embeddings_id'), 'video_embeddings', ['id'], unique=False)
    op.create_index(op.f('ix_video_embeddings_video_id'), 'video_embeddings', ['video_id'], unique=False)
    op.create_index(op.f('ix_video_embeddings_frame_id'), 'video_embeddings', ['frame_id'], unique=False)
    op.create_index(op.f('ix_video_embeddings_scene_id'), 'video_embeddings', ['scene_id'], unique=False)
    op.create_index(op.f('ix_video_embeddings_embedding_type'), 'video_embeddings', ['embedding_type'], unique=False)
    op.create_index(op.f('ix_video_embeddings_timestamp'), 'video_embeddings', ['timestamp'], unique=False)
    op.create_index(op.f('ix_video_embeddings_created_at'), 'video_embeddings', ['created_at'], unique=False)


def downgrade() -> None:
    """Drop all tables"""
    op.drop_table('video_embeddings')
    op.drop_table('highlights')
    op.drop_table('summaries')
    op.drop_table('transcripts')
    op.drop_table('frames')
    op.drop_table('scenes')
    op.drop_table('videos')
