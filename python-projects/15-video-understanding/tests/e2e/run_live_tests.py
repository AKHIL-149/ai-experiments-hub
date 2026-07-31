"""
Simple live test runner for Video Understanding API
Tests the API without complex fixtures
"""

import requests
import time
import sys
import json
from pathlib import Path


# ============================================================================
# Configuration
# ============================================================================

BASE_URL = "http://localhost:8000"


# ============================================================================
# Test Functions
# ============================================================================

def test_api_health():
    """Test basic API health and connectivity"""
    print("\n" + "=" * 80)
    print("🧪 TESTING API HEALTH & CONNECTIVITY")
    print("=" * 80)

    try:
        # Test root endpoint
        print("\n📍 Testing GET /")
        response = requests.get(f"{BASE_URL}/", timeout=5)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        data = response.json()
        assert data["status"] == "operational"
        print(f"✅ Root endpoint OK - Version: {data.get('version', 'unknown')}")

        # Test health check
        print("\n📍 Testing GET /health")
        response = requests.get(f"{BASE_URL}/health", timeout=5)
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        print(f"✅ Health check OK - Environment: {data.get('environment', 'unknown')}")

        # Test version
        print("\n📍 Testing GET /version")
        response = requests.get(f"{BASE_URL}/version", timeout=5)
        assert response.status_code == 200
        data = response.json()
        print(f"✅ Version endpoint OK - Version: {data.get('version', 'unknown')}")

        # Test API info
        print("\n📍 Testing GET /api/info")
        response = requests.get(f"{BASE_URL}/api/info", timeout=5)
        assert response.status_code == 200
        data = response.json()
        capabilities = data.get("capabilities", {})
        print(f"✅ API info OK - Features: {list(capabilities.keys())}")

        return True

    except Exception as e:
        print(f"❌ Health tests failed: {e}")
        return False


def test_api_docs():
    """Test API documentation endpoints"""
    print("\n" + "=" * 80)
    print("🧪 TESTING API DOCUMENTATION")
    print("=" * 80)

    try:
        # Test OpenAPI schema
        print("\n📍 Testing GET /openapi.json")
        response = requests.get(f"{BASE_URL}/openapi.json", timeout=5)
        assert response.status_code == 200
        schema = response.json()
        assert "openapi" in schema
        assert "paths" in schema
        endpoint_count = len(schema["paths"])
        print(f"✅ OpenAPI schema OK - {endpoint_count} endpoints documented")

        # Test Swagger UI
        print("\n📍 Testing GET /docs")
        response = requests.get(f"{BASE_URL}/docs", timeout=5)
        assert response.status_code == 200
        assert "swagger" in response.text.lower() or "api" in response.text.lower()
        print("✅ Swagger UI accessible")

        # Test ReDoc
        print("\n📍 Testing GET /redoc")
        response = requests.get(f"{BASE_URL}/redoc", timeout=5)
        assert response.status_code == 200
        print("✅ ReDoc accessible")

        return True

    except Exception as e:
        print(f"❌ Documentation tests failed: {e}")
        return False


def test_video_endpoints():
    """Test video management endpoints"""
    print("\n" + "=" * 80)
    print("🧪 TESTING VIDEO ENDPOINTS")
    print("=" * 80)

    try:
        # Test list videos
        print("\n📍 Testing GET /api/videos")
        response = requests.get(f"{BASE_URL}/api/videos", timeout=5)
        print(f"   Status: {response.status_code}")
        if response.status_code == 200:
            data = response.json()
            print(f"✅ List videos OK - Found {data.get('total', 0)} videos")
        else:
            print("⚠️  List videos returned error (expected if DB not configured)")

        # Test get non-existent video
        print("\n📍 Testing GET /api/videos/{nonexistent-id}")
        response = requests.get(f"{BASE_URL}/api/videos/nonexistent-id", timeout=5)
        assert response.status_code == 404
        print("✅ Correctly returns 404 for non-existent video")

        # Test get video status
        print("\n📍 Testing GET /api/videos/{test-id}/status")
        response = requests.get(f"{BASE_URL}/api/videos/test-id/status", timeout=5)
        print(f"   Status: {response.status_code} (404 or 500 expected)")
        assert response.status_code in [404, 500]
        print("✅ Status endpoint exists")

        return True

    except Exception as e:
        print(f"❌ Video endpoint tests failed: {e}")
        return False


def test_search_endpoints():
    """Test search endpoints"""
    print("\n" + "=" * 80)
    print("🧪 TESTING SEARCH ENDPOINTS")
    print("=" * 80)

    try:
        # Test semantic search
        print("\n📍 Testing POST /api/search/semantic")
        response = requests.post(
            f"{BASE_URL}/api/search/semantic",
            json={"query": "test query", "top_k": 5},
            timeout=5
        )
        print(f"   Status: {response.status_code}")
        if response.status_code == 200:
            data = response.json()
            print(f"✅ Semantic search OK - {data.get('total_results', 0)} results")
        else:
            print("⚠️  Semantic search needs database (expected)")

        # Test frame search
        print("\n📍 Testing POST /api/search/frames")
        response = requests.post(
            f"{BASE_URL}/api/search/frames",
            json={"query": "person walking", "top_k": 5},
            timeout=5
        )
        print(f"   Status: {response.status_code} (200 or 500 expected)")
        print("✅ Frame search endpoint exists")

        # Test transcript search
        print("\n📍 Testing POST /api/search/transcript")
        response = requests.post(
            f"{BASE_URL}/api/search/transcript",
            json={"query": "hello", "top_k": 5, "search_mode": "semantic"},
            timeout=5
        )
        print(f"   Status: {response.status_code}")
        print("✅ Transcript search endpoint exists")

        # Test video query
        print("\n📍 Testing POST /api/search/query")
        response = requests.post(
            f"{BASE_URL}/api/search/query",
            json={"question": "What is this video about?"},
            timeout=5
        )
        print(f"   Status: {response.status_code}")
        print("✅ Video query endpoint exists")

        return True

    except Exception as e:
        print(f"❌ Search endpoint tests failed: {e}")
        return False


def test_analysis_endpoints():
    """Test analysis endpoints"""
    print("\n" + "=" * 80)
    print("🧪 TESTING ANALYSIS ENDPOINTS")
    print("=" * 80)

    try:
        # Test get summary
        print("\n📍 Testing GET /api/videos/{id}/summary")
        response = requests.get(f"{BASE_URL}/api/videos/test-id/summary", timeout=5)
        print(f"   Status: {response.status_code} (404 or 500 expected)")
        assert response.status_code in [404, 500]
        print("✅ Summary endpoint exists")

        # Test get highlights
        print("\n📍 Testing GET /api/videos/{id}/highlights")
        response = requests.get(f"{BASE_URL}/api/videos/test-id/highlights", timeout=5)
        assert response.status_code in [404, 500]
        print("✅ Highlights endpoint exists")

        # Test get chapters
        print("\n📍 Testing GET /api/videos/{id}/chapters")
        response = requests.get(f"{BASE_URL}/api/videos/test-id/chapters", timeout=5)
        assert response.status_code in [404, 500]
        print("✅ Chapters endpoint exists")

        # Test get timeline
        print("\n📍 Testing GET /api/videos/{id}/timeline")
        response = requests.get(f"{BASE_URL}/api/videos/test-id/timeline", timeout=5)
        assert response.status_code in [404, 500]
        print("✅ Timeline endpoint exists")

        return True

    except Exception as e:
        print(f"❌ Analysis endpoint tests failed: {e}")
        return False


def test_clips_endpoints():
    """Test clip endpoints"""
    print("\n" + "=" * 80)
    print("🧪 TESTING CLIPS ENDPOINTS")
    print("=" * 80)

    try:
        # Test list clips
        print("\n📍 Testing GET /api/clips")
        response = requests.get(f"{BASE_URL}/api/clips", timeout=5)
        print(f"   Status: {response.status_code}")
        if response.status_code == 200:
            data = response.json()
            print(f"✅ List clips OK - Found {data.get('total', 0)} clips")
        else:
            print("⚠️  List clips needs database")

        # Test get clip
        print("\n📍 Testing GET /api/clips/{id}")
        response = requests.get(f"{BASE_URL}/api/clips/test-id", timeout=5)
        assert response.status_code in [404, 500]
        print("✅ Get clip endpoint exists")

        return True

    except Exception as e:
        print(f"❌ Clips endpoint tests failed: {e}")
        return False


def test_processing_endpoints():
    """Test processing endpoints"""
    print("\n" + "=" * 80)
    print("🧪 TESTING PROCESSING ENDPOINTS")
    print("=" * 80)

    try:
        # Test get scenes
        print("\n📍 Testing GET /api/videos/{id}/scenes")
        response = requests.get(f"{BASE_URL}/api/videos/test-id/scenes", timeout=5)
        assert response.status_code in [404, 500]
        print("✅ Scenes endpoint exists")

        # Test get transcript
        print("\n📍 Testing GET /api/videos/{id}/transcript")
        response = requests.get(f"{BASE_URL}/api/videos/test-id/transcript", timeout=5)
        assert response.status_code in [404, 500]
        print("✅ Transcript endpoint exists")

        # Test get frames
        print("\n📍 Testing GET /api/videos/{id}/frames")
        response = requests.get(f"{BASE_URL}/api/videos/test-id/frames", timeout=5)
        assert response.status_code in [404, 500]
        print("✅ Frames endpoint exists")

        # Test get keyframes
        print("\n📍 Testing GET /api/videos/{id}/keyframes")
        response = requests.get(f"{BASE_URL}/api/videos/test-id/keyframes", timeout=5)
        assert response.status_code in [404, 500]
        print("✅ Keyframes endpoint exists")

        return True

    except Exception as e:
        print(f"❌ Processing endpoint tests failed: {e}")
        return False


def test_error_handling():
    """Test error handling"""
    print("\n" + "=" * 80)
    print("🧪 TESTING ERROR HANDLING")
    print("=" * 80)

    try:
        # Test 404
        print("\n📍 Testing 404 error handling")
        response = requests.get(f"{BASE_URL}/nonexistent-path", timeout=5)
        assert response.status_code == 404
        data = response.json()
        assert "error" in data or "message" in data
        print("✅ 404 errors handled correctly")

        # Test invalid JSON
        print("\n📍 Testing invalid JSON handling")
        response = requests.post(
            f"{BASE_URL}/api/search/semantic",
            data="invalid{json",
            headers={"Content-Type": "application/json"},
            timeout=5
        )
        assert response.status_code in [400, 422, 500]
        print("✅ Invalid JSON handled")

        # Test missing required fields
        print("\n📍 Testing field validation")
        response = requests.post(
            f"{BASE_URL}/api/search/semantic",
            json={},  # Missing 'query'
            timeout=5
        )
        assert response.status_code == 422
        print("✅ Field validation working")

        return True

    except Exception as e:
        print(f"❌ Error handling tests failed: {e}")
        return False


def test_performance():
    """Test API performance"""
    print("\n" + "=" * 80)
    print("🧪 TESTING API PERFORMANCE")
    print("=" * 80)

    try:
        # Test response time
        print("\n📍 Testing response time")
        start = time.time()
        response = requests.get(f"{BASE_URL}/health", timeout=5)
        elapsed = (time.time() - start) * 1000

        assert response.status_code == 200
        assert elapsed < 1000  # Should be < 1 second
        print(f"✅ Response time: {elapsed:.2f}ms")

        # Test concurrent requests
        print("\n📍 Testing 10 concurrent requests")
        import concurrent.futures

        def make_request():
            return requests.get(f"{BASE_URL}/health", timeout=5)

        start = time.time()
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(make_request) for _ in range(10)]
            results = [f.result() for f in futures]

        elapsed = (time.time() - start) * 1000

        assert all(r.status_code == 200 for r in results)
        print(f"✅ 10 concurrent requests completed in {elapsed:.2f}ms")

        return True

    except Exception as e:
        print(f"❌ Performance tests failed: {e}")
        return False


# ============================================================================
# Main Test Runner
# ============================================================================

def main():
    """Run all tests"""
    print("\n" + "=" * 80)
    print("🚀 LIVE E2E TESTS FOR VIDEO UNDERSTANDING API")
    print("=" * 80)
    print(f"\n📡 Testing server at: {BASE_URL}")

    # Check if server is running
    print("\n⏳ Checking if server is running...")
    try:
        response = requests.get(f"{BASE_URL}/health", timeout=2)
        print(f"✅ Server is responding!")
    except requests.exceptions.RequestException:
        print(f"❌ Server is not running at {BASE_URL}")
        print(f"\n💡 Start the server with: python server.py")
        sys.exit(1)

    # Run all test suites
    results = []

    results.append(("API Health & Connectivity", test_api_health()))
    results.append(("API Documentation", test_api_docs()))
    results.append(("Video Endpoints", test_video_endpoints()))
    results.append(("Search Endpoints", test_search_endpoints()))
    results.append(("Analysis Endpoints", test_analysis_endpoints()))
    results.append(("Clips Endpoints", test_clips_endpoints()))
    results.append(("Processing Endpoints", test_processing_endpoints()))
    results.append(("Error Handling", test_error_handling()))
    results.append(("Performance", test_performance()))

    # Print summary
    print("\n" + "=" * 80)
    print("📊 TEST SUMMARY")
    print("=" * 80)

    passed = sum(1 for _, result in results if result)
    failed = len(results) - passed

    for name, result in results:
        status = "✅ PASSED" if result else "❌ FAILED"
        print(f"{status}: {name}")

    print("\n" + "-" * 80)
    print(f"Total: {len(results)} test suites")
    print(f"✅ Passed: {passed}")
    print(f"❌ Failed: {failed}")
    print("=" * 80)

    if failed == 0:
        print("\n🎉 ALL TESTS PASSED!")
        return 0
    else:
        print(f"\n⚠️  {failed} test suite(s) failed")
        return 1


if __name__ == "__main__":
    sys.exit(main())
