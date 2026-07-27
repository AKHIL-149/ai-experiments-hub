"""
Video summarizer for generating overall video summaries
Use transcript and scene descriptions to create comprehensive summaries
"""

import logging
from typing import List, Optional, Dict, Any
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)


class SummaryLength(str, Enum):
    """Summary length options"""
    BRIEF = "brief"  # 2-3 sentences
    SHORT = "short"  # 1 paragraph
    MEDIUM = "medium"  # 2-3 paragraphs
    DETAILED = "detailed"  # Multiple paragraphs
    COMPREHENSIVE = "comprehensive"  # Full analysis


@dataclass
class VideoSummary:
    """Video summary result"""
    video_id: str
    summary_text: str
    summary_length: SummaryLength

    # Optional components
    key_points: List[str] = field(default_factory=list)
    main_topics: List[str] = field(default_factory=list)
    speakers: List[str] = field(default_factory=list)

    # Metadata
    word_count: int = 0
    num_scenes: int = 0
    duration: float = 0.0

    # LLM info
    tokens_used: Dict[str, int] = field(default_factory=dict)
    cost_usd: float = 0.0

    metadata: Dict[str, Any] = field(default_factory=dict)


class VideoSummarizer:
    """
    Generate overall video summaries
    Combine transcript and visual context for comprehensive summaries
    """

    def __init__(
        self,
        llm_client=None,
        default_length: SummaryLength = SummaryLength.MEDIUM,
        include_timestamps: bool = True,
        include_key_points: bool = True,
    ):
        """
        Initialize video summarizer

        Args:
            llm_client: LLMClient instance
            default_length: Default summary length
            include_timestamps: Include timestamps in summary
            include_key_points: Extract key points
        """
        self.llm_client = llm_client
        self.default_length = default_length
        self.include_timestamps = include_timestamps
        self.include_key_points = include_key_points

        logger.info(
            f"Initialized VideoSummarizer "
            f"(length={default_length.value})"
        )

    def summarize_video(
        self,
        video_id: str,
        duration: float,
        transcript: Optional[str] = None,
        scenes: Optional[List[Dict[str, Any]]] = None,
        enriched_scenes: Optional[List[Any]] = None,
        length: Optional[SummaryLength] = None,
    ) -> VideoSummary:
        """
        Generate video summary

        Args:
            video_id: Video identifier
            duration: Video duration in seconds
            transcript: Full video transcript
            scenes: Scene list
            enriched_scenes: Enriched scenes with context
            length: Summary length (overrides default)

        Returns:
            VideoSummary
        """
        length = length or self.default_length

        logger.info(
            f"Summarizing video {video_id} "
            f"(duration={duration:.1f}s, length={length.value})"
        )

        # Prepare context for LLM
        context = self._prepare_context(
            duration=duration,
            transcript=transcript,
            scenes=scenes,
            enriched_scenes=enriched_scenes,
        )

        # Build prompt
        prompt = self._build_summary_prompt(
            context=context,
            length=length,
        )

        # Generate summary using LLM
        if self.llm_client:
            response = self.llm_client.generate(
                prompt=prompt,
                max_tokens=self._get_max_tokens(length),
                temperature=0.3,  # Lower temperature for factual summaries
                system_prompt=self._get_system_prompt(),
            )

            summary_text = response["text"]
            tokens_used = response.get("tokens", {})
            cost_usd = self.llm_client.estimate_cost(tokens_used)
        else:
            # Fallback: simple text-based summary
            summary_text = self._generate_fallback_summary(context, length)
            tokens_used = {}
            cost_usd = 0.0

        # Extract key points if requested
        key_points = []
        if self.include_key_points:
            key_points = self._extract_key_points(
                summary_text=summary_text,
                context=context,
            )

        # Extract main topics
        main_topics = self._extract_main_topics(context)

        # Extract speakers
        speakers = self._extract_speakers(context)

        # Calculate word count
        word_count = len(summary_text.split())

        return VideoSummary(
            video_id=video_id,
            summary_text=summary_text,
            summary_length=length,
            key_points=key_points,
            main_topics=main_topics,
            speakers=speakers,
            word_count=word_count,
            num_scenes=len(scenes) if scenes else 0,
            duration=duration,
            tokens_used=tokens_used,
            cost_usd=cost_usd,
            metadata={
                "has_transcript": bool(transcript),
                "has_scenes": bool(scenes),
                "has_enriched_scenes": bool(enriched_scenes),
            },
        )

    def _prepare_context(
        self,
        duration: float,
        transcript: Optional[str],
        scenes: Optional[List[Dict[str, Any]]],
        enriched_scenes: Optional[List[Any]],
    ) -> Dict[str, Any]:
        """
        Prepare context for summarization

        Args:
            duration: Video duration
            transcript: Transcript text
            scenes: Scene list
            enriched_scenes: Enriched scenes

        Returns:
            Context dictionary
        """
        context = {
            "duration": duration,
            "duration_formatted": self._format_duration(duration),
        }

        # Add transcript
        if transcript:
            context["transcript"] = transcript
            context["transcript_length"] = len(transcript)

        # Add scene information
        if enriched_scenes:
            context["scenes"] = []
            for scene in enriched_scenes:
                scene_info = {
                    "scene_id": scene.scene_id,
                    "start_time": scene.start_time,
                    "end_time": scene.end_time,
                    "duration": scene.duration,
                    "title": scene.title,
                    "description": scene.description,
                }
                context["scenes"].append(scene_info)
        elif scenes:
            context["scenes"] = scenes

        return context

    def _build_summary_prompt(
        self,
        context: Dict[str, Any],
        length: SummaryLength,
    ) -> str:
        """
        Build prompt for LLM

        Args:
            context: Video context
            length: Summary length

        Returns:
            Prompt string
        """
        parts = []

        # Header
        parts.append(f"Video Duration: {context.get('duration_formatted', 'Unknown')}")
        parts.append("")

        # Transcript
        if "transcript" in context:
            transcript = context["transcript"]
            # Truncate if too long
            if len(transcript) > 10000:
                transcript = transcript[:10000] + "... [truncated]"
            parts.append("Transcript:")
            parts.append(transcript)
            parts.append("")

        # Scene descriptions
        if "scenes" in context and context["scenes"]:
            parts.append("Scene Breakdown:")
            for scene in context["scenes"]:
                scene_desc = (
                    f"- Scene {scene.get('scene_id', '?')} "
                    f"({scene.get('start_time', 0):.1f}s - {scene.get('end_time', 0):.1f}s): "
                    f"{scene.get('description', scene.get('title', 'No description'))}"
                )
                parts.append(scene_desc)
            parts.append("")

        # Instructions
        parts.append(self._get_length_instruction(length))

        return "\n".join(parts)

    def _get_system_prompt(self) -> str:
        """Get system prompt for LLM"""
        return (
            "You are a video summarization expert. "
            "Your task is to create clear, accurate, and engaging summaries of videos "
            "based on transcripts and scene descriptions. "
            "Focus on the main ideas, key points, and overall narrative. "
            "Be concise and avoid unnecessary details."
        )

    def _get_length_instruction(self, length: SummaryLength) -> str:
        """Get instruction for specific summary length"""
        instructions = {
            SummaryLength.BRIEF: (
                "Please provide a BRIEF summary in 2-3 sentences that captures "
                "the essence of this video."
            ),
            SummaryLength.SHORT: (
                "Please provide a SHORT summary in one paragraph (4-6 sentences) "
                "that covers the main points of this video."
            ),
            SummaryLength.MEDIUM: (
                "Please provide a MEDIUM-length summary in 2-3 paragraphs "
                "that covers the main topics, key points, and overall narrative."
            ),
            SummaryLength.DETAILED: (
                "Please provide a DETAILED summary in multiple paragraphs "
                "that thoroughly covers all major topics, key arguments, "
                "and important details."
            ),
            SummaryLength.COMPREHENSIVE: (
                "Please provide a COMPREHENSIVE analysis and summary "
                "that covers all aspects of the video, including context, "
                "main arguments, supporting details, conclusions, and implications."
            ),
        }
        return instructions.get(length, instructions[SummaryLength.MEDIUM])

    def _get_max_tokens(self, length: SummaryLength) -> int:
        """Get max tokens for summary length"""
        token_limits = {
            SummaryLength.BRIEF: 150,
            SummaryLength.SHORT: 300,
            SummaryLength.MEDIUM: 600,
            SummaryLength.DETAILED: 1200,
            SummaryLength.COMPREHENSIVE: 2500,
        }
        return token_limits.get(length, 600)

    def _generate_fallback_summary(
        self,
        context: Dict[str, Any],
        length: SummaryLength,
    ) -> str:
        """
        Generate fallback summary without LLM

        Args:
            context: Video context
            length: Summary length

        Returns:
            Summary text
        """
        parts = []

        # Basic info
        parts.append(
            f"This is a {context.get('duration_formatted', 'unknown duration')} video."
        )

        # Scene count
        if "scenes" in context:
            parts.append(f"It contains {len(context['scenes'])} scenes.")

        # Transcript snippet
        if "transcript" in context:
            transcript = context["transcript"]
            snippet_length = 200 if length == SummaryLength.BRIEF else 500
            snippet = transcript[:snippet_length]
            if len(transcript) > snippet_length:
                snippet += "..."
            parts.append(f"The video discusses: {snippet}")

        return " ".join(parts)

    def _extract_key_points(
        self,
        summary_text: str,
        context: Dict[str, Any],
    ) -> List[str]:
        """
        Extract key points from summary

        Args:
            summary_text: Generated summary
            context: Video context

        Returns:
            List of key points
        """
        # Simple extraction: look for bullet points or numbered lists in summary
        key_points = []

        lines = summary_text.split("\n")
        for line in lines:
            line = line.strip()
            # Check for bullet points or numbers
            if line.startswith(("-", "*", "•")) or (
                len(line) > 2 and line[0].isdigit() and line[1] in (".", ")")
            ):
                # Remove bullet/number
                point = line.lstrip("-*•0123456789.) ").strip()
                if point:
                    key_points.append(point)

        # If no explicit points found, try to extract from first sentences
        if not key_points and self.llm_client:
            # Use LLM to extract key points
            prompt = (
                f"Extract 3-5 key points from this summary:\n\n{summary_text}\n\n"
                f"Return only the key points as a numbered list."
            )
            try:
                response = self.llm_client.generate(
                    prompt=prompt,
                    max_tokens=300,
                    temperature=0.3,
                )
                # Parse response
                for line in response["text"].split("\n"):
                    line = line.strip()
                    if line and (
                        line.startswith(("-", "*", "•"))
                        or (len(line) > 2 and line[0].isdigit())
                    ):
                        point = line.lstrip("-*•0123456789.) ").strip()
                        if point:
                            key_points.append(point)
            except Exception as e:
                logger.warning(f"Failed to extract key points: {e}")

        return key_points[:5]  # Limit to top 5

    def _extract_main_topics(self, context: Dict[str, Any]) -> List[str]:
        """Extract main topics from context"""
        topics = set()

        # From scene titles
        if "scenes" in context:
            for scene in context["scenes"]:
                title = scene.get("title", "")
                # Extract topic from title
                if title and ":" in title:
                    topic = title.split(":")[1].strip()
                    topics.add(topic)

        return list(topics)[:5]

    def _extract_speakers(self, context: Dict[str, Any]) -> List[str]:
        """Extract speakers from context"""
        speakers = set()

        # From scenes
        if "scenes" in context:
            for scene in context["scenes"]:
                desc = scene.get("description", "")
                # Look for speaker mentions
                if "Speaker" in desc or "speaker" in desc:
                    # Simple extraction
                    import re
                    matches = re.findall(r"Speaker \d+", desc)
                    speakers.update(matches)

        return list(speakers)

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

    def summarize_batch(
        self,
        videos: List[Dict[str, Any]],
        length: Optional[SummaryLength] = None,
    ) -> List[VideoSummary]:
        """
        Summarize multiple videos in batch

        Args:
            videos: List of video data dicts
            length: Summary length

        Returns:
            List of VideoSummary objects
        """
        summaries = []

        for video in videos:
            try:
                summary = self.summarize_video(
                    video_id=video.get("video_id", ""),
                    duration=video.get("duration", 0.0),
                    transcript=video.get("transcript"),
                    scenes=video.get("scenes"),
                    enriched_scenes=video.get("enriched_scenes"),
                    length=length,
                )
                summaries.append(summary)
            except Exception as e:
                logger.error(f"Failed to summarize video {video.get('video_id')}: {e}")

        return summaries

    def export_summary_to_dict(self, summary: VideoSummary) -> Dict[str, Any]:
        """
        Export summary to dictionary

        Args:
            summary: VideoSummary

        Returns:
            Dictionary representation
        """
        return {
            "video_id": summary.video_id,
            "summary_text": summary.summary_text,
            "summary_length": summary.summary_length.value,
            "key_points": summary.key_points,
            "main_topics": summary.main_topics,
            "speakers": summary.speakers,
            "word_count": summary.word_count,
            "num_scenes": summary.num_scenes,
            "duration": summary.duration,
            "tokens_used": summary.tokens_used,
            "cost_usd": summary.cost_usd,
            "metadata": summary.metadata,
        }


def summarize_video(
    video_id: str,
    duration: float,
    transcript: Optional[str] = None,
    scenes: Optional[List[Dict[str, Any]]] = None,
    llm_client=None,
    length: SummaryLength = SummaryLength.MEDIUM,
) -> VideoSummary:
    """
    Convenience function to summarize video

    Args:
        video_id: Video identifier
        duration: Video duration
        transcript: Transcript text
        scenes: Scene list
        llm_client: LLMClient instance
        length: Summary length

    Returns:
        VideoSummary
    """
    summarizer = VideoSummarizer(llm_client=llm_client)
    return summarizer.summarize_video(
        video_id=video_id,
        duration=duration,
        transcript=transcript,
        scenes=scenes,
        length=length,
    )
