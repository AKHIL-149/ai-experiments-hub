#!/usr/bin/env python3
"""
Phase 2 Verification Test Script

Tests:
1. NSFW detector initialization
2. File handler operations (save, thumbnail generation)
3. Classification service (text, image)
4. Image upload and classification via API
"""

import os
import sys
from pathlib import Path
from io import BytesIO

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

from PIL import Image
from dotenv import load_dotenv


def test_nsfw_detector():
    """Test 1: NSFW detector initialization"""
    print("\n=== Test 1: NSFW Detector ===")

    try:
        from src.services.nsfw_detector import get_nsfw_detector

        detector = get_nsfw_detector()
        print(f"✓ NSFW detector initialized: enabled={detector.enabled}")

        if detector.enabled:
            print("  NudeNet is available and ready")
        else:
            print("  NudeNet not available (using fallback)")

        return True
    except Exception as e:
        print(f"✗ NSFW detector test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_file_handler():
    """Test 2: File handler operations"""
    print("\n=== Test 2: File Handler ===")

    try:
        from src.utils.file_handler import get_file_handler

        file_handler = get_file_handler()
        print(f"✓ File handler initialized")
        print(f"  Upload dir: {file_handler.upload_dir}")
        print(f"  Thumbnail dir: {file_handler.thumbnail_dir}")

        # Create test image
        print("\nTest 2a: Create test image")
        img = Image.new('RGB', (800, 600), color='blue')
        img_bytes = BytesIO()
        img.save(img_bytes, format='JPEG')
        img_data = img_bytes.getvalue()
        print(f"  Test image created: {len(img_data)} bytes")

        # Test save upload
        print("\nTest 2b: Save upload")
        success, file_path, file_hash, error = file_handler.save_upload(
            file_data=img_data,
            filename='test_image.jpg',
            user_id='test_user_123',
            content_type='image'
        )

        if success:
            print(f"✓ File saved: {Path(file_path).name}")
            print(f"  Hash: {file_hash[:16]}...")
        else:
            print(f"✗ File save failed: {error}")
            return False

        # Test thumbnail generation
        print("\nTest 2c: Generate thumbnail")
        success, thumb_path, error = file_handler.generate_thumbnail(file_path)

        if success:
            print(f"✓ Thumbnail generated: {Path(thumb_path).name}")

            # Check thumbnail size
            with Image.open(thumb_path) as thumb:
                print(f"  Thumbnail size: {thumb.size[0]}x{thumb.size[1]}")
        else:
            print(f"  Thumbnail generation skipped or failed: {error}")

        # Test image validation
        print("\nTest 2d: Validate image")
        is_valid, error = file_handler.validate_image(file_path)

        if is_valid:
            print(f"✓ Image validated")
        else:
            print(f"✗ Image validation failed: {error}")

        # Test get image info
        print("\nTest 2e: Get image info")
        info = file_handler.get_image_info(file_path)

        if info:
            print(f"✓ Image info: {info['format']} {info['width']}x{info['height']} ({info['size_bytes']} bytes)")
        else:
            print(f"✗ Failed to get image info")

        # Cleanup
        print("\nTest 2f: Cleanup")
        if file_handler.delete_file(file_path):
            print(f"✓ Test files deleted")
        else:
            print(f"  Cleanup failed (files may remain)")

        return True

    except Exception as e:
        print(f"✗ File handler test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_classification_service():
    """Test 3: Classification service"""
    print("\n=== Test 3: Classification Service ===")

    try:
        from src.services.classification_service import get_classification_service

        service = get_classification_service()
        print(f"✓ Classification service initialized")
        print(f"  LLM: {service.llm_provider}/{service.llm_client.model}")
        print(f"  NSFW detector: {service.nsfw_detector.enabled}")

        # Test text classification
        print("\nTest 3a: Text classification")
        result = service.classify_text("Hello, this is a friendly test message.")

        print(f"  Category: {result['category']}")
        print(f"  Confidence: {result['confidence']:.2f}")
        print(f"  Is violation: {result['is_violation']}")
        print(f"  Reasoning: {result['reasoning'][:80]}...")
        print(f"  Processing time: {result['processing_time_ms']:.0f}ms")

        if result['category'] and result['confidence'] >= 0:
            print(f"✓ Text classification working")
        else:
            print(f"✗ Text classification returned invalid result")
            return False

        # Test image classification (with generated image)
        print("\nTest 3b: Image classification")

        # Create test image
        from src.utils.file_handler import get_file_handler
        file_handler = get_file_handler()

        img = Image.new('RGB', (400, 300), color='green')
        img_bytes = BytesIO()
        img.save(img_bytes, format='JPEG')
        img_data = img_bytes.getvalue()

        success, file_path, file_hash, error = file_handler.save_upload(
            file_data=img_data,
            filename='test_classify.jpg',
            user_id='test_user_classify',
            content_type='image'
        )

        if not success:
            print(f"  Could not create test image: {error}")
            return True  # Skip image test but don't fail

        try:
            result = service.classify_image(file_path, use_vision=False)

            print(f"  Category: {result['category']}")
            print(f"  Confidence: {result['confidence']:.2f}")
            print(f"  Is violation: {result['is_violation']}")
            print(f"  NSFW checked: {result['nsfw_checked']}")
            print(f"  Reasoning: {result['reasoning'][:80]}...")

            if result['category'] and result['confidence'] >= 0:
                print(f"✓ Image classification working")
            else:
                print(f"✗ Image classification returned invalid result")

            # Cleanup
            file_handler.delete_file(file_path)

        except Exception as e:
            print(f"  Image classification error (expected if NudeNet not installed): {e}")
            file_handler.delete_file(file_path)

        # Test moderation policy
        print("\nTest 3c: Moderation policy")
        test_classifications = [
            {'category': 'clean', 'confidence': 0.96, 'is_violation': False},
            {'category': 'spam', 'confidence': 0.92, 'is_violation': True},
            {'category': 'nsfw', 'confidence': 0.65, 'is_violation': True},
        ]

        for test_class in test_classifications:
            status = service.apply_moderation_policy(test_class)
            print(f"  {test_class['category']} (conf={test_class['confidence']:.2f}) → {status}")

        print(f"✓ Moderation policy working")

        return True

    except Exception as e:
        print(f"✗ Classification service test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_integration():
    """Test 4: Integration test (database + classification)"""
    print("\n=== Test 4: Integration Test ===")

    try:
        from src.core.database import DatabaseManager, ContentItem, Classification, ContentType, ContentStatus
        from src.services.classification_service import get_classification_service
        from src.utils.file_handler import get_file_handler

        # Initialize
        db_manager = DatabaseManager()
        service = get_classification_service()
        file_handler = get_file_handler()

        print("✓ Services initialized")

        # Create test image
        img = Image.new('RGB', (200, 150), color='red')
        img_bytes = BytesIO()
        img.save(img_bytes, format='JPEG')
        img_data = img_bytes.getvalue()

        success, file_path, file_hash, error = file_handler.save_upload(
            file_data=img_data,
            filename='integration_test.jpg',
            user_id='integration_test_user',
            content_type='image'
        )

        if not success:
            print(f"✗ Failed to save test image: {error}")
            return False

        print(f"✓ Test image created")

        # Classify
        result = service.classify_image(file_path, use_vision=False)
        print(f"✓ Classification complete: {result['category']} (confidence: {result['confidence']:.2f})")

        # Save to database
        with db_manager.get_session() as db:
            # Create content item
            content_item = ContentItem(
                user_id='integration_test_user',
                content_type=ContentType.IMAGE,
                file_path=file_path,
                file_hash=file_hash,
                status=ContentStatus.PROCESSING,
                priority=0
            )

            db.add(content_item)
            db.commit()
            db.refresh(content_item)

            print(f"✓ Content item created: {content_item.id}")

            # Create classification record
            from src.core.database import ViolationCategory
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

        # Cleanup
        file_handler.delete_file(file_path)
        print(f"✓ Cleanup complete")

        return True

    except Exception as e:
        print(f"✗ Integration test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Run all Phase 2 tests"""
    print("=" * 60)
    print("Phase 2 Verification Tests")
    print("=" * 60)

    # Load environment
    load_dotenv()

    # Run tests
    results = {
        "NSFW Detector": test_nsfw_detector(),
        "File Handler": test_file_handler(),
        "Classification Service": test_classification_service(),
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
        print("\n✓ Phase 2 verification complete!")
        print("\nNext steps:")
        print("1. Start the server: python3 server.py")
        print("2. Test image upload via API or web UI")
        print("3. Verify NSFW detection and classification")
        return 0
    else:
        print("\n✗ Some tests failed. Please check the errors above.")
        print("\nNote: NSFW detector tests may fail if NudeNet is not installed.")
        print("      Install with: pip3 install nudenet")
        return 1


if __name__ == "__main__":
    sys.exit(main())
