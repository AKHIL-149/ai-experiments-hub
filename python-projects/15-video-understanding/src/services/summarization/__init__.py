"""
Summarization services
Generate summaries from video analysis
"""

from src.services.summarization.video_summarizer import (
    VideoSummarizer,
    VideoSummary,
    SummaryLength,
    summarize_video,
)
from src.services.summarization.scene_summarizer import (
    SceneSummarizer,
    SceneSummary,
    KeyMoment,
    summarize_scene,
)
from src.services.summarization.chapter_generator import (
    ChapterGenerator,
    Chapter,
    ChapterCollection,
    generate_chapters,
)
from src.services.summarization.templates import (
    SummaryTemplateManager,
    SummaryTemplate,
    TemplateFormat,
    format_summary,
    get_template_manager,
)

__all__ = [
    'VideoSummarizer',
    'VideoSummary',
    'SummaryLength',
    'summarize_video',
    'SceneSummarizer',
    'SceneSummary',
    'KeyMoment',
    'summarize_scene',
    'ChapterGenerator',
    'Chapter',
    'ChapterCollection',
    'generate_chapters',
    'SummaryTemplateManager',
    'SummaryTemplate',
    'TemplateFormat',
    'format_summary',
    'get_template_manager',
]
