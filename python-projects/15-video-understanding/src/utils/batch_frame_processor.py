"""
Batch frame processor for efficient parallel processing of video frames
Memory-efficient with chunked processing support
"""

import logging
from pathlib import Path
from typing import List, Callable, Any, Optional, Tuple, TypeVar
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor, as_completed
from dataclasses import dataclass

logger = logging.getLogger(__name__)

T = TypeVar('T')
R = TypeVar('R')


@dataclass
class BatchResult:
    """Result from batch processing"""
    successful: List[Any]
    failed: List[Tuple[Any, Exception]]
    total_processed: int
    success_count: int
    failure_count: int


class ExecutorType:
    """Types of executors for parallel processing"""
    THREAD = "thread"  # Thread-based (I/O bound tasks)
    PROCESS = "process"  # Process-based (CPU bound tasks)


class BatchFrameProcessor:
    """
    Process frames in parallel batches for efficiency
    Supports both thread-based and process-based parallelism
    """

    def __init__(
        self,
        batch_size: int = 32,
        max_workers: Optional[int] = None,
        executor_type: str = ExecutorType.THREAD
    ):
        """
        Initialize batch frame processor

        Args:
            batch_size: Number of items per batch
            max_workers: Maximum number of workers (None = CPU count)
            executor_type: Type of executor to use
        """
        self.batch_size = batch_size
        self.max_workers = max_workers
        self.executor_type = executor_type

    def process_batch(
        self,
        items: List[T],
        process_func: Callable[[T], R],
        show_progress: bool = True,
        ignore_errors: bool = False
    ) -> BatchResult:
        """
        Process items in parallel batches

        Args:
            items: List of items to process
            process_func: Function to apply to each item
            show_progress: Log progress information
            ignore_errors: Continue processing if individual items fail

        Returns:
            BatchResult with processing results

        Raises:
            RuntimeError: If processing fails and ignore_errors is False
        """
        if not items:
            return BatchResult(
                successful=[],
                failed=[],
                total_processed=0,
                success_count=0,
                failure_count=0
            )

        logger.info(
            f"Processing {len(items)} items in batches of {self.batch_size} "
            f"using {self.executor_type} executor"
        )

        successful = []
        failed = []

        # Create executor
        executor_class = (
            ThreadPoolExecutor if self.executor_type == ExecutorType.THREAD
            else ProcessPoolExecutor
        )

        with executor_class(max_workers=self.max_workers) as executor:
            # Submit all tasks
            future_to_item = {
                executor.submit(process_func, item): item
                for item in items
            }

            # Process results as they complete
            completed_count = 0

            for future in as_completed(future_to_item):
                item = future_to_item[future]
                completed_count += 1

                try:
                    result = future.result()
                    successful.append(result)

                    if show_progress and completed_count % self.batch_size == 0:
                        logger.info(
                            f"Processed {completed_count}/{len(items)} items "
                            f"({(completed_count / len(items) * 100):.1f}%)"
                        )

                except Exception as e:
                    logger.error(f"Failed to process item {item}: {e}")
                    failed.append((item, e))

                    if not ignore_errors:
                        raise RuntimeError(f"Processing failed for item {item}") from e

        logger.info(
            f"Batch processing complete: "
            f"{len(successful)} successful, {len(failed)} failed"
        )

        return BatchResult(
            successful=successful,
            failed=failed,
            total_processed=len(items),
            success_count=len(successful),
            failure_count=len(failed)
        )

    def process_in_chunks(
        self,
        items: List[T],
        process_func: Callable[[List[T]], List[R]],
        show_progress: bool = True
    ) -> List[R]:
        """
        Process items in chunks (batch function receives list of items)

        This is useful when the processing function can handle multiple items
        more efficiently than processing them one at a time.

        Args:
            items: List of items to process
            process_func: Function that processes a batch of items
            show_progress: Log progress information

        Returns:
            List of all results
        """
        if not items:
            return []

        logger.info(
            f"Processing {len(items)} items in {self.batch_size}-item chunks"
        )

        all_results = []

        # Split into chunks
        for i in range(0, len(items), self.batch_size):
            chunk = items[i:i + self.batch_size]

            if show_progress:
                logger.info(
                    f"Processing chunk {i // self.batch_size + 1}/"
                    f"{(len(items) + self.batch_size - 1) // self.batch_size} "
                    f"({len(chunk)} items)"
                )

            try:
                chunk_results = process_func(chunk)
                all_results.extend(chunk_results)

            except Exception as e:
                logger.error(f"Failed to process chunk starting at index {i}: {e}")
                raise

        logger.info(f"Processed {len(all_results)} total results")

        return all_results

    def process_frames_batch(
        self,
        frame_paths: List[Path],
        process_func: Callable[[Path], Any],
        show_progress: bool = True,
        ignore_errors: bool = True
    ) -> BatchResult:
        """
        Convenience method for processing frame files in batch

        Args:
            frame_paths: List of frame file paths
            process_func: Function to process each frame
            show_progress: Log progress
            ignore_errors: Continue if individual frames fail

        Returns:
            BatchResult with processing results
        """
        return self.process_batch(
            items=frame_paths,
            process_func=process_func,
            show_progress=show_progress,
            ignore_errors=ignore_errors
        )

    def map(
        self,
        func: Callable[[T], R],
        items: List[T],
        ignore_errors: bool = False
    ) -> List[R]:
        """
        Map function over items in parallel (similar to Python's map)

        Args:
            func: Function to apply
            items: Items to process
            ignore_errors: Skip failed items instead of raising

        Returns:
            List of results
        """
        result = self.process_batch(
            items=items,
            process_func=func,
            show_progress=False,
            ignore_errors=ignore_errors
        )

        return result.successful

    def filter(
        self,
        predicate: Callable[[T], bool],
        items: List[T]
    ) -> List[T]:
        """
        Filter items in parallel using predicate

        Args:
            predicate: Function that returns True to keep item
            items: Items to filter

        Returns:
            Filtered list of items
        """
        def check_item(item: T) -> Optional[T]:
            """Return item if predicate is True, else None"""
            return item if predicate(item) else None

        result = self.process_batch(
            items=items,
            process_func=check_item,
            show_progress=False,
            ignore_errors=True
        )

        # Filter out None values
        return [item for item in result.successful if item is not None]


class StreamingBatchProcessor:
    """
    Process frames in a streaming fashion for memory efficiency
    Processes frames as they are generated without loading all into memory
    """

    def __init__(
        self,
        batch_size: int = 32,
        max_workers: Optional[int] = None
    ):
        """
        Initialize streaming batch processor

        Args:
            batch_size: Size of processing batches
            max_workers: Maximum number of workers
        """
        self.batch_size = batch_size
        self.max_workers = max_workers

    def process_stream(
        self,
        item_generator,
        process_func: Callable[[T], R],
        callback: Optional[Callable[[R], None]] = None
    ) -> int:
        """
        Process items from a generator in streaming fashion

        Args:
            item_generator: Generator that yields items to process
            process_func: Function to process each item
            callback: Optional callback to handle each result

        Returns:
            Number of items processed
        """
        processed_count = 0
        batch = []

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            for item in item_generator:
                batch.append(item)

                # Process when batch is full
                if len(batch) >= self.batch_size:
                    processed_count += self._process_batch_chunk(
                        batch, process_func, executor, callback
                    )
                    batch = []

            # Process remaining items
            if batch:
                processed_count += self._process_batch_chunk(
                    batch, process_func, executor, callback
                )

        logger.info(f"Streaming processing complete: {processed_count} items")
        return processed_count

    def _process_batch_chunk(
        self,
        batch: List[T],
        process_func: Callable[[T], R],
        executor: ThreadPoolExecutor,
        callback: Optional[Callable[[R], None]]
    ) -> int:
        """Process a chunk of items"""
        futures = [executor.submit(process_func, item) for item in batch]

        processed = 0
        for future in as_completed(futures):
            try:
                result = future.result()
                if callback:
                    callback(result)
                processed += 1

            except Exception as e:
                logger.error(f"Failed to process item in stream: {e}")

        return processed


def process_frames_parallel(
    frame_paths: List[Path],
    process_func: Callable[[Path], Any],
    batch_size: int = 32,
    max_workers: Optional[int] = None,
    executor_type: str = ExecutorType.THREAD
) -> BatchResult:
    """
    Convenience function to process frames in parallel

    Args:
        frame_paths: List of frame paths
        process_func: Function to process each frame
        batch_size: Batch size for processing
        max_workers: Maximum number of workers
        executor_type: Type of executor

    Returns:
        BatchResult with processing results
    """
    processor = BatchFrameProcessor(
        batch_size=batch_size,
        max_workers=max_workers,
        executor_type=executor_type
    )

    return processor.process_frames_batch(
        frame_paths=frame_paths,
        process_func=process_func
    )
