"""Progress Tracker - Real-time progress tracking and state management"""

import json
import logging
from pathlib import Path
from typing import Dict, Optional
from datetime import datetime
from enum import Enum

logger = logging.getLogger(__name__)


class ProcessingStage(Enum):
    """Processing stages for meetings"""
    VALIDATION = "validation"
    TRANSCRIPTION = "transcription"
    SUMMARIZATION = "summarization"
    ACTION_EXTRACTION = "action_extraction"
    REPORT_GENERATION = "report_generation"
    COMPLETED = "completed"
    FAILED = "failed"


class ProgressTracker:
    """
    Track processing progress and enable resume capability.

    Features:
    - Real-time progress updates
    - State persistence for resume
    - Cancellation support
    - Progress callbacks
    """

    def __init__(
        self,
        job_id: str,
        state_dir: str = "./data/progress",
        enable_persistence: bool = True
    ):
        """
        Initialize Progress Tracker

        Args:
            job_id: Unique job identifier
            state_dir: Directory to store progress state
            enable_persistence: Whether to save state to disk
        """
        self.job_id = job_id
        self.state_dir = Path(state_dir)
        self.enable_persistence = enable_persistence

        # Create state directory
        if self.enable_persistence:
            self.state_dir.mkdir(parents=True, exist_ok=True)

        # Initialize state
        self.state = {
            "job_id": job_id,
            "status": "initialized",
            "current_stage": None,
            "progress_percent": 0,
            "started_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
            "completed_at": None,
            "stages": {},
            "metadata": {},
            "errors": [],
            "can_resume": False
        }

        # Callbacks
        self.callbacks = []

        # Cancellation flag
        self.cancelled = False

    def start(self, metadata: Optional[Dict] = None):
        """
        Start tracking progress

        Args:
            metadata: Optional metadata about the job
        """
        self.state["status"] = "running"
        self.state["started_at"] = datetime.now().isoformat()

        if metadata:
            self.state["metadata"].update(metadata)

        self._save_state()
        self._notify_callbacks()

    def update_stage(
        self,
        stage: ProcessingStage,
        progress_percent: Optional[int] = None,
        message: Optional[str] = None
    ):
        """
        Update current processing stage

        Args:
            stage: Current processing stage
            progress_percent: Overall progress (0-100)
            message: Optional status message
        """
        if self.cancelled:
            raise InterruptedError("Processing was cancelled")

        self.state["current_stage"] = stage.value
        self.state["updated_at"] = datetime.now().isoformat()

        if progress_percent is not None:
            self.state["progress_percent"] = min(100, max(0, progress_percent))

        # Update stage info
        if stage.value not in self.state["stages"]:
            self.state["stages"][stage.value] = {
                "started_at": datetime.now().isoformat(),
                "completed_at": None,
                "status": "in_progress"
            }

        if message:
            self.state["stages"][stage.value]["message"] = message

        logger.info(f"Progress: {stage.value} - {progress_percent}%")

        self._save_state()
        self._notify_callbacks()

    def complete_stage(self, stage: ProcessingStage, result: Optional[Dict] = None):
        """
        Mark a stage as completed

        Args:
            stage: Completed stage
            result: Optional result data
        """
        if stage.value in self.state["stages"]:
            self.state["stages"][stage.value]["completed_at"] = datetime.now().isoformat()
            self.state["stages"][stage.value]["status"] = "completed"

            if result:
                self.state["stages"][stage.value]["result"] = result

        self._save_state()
        self._notify_callbacks()

    def complete(self, result: Optional[Dict] = None):
        """
        Mark job as completed

        Args:
            result: Optional final result
        """
        self.state["status"] = "completed"
        self.state["current_stage"] = ProcessingStage.COMPLETED.value
        self.state["progress_percent"] = 100
        self.state["completed_at"] = datetime.now().isoformat()
        self.state["can_resume"] = False

        if result:
            self.state["result"] = result

        self._save_state()
        self._notify_callbacks()

        logger.info(f"Job {self.job_id} completed")

    def fail(self, error: str, stage: Optional[ProcessingStage] = None):
        """
        Mark job as failed

        Args:
            error: Error message
            stage: Stage where failure occurred
        """
        self.state["status"] = "failed"
        self.state["current_stage"] = ProcessingStage.FAILED.value
        self.state["completed_at"] = datetime.now().isoformat()

        error_info = {
            "message": error,
            "stage": stage.value if stage else None,
            "timestamp": datetime.now().isoformat()
        }

        self.state["errors"].append(error_info)

        # Mark stage as failed
        if stage and stage.value in self.state["stages"]:
            self.state["stages"][stage.value]["status"] = "failed"
            self.state["stages"][stage.value]["error"] = error

        self._save_state()
        self._notify_callbacks()

        logger.error(f"Job {self.job_id} failed: {error}")

    def cancel(self):
        """Cancel the job"""
        self.cancelled = True
        self.state["status"] = "cancelled"
        self.state["completed_at"] = datetime.now().isoformat()

        self._save_state()
        self._notify_callbacks()

        logger.info(f"Job {self.job_id} cancelled")

    def is_cancelled(self) -> bool:
        """Check if job is cancelled"""
        return self.cancelled

    def enable_resume(self, checkpoint_data: Dict):
        """
        Enable resume capability

        Args:
            checkpoint_data: Data needed to resume
        """
        self.state["can_resume"] = True
        self.state["checkpoint"] = checkpoint_data
        self.state["checkpoint_at"] = datetime.now().isoformat()

        self._save_state()

    def add_callback(self, callback):
        """
        Add progress callback

        Args:
            callback: Function to call on progress updates
        """
        self.callbacks.append(callback)

    def _notify_callbacks(self):
        """Notify all registered callbacks"""
        for callback in self.callbacks:
            try:
                callback(self.state.copy())
            except Exception as e:
                logger.error(f"Callback error: {str(e)}")

    def _save_state(self):
        """Save state to disk"""
        if not self.enable_persistence:
            return

        state_file = self.state_dir / f"{self.job_id}.json"

        try:
            with open(state_file, 'w', encoding='utf-8') as f:
                json.dump(self.state, f, indent=2, default=str)
        except Exception as e:
            logger.error(f"Failed to save progress state: {str(e)}")

    def get_state(self) -> Dict:
        """Get current state"""
        return self.state.copy()

    def get_progress_percent(self) -> int:
        """Get current progress percentage"""
        return self.state["progress_percent"]

    def get_elapsed_time(self) -> float:
        """Get elapsed time in seconds"""
        started = datetime.fromisoformat(self.state["started_at"])
        now = datetime.now()
        return (now - started).total_seconds()

    @classmethod
    def load_state(cls, job_id: str, state_dir: str = "./data/progress") -> Optional['ProgressTracker']:
        """
        Load progress tracker from saved state

        Args:
            job_id: Job identifier
            state_dir: State directory

        Returns:
            ProgressTracker instance or None if not found
        """
        state_file = Path(state_dir) / f"{job_id}.json"

        if not state_file.exists():
            return None

        try:
            with open(state_file, 'r', encoding='utf-8') as f:
                state = json.load(f)

            tracker = cls(job_id, state_dir)
            tracker.state = state

            logger.info(f"Loaded progress state for job {job_id}")

            return tracker

        except Exception as e:
            logger.error(f"Failed to load progress state: {str(e)}")
            return None

    @classmethod
    def list_jobs(cls, state_dir: str = "./data/progress") -> List[Dict]:
        """
        List all tracked jobs

        Args:
            state_dir: State directory

        Returns:
            List of job state dictionaries
        """
        state_path = Path(state_dir)

        if not state_path.exists():
            return []

        jobs = []

        for state_file in state_path.glob("*.json"):
            try:
                with open(state_file, 'r', encoding='utf-8') as f:
                    state = json.load(f)
                jobs.append(state)
            except Exception as e:
                logger.error(f"Failed to load {state_file}: {str(e)}")

        return sorted(jobs, key=lambda x: x.get("started_at", ""), reverse=True)

    @classmethod
    def cleanup_old_jobs(
        cls,
        state_dir: str = "./data/progress",
        max_age_days: int = 7
    ) -> int:
        """
        Clean up old job states

        Args:
            state_dir: State directory
            max_age_days: Maximum age to keep

        Returns:
            Number of jobs cleaned up
        """
        state_path = Path(state_dir)

        if not state_path.exists():
            return 0

        cutoff = datetime.now().timestamp() - (max_age_days * 24 * 60 * 60)
        cleaned = 0

        for state_file in state_path.glob("*.json"):
            if state_file.stat().st_mtime < cutoff:
                try:
                    state_file.unlink()
                    cleaned += 1
                except Exception as e:
                    logger.error(f"Failed to delete {state_file}: {str(e)}")

        logger.info(f"Cleaned up {cleaned} old job states")

        return cleaned
