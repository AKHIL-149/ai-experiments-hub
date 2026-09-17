"""Meeting Analyzer - Main orchestrator for full meeting analysis pipeline"""

import json
import logging
from pathlib import Path
from datetime import datetime
from typing import Dict, Optional, Callable

from .audio_processor import AudioProcessor
from .transcription_service import TranscriptionService
from .cache_manager import CacheManager
from .llm_client import LLMClient
from .summarizer import Summarizer
from .action_extractor import ActionExtractor

try:  # entry points put src/ on sys.path (import "utils.x"); support both
    from utils.summary_templates import SummaryTemplateManager
    from utils.video_processor import VideoProcessor
except ImportError:  # pragma: no cover
    from ..utils.summary_templates import SummaryTemplateManager
    from ..utils.video_processor import VideoProcessor

logger = logging.getLogger(__name__)


class MeetingAnalyzer:
    """
    Orchestrate full meeting analysis pipeline:
    Audio → Transcription → Summarization → Action Extraction → Report Generation

    Manages caching at each stage for cost optimization.
    """

    def __init__(
        self,
        transcription_service: TranscriptionService,
        llm_client: LLMClient,
        cache_manager: Optional[CacheManager] = None,
        audio_processor: Optional[AudioProcessor] = None,
        template_manager: Optional[SummaryTemplateManager] = None,
        video_processor: Optional[VideoProcessor] = None
    ):
        """
        Initialize Meeting Analyzer

        Args:
            transcription_service: Transcription service instance
            llm_client: LLM client for summarization/extraction
            cache_manager: Optional cache manager
            audio_processor: Optional audio processor
            template_manager: Optional SummaryTemplateManager for
                --template report rendering (defaults to one that also
                picks up ./templates/custom/*.md)
        """
        self.transcription_service = transcription_service
        self.llm_client = llm_client
        self.cache_manager = cache_manager
        self.audio_processor = audio_processor or AudioProcessor()
        self.template_manager = template_manager or SummaryTemplateManager(
            custom_templates_dir='./templates/custom'
        )
        self.video_processor = video_processor or VideoProcessor()

        # Initialize AI components
        self.summarizer = Summarizer(llm_client)
        self.action_extractor = ActionExtractor(llm_client)

        logger.info("Meeting Analyzer initialized")

    def analyze_meeting(
        self,
        audio_path: str,
        summary_level: str = "standard",
        extract_actions: bool = True,
        extract_topics: bool = True,
        language: Optional[str] = None,
        all_levels: bool = False,
        progress_callback: Optional[Callable[[str], None]] = None
    ) -> Dict:
        """
        Perform full meeting analysis

        Args:
            audio_path: Path to audio file
            summary_level: Summary detail level ("brief", "standard", "detailed") -
                also which level result["summary"] is set to when
                all_levels=True (the other two are still generated, just
                not the "primary" one every existing caller reads).
            extract_actions: Whether to extract action items
            extract_topics: Whether to extract key topics
            language: Language code (optional)
            all_levels: Generate brief + standard + detailed summaries in
                one pass (result["summary_levels"] holds all three; each
                is independently cached, so re-running with a different
                summary_level on the same transcript is free).
            progress_callback: Optional callback invoked with an event
                name ("transcription_done", "summarization_done") right
                as each real pipeline step finishes, so a caller (the web
                server) can report genuine per-stage progress instead of
                only knowing "the whole thing" finished. May be called
                from a worker thread if this method itself is invoked via
                asyncio.to_thread - callers must marshal their own
                thread-unsafe work (DB/asyncio) accordingly. Best-effort:
                a raising callback is logged and swallowed rather than
                failing the analysis.

        Returns:
            dict with complete analysis:
                {
                    "metadata": {...},
                    "transcript": {...},
                    "summary": {...},
                    "actions": {...},
                    "topics": [...],
                    "statistics": {...}
                }
        """
        logger.info(f"Starting meeting analysis: {audio_path}")

        # Step 0: if given a video file, pull the audio track out first.
        # Idempotent - is_video_file() is False for plain audio.
        source_file = Path(audio_path).name
        extracted_audio = None
        if self.video_processor.is_video_file(audio_path):
            logger.info(f"Detected video file: {source_file} - extracting audio track")
            audio_path = self.video_processor.extract_audio(audio_path)
            extracted_audio = audio_path
            logger.info(f"Extracted audio to: {audio_path}")

        start_time = datetime.now()
        statistics = {
            "total_cost_usd": 0.0,
            "cache_hits": 0,
            "cache_misses": 0,
            "transcription_backend": getattr(self.transcription_service, "backend", "unknown"),
            "llm_provider": getattr(self.llm_client, "backend", "unknown"),
            "llm_model": getattr(self.llm_client, "model", "unknown"),
            "processing_time_seconds": 0
        }

        # Step 1: Get audio metadata
        logger.info("Step 1: Extracting audio metadata")
        metadata = self.audio_processor.get_metadata(audio_path)

        # Step 2: Transcribe audio (with caching)
        logger.info("Step 2: Transcribing audio")
        transcript_result = self.transcription_service.transcribe(
            audio_path,
            language=language
        )

        # Transcription is the last step that touches the audio file, so
        # a temp track extracted from a video can go now. (The transcript
        # itself is cached by content hash, so a re-run re-extracts to an
        # identical file and still hits the cache.)
        if extracted_audio:
            try:
                Path(extracted_audio).unlink(missing_ok=True)
                logger.info(f"Removed temporary extracted audio: {extracted_audio}")
            except OSError as e:
                logger.warning(f"Could not remove temp audio {extracted_audio}: {e}")

        if transcript_result.get("cached"):
            statistics["cache_hits"] += 1
        else:
            statistics["cache_misses"] += 1

        transcript_text = transcript_result["text"]
        self._emit_progress(progress_callback, "transcription_done")

        # Step 3: Summarize transcript (with caching)
        summary_levels = None
        if all_levels:
            logger.info("Step 3: Generating brief + standard + detailed summaries")
            summary_levels = {}
            for lvl in ("brief", "standard", "detailed"):
                lvl_result = self._summarize_with_cache(transcript_text, lvl)
                summary_levels[lvl] = lvl_result
                if lvl_result.get("cached"):
                    statistics["cache_hits"] += 1
                else:
                    statistics["cache_misses"] += 1
                    statistics["total_cost_usd"] += lvl_result.get("estimated_cost", 0.0)
            # requested summary_level stays the "primary" result - every
            # existing reader (report generators, templates, the web
            # result view) keeps working against result["summary"]
            # unchanged; summary_levels carries the other two.
            summary_result = summary_levels.get(summary_level, summary_levels["standard"])
        else:
            logger.info(f"Step 3: Generating {summary_level} summary")
            summary_result = self._summarize_with_cache(transcript_text, summary_level)

            if summary_result.get("cached"):
                statistics["cache_hits"] += 1
            else:
                statistics["cache_misses"] += 1
                statistics["total_cost_usd"] += summary_result.get("estimated_cost", 0.0)

        self._emit_progress(progress_callback, "summarization_done")

        # Step 4: Extract action items (if enabled)
        actions_result = None
        if extract_actions:
            logger.info("Step 4: Extracting action items")
            actions_result = self.action_extractor.extract_actions(
                transcript_text,
                summary=summary_result["summary"]
            )
            # Estimate cost for action extraction
            tokens = actions_result.get("tokens_used", {})
            if tokens:
                cost = self.llm_client.estimate_cost(tokens)
                statistics["total_cost_usd"] += cost

        # Step 5: Extract key topics (if enabled)
        topics = None
        if extract_topics:
            logger.info("Step 5: Extracting key topics")
            topics = self.summarizer.extract_key_topics(transcript_text)

        # Calculate processing time
        end_time = datetime.now()
        statistics["processing_time_seconds"] = (end_time - start_time).total_seconds()

        # Compile final result
        result = {
            "metadata": {
                "audio_file": Path(audio_path).name,
                "source_file": source_file,
                "analyzed_at": datetime.now().isoformat(),
                **metadata
            },
            "transcript": {
                "text": transcript_text,
                "language": transcript_result.get("language", "unknown"),
                "backend": transcript_result.get("backend", "unknown"),
                "cached": transcript_result.get("cached", False)
            },
            "summary": {
                "text": summary_result["summary"],
                "level": summary_level,
                "word_count": summary_result.get("word_count", 0),
                "cached": summary_result.get("cached", False)
            },
            "actions": actions_result,
            "topics": topics,
            "statistics": statistics
        }

        if summary_levels:
            result["summary_levels"] = {
                lvl: {
                    "text": lvl_result["summary"],
                    "word_count": lvl_result.get("word_count", 0),
                    "cached": lvl_result.get("cached", False)
                }
                for lvl, lvl_result in summary_levels.items()
            }

        logger.info(
            f"Analysis complete: {statistics['processing_time_seconds']:.1f}s, "
            f"${statistics['total_cost_usd']:.4f} cost"
        )

        return result

    @staticmethod
    def _emit_progress(callback: Optional[Callable[[str], None]], event: str):
        """Best-effort progress_callback invocation - a bad callback
        shouldn't be able to fail the analysis it's just reporting on."""
        if not callback:
            return
        try:
            callback(event)
        except Exception as e:
            logger.warning(f"progress_callback raised for event '{event}': {e}")

    def _summarize_with_cache(self, transcript: str, level: str) -> Dict:
        """
        Summarize with cache support

        Args:
            transcript: Transcript text
            level: Summary level

        Returns:
            Summary result with cache status
        """
        # Check cache. level is part of the cache key (not just a
        # post-hoc validation check) - brief/standard/detailed summaries
        # of the same transcript are different results, each with its
        # own slot, so generating one level doesn't evict another.
        if self.cache_manager:
            transcript_hash = self.cache_manager.hash_text(transcript)
            model = self.llm_client.model

            cached_summary = self.cache_manager.get_summary(transcript_hash, model, level=level)

            if cached_summary and cached_summary.get("level") == level:
                logger.info(f"Using cached {level} summary")
                cached_summary["cached"] = True
                return cached_summary

        # Generate new summary
        summary_result = self.summarizer.summarize(transcript, level=level)

        # Cache the result
        if self.cache_manager:
            transcript_hash = self.cache_manager.hash_text(transcript)
            self.cache_manager.set_summary(transcript_hash, self.llm_client.model, summary_result, level=level)

        summary_result["cached"] = False
        return summary_result

    def generate_report(
        self,
        analysis_result: Dict,
        format: str = "markdown",
        output_path: Optional[str] = None,
        template: Optional[str] = None
    ) -> str:
        """
        Generate formatted report from analysis

        Args:
            analysis_result: Result from analyze_meeting()
            format: Output format ("markdown", "json", "html", "txt")
            output_path: Optional path to save report
            template: Optional named summary template (executive, detailed,
                brief, meeting_minutes, technical, or a custom
                templates/custom/<name>.md). When set, the report is
                rendered from that Jinja2 template and `format` is ignored
                (templates always produce Markdown).

        Returns:
            Formatted report string
        """
        if template:
            logger.info(f"Generating report from template: {template}")
            report = self.template_manager.render_summary(template, analysis_result)
        elif format == "json":
            logger.info("Generating json report")
            report = self._generate_json_report(analysis_result)
        elif format == "html":
            logger.info("Generating html report")
            report = self._generate_html_report(analysis_result)
        elif format == "txt":
            logger.info("Generating txt report")
            report = self._generate_text_report(analysis_result)
        else:  # markdown (default)
            logger.info("Generating markdown report")
            report = self._generate_markdown_report(analysis_result)

        # Save to file if path provided
        if output_path:
            Path(output_path).parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(report)
            logger.info(f"Report saved to: {output_path}")

        return report

    def _generate_markdown_report(self, result: Dict) -> str:
        """Generate Markdown report"""
        report = []

        # Header
        report.append(f"# Meeting Analysis Report")
        report.append(f"\n**File:** {(result['metadata'].get('source_file') or result['metadata']['audio_file'])}")
        report.append(f"**Analyzed:** {result['metadata']['analyzed_at']}")
        report.append(f"**Duration:** {result['metadata']['duration_seconds']:.1f}s")
        report.append("")

        # Summary - all three levels if all_levels=True was used,
        # otherwise just the one that was generated.
        if result.get('summary_levels'):
            for lvl in ("brief", "standard", "detailed"):
                lvl_data = result['summary_levels'].get(lvl)
                if not lvl_data:
                    continue
                report.append(f"## Summary ({lvl.capitalize()})")
                report.append("")
                report.append(lvl_data['text'])
                report.append("")
        else:
            report.append("## Summary")
            report.append("")
            report.append(result['summary']['text'])
            report.append("")

        # Key Topics
        if result.get('topics'):
            report.append("## Key Topics")
            report.append("")
            for i, topic in enumerate(result['topics'], 1):
                report.append(f"{i}. {topic}")
            report.append("")

        # Action Items
        if result.get('actions'):
            actions_report = self.action_extractor.generate_action_report(result['actions'])
            report.append(actions_report)

        # Statistics
        stats = result['statistics']
        report.append("## Statistics")
        report.append("")
        report.append(f"- **Processing Time:** {stats['processing_time_seconds']:.1f}s")
        report.append(f"- **Total Cost:** ${stats['total_cost_usd']:.4f}")
        report.append(f"- **Cache Hits:** {stats['cache_hits']}")
        report.append(f"- **Cache Misses:** {stats['cache_misses']}")
        report.append("")

        # Transcript
        report.append("## Full Transcript")
        report.append("")
        report.append(f"**Language:** {result['transcript']['language']}")
        report.append(f"**Backend:** {result['transcript']['backend']}")
        report.append("")
        report.append(result['transcript']['text'])
        report.append("")

        return "\n".join(report)

    def _generate_json_report(self, result: Dict) -> str:
        """Generate JSON report"""
        return json.dumps(result, indent=2, ensure_ascii=False)

    def _generate_text_report(self, result: Dict) -> str:
        """Generate plain text report"""
        report = []

        report.append("="*60)
        report.append("MEETING ANALYSIS REPORT")
        report.append("="*60)
        report.append("")
        report.append(f"File: {(result['metadata'].get('source_file') or result['metadata']['audio_file'])}")
        report.append(f"Analyzed: {result['metadata']['analyzed_at']}")
        report.append(f"Duration: {result['metadata']['duration_seconds']:.1f}s")
        report.append("")

        if result.get('summary_levels'):
            for lvl in ("brief", "standard", "detailed"):
                lvl_data = result['summary_levels'].get(lvl)
                if not lvl_data:
                    continue
                report.append("-"*60)
                report.append(f"SUMMARY ({lvl.upper()})")
                report.append("-"*60)
                report.append("")
                report.append(lvl_data['text'])
                report.append("")
        else:
            report.append("-"*60)
            report.append("SUMMARY")
            report.append("-"*60)
            report.append("")
            report.append(result['summary']['text'])
            report.append("")

        if result.get('actions') and result['actions']['action_items']:
            report.append("-"*60)
            report.append("ACTION ITEMS")
            report.append("-"*60)
            report.append("")

            for action in result['actions']['action_items']:
                report.append(f"[{action['id']}] {action['description']}")
                report.append(f"    Assignee: {action.get('assignee', 'Unassigned')}")
                report.append(f"    Due: {action.get('due_date', 'Not specified')}")
                report.append("")

        report.append("-"*60)
        report.append("FULL TRANSCRIPT")
        report.append("-"*60)
        report.append("")
        report.append(result['transcript']['text'])
        report.append("")

        return "\n".join(report)

    def _generate_html_report(self, result: Dict) -> str:
        """Generate HTML report"""
        if result.get('summary_levels'):
            summary_html = ''.join(
                f"<h2>Summary ({lvl.capitalize()})</h2><p>{result['summary_levels'][lvl]['text']}</p>"
                for lvl in ("brief", "standard", "detailed")
                if lvl in result['summary_levels']
            )
        else:
            summary_html = f"<h2>Summary</h2><p>{result['summary']['text']}</p>"

        html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>Meeting Analysis Report</title>
    <style>
        body {{ font-family: Arial, sans-serif; max-width: 900px; margin: 40px auto; padding: 0 20px; }}
        h1 {{ color: #333; border-bottom: 2px solid #0066cc; padding-bottom: 10px; }}
        h2 {{ color: #0066cc; margin-top: 30px; }}
        .metadata {{ background: #f5f5f5; padding: 15px; border-radius: 5px; }}
        .action-item {{ background: #fff3cd; padding: 10px; margin: 10px 0; border-left: 4px solid #ffc107; }}
        .decision {{ background: #d1ecf1; padding: 10px; margin: 10px 0; border-left: 4px solid #0c5460; }}
        .transcript {{ background: #f8f9fa; padding: 15px; border-radius: 5px; white-space: pre-wrap; }}
        .stats {{ display: grid; grid-template-columns: repeat(2, 1fr); gap: 10px; }}
        .stat-box {{ background: #e9ecef; padding: 10px; border-radius: 5px; }}
    </style>
</head>
<body>
    <h1>Meeting Analysis Report</h1>

    <div class="metadata">
        <p><strong>File:</strong> {(result['metadata'].get('source_file') or result['metadata']['audio_file'])}</p>
        <p><strong>Analyzed:</strong> {result['metadata']['analyzed_at']}</p>
        <p><strong>Duration:</strong> {result['metadata']['duration_seconds']:.1f}s</p>
    </div>

    {summary_html}

    {'<h2>Key Topics</h2><ul>' + ''.join(f'<li>{topic}</li>' for topic in result.get('topics', [])) + '</ul>' if result.get('topics') else ''}

    {self._generate_actions_html(result.get('actions')) if result.get('actions') else ''}

    <h2>Statistics</h2>
    <div class="stats">
        <div class="stat-box">
            <strong>Processing Time:</strong> {result['statistics']['processing_time_seconds']:.1f}s
        </div>
        <div class="stat-box">
            <strong>Total Cost:</strong> ${result['statistics']['total_cost_usd']:.4f}
        </div>
        <div class="stat-box">
            <strong>Cache Hits:</strong> {result['statistics']['cache_hits']}
        </div>
        <div class="stat-box">
            <strong>Cache Misses:</strong> {result['statistics']['cache_misses']}
        </div>
    </div>

    <h2>Full Transcript</h2>
    <div class="transcript">{result['transcript']['text']}</div>
</body>
</html>"""

        return html

    def _generate_actions_html(self, actions: Dict) -> str:
        """Generate HTML for actions section"""
        html = []

        if actions.get('action_items'):
            html.append("<h2>Action Items</h2>")
            for action in actions['action_items']:
                html.append(f"""<div class="action-item">
    <strong>{action['id']}. {action['description']}</strong><br>
    Assignee: {action.get('assignee', 'Unassigned')} |
    Due: {action.get('due_date', 'Not specified')} |
    Priority: {action.get('priority', 'medium')}
</div>""")

        if actions.get('decisions'):
            html.append("<h2>Decisions Made</h2>")
            for decision in actions['decisions']:
                html.append(f"""<div class="decision">
    <strong>{decision['id']}. {decision['decision']}</strong><br>
    Context: {decision.get('context', 'N/A')}
</div>""")

        return "\n".join(html)
