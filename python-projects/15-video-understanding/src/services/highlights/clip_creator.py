"""
Clip creator for extracting video clips from timestamp ranges
Use ffmpeg for precise clipping with optional fade effects
"""

import logging
import os
import subprocess
from typing import Optional, Dict, Any, Callable
from dataclasses import dataclass, field
from pathlib import Path
import hashlib

logger = logging.getLogger(__name__)


@dataclass
class ClipConfig:
    """Configuration for clip creation"""
    # Output settings
    output_format: str = "mp4"
    video_codec: str = "libx264"
    audio_codec: str = "aac"
    preset: str = "medium"  # ultrafast, fast, medium, slow, slower
    crf: int = 23  # Quality (lower = better, 18-28 recommended)

    # Effects
    fade_in_duration: float = 0.0  # Seconds
    fade_out_duration: float = 0.0  # Seconds

    # Processing
    copy_streams: bool = False  # Fast copy without re-encoding
    include_audio: bool = True

    # Resolution
    max_width: Optional[int] = None
    max_height: Optional[int] = None

    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ClipMetadata:
    """Metadata for created clip"""
    clip_id: str
    source_video_id: str
    source_video_path: str

    # Time range
    start_time: float
    end_time: float
    duration: float

    # Output
    output_path: str
    file_size_bytes: int

    # Configuration
    config: ClipConfig

    # Processing info
    creation_time: Optional[str] = None
    ffmpeg_command: Optional[str] = None

    metadata: Dict[str, Any] = field(default_factory=dict)


class ClipCreator:
    """
    Create video clips from timestamp ranges
    Use ffmpeg for precise extraction with optional effects
    """

    def __init__(
        self,
        output_dir: str = "./clips",
        ffmpeg_path: str = "ffmpeg",
        default_config: Optional[ClipConfig] = None,
    ):
        """
        Initialize clip creator

        Args:
            output_dir: Directory for output clips
            ffmpeg_path: Path to ffmpeg executable
            default_config: Default clip configuration
        """
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self.ffmpeg_path = ffmpeg_path
        self.default_config = default_config or ClipConfig()

        # Verify ffmpeg is available
        self._verify_ffmpeg()

        logger.info(f"Initialized ClipCreator (output_dir={output_dir})")

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
            logger.error(f"FFmpeg not found or not working: {e}")
            raise RuntimeError(
                f"FFmpeg not available at {self.ffmpeg_path}. "
                "Please install ffmpeg or provide correct path."
            )

    def create_clip(
        self,
        video_path: str,
        start_time: float,
        end_time: float,
        video_id: Optional[str] = None,
        output_filename: Optional[str] = None,
        config: Optional[ClipConfig] = None,
        progress_callback: Optional[Callable[[float], None]] = None,
    ) -> ClipMetadata:
        """
        Create video clip from timestamp range

        Args:
            video_path: Path to source video
            start_time: Start time in seconds
            end_time: End time in seconds
            video_id: Optional video identifier
            output_filename: Optional custom filename
            config: Clip configuration (uses default if not provided)
            progress_callback: Optional progress callback

        Returns:
            ClipMetadata
        """
        # Validate inputs
        if not os.path.exists(video_path):
            raise FileNotFoundError(f"Video not found: {video_path}")

        if start_time < 0 or end_time <= start_time:
            raise ValueError(
                f"Invalid time range: start={start_time}, end={end_time}"
            )

        duration = end_time - start_time
        config = config or self.default_config

        # Generate clip ID and output path
        clip_id = self._generate_clip_id(video_path, start_time, end_time)

        if output_filename:
            output_path = self.output_dir / output_filename
        else:
            output_path = self._generate_output_path(
                video_id or "video",
                clip_id,
                config.output_format,
            )

        logger.info(
            f"Creating clip: {start_time:.2f}s to {end_time:.2f}s "
            f"(duration: {duration:.2f}s)"
        )

        # Build ffmpeg command
        ffmpeg_command = self._build_ffmpeg_command(
            video_path=video_path,
            output_path=str(output_path),
            start_time=start_time,
            duration=duration,
            config=config,
        )

        # Execute ffmpeg
        self._execute_ffmpeg(
            command=ffmpeg_command,
            progress_callback=progress_callback,
        )

        # Get file size
        file_size = os.path.getsize(output_path)

        # Create metadata
        metadata = ClipMetadata(
            clip_id=clip_id,
            source_video_id=video_id or "",
            source_video_path=video_path,
            start_time=start_time,
            end_time=end_time,
            duration=duration,
            output_path=str(output_path),
            file_size_bytes=file_size,
            config=config,
            ffmpeg_command=" ".join(ffmpeg_command),
        )

        logger.info(
            f"Clip created successfully: {output_path} "
            f"({file_size / 1024 / 1024:.2f} MB)"
        )

        return metadata

    def create_clip_batch(
        self,
        video_path: str,
        time_ranges: list[tuple[float, float]],
        video_id: Optional[str] = None,
        config: Optional[ClipConfig] = None,
        progress_callback: Optional[Callable[[int, int], None]] = None,
    ) -> list[ClipMetadata]:
        """
        Create multiple clips from a video

        Args:
            video_path: Path to source video
            time_ranges: List of (start_time, end_time) tuples
            video_id: Optional video identifier
            config: Clip configuration
            progress_callback: Optional progress callback (current, total)

        Returns:
            List of ClipMetadata
        """
        logger.info(f"Creating {len(time_ranges)} clips from {video_path}")

        clips = []

        for i, (start_time, end_time) in enumerate(time_ranges, 1):
            try:
                clip = self.create_clip(
                    video_path=video_path,
                    start_time=start_time,
                    end_time=end_time,
                    video_id=video_id,
                    config=config,
                )
                clips.append(clip)

                if progress_callback:
                    progress_callback(i, len(time_ranges))

            except Exception as e:
                logger.error(
                    f"Failed to create clip {i}/{len(time_ranges)}: {e}"
                )
                continue

        logger.info(f"Created {len(clips)}/{len(time_ranges)} clips")

        return clips

    def _build_ffmpeg_command(
        self,
        video_path: str,
        output_path: str,
        start_time: float,
        duration: float,
        config: ClipConfig,
    ) -> list[str]:
        """Build ffmpeg command for clip extraction"""
        command = [self.ffmpeg_path]

        # Input settings
        command.extend([
            "-ss", str(start_time),  # Seek to start time
            "-i", video_path,  # Input file
            "-t", str(duration),  # Duration
        ])

        # Video codec
        if config.copy_streams:
            # Fast copy without re-encoding
            command.extend(["-c", "copy"])
        else:
            # Re-encode with quality settings
            command.extend([
                "-c:v", config.video_codec,
                "-preset", config.preset,
                "-crf", str(config.crf),
            ])

            # Audio codec
            if config.include_audio:
                command.extend(["-c:a", config.audio_codec])
            else:
                command.extend(["-an"])  # No audio

        # Resolution
        if config.max_width or config.max_height:
            scale_filter = self._build_scale_filter(
                config.max_width,
                config.max_height,
            )
            command.extend(["-vf", scale_filter])

        # Fade effects
        if config.fade_in_duration > 0 or config.fade_out_duration > 0:
            if not config.copy_streams:
                fade_filter = self._build_fade_filter(
                    duration=duration,
                    fade_in=config.fade_in_duration,
                    fade_out=config.fade_out_duration,
                )

                # Combine with scale filter if present
                if config.max_width or config.max_height:
                    # Already have -vf, need to combine filters
                    existing_filter = command[-1]
                    command[-1] = f"{existing_filter},{fade_filter}"
                else:
                    command.extend(["-vf", fade_filter])

        # Output settings
        command.extend([
            "-y",  # Overwrite output file
            output_path,
        ])

        return command

    def _build_scale_filter(
        self,
        max_width: Optional[int],
        max_height: Optional[int],
    ) -> str:
        """Build scale filter for resolution limiting"""
        if max_width and max_height:
            # Scale to fit within bounds
            return f"scale='min({max_width},iw)':'min({max_height},ih)':force_original_aspect_ratio=decrease"
        elif max_width:
            return f"scale={max_width}:-1"
        elif max_height:
            return f"scale=-1:{max_height}"
        else:
            return ""

    def _build_fade_filter(
        self,
        duration: float,
        fade_in: float,
        fade_out: float,
    ) -> str:
        """Build fade filter"""
        filters = []

        if fade_in > 0:
            filters.append(f"fade=t=in:st=0:d={fade_in}")

        if fade_out > 0:
            fade_start = duration - fade_out
            filters.append(f"fade=t=out:st={fade_start}:d={fade_out}")

        return ",".join(filters)

    def _execute_ffmpeg(
        self,
        command: list[str],
        progress_callback: Optional[Callable[[float], None]] = None,
    ):
        """Execute ffmpeg command"""
        logger.debug(f"FFmpeg command: {' '.join(command)}")

        try:
            # Run ffmpeg
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

                # Parse progress (ffmpeg outputs to stderr)
                if "time=" in line and progress_callback:
                    # Extract time (format: time=00:00:10.50)
                    try:
                        time_str = line.split("time=")[1].split()[0]
                        # Convert to seconds (simple parsing)
                        parts = time_str.split(":")
                        if len(parts) == 3:
                            hours = float(parts[0])
                            minutes = float(parts[1])
                            seconds = float(parts[2])
                            current_time = hours * 3600 + minutes * 60 + seconds

                            # Call progress callback
                            progress_callback(current_time)
                    except (IndexError, ValueError):
                        pass

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
            raise RuntimeError(f"Failed to create clip: {e.stderr}")
        except Exception as e:
            logger.error(f"Clip creation failed: {e}")
            raise

    def _generate_clip_id(
        self,
        video_path: str,
        start_time: float,
        end_time: float,
    ) -> str:
        """Generate unique clip ID"""
        content = f"{video_path}_{start_time}_{end_time}"
        hash_object = hashlib.sha256(content.encode())
        return hash_object.hexdigest()[:16]

    def _generate_output_path(
        self,
        video_id: str,
        clip_id: str,
        output_format: str,
    ) -> Path:
        """Generate output file path"""
        filename = f"{video_id}_clip_{clip_id}.{output_format}"
        return self.output_dir / filename

    def delete_clip(self, clip_path: str) -> bool:
        """
        Delete a clip file

        Args:
            clip_path: Path to clip file

        Returns:
            True if deleted successfully
        """
        try:
            if os.path.exists(clip_path):
                os.remove(clip_path)
                logger.info(f"Deleted clip: {clip_path}")
                return True
            else:
                logger.warning(f"Clip not found: {clip_path}")
                return False
        except Exception as e:
            logger.error(f"Failed to delete clip: {e}")
            return False

    def get_clip_info(self, clip_path: str) -> Dict[str, Any]:
        """
        Get information about a clip

        Args:
            clip_path: Path to clip file

        Returns:
            Dictionary with clip information
        """
        if not os.path.exists(clip_path):
            raise FileNotFoundError(f"Clip not found: {clip_path}")

        # Use ffprobe to get info
        command = [
            "ffprobe",
            "-v", "quiet",
            "-print_format", "json",
            "-show_format",
            "-show_streams",
            clip_path,
        ]

        try:
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                check=True,
            )

            import json
            info = json.loads(result.stdout)

            return {
                "path": clip_path,
                "size_bytes": os.path.getsize(clip_path),
                "duration": float(info["format"].get("duration", 0)),
                "format": info["format"],
                "streams": info["streams"],
            }

        except Exception as e:
            logger.error(f"Failed to get clip info: {e}")
            return {
                "path": clip_path,
                "size_bytes": os.path.getsize(clip_path),
                "error": str(e),
            }


def create_clip(
    video_path: str,
    start_time: float,
    end_time: float,
    output_dir: str = "./clips",
    video_id: Optional[str] = None,
    config: Optional[ClipConfig] = None,
) -> ClipMetadata:
    """
    Convenience function to create a clip

    Args:
        video_path: Path to source video
        start_time: Start time in seconds
        end_time: End time in seconds
        output_dir: Output directory
        video_id: Optional video identifier
        config: Clip configuration

    Returns:
        ClipMetadata
    """
    creator = ClipCreator(output_dir=output_dir)

    return creator.create_clip(
        video_path=video_path,
        start_time=start_time,
        end_time=end_time,
        video_id=video_id,
        config=config,
    )
