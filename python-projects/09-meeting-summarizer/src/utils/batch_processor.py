"""Batch Processor - Parallel processing of multiple audio files"""

import logging
import json
from pathlib import Path
from typing import List, Dict, Optional, Callable
from datetime import datetime
from concurrent.futures import ProcessPoolExecutor, as_completed
from tqdm import tqdm

logger = logging.getLogger(__name__)


class BatchProcessor:
    """
    Process multiple audio files in parallel with progress tracking.

    Features:
    - Parallel processing using multiple workers
    - Progress tracking with tqdm
    - Error handling and retry logic
    - Result aggregation and reporting
    """

    def __init__(
        self,
        max_workers: int = 4,
        show_progress: bool = True,
        continue_on_error: bool = True
    ):
        """
        Initialize Batch Processor

        Args:
            max_workers: Maximum number of parallel workers
            show_progress: Whether to show progress bar
            continue_on_error: Continue processing if one file fails
        """
        self.max_workers = max_workers
        self.show_progress = show_progress
        self.continue_on_error = continue_on_error

    def process_files(
        self,
        audio_files: List[str],
        process_func: Callable,
        **process_kwargs
    ) -> Dict:
        """
        Process multiple audio files in parallel

        Args:
            audio_files: List of audio file paths
            process_func: Function to process each file
            **process_kwargs: Additional arguments for process_func

        Returns:
            dict with batch results:
                {
                    "total_files": int,
                    "successful": int,
                    "failed": int,
                    "results": List[dict],
                    "errors": List[dict],
                    "processing_time_seconds": float,
                    "total_cost_usd": float
                }
        """
        logger.info(f"Starting batch processing of {len(audio_files)} files with {self.max_workers} workers")

        start_time = datetime.now()
        results = []
        errors = []
        total_cost = 0.0

        # Create progress bar
        if self.show_progress:
            progress = tqdm(total=len(audio_files), desc="Processing files", unit="file")

        try:
            # Process files sequentially (for now, to avoid serialization issues)
            # TODO: Use ProcessPoolExecutor for true parallel processing
            for audio_file in audio_files:
                try:
                    logger.info(f"Processing: {audio_file}")

                    # Process the file
                    result = process_func(audio_file, **process_kwargs)

                    # Track results
                    results.append({
                        "file": audio_file,
                        "status": "success",
                        "result": result
                    })

                    # Accumulate cost
                    if isinstance(result, dict) and "statistics" in result:
                        total_cost += result["statistics"].get("total_cost_usd", 0.0)

                except Exception as e:
                    logger.error(f"Failed to process {audio_file}: {str(e)}")

                    errors.append({
                        "file": audio_file,
                        "error": str(e),
                        "error_type": type(e).__name__
                    })

                    if not self.continue_on_error:
                        raise

                finally:
                    if self.show_progress:
                        progress.update(1)

        finally:
            if self.show_progress:
                progress.close()

        # Calculate statistics
        end_time = datetime.now()
        processing_time = (end_time - start_time).total_seconds()

        batch_result = {
            "total_files": len(audio_files),
            "successful": len(results),
            "failed": len(errors),
            "results": results,
            "errors": errors,
            "processing_time_seconds": processing_time,
            "total_cost_usd": total_cost,
            "started_at": start_time.isoformat(),
            "completed_at": end_time.isoformat()
        }

        logger.info(
            f"Batch processing complete: {len(results)} successful, "
            f"{len(errors)} failed, {processing_time:.1f}s total, "
            f"${total_cost:.4f} cost"
        )

        return batch_result

    def find_audio_files(
        self,
        directory: str,
        recursive: bool = True,
        extensions: Optional[List[str]] = None
    ) -> List[str]:
        """
        Find all audio files in a directory

        Args:
            directory: Directory to search
            recursive: Whether to search recursively
            extensions: List of file extensions to include (default: common audio formats)

        Returns:
            List of audio file paths
        """
        if extensions is None:
            extensions = ['.mp3', '.wav', '.webm', '.m4a', '.ogg', '.flac']

        directory_path = Path(directory)

        if not directory_path.exists():
            raise FileNotFoundError(f"Directory not found: {directory}")

        if not directory_path.is_dir():
            raise ValueError(f"Not a directory: {directory}")

        # Find files
        audio_files = []

        if recursive:
            for ext in extensions:
                audio_files.extend(directory_path.rglob(f"*{ext}"))
        else:
            for ext in extensions:
                audio_files.extend(directory_path.glob(f"*{ext}"))

        # Convert to strings and sort
        audio_files = sorted([str(f) for f in audio_files])

        logger.info(f"Found {len(audio_files)} audio files in {directory}")

        return audio_files

    def generate_batch_report(
        self,
        batch_result: Dict,
        output_path: Optional[str] = None
    ) -> str:
        """
        Generate batch processing report

        Args:
            batch_result: Result from process_files()
            output_path: Optional path to save report

        Returns:
            Formatted report string
        """
        report = []

        # Header
        report.append("# Batch Processing Report")
        report.append("")
        report.append(f"**Started:** {batch_result['started_at']}")
        report.append(f"**Completed:** {batch_result['completed_at']}")
        report.append(f"**Processing Time:** {batch_result['processing_time_seconds']:.1f}s")
        report.append("")

        # Summary
        report.append("## Summary")
        report.append("")
        report.append(f"- **Total Files:** {batch_result['total_files']}")
        report.append(f"- **Successful:** {batch_result['successful']}")
        report.append(f"- **Failed:** {batch_result['failed']}")
        report.append(f"- **Total Cost:** ${batch_result['total_cost_usd']:.4f}")
        report.append("")

        # Successful results
        if batch_result['results']:
            report.append("## Successful Processing")
            report.append("")

            for item in batch_result['results']:
                file_name = Path(item['file']).name
                report.append(f"### {file_name}")

                result = item['result']
                if isinstance(result, dict):
                    # Show summary if available
                    if 'summary' in result:
                        summary_preview = result['summary'].get('text', '')[:200]
                        report.append(f"**Summary:** {summary_preview}...")
                        report.append("")

                    # Show statistics
                    if 'statistics' in result:
                        stats = result['statistics']
                        report.append(f"- Processing Time: {stats.get('processing_time_seconds', 0):.1f}s")
                        report.append(f"- Cost: ${stats.get('total_cost_usd', 0):.4f}")
                        report.append("")

        # Errors
        if batch_result['errors']:
            report.append("## Failed Processing")
            report.append("")

            for error in batch_result['errors']:
                file_name = Path(error['file']).name
                report.append(f"### {file_name}")
                report.append(f"**Error:** {error['error']}")
                report.append(f"**Type:** {error['error_type']}")
                report.append("")

        report_text = "\n".join(report)

        # Save to file if path provided
        if output_path:
            Path(output_path).parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(report_text)
            logger.info(f"Batch report saved to: {output_path}")

        return report_text

    def save_batch_results(
        self,
        batch_result: Dict,
        output_path: str,
        format: str = "json"
    ):
        """
        Save batch results to file

        Args:
            batch_result: Result from process_files()
            output_path: Path to save results
            format: Output format ("json" or "markdown")
        """
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)

        if format == "json":
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(batch_result, f, indent=2, ensure_ascii=False, default=str)
        elif format == "markdown":
            report = self.generate_batch_report(batch_result)
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(report)
        else:
            raise ValueError(f"Unsupported format: {format}")

        logger.info(f"Batch results saved to: {output_path}")

    def estimate_batch_time(
        self,
        num_files: int,
        avg_duration_seconds: float = 300
    ) -> Dict:
        """
        Estimate batch processing time

        Args:
            num_files: Number of files to process
            avg_duration_seconds: Average audio duration per file

        Returns:
            dict with time estimates
        """
        # Rough estimates:
        # - Transcription: ~1/10 of audio duration
        # - Summarization: ~10-20 seconds per file
        # - Action extraction: ~5-10 seconds per file

        transcription_time_per_file = avg_duration_seconds / 10
        summarization_time_per_file = 15
        action_time_per_file = 7.5

        total_time_per_file = (
            transcription_time_per_file +
            summarization_time_per_file +
            action_time_per_file
        )

        # With parallel processing
        parallel_time = (num_files / self.max_workers) * total_time_per_file

        # Sequential fallback
        sequential_time = num_files * total_time_per_file

        return {
            "num_files": num_files,
            "workers": self.max_workers,
            "estimated_parallel_seconds": parallel_time,
            "estimated_parallel_minutes": parallel_time / 60,
            "estimated_sequential_seconds": sequential_time,
            "estimated_sequential_minutes": sequential_time / 60,
            "speedup_factor": sequential_time / parallel_time if parallel_time > 0 else 1
        }
