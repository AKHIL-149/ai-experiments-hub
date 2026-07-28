"""
Highlight exporter for creating highlight reels
Concatenate multiple clips with transitions and effects
"""

import logging
import os
import subprocess
from typing import List, Optional, Dict, Any, Callable
from dataclasses import dataclass, field
from pathlib import Path
import tempfile

logger = logging.getLogger(__name__)


@dataclass
class TransitionConfig:
    """Configuration for transitions between clips"""
    transition_type: str = "fade"  # fade, dissolve, wipeleft, wiperight, none
    transition_duration: float = 0.5  # Seconds

    # Fade transitions
    fade_color: str = "black"  # black, white

    # Advanced transitions (require complex filters)
    use_advanced: bool = False


@dataclass
class ExportConfig:
    """Configuration for highlight reel export"""
    # Output settings
    output_format: str = "mp4"
    video_codec: str = "libx264"
    audio_codec: str = "aac"
    preset: str = "medium"
    crf: int = 23

    # Transitions
    transition: Optional[TransitionConfig] = None

    # Title cards
    include_title_cards: bool = False
    title_duration: float = 2.0

    # Intro/Outro
    intro_path: Optional[str] = None
    outro_path: Optional[str] = None

    # Audio
    background_music_path: Optional[str] = None
    music_volume: float = 0.3  # 0.0 to 1.0

    # Resolution
    output_width: Optional[int] = None
    output_height: Optional[int] = None

    # Metadata
    include_timestamps: bool = True
    include_titles: bool = True

    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class HighlightReel:
    """Exported highlight reel metadata"""
    reel_id: str
    video_id: str
    output_path: str

    # Content
    num_highlights: int
    total_duration: float
    highlights: List[Any]  # List of Highlight objects

    # File info
    file_size_bytes: int

    # Configuration
    config: ExportConfig

    # Processing info
    creation_time: Optional[str] = None
    ffmpeg_command: Optional[str] = None

    metadata: Dict[str, Any] = field(default_factory=dict)


class HighlightExporter:
    """
    Export highlight reels from multiple clips
    Concatenate clips with transitions and effects
    """

    def __init__(
        self,
        output_dir: str = "./highlight_reels",
        ffmpeg_path: str = "ffmpeg",
        default_config: Optional[ExportConfig] = None,
    ):
        """
        Initialize highlight exporter

        Args:
            output_dir: Directory for output reels
            ffmpeg_path: Path to ffmpeg executable
            default_config: Default export configuration
        """
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self.ffmpeg_path = ffmpeg_path
        self.default_config = default_config or ExportConfig()

        if self.default_config.transition is None:
            self.default_config.transition = TransitionConfig()

        # Verify ffmpeg
        self._verify_ffmpeg()

        logger.info(f"Initialized HighlightExporter (output_dir={output_dir})")

    def _verify_ffmpeg(self):
        """Verify ffmpeg is available"""
        try:
            result = subprocess.run(
                [self.ffmpeg_path, "-version"],
                capture_output=True,
                text=True,
                check=True,
            )
            logger.debug(f"FFmpeg version: {result.stdout.split()[2]}")
        except (subprocess.CalledProcessError, FileNotFoundError) as e:
            logger.error(f"FFmpeg not found: {e}")
            raise RuntimeError(
                f"FFmpeg not available at {self.ffmpeg_path}"
            )

    def export_highlight_reel(
        self,
        video_id: str,
        highlights: List[Any],
        clip_paths: List[str],
        reel_id: Optional[str] = None,
        output_filename: Optional[str] = None,
        config: Optional[ExportConfig] = None,
        progress_callback: Optional[Callable[[int, int], None]] = None,
    ) -> HighlightReel:
        """
        Export highlight reel from clips

        Args:
            video_id: Video identifier
            highlights: List of Highlight objects
            clip_paths: Paths to clip files (same order as highlights)
            reel_id: Optional reel identifier
            output_filename: Optional custom filename
            config: Export configuration
            progress_callback: Optional progress callback

        Returns:
            HighlightReel metadata
        """
        if len(highlights) != len(clip_paths):
            raise ValueError(
                f"Mismatch: {len(highlights)} highlights, {len(clip_paths)} clips"
            )

        if not clip_paths:
            raise ValueError("No clips provided")

        config = config or self.default_config
        reel_id = reel_id or f"{video_id}_reel"

        logger.info(
            f"Exporting highlight reel: {len(clip_paths)} clips "
            f"for video {video_id}"
        )

        # Generate output path
        if output_filename:
            output_path = self.output_dir / output_filename
        else:
            output_path = self.output_dir / f"{reel_id}.{config.output_format}"

        # Create temporary directory for processing
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)

            # Build concatenation command
            if config.transition and config.transition.transition_type != "none":
                # Use complex filter for transitions
                self._export_with_transitions(
                    clip_paths=clip_paths,
                    output_path=str(output_path),
                    config=config,
                    temp_dir=temp_path,
                    progress_callback=progress_callback,
                )
            else:
                # Simple concatenation without transitions
                self._export_simple_concat(
                    clip_paths=clip_paths,
                    output_path=str(output_path),
                    config=config,
                    temp_dir=temp_path,
                    progress_callback=progress_callback,
                )

        # Get file size
        file_size = os.path.getsize(output_path)

        # Calculate total duration
        total_duration = sum(h.duration for h in highlights)

        # Create metadata
        reel = HighlightReel(
            reel_id=reel_id,
            video_id=video_id,
            output_path=str(output_path),
            num_highlights=len(highlights),
            total_duration=total_duration,
            highlights=highlights,
            file_size_bytes=file_size,
            config=config,
        )

        logger.info(
            f"Highlight reel exported: {output_path} "
            f"({file_size / 1024 / 1024:.2f} MB, {total_duration:.1f}s)"
        )

        return reel

    def _export_simple_concat(
        self,
        clip_paths: List[str],
        output_path: str,
        config: ExportConfig,
        temp_dir: Path,
        progress_callback: Optional[Callable[[int, int], None]] = None,
    ):
        """Export using simple concatenation (no transitions)"""
        logger.info("Exporting with simple concatenation")

        # Create concat file
        concat_file = temp_dir / "concat.txt"

        with open(concat_file, "w") as f:
            for clip_path in clip_paths:
                f.write(f"file '{os.path.abspath(clip_path)}'\n")

        # Build ffmpeg command
        command = [
            self.ffmpeg_path,
            "-f", "concat",
            "-safe", "0",
            "-i", str(concat_file),
            "-c:v", config.video_codec,
            "-c:a", config.audio_codec,
            "-preset", config.preset,
            "-crf", str(config.crf),
        ]

        # Resolution
        if config.output_width and config.output_height:
            command.extend([
                "-s", f"{config.output_width}x{config.output_height}",
            ])

        # Background music
        if config.background_music_path and os.path.exists(config.background_music_path):
            command.extend([
                "-i", config.background_music_path,
                "-filter_complex",
                f"[0:a][1:a]amix=inputs=2:duration=shortest:weights=1 {config.music_volume}[aout]",
                "-map", "0:v",
                "-map", "[aout]",
            ])

        command.extend([
            "-y",
            output_path,
        ])

        # Execute
        self._execute_ffmpeg(command, progress_callback)

    def _export_with_transitions(
        self,
        clip_paths: List[str],
        output_path: str,
        config: ExportConfig,
        temp_dir: Path,
        progress_callback: Optional[Callable[[int, int], None]] = None,
    ):
        """Export with transitions between clips"""
        logger.info(
            f"Exporting with {config.transition.transition_type} transitions"
        )

        # Build complex filter for transitions
        filter_complex = self._build_transition_filter(
            num_clips=len(clip_paths),
            transition_config=config.transition,
        )

        # Build ffmpeg command
        command = [self.ffmpeg_path]

        # Add all clip inputs
        for clip_path in clip_paths:
            command.extend(["-i", clip_path])

        # Add filter complex
        command.extend([
            "-filter_complex", filter_complex,
            "-map", "[outv]",
            "-map", "[outa]",
            "-c:v", config.video_codec,
            "-c:a", config.audio_codec,
            "-preset", config.preset,
            "-crf", str(config.crf),
            "-y",
            output_path,
        ])

        # Execute
        self._execute_ffmpeg(command, progress_callback)

    def _build_transition_filter(
        self,
        num_clips: int,
        transition_config: TransitionConfig,
    ) -> str:
        """Build ffmpeg filter for transitions"""
        if num_clips == 1:
            # No transition needed
            return "[0:v]copy[outv];[0:a]acopy[outa]"

        transition_type = transition_config.transition_type
        duration = transition_config.transition_duration

        # Build filter chain
        filter_parts = []
        audio_parts = []

        # Process each pair of clips
        for i in range(num_clips - 1):
            # Video transition
            if transition_type == "fade":
                # Crossfade transition
                if i == 0:
                    filter_parts.append(
                        f"[{i}:v][{i+1}:v]xfade=transition=fade:duration={duration}:offset=0[v{i}]"
                    )
                else:
                    filter_parts.append(
                        f"[v{i-1}][{i+1}:v]xfade=transition=fade:duration={duration}:offset=0[v{i}]"
                    )

            # Audio crossfade
            if i == 0:
                audio_parts.append(
                    f"[{i}:a][{i+1}:a]acrossfade=d={duration}[a{i}]"
                )
            else:
                audio_parts.append(
                    f"[a{i-1}][{i+1}:a]acrossfade=d={duration}[a{i}]"
                )

        # Combine all filters
        video_filter = ";".join(filter_parts)
        audio_filter = ";".join(audio_parts)

        final_video_label = f"v{num_clips-2}" if num_clips > 1 else "0:v"
        final_audio_label = f"a{num_clips-2}" if num_clips > 1 else "0:a"

        full_filter = f"{video_filter};{audio_filter};[{final_video_label}]copy[outv];[{final_audio_label}]acopy[outa]"

        return full_filter

    def _execute_ffmpeg(
        self,
        command: List[str],
        progress_callback: Optional[Callable[[int, int], None]] = None,
    ):
        """Execute ffmpeg command"""
        logger.debug(f"FFmpeg command: {' '.join(command)}")

        try:
            process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )

            # Monitor progress
            stderr_output = []
            for line in process.stderr:
                stderr_output.append(line)
                # Could parse progress here if needed

            # Wait for completion
            return_code = process.wait()

            if return_code != 0:
                error_output = "".join(stderr_output)
                raise subprocess.CalledProcessError(
                    return_code,
                    command,
                    stderr=error_output,
                )

        except subprocess.CalledProcessError as e:
            logger.error(f"FFmpeg failed: {e.stderr}")
            raise RuntimeError(f"Failed to export highlight reel: {e.stderr}")
        except Exception as e:
            logger.error(f"Export failed: {e}")
            raise

    def add_title_cards(
        self,
        highlights: List[Any],
        clip_paths: List[str],
        output_dir: Path,
    ) -> List[str]:
        """
        Create title cards for highlights

        Args:
            highlights: List of highlights
            clip_paths: Paths to clip files
            output_dir: Output directory for title cards

        Returns:
            List of paths (alternating: title, clip, title, clip, ...)
        """
        # TODO: Implement title card generation
        # For now, just return clip paths
        logger.warning("Title card generation not yet implemented")
        return clip_paths

    def export_to_format(
        self,
        reel: HighlightReel,
        format: str = "json",
    ) -> Dict[str, Any]:
        """
        Export reel metadata to various formats

        Args:
            reel: HighlightReel object
            format: Output format (json, vtt, srt)

        Returns:
            Formatted data
        """
        if format == "json":
            return {
                "reel_id": reel.reel_id,
                "video_id": reel.video_id,
                "output_path": reel.output_path,
                "num_highlights": reel.num_highlights,
                "total_duration": reel.total_duration,
                "file_size_bytes": reel.file_size_bytes,
                "highlights": [
                    {
                        "highlight_id": h.highlight_id,
                        "title": h.title,
                        "start_time": h.start_time,
                        "end_time": h.end_time,
                        "duration": h.duration,
                        "importance_score": h.importance_score,
                        "highlight_type": h.highlight_type.value,
                        "rank": h.rank,
                    }
                    for h in reel.highlights
                ],
                "metadata": reel.metadata,
            }
        elif format == "vtt":
            return self._export_to_vtt(reel)
        elif format == "srt":
            return self._export_to_srt(reel)
        else:
            raise ValueError(f"Unsupported format: {format}")

    def _export_to_vtt(self, reel: HighlightReel) -> str:
        """Export reel chapters to WebVTT format"""
        lines = ["WEBVTT", ""]

        current_time = 0.0

        for highlight in reel.highlights:
            start = self._format_vtt_timestamp(current_time)
            end = self._format_vtt_timestamp(current_time + highlight.duration)

            lines.append(f"{start} --> {end}")
            lines.append(highlight.title or f"Highlight {highlight.rank}")
            lines.append("")

            current_time += highlight.duration

        return "\n".join(lines)

    def _export_to_srt(self, reel: HighlightReel) -> str:
        """Export reel chapters to SRT format"""
        lines = []

        current_time = 0.0

        for i, highlight in enumerate(reel.highlights, 1):
            start = self._format_srt_timestamp(current_time)
            end = self._format_srt_timestamp(current_time + highlight.duration)

            lines.append(str(i))
            lines.append(f"{start} --> {end}")
            lines.append(highlight.title or f"Highlight {highlight.rank}")
            lines.append("")

            current_time += highlight.duration

        return "\n".join(lines)

    def _format_vtt_timestamp(self, seconds: float) -> str:
        """Format timestamp for WebVTT (HH:MM:SS.mmm)"""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = seconds % 60

        return f"{hours:02d}:{minutes:02d}:{secs:06.3f}"

    def _format_srt_timestamp(self, seconds: float) -> str:
        """Format timestamp for SRT (HH:MM:SS,mmm)"""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        millis = int((seconds % 1) * 1000)

        return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def export_highlight_reel(
    video_id: str,
    highlights: List[Any],
    clip_paths: List[str],
    output_dir: str = "./highlight_reels",
    config: Optional[ExportConfig] = None,
) -> HighlightReel:
    """
    Convenience function to export highlight reel

    Args:
        video_id: Video identifier
        highlights: List of Highlight objects
        clip_paths: Paths to clip files
        output_dir: Output directory
        config: Export configuration

    Returns:
        HighlightReel metadata
    """
    exporter = HighlightExporter(output_dir=output_dir)

    return exporter.export_highlight_reel(
        video_id=video_id,
        highlights=highlights,
        clip_paths=clip_paths,
        config=config,
    )
