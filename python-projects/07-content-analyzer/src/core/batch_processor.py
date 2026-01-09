"""Batch processing functionality for multiple images."""
from typing import Dict, List, Optional, Any, Callable
from PIL import Image
from pathlib import Path
import json
import csv
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
import time


class BatchProcessor:
    """Process multiple images in batch for vision analysis or OCR."""

    def __init__(
        self,
        vision_client=None,
        ocr_processor=None,
        max_workers: int = 4
    ):
        """Initialize batch processor.

        Args:
            vision_client: VisionClient instance for vision analysis
            ocr_processor: OCRProcessor instance for OCR
            max_workers: Maximum number of concurrent workers
        """
        self.vision_client = vision_client
        self.ocr_processor = ocr_processor
        self.max_workers = max_workers

    def batch_analyze(
        self,
        images: List[Image.Image],
        image_names: Optional[List[str]] = None,
        prompt: str = "Describe this image in detail.",
        temperature: float = 0.7,
        max_tokens: int = 1000,
        progress_callback: Optional[Callable] = None
    ) -> Dict[str, Any]:
        """Perform batch vision analysis on multiple images.

        Args:
            images: List of images to analyze
            image_names: Optional list of image names/identifiers
            prompt: Analysis prompt
            temperature: Sampling temperature
            max_tokens: Maximum tokens per response
            progress_callback: Optional callback for progress updates

        Returns:
            Dictionary with batch results
        """
        if not self.vision_client:
            raise ValueError("Vision client required for batch analysis")

        if not image_names:
            image_names = [f"image_{i+1}" for i in range(len(images))]

        results = []
        errors = []
        start_time = time.time()

        def analyze_image(index: int, image: Image.Image, name: str):
            """Analyze a single image."""
            try:
                result = self.vision_client.analyze(
                    prompt=prompt,
                    images=[image],
                    temperature=temperature,
                    max_tokens=max_tokens
                )
                return {
                    'index': index,
                    'name': name,
                    'result': result,
                    'success': True,
                    'error': None
                }
            except Exception as e:
                return {
                    'index': index,
                    'name': name,
                    'result': None,
                    'success': False,
                    'error': str(e)
                }

        # Process images concurrently
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = {
                executor.submit(analyze_image, i, img, name): (i, name)
                for i, (img, name) in enumerate(zip(images, image_names))
            }

            completed = 0
            for future in as_completed(futures):
                result = future.result()

                if result['success']:
                    results.append(result)
                else:
                    errors.append(result)

                completed += 1

                # Call progress callback if provided
                if progress_callback:
                    progress_callback(completed, len(images), result)

        # Sort results by index to maintain order
        results.sort(key=lambda x: x['index'])
        errors.sort(key=lambda x: x['index'])

        elapsed_time = time.time() - start_time

        return {
            'total_images': len(images),
            'successful': len(results),
            'failed': len(errors),
            'results': results,
            'errors': errors,
            'elapsed_time': elapsed_time,
            'avg_time_per_image': elapsed_time / len(images) if images else 0
        }

    def batch_ocr(
        self,
        images: List[Image.Image],
        image_names: Optional[List[str]] = None,
        language: str = 'eng',
        method: str = 'auto',
        fallback_to_vision: bool = False,
        confidence_threshold: float = 60.0,
        progress_callback: Optional[Callable] = None
    ) -> Dict[str, Any]:
        """Perform batch OCR on multiple images.

        Args:
            images: List of images to process
            image_names: Optional list of image names/identifiers
            language: OCR language code
            method: OCR method ('auto', 'tesseract', 'vision')
            fallback_to_vision: Use vision fallback for low confidence
            confidence_threshold: Minimum confidence threshold
            progress_callback: Optional callback for progress updates

        Returns:
            Dictionary with batch results
        """
        if not self.ocr_processor:
            raise ValueError("OCR processor required for batch OCR")

        if not image_names:
            image_names = [f"image_{i+1}" for i in range(len(images))]

        results = []
        errors = []
        start_time = time.time()

        def ocr_image(index: int, image: Image.Image, name: str):
            """OCR a single image."""
            try:
                result = self.ocr_processor.extract_text(
                    image=image,
                    language=language,
                    fallback_to_vision=fallback_to_vision,
                    confidence_threshold=confidence_threshold
                )
                return {
                    'index': index,
                    'name': name,
                    'text': result['text'],
                    'method': result['method'],
                    'confidence': result['confidence'],
                    'language': result['language'],
                    'success': True,
                    'error': None
                }
            except Exception as e:
                return {
                    'index': index,
                    'name': name,
                    'text': None,
                    'method': None,
                    'confidence': 0,
                    'language': None,
                    'success': False,
                    'error': str(e)
                }

        # Process images concurrently
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = {
                executor.submit(ocr_image, i, img, name): (i, name)
                for i, (img, name) in enumerate(zip(images, image_names))
            }

            completed = 0
            for future in as_completed(futures):
                result = future.result()

                if result['success']:
                    results.append(result)
                else:
                    errors.append(result)

                completed += 1

                # Call progress callback if provided
                if progress_callback:
                    progress_callback(completed, len(images), result)

        # Sort results by index to maintain order
        results.sort(key=lambda x: x['index'])
        errors.sort(key=lambda x: x['index'])

        elapsed_time = time.time() - start_time

        return {
            'total_images': len(images),
            'successful': len(results),
            'failed': len(errors),
            'results': results,
            'errors': errors,
            'elapsed_time': elapsed_time,
            'avg_time_per_image': elapsed_time / len(images) if images else 0
        }

    def export_to_json(
        self,
        batch_results: Dict[str, Any],
        output_path: Path,
        include_metadata: bool = True
    ) -> None:
        """Export batch results to JSON file.

        Args:
            batch_results: Batch processing results
            output_path: Path to output JSON file
            include_metadata: Include processing metadata
        """
        export_data = {
            'results': batch_results['results'],
            'errors': batch_results['errors']
        }

        if include_metadata:
            export_data['metadata'] = {
                'total_images': batch_results['total_images'],
                'successful': batch_results['successful'],
                'failed': batch_results['failed'],
                'elapsed_time': batch_results['elapsed_time'],
                'avg_time_per_image': batch_results['avg_time_per_image'],
                'timestamp': datetime.now().isoformat()
            }

        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(export_data, f, indent=2, ensure_ascii=False)

    def export_to_csv(
        self,
        batch_results: Dict[str, Any],
        output_path: Path,
        result_type: str = 'vision'
    ) -> None:
        """Export batch results to CSV file.

        Args:
            batch_results: Batch processing results
            output_path: Path to output CSV file
            result_type: Type of results ('vision' or 'ocr')
        """
        results = batch_results['results']

        with open(output_path, 'w', newline='', encoding='utf-8') as f:
            if result_type == 'vision':
                fieldnames = ['index', 'name', 'result', 'success']
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()

                for result in results:
                    writer.writerow({
                        'index': result['index'],
                        'name': result['name'],
                        'result': result['result'],
                        'success': result['success']
                    })

            elif result_type == 'ocr':
                fieldnames = ['index', 'name', 'text', 'method', 'confidence', 'language', 'success']
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()

                for result in results:
                    writer.writerow({
                        'index': result['index'],
                        'name': result['name'],
                        'text': result['text'],
                        'method': result['method'],
                        'confidence': result['confidence'],
                        'language': result['language'],
                        'success': result['success']
                    })

        # Also write errors to separate file if any
        if batch_results['errors']:
            error_path = output_path.parent / f"{output_path.stem}_errors{output_path.suffix}"
            with open(error_path, 'w', newline='', encoding='utf-8') as f:
                fieldnames = ['index', 'name', 'error']
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()

                for error in batch_results['errors']:
                    writer.writerow({
                        'index': error['index'],
                        'name': error['name'],
                        'error': error['error']
                    })

    def export_to_txt(
        self,
        batch_results: Dict[str, Any],
        output_path: Path,
        result_type: str = 'vision'
    ) -> None:
        """Export batch results to plain text file.

        Args:
            batch_results: Batch processing results
            output_path: Path to output text file
            result_type: Type of results ('vision' or 'ocr')
        """
        with open(output_path, 'w', encoding='utf-8') as f:
            # Write header
            f.write("=" * 80 + "\n")
            f.write(f"Batch Processing Results - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write("=" * 80 + "\n\n")

            # Write summary
            f.write(f"Total Images: {batch_results['total_images']}\n")
            f.write(f"Successful: {batch_results['successful']}\n")
            f.write(f"Failed: {batch_results['failed']}\n")
            f.write(f"Total Time: {batch_results['elapsed_time']:.2f}s\n")
            f.write(f"Avg Time/Image: {batch_results['avg_time_per_image']:.2f}s\n\n")

            # Write results
            f.write("-" * 80 + "\n")
            f.write("RESULTS\n")
            f.write("-" * 80 + "\n\n")

            for result in batch_results['results']:
                f.write(f"[{result['index'] + 1}] {result['name']}\n")
                f.write("-" * 40 + "\n")

                if result_type == 'vision':
                    f.write(f"{result['result']}\n")
                elif result_type == 'ocr':
                    f.write(f"Method: {result['method']}\n")
                    f.write(f"Confidence: {result['confidence']}%\n")
                    f.write(f"Language: {result['language']}\n")
                    f.write(f"Text:\n{result['text']}\n")

                f.write("\n")

            # Write errors if any
            if batch_results['errors']:
                f.write("-" * 80 + "\n")
                f.write("ERRORS\n")
                f.write("-" * 80 + "\n\n")

                for error in batch_results['errors']:
                    f.write(f"[{error['index'] + 1}] {error['name']}\n")
                    f.write(f"Error: {error['error']}\n\n")
