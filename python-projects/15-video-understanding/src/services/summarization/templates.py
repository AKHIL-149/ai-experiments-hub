"""
Summary template manager for customizable summary formats
Support different output formats with timestamps and key points
"""

import logging
from typing import List, Optional, Dict, Any, Callable
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)


class TemplateFormat(str, Enum):
    """Summary template formats"""
    PLAIN_TEXT = "plain_text"
    MARKDOWN = "markdown"
    HTML = "html"
    JSON = "json"
    STRUCTURED = "structured"


@dataclass
class SummaryTemplate:
    """Template for summary generation"""
    name: str
    format: TemplateFormat
    template_string: str

    # Options
    include_timestamps: bool = True
    include_key_points: bool = True
    include_speakers: bool = True
    include_chapters: bool = False
    include_metadata: bool = False

    # Formatting
    timestamp_format: str = "HH:MM:SS"  # or "seconds"
    max_length: Optional[int] = None

    metadata: Dict[str, Any] = field(default_factory=dict)


class SummaryTemplateManager:
    """
    Manage summary templates and format summaries
    Support multiple output formats with customization
    """

    def __init__(self):
        """Initialize summary template manager"""
        self.templates: Dict[str, SummaryTemplate] = {}
        self._register_default_templates()

        logger.info("Initialized SummaryTemplateManager")

    def _register_default_templates(self):
        """Register default templates"""
        # Plain text template
        self.register_template(SummaryTemplate(
            name="plain_brief",
            format=TemplateFormat.PLAIN_TEXT,
            template_string=(
                "{title}\n"
                "{duration_formatted}\n\n"
                "{summary_text}\n"
            ),
            include_timestamps=False,
            include_key_points=False,
        ))

        # Plain text with key points
        self.register_template(SummaryTemplate(
            name="plain_detailed",
            format=TemplateFormat.PLAIN_TEXT,
            template_string=(
                "{title}\n"
                "Duration: {duration_formatted}\n\n"
                "SUMMARY:\n"
                "{summary_text}\n\n"
                "KEY POINTS:\n"
                "{key_points_list}\n"
            ),
            include_timestamps=True,
            include_key_points=True,
        ))

        # Markdown template
        self.register_template(SummaryTemplate(
            name="markdown",
            format=TemplateFormat.MARKDOWN,
            template_string=(
                "# {title}\n\n"
                "**Duration:** {duration_formatted}\n\n"
                "## Summary\n\n"
                "{summary_text}\n\n"
                "## Key Points\n\n"
                "{key_points_markdown}\n"
            ),
            include_timestamps=True,
            include_key_points=True,
        ))

        # Markdown with chapters
        self.register_template(SummaryTemplate(
            name="markdown_chapters",
            format=TemplateFormat.MARKDOWN,
            template_string=(
                "# {title}\n\n"
                "**Duration:** {duration_formatted}\n\n"
                "## Summary\n\n"
                "{summary_text}\n\n"
                "## Chapters\n\n"
                "{chapters_markdown}\n\n"
                "## Key Points\n\n"
                "{key_points_markdown}\n"
            ),
            include_timestamps=True,
            include_key_points=True,
            include_chapters=True,
        ))

        # HTML template
        self.register_template(SummaryTemplate(
            name="html",
            format=TemplateFormat.HTML,
            template_string=(
                "<div class='video-summary'>\n"
                "  <h1>{title}</h1>\n"
                "  <p class='duration'><strong>Duration:</strong> {duration_formatted}</p>\n"
                "  <div class='summary'>\n"
                "    <h2>Summary</h2>\n"
                "    <p>{summary_text}</p>\n"
                "  </div>\n"
                "  <div class='key-points'>\n"
                "    <h2>Key Points</h2>\n"
                "    {key_points_html}\n"
                "  </div>\n"
                "</div>\n"
            ),
            include_timestamps=True,
            include_key_points=True,
        ))

    def register_template(self, template: SummaryTemplate):
        """
        Register a custom template

        Args:
            template: SummaryTemplate to register
        """
        self.templates[template.name] = template
        logger.debug(f"Registered template: {template.name}")

    def format_video_summary(
        self,
        summary: Any,
        template_name: str = "plain_detailed",
        **kwargs,
    ) -> str:
        """
        Format video summary using template

        Args:
            summary: VideoSummary object
            template_name: Name of template to use
            **kwargs: Additional template variables

        Returns:
            Formatted summary string
        """
        template = self.templates.get(template_name)
        if not template:
            logger.warning(f"Template {template_name} not found, using plain_brief")
            template = self.templates["plain_brief"]

        # Prepare template variables
        variables = self._prepare_video_summary_variables(
            summary, template, **kwargs
        )

        # Format using template
        try:
            formatted = template.template_string.format(**variables)
        except KeyError as e:
            logger.error(f"Template formatting error: {e}")
            formatted = summary.summary_text

        # Apply max length if specified
        if template.max_length and len(formatted) > template.max_length:
            formatted = formatted[:template.max_length - 3] + "..."

        return formatted

    def format_scene_summary(
        self,
        summary: Any,
        template_name: str = "plain_brief",
        **kwargs,
    ) -> str:
        """
        Format scene summary using template

        Args:
            summary: SceneSummary object
            template_name: Name of template to use
            **kwargs: Additional template variables

        Returns:
            Formatted summary string
        """
        template = self.templates.get(template_name)
        if not template:
            template = self.templates["plain_brief"]

        # Prepare template variables
        variables = self._prepare_scene_summary_variables(
            summary, template, **kwargs
        )

        # Format using template
        try:
            formatted = template.template_string.format(**variables)
        except KeyError as e:
            logger.error(f"Template formatting error: {e}")
            formatted = summary.summary_text

        return formatted

    def format_chapters(
        self,
        chapters: Any,
        template_name: str = "markdown",
        **kwargs,
    ) -> str:
        """
        Format chapters using template

        Args:
            chapters: ChapterCollection object
            template_name: Name of template to use
            **kwargs: Additional template variables

        Returns:
            Formatted chapters string
        """
        template = self.templates.get(template_name)
        if not template:
            template = self.templates["markdown"]

        # Prepare variables
        variables = self._prepare_chapters_variables(
            chapters, template, **kwargs
        )

        # Format using template
        try:
            formatted = template.template_string.format(**variables)
        except KeyError as e:
            logger.error(f"Template formatting error: {e}")
            formatted = str(chapters)

        return formatted

    def _prepare_video_summary_variables(
        self,
        summary: Any,
        template: SummaryTemplate,
        **kwargs,
    ) -> Dict[str, str]:
        """Prepare template variables for video summary"""
        variables = {
            "title": kwargs.get("title", f"Video Summary: {summary.video_id}"),
            "video_id": summary.video_id,
            "summary_text": summary.summary_text,
            "duration": summary.duration,
            "duration_formatted": self._format_duration(summary.duration),
            "num_scenes": summary.num_scenes,
            "word_count": summary.word_count,
        }

        # Key points
        if template.include_key_points and summary.key_points:
            variables["key_points_list"] = self._format_key_points_plain(
                summary.key_points
            )
            variables["key_points_markdown"] = self._format_key_points_markdown(
                summary.key_points
            )
            variables["key_points_html"] = self._format_key_points_html(
                summary.key_points
            )
        else:
            variables["key_points_list"] = ""
            variables["key_points_markdown"] = ""
            variables["key_points_html"] = ""

        # Speakers
        if template.include_speakers and summary.speakers:
            variables["speakers"] = ", ".join(summary.speakers)
        else:
            variables["speakers"] = ""

        # Topics
        if summary.main_topics:
            variables["topics"] = ", ".join(summary.main_topics)
        else:
            variables["topics"] = ""

        # Metadata
        if template.include_metadata:
            variables["metadata"] = self._format_metadata(summary.metadata)
        else:
            variables["metadata"] = ""

        # Additional kwargs
        variables.update(kwargs)

        return variables

    def _prepare_scene_summary_variables(
        self,
        summary: Any,
        template: SummaryTemplate,
        **kwargs,
    ) -> Dict[str, str]:
        """Prepare template variables for scene summary"""
        variables = {
            "title": f"Scene {summary.scene_id}",
            "scene_id": summary.scene_id,
            "summary_text": summary.summary_text,
            "start_time": summary.start_time,
            "end_time": summary.end_time,
            "duration": summary.duration,
            "duration_formatted": self._format_duration(summary.duration),
        }

        # Timestamps
        if template.include_timestamps:
            variables["start_time_formatted"] = self._format_timestamp(
                summary.start_time, template.timestamp_format
            )
            variables["end_time_formatted"] = self._format_timestamp(
                summary.end_time, template.timestamp_format
            )

        # Key moments
        if summary.key_moments:
            variables["key_moments"] = self._format_key_moments(
                summary.key_moments
            )
        else:
            variables["key_moments"] = ""

        # Objects and actions
        if summary.detected_objects:
            variables["objects"] = ", ".join(summary.detected_objects[:5])
        else:
            variables["objects"] = ""

        if summary.detected_actions:
            variables["actions"] = ", ".join(summary.detected_actions[:3])
        else:
            variables["actions"] = ""

        # Speakers
        if template.include_speakers and summary.speakers:
            variables["speakers"] = ", ".join(summary.speakers)
        else:
            variables["speakers"] = ""

        variables.update(kwargs)

        return variables

    def _prepare_chapters_variables(
        self,
        chapters: Any,
        template: SummaryTemplate,
        **kwargs,
    ) -> Dict[str, str]:
        """Prepare template variables for chapters"""
        variables = {
            "title": kwargs.get("title", "Video Chapters"),
            "num_chapters": len(chapters.chapters),
            "total_duration": chapters.total_duration,
            "duration_formatted": self._format_duration(chapters.total_duration),
        }

        # Format chapters
        variables["chapters_plain"] = self._format_chapters_plain(
            chapters.chapters
        )
        variables["chapters_markdown"] = self._format_chapters_markdown(
            chapters.chapters
        )
        variables["chapters_html"] = self._format_chapters_html(
            chapters.chapters
        )

        variables.update(kwargs)

        return variables

    def _format_key_points_plain(self, key_points: List[str]) -> str:
        """Format key points as plain text list"""
        if not key_points:
            return "None"

        lines = []
        for i, point in enumerate(key_points, 1):
            lines.append(f"{i}. {point}")

        return "\n".join(lines)

    def _format_key_points_markdown(self, key_points: List[str]) -> str:
        """Format key points as markdown list"""
        if not key_points:
            return "*No key points identified*"

        lines = []
        for point in key_points:
            lines.append(f"- {point}")

        return "\n".join(lines)

    def _format_key_points_html(self, key_points: List[str]) -> str:
        """Format key points as HTML list"""
        if not key_points:
            return "<p><em>No key points identified</em></p>"

        lines = ["<ul>"]
        for point in key_points:
            lines.append(f"  <li>{point}</li>")
        lines.append("</ul>")

        return "\n".join(lines)

    def _format_key_moments(self, key_moments: List[Any]) -> str:
        """Format key moments"""
        if not key_moments:
            return "None"

        lines = []
        for moment in key_moments:
            timestamp = self._format_timestamp(moment.timestamp, "HH:MM:SS")
            lines.append(f"- [{timestamp}] {moment.description}")

        return "\n".join(lines)

    def _format_chapters_plain(self, chapters: List[Any]) -> str:
        """Format chapters as plain text"""
        if not chapters:
            return "None"

        lines = []
        for chapter in chapters:
            timestamp = self._format_timestamp(chapter.start_time, "HH:MM:SS")
            lines.append(
                f"{chapter.chapter_number}. [{timestamp}] {chapter.title}"
            )
            if chapter.description:
                lines.append(f"   {chapter.description}")

        return "\n".join(lines)

    def _format_chapters_markdown(self, chapters: List[Any]) -> str:
        """Format chapters as markdown"""
        if not chapters:
            return "*No chapters*"

        lines = []
        for chapter in chapters:
            timestamp = self._format_timestamp(chapter.start_time, "HH:MM:SS")
            lines.append(f"### {chapter.chapter_number}. {chapter.title}")
            lines.append(f"**Time:** {timestamp}")
            if chapter.description:
                lines.append(f"\n{chapter.description}")
            lines.append("")

        return "\n".join(lines)

    def _format_chapters_html(self, chapters: List[Any]) -> str:
        """Format chapters as HTML"""
        if not chapters:
            return "<p><em>No chapters</em></p>"

        lines = ["<div class='chapters'>"]
        for chapter in chapters:
            timestamp = self._format_timestamp(chapter.start_time, "HH:MM:SS")
            lines.append(f"  <div class='chapter'>")
            lines.append(f"    <h3>{chapter.chapter_number}. {chapter.title}</h3>")
            lines.append(f"    <p class='timestamp'><strong>Time:</strong> {timestamp}</p>")
            if chapter.description:
                lines.append(f"    <p>{chapter.description}</p>")
            lines.append(f"  </div>")
        lines.append("</div>")

        return "\n".join(lines)

    def _format_duration(self, seconds: float) -> str:
        """Format duration in human-readable format"""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)

        if hours > 0:
            return f"{hours}h {minutes}m {secs}s"
        elif minutes > 0:
            return f"{minutes}m {secs}s"
        else:
            return f"{secs}s"

    def _format_timestamp(self, seconds: float, format: str = "HH:MM:SS") -> str:
        """Format timestamp"""
        if format == "seconds":
            return f"{seconds:.1f}s"

        # HH:MM:SS format
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)

        if hours > 0:
            return f"{hours:02d}:{minutes:02d}:{secs:02d}"
        else:
            return f"{minutes:02d}:{secs:02d}"

    def _format_metadata(self, metadata: Dict[str, Any]) -> str:
        """Format metadata"""
        if not metadata:
            return ""

        lines = []
        for key, value in metadata.items():
            lines.append(f"{key}: {value}")

        return "\n".join(lines)

    def list_templates(self) -> List[str]:
        """List available template names"""
        return list(self.templates.keys())

    def get_template(self, name: str) -> Optional[SummaryTemplate]:
        """Get template by name"""
        return self.templates.get(name)


# Global template manager instance
_template_manager = SummaryTemplateManager()


def format_summary(
    summary: Any,
    template: str = "plain_detailed",
    **kwargs,
) -> str:
    """
    Convenience function to format summary

    Args:
        summary: Summary object (VideoSummary or SceneSummary)
        template: Template name
        **kwargs: Additional template variables

    Returns:
        Formatted summary string
    """
    # Detect summary type
    if hasattr(summary, "video_id"):
        return _template_manager.format_video_summary(
            summary, template, **kwargs
        )
    elif hasattr(summary, "scene_id"):
        return _template_manager.format_scene_summary(
            summary, template, **kwargs
        )
    else:
        return str(summary)


def get_template_manager() -> SummaryTemplateManager:
    """Get global template manager instance"""
    return _template_manager
