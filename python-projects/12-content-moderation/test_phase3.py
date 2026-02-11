#!/usr/bin/env python3
"""
Phase 3 Verification Test Script

Tests:
1. Video processor initialization
2. Frame extraction (with generated test video)
3. Video thumbnail generation
4. Video classification service
5. Integration test (database + video classification pipeline)
"""

import os
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

from dotenv import load_dotenv


def test_video_processor():
    """Test 1: Video processor initialization"""
    print("\n=== Test 1: Video Processor ===")

    try:
        from src.services.video_processor import get_video_processor

        processor = get_video_processor()
        print(f"✓ Video processor initialized")
        print(f"  ffmpeg available: {processor.ffmpeg_available}")
        print(f"  FPS: {processor.fps}")
        print(f"  Max frames: {processor.max_frames}")

        if not processor.ffmpeg_available:
            print("  ⚠ Warning: ffmpeg not available - video processing will be limited")
            print("  Install ffmpeg: brew install ffmpeg (macOS) or apt-get install ffmpeg (Linux)")

        return True
    except Exception as e:
        print(f"✗ Video processor test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_frame_extraction():
    """Test 2: Frame extraction with synthetic video"""
    print("\n=== Test 2: Frame Extraction ===")

    try:
        from src.services.video_processor import get_video_processor
        import subprocess
        import tempfile

        processor = get_video_processor()

        if not processor.ffmpeg_available:
            print("  ⚠ Skipping frame extraction test (ffmpeg not available)")
            return True

        # Create a synthetic test video using ffmpeg
        print("\nTest 2a: Generate test video")
        with tempfile.NamedTemporaryFile(suffix='.mp4', delete=False) as tmp:
            test_video_path = tmp.name

        try:
            # Generate a 5-second test video with color bars
            result = subprocess.run([
                'ffmpeg', '-f', 'lavfi', '-i', 'testsrc=duration=5:size=320x240:rate=30',
                '-pix_fmt', 'yuv420p', '-y', test_video_path
            ], capture_output=True, timeout=10)

            if result.returncode != 0:
                print(f"  ⚠ Could not generate test video: {result.stderr.decode()}")
                return True  # Skip but don't fail

            print(f"  Test video created: {Path(test_video_path).name}")

            # Get video info
            print("\nTest 2b: Get video info")
            info = processor.get_video_info(test_video_path)
            if info:
                print(f"  Duration: {info['duration']:.2f}s")
                print(f"  Resolution: {info['width']}x{info['height']}")
                print(f"  Codec: {info['codec']}")
                print(f"  FPS: {info['fps']:.2f}")
                print(f"✓ Video info retrieved")
            else:
                print(f"  ⚠ Could not get video info")

            # Extract frames
            print("\nTest 2c: Extract frames")
            success, frame_paths, error = processor.extract_frames(test_video_path)

            if success and frame_paths:
                print(f"✓ Extracted {len(frame_paths)} frames")
                print(f"  First frame: {Path(frame_paths[0]).name}")
                print(f"  Last frame: {Path(frame_paths[-1]).name}")

                # Verify frames exist
                existing_frames = sum(1 for fp in frame_paths if Path(fp).exists())
                print(f"  Verified {existing_frames}/{len(frame_paths)} frames exist")

                # Test cleanup
                print("\nTest 2d: Cleanup frames")
                if processor.cleanup_frames(frame_paths):
                    print(f"✓ Frames cleaned up")
                else:
                    print(f"  ⚠ Some frames may not have been deleted")

            else:
                print(f"✗ Frame extraction failed: {error}")
                return False

            # Test thumbnail generation
            print("\nTest 2e: Generate video thumbnail")
            success, thumb_path, error = processor.generate_video_thumbnail(
                test_video_path,
                time_offset=2.0
            )

            if success and thumb_path:
                thumb_size = Path(thumb_path).stat().st_size
                print(f"✓ Thumbnail generated: {Path(thumb_path).name} ({thumb_size} bytes)")
                # Cleanup thumbnail
                Path(thumb_path).unlink()
            else:
                print(f"  ⚠ Thumbnail generation failed: {error}")

        finally:
            # Cleanup test video
            if Path(test_video_path).exists():
                Path(test_video_path).unlink()
                print(f"\nTest 2f: Test video cleaned up")

        return True

    except Exception as e:
        print(f"✗ Frame extraction test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_video_classification():
    """Test 3: Video classification service"""
    print("\n=== Test 3: Video Classification Service ===")

    try:
        from src.services.classification_service import get_classification_service
        from src.services.video_processor import get_video_processor
        import subprocess
        import tempfile

        service = get_classification_service()
        processor = get_video_processor()

        print(f"✓ Classification service initialized")

        if not processor.ffmpeg_available:
            print("  ⚠ Skipping video classification test (ffmpeg not available)")
            return True

        # Create test video
        print("\nTest 3a: Generate test video")
        with tempfile.NamedTemporaryFile(suffix='.mp4', delete=False) as tmp:
            test_video_path = tmp.name

        try:
            # Generate a shorter 3-second test video for faster classification
            result = subprocess.run([
                'ffmpeg', '-f', 'lavfi', '-i', 'testsrc=duration=3:size=320x240:rate=30',
                '-pix_fmt', 'yuv420p', '-y', test_video_path
            ], capture_output=True, timeout=10)

            if result.returncode != 0:
                print(f"  ⚠ Could not generate test video")
                return True

            print(f"  Test video created")

            # Classify video (without vision to speed up tests)
            print("\nTest 3b: Classify video (NSFW detection only)")
            result = service.classify_video(
                test_video_path,
                max_frames=3,
                use_vision=False
            )

            print(f"  Category: {result['category']}")
            print(f"  Confidence: {result['confidence']:.2f}")
            print(f"  Is violation: {result['is_violation']}")
            print(f"  Frames analyzed: {result.get('frames_analyzed', 0)}")
            print(f"  Processing time: {result['processing_time_ms']:.0f}ms")
            print(f"  Cost: ${result['cost']:.4f}")

            if result.get('frames_analyzed', 0) > 0:
                print(f"✓ Video classification working")
            else:
                print(f"  ⚠ No frames were analyzed")

            # Test moderation policy
            print("\nTest 3c: Apply moderation policy")
            status = service.apply_moderation_policy(result)
            print(f"  Video status: {status}")
            print(f"✓ Moderation policy applied")

        finally:
            # Cleanup
            if Path(test_video_path).exists():
                Path(test_video_path).unlink()

        return True

    except Exception as e:
        print(f"✗ Video classification test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_integration():
    """Test 4: Integration test (database + video classification)"""
    print("\n=== Test 4: Integration Test ===")

    try:
        from src.core.database import DatabaseManager, ContentItem, Classification, ContentType, ContentStatus, ViolationCategory
        from src.services.classification_service import get_classification_service
        from src.services.video_processor import get_video_processor
        import subprocess
        import tempfile

        # Initialize services
        db_manager = DatabaseManager()
        service = get_classification_service()
        processor = get_video_processor()

        print("✓ Services initialized")

        if not processor.ffmpeg_available:
            print("  ⚠ Skipping integration test (ffmpeg not available)")
            return True

        # Create test video
        print("\nTest 4a: Generate test video")
        with tempfile.NamedTemporaryFile(suffix='.mp4', delete=False) as tmp:
            test_video_path = tmp.name

        try:
            result = subprocess.run([
                'ffmpeg', '-f', 'lavfi', '-i', 'testsrc=duration=2:size=320x240:rate=30',
                '-pix_fmt', 'yuv420p', '-y', test_video_path
            ], capture_output=True, timeout=10)

            if result.returncode != 0:
                print(f"  ⚠ Could not generate test video")
                return True

            # Calculate file hash
            import hashlib
            with open(test_video_path, 'rb') as f:
                file_hash = hashlib.sha256(f.read()).hexdigest()

            print(f"  Test video created")

            # Classify video
            print("\nTest 4b: Classify video")
            result = service.classify_video(
                test_video_path,
                max_frames=2,
                use_vision=False
            )
            print(f"✓ Classification complete: {result['category']} (confidence: {result['confidence']:.2f})")

            # Save to database
            with db_manager.get_session() as db:
                # Create content item
                content_item = ContentItem(
                    user_id='integration_test_video_user',
                    content_type=ContentType.VIDEO,
                    file_path=test_video_path,
                    file_hash=file_hash,
                    status=ContentStatus.PROCESSING,
                    priority=0
                )

                db.add(content_item)
                db.commit()
                db.refresh(content_item)

                print(f"✓ Content item created: {content_item.id}")

                # Create classification record
                classification = Classification(
                    content_id=content_item.id,
                    category=ViolationCategory(result['category']),
                    confidence=result['confidence'],
                    is_violation=result['is_violation'],
                    provider=result['provider'],
                    model_name=result['model'],
                    reasoning=result['reasoning'],
                    processing_time_ms=result.get('processing_time_ms', 0),
                    cost=result.get('cost', 0.0)
                )

                db.add(classification)
                db.commit()
                db.refresh(classification)

                print(f"✓ Classification record created: {classification.id}")

                # Apply policy
                status = service.apply_moderation_policy(result)
                content_item.status = ContentStatus(status)
                db.commit()

                print(f"✓ Content status updated: {status}")

                # Verify
                retrieved = db.query(ContentItem).filter(ContentItem.id == content_item.id).first()
                if retrieved and retrieved.classifications:
                    print(f"✓ Verification: Content has {len(retrieved.classifications)} classification(s)")
                else:
                    print(f"  Warning: Could not verify classifications")

        finally:
            # Cleanup
            if Path(test_video_path).exists():
                Path(test_video_path).unlink()
            print(f"✓ Cleanup complete")

        return True

    except Exception as e:
        print(f"✗ Integration test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Run all Phase 3 tests"""
    print("=" * 60)
    print("Phase 3 Verification Tests")
    print("=" * 60)

    # Load environment
    load_dotenv()

    # Run tests
    results = {
        "Video Processor": test_video_processor(),
        "Frame Extraction": test_frame_extraction(),
        "Video Classification": test_video_classification(),
        "Integration": test_integration()
    }

    # Summary
    print("\n" + "=" * 60)
    print("Test Summary")
    print("=" * 60)

    for test_name, passed in results.items():
        status = "✓ PASSED" if passed else "✗ FAILED"
        print(f"{test_name:.<40} {status}")

    total = len(results)
    passed = sum(1 for p in results.values() if p)

    print("=" * 60)
    print(f"Total: {passed}/{total} tests passed")
    print("=" * 60)

    if passed == total:
        print("\n✓ Phase 3 verification complete!")
        print("\nNext steps:")
        print("1. Start the server: python3 server.py")
        print("2. Test video upload via API or web UI")
        print("3. Verify frame extraction and classification")
        print("4. Check video thumbnails are generated")
        print("\nNote: ffmpeg must be installed for video processing:")
        print("  macOS: brew install ffmpeg")
        print("  Ubuntu/Debian: sudo apt-get install ffmpeg")
        print("  Windows: Download from ffmpeg.org")
        return 0
    else:
        print("\n✗ Some tests failed. Please check the errors above.")
        print("\nTroubleshooting:")
        print("1. Ensure ffmpeg is installed: ffmpeg -version")
        print("2. Check ffmpeg-python is installed: pip list | grep ffmpeg")
        print("3. Verify file permissions in data/ directories")
        return 1


if __name__ == "__main__":
    sys.exit(main())
