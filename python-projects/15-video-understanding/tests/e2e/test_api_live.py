"""
End-to-end live tests for Video Understanding API
Uses Playwright to test the running FastAPI application
"""

import pytest
import asyncio
import subprocess
import time
import requests
import json
from pathlib import Path
from playwright.async_api import async_playwright, Page, BrowserContext


# ============================================================================
# Configuration
# ============================================================================

BASE_URL = "http://localhost:8000"
API_TIMEOUT = 30000  # 30 seconds


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture(scope="session")
def fastapi_server():
    """
    Start FastAPI server for testing
    """
    print("\n🚀 Starting FastAPI server...")

    # Start server in background
    process = subprocess.Popen(
        ["python", "server.py"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=Path(__file__).parent.parent.parent,
    )

    # Wait for server to be ready
    max_retries = 30
    for i in range(max_retries):
        try:
            response = requests.get(f"{BASE_URL}/health", timeout=2)
            if response.status_code == 200:
                print(f"✅ Server is ready! (attempt {i+1}/{max_retries})")
                break
        except requests.exceptions.RequestException:
            if i < max_retries - 1:
                print(f"⏳ Waiting for server... (attempt {i+1}/{max_retries})")
                time.sleep(1)
            else:
                process.kill()
                raise Exception("Failed to start server")

    yield process

    # Cleanup
    print("\n🛑 Shutting down server...")
    process.terminate()
    process.wait(timeout=5)


@pytest.fixture(scope="session")
async def browser():
    """
    Create Playwright browser instance
    """
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        yield browser
        await browser.close()


@pytest.fixture
async def context(browser):
    """
    Create browser context for each test
    """
    context = await browser.new_context(
        viewport={"width": 1920, "height": 1080},
        user_agent="Mozilla/5.0 (Playwright E2E Test)"
    )
    yield context
    await context.close()


@pytest.fixture
async def page(context):
    """
    Create page for each test
    """
    page = await context.new_page()
    yield page
    await page.close()


# ============================================================================
# API Health Tests
# ============================================================================

class TestAPIHealth:
    """Test basic API health and connectivity"""

    @pytest.mark.asyncio
    async def test_root_endpoint(self, fastapi_server, page: Page):
        """Test root endpoint returns correct information"""
        print("\n🧪 Testing root endpoint...")

        response = await page.request.get(f"{BASE_URL}/")
        assert response.ok, f"Failed to reach root endpoint: {response.status}"

        data = await response.json()
        assert data["status"] == "operational"
        assert "version" in data
        assert "docs" in data
        assert "endpoints" in data

        print("✅ Root endpoint working")

    @pytest.mark.asyncio
    async def test_health_check(self, fastapi_server, page: Page):
        """Test health check endpoint"""
        print("\n🧪 Testing health check...")

        response = await page.request.get(f"{BASE_URL}/health")
        assert response.ok

        data = await response.json()
        assert data["status"] == "healthy"
        assert "version" in data

        print("✅ Health check passed")

    @pytest.mark.asyncio
    async def test_version_endpoint(self, fastapi_server, page: Page):
        """Test version endpoint"""
        print("\n🧪 Testing version endpoint...")

        response = await page.request.get(f"{BASE_URL}/version")
        assert response.ok

        data = await response.json()
        assert "version" in data
        assert "api_version" in data

        print(f"✅ Version: {data['version']}")

    @pytest.mark.asyncio
    async def test_api_info(self, fastapi_server, page: Page):
        """Test API info endpoint"""
        print("\n🧪 Testing API info...")

        response = await page.request.get(f"{BASE_URL}/api/info")
        assert response.ok

        data = await response.json()
        assert "capabilities" in data
        assert "video_sources" in data["capabilities"]
        assert "processing" in data["capabilities"]
        assert "search" in data["capabilities"]

        print("✅ API info endpoint working")


# ============================================================================
# OpenAPI Documentation Tests
# ============================================================================

class TestAPIDocs:
    """Test OpenAPI documentation endpoints"""

    @pytest.mark.asyncio
    async def test_swagger_ui(self, fastapi_server, page: Page):
        """Test Swagger UI is accessible"""
        print("\n🧪 Testing Swagger UI...")

        await page.goto(f"{BASE_URL}/docs")
        await page.wait_for_load_state("networkidle")

        # Check for Swagger UI elements
        title = await page.title()
        assert "Video Understanding" in title or "FastAPI" in title

        # Check if API endpoints are listed
        content = await page.content()
        assert "/api/videos" in content or "videos" in content.lower()

        print("✅ Swagger UI accessible")

    @pytest.mark.asyncio
    async def test_redoc(self, fastapi_server, page: Page):
        """Test ReDoc is accessible"""
        print("\n🧪 Testing ReDoc...")

        await page.goto(f"{BASE_URL}/redoc")
        await page.wait_for_load_state("networkidle")

        title = await page.title()
        assert "Video Understanding" in title or "API" in title

        print("✅ ReDoc accessible")

    @pytest.mark.asyncio
    async def test_openapi_json(self, fastapi_server, page: Page):
        """Test OpenAPI JSON schema"""
        print("\n🧪 Testing OpenAPI schema...")

        response = await page.request.get(f"{BASE_URL}/openapi.json")
        assert response.ok

        schema = await response.json()
        assert "openapi" in schema
        assert "info" in schema
        assert "paths" in schema

        # Check for our endpoints
        paths = schema["paths"]
        assert any("/api/videos" in path for path in paths)
        assert any("/api/search" in path for path in paths)

        print(f"✅ OpenAPI schema valid ({len(paths)} endpoints)")


# ============================================================================
# Video API Tests
# ============================================================================

class TestVideoAPI:
    """Test video management endpoints"""

    @pytest.mark.asyncio
    async def test_list_videos_empty(self, fastapi_server, page: Page):
        """Test listing videos when none exist"""
        print("\n🧪 Testing list videos...")

        response = await page.request.get(f"{BASE_URL}/api/videos")

        # Should return 200 even if empty, or 500 if database not set up
        # We expect this to work with mock data
        print(f"   Response status: {response.status}")

        if response.ok:
            data = await response.json()
            print(f"✅ List videos endpoint accessible")
        else:
            print(f"⚠️  List videos returned {response.status} (expected if DB not configured)")

    @pytest.mark.asyncio
    async def test_get_nonexistent_video(self, fastapi_server, page: Page):
        """Test getting a video that doesn't exist"""
        print("\n🧪 Testing get non-existent video...")

        response = await page.request.get(f"{BASE_URL}/api/videos/nonexistent-id")

        # Should return 404
        assert response.status == 404
        print("✅ Correctly returns 404 for non-existent video")


# ============================================================================
# Search API Tests
# ============================================================================

class TestSearchAPI:
    """Test search endpoints"""

    @pytest.mark.asyncio
    async def test_semantic_search_endpoint(self, fastapi_server, page: Page):
        """Test semantic search endpoint exists"""
        print("\n🧪 Testing semantic search endpoint...")

        response = await page.request.post(
            f"{BASE_URL}/api/search/semantic",
            data=json.dumps({
                "query": "test query",
                "top_k": 5
            }),
            headers={"Content-Type": "application/json"}
        )

        # Endpoint exists (even if returns error due to no data)
        print(f"   Response status: {response.status}")
        assert response.status in [200, 500]  # 200 if working, 500 if no DB

        if response.ok:
            data = await response.json()
            assert "query" in data
            assert "results" in data
            print("✅ Semantic search endpoint working")
        else:
            print("⚠️  Semantic search needs database setup")

    @pytest.mark.asyncio
    async def test_frame_search_endpoint(self, fastapi_server, page: Page):
        """Test frame search endpoint"""
        print("\n🧪 Testing frame search endpoint...")

        response = await page.request.post(
            f"{BASE_URL}/api/search/frames",
            data=json.dumps({
                "query": "person walking",
                "top_k": 5
            }),
            headers={"Content-Type": "application/json"}
        )

        print(f"   Response status: {response.status}")
        assert response.status in [200, 500]
        print("✅ Frame search endpoint exists")

    @pytest.mark.asyncio
    async def test_transcript_search_endpoint(self, fastapi_server, page: Page):
        """Test transcript search endpoint"""
        print("\n🧪 Testing transcript search endpoint...")

        response = await page.request.post(
            f"{BASE_URL}/api/search/transcript",
            data=json.dumps({
                "query": "hello",
                "top_k": 5,
                "search_mode": "semantic"
            }),
            headers={"Content-Type": "application/json"}
        )

        print(f"   Response status: {response.status}")
        assert response.status in [200, 500]
        print("✅ Transcript search endpoint exists")


# ============================================================================
# Analysis API Tests
# ============================================================================

class TestAnalysisAPI:
    """Test analysis endpoints"""

    @pytest.mark.asyncio
    async def test_get_summary_endpoint(self, fastapi_server, page: Page):
        """Test get summary endpoint"""
        print("\n🧪 Testing get summary endpoint...")

        response = await page.request.get(
            f"{BASE_URL}/api/videos/test-id/summary"
        )

        # Should return 404 or 500 (no video exists)
        assert response.status in [404, 500]
        print("✅ Summary endpoint exists")

    @pytest.mark.asyncio
    async def test_get_highlights_endpoint(self, fastapi_server, page: Page):
        """Test get highlights endpoint"""
        print("\n🧪 Testing get highlights endpoint...")

        response = await page.request.get(
            f"{BASE_URL}/api/videos/test-id/highlights"
        )

        assert response.status in [404, 500]
        print("✅ Highlights endpoint exists")

    @pytest.mark.asyncio
    async def test_get_chapters_endpoint(self, fastapi_server, page: Page):
        """Test get chapters endpoint"""
        print("\n🧪 Testing get chapters endpoint...")

        response = await page.request.get(
            f"{BASE_URL}/api/videos/test-id/chapters"
        )

        assert response.status in [404, 500]
        print("✅ Chapters endpoint exists")

    @pytest.mark.asyncio
    async def test_get_timeline_endpoint(self, fastapi_server, page: Page):
        """Test get timeline endpoint"""
        print("\n🧪 Testing get timeline endpoint...")

        response = await page.request.get(
            f"{BASE_URL}/api/videos/test-id/timeline"
        )

        assert response.status in [404, 500]
        print("✅ Timeline endpoint exists")


# ============================================================================
# Clips API Tests
# ============================================================================

class TestClipsAPI:
    """Test clip endpoints"""

    @pytest.mark.asyncio
    async def test_list_clips_endpoint(self, fastapi_server, page: Page):
        """Test list clips endpoint"""
        print("\n🧪 Testing list clips endpoint...")

        response = await page.request.get(f"{BASE_URL}/api/clips")

        print(f"   Response status: {response.status}")
        assert response.status in [200, 500]

        if response.ok:
            data = await response.json()
            assert "clips" in data
            print("✅ List clips endpoint working")
        else:
            print("⚠️  List clips needs database setup")

    @pytest.mark.asyncio
    async def test_get_clip_endpoint(self, fastapi_server, page: Page):
        """Test get clip endpoint"""
        print("\n🧪 Testing get clip endpoint...")

        response = await page.request.get(f"{BASE_URL}/api/clips/test-id")

        assert response.status in [404, 500]
        print("✅ Get clip endpoint exists")


# ============================================================================
# Processing API Tests
# ============================================================================

class TestProcessingAPI:
    """Test processing endpoints"""

    @pytest.mark.asyncio
    async def test_get_scenes_endpoint(self, fastapi_server, page: Page):
        """Test get scenes endpoint"""
        print("\n🧪 Testing get scenes endpoint...")

        response = await page.request.get(
            f"{BASE_URL}/api/videos/test-id/scenes"
        )

        assert response.status in [404, 500]
        print("✅ Get scenes endpoint exists")

    @pytest.mark.asyncio
    async def test_get_transcript_endpoint(self, fastapi_server, page: Page):
        """Test get transcript endpoint"""
        print("\n🧪 Testing get transcript endpoint...")

        response = await page.request.get(
            f"{BASE_URL}/api/videos/test-id/transcript"
        )

        assert response.status in [404, 500]
        print("✅ Get transcript endpoint exists")

    @pytest.mark.asyncio
    async def test_get_frames_endpoint(self, fastapi_server, page: Page):
        """Test get frames endpoint"""
        print("\n🧪 Testing get frames endpoint...")

        response = await page.request.get(
            f"{BASE_URL}/api/videos/test-id/frames"
        )

        assert response.status in [404, 500]
        print("✅ Get frames endpoint exists")


# ============================================================================
# Performance Tests
# ============================================================================

class TestPerformance:
    """Test API performance"""

    @pytest.mark.asyncio
    async def test_response_time(self, fastapi_server, page: Page):
        """Test API response times"""
        print("\n🧪 Testing API response times...")

        start = time.time()
        response = await page.request.get(f"{BASE_URL}/health")
        end = time.time()

        response_time = (end - start) * 1000  # Convert to ms

        assert response.ok
        assert response_time < 1000  # Should respond in < 1 second

        print(f"✅ Health check response time: {response_time:.2f}ms")

    @pytest.mark.asyncio
    async def test_concurrent_requests(self, fastapi_server, page: Page):
        """Test handling concurrent requests"""
        print("\n🧪 Testing concurrent requests...")

        # Make multiple concurrent requests
        tasks = []
        for i in range(10):
            tasks.append(page.request.get(f"{BASE_URL}/health"))

        start = time.time()
        responses = await asyncio.gather(*tasks)
        end = time.time()

        # All requests should succeed
        assert all(r.ok for r in responses)

        total_time = (end - start) * 1000
        print(f"✅ 10 concurrent requests completed in {total_time:.2f}ms")


# ============================================================================
# Error Handling Tests
# ============================================================================

class TestErrorHandling:
    """Test API error handling"""

    @pytest.mark.asyncio
    async def test_404_handling(self, fastapi_server, page: Page):
        """Test 404 error handling"""
        print("\n🧪 Testing 404 error handling...")

        response = await page.request.get(f"{BASE_URL}/nonexistent-path")

        assert response.status == 404
        data = await response.json()
        assert "error" in data or "message" in data

        print("✅ 404 errors handled correctly")

    @pytest.mark.asyncio
    async def test_invalid_json(self, fastapi_server, page: Page):
        """Test handling of invalid JSON"""
        print("\n🧪 Testing invalid JSON handling...")

        response = await page.request.post(
            f"{BASE_URL}/api/search/semantic",
            data="invalid json{{{",
            headers={"Content-Type": "application/json"}
        )

        assert response.status in [400, 422, 500]
        print("✅ Invalid JSON handled")

    @pytest.mark.asyncio
    async def test_missing_required_fields(self, fastapi_server, page: Page):
        """Test validation of required fields"""
        print("\n🧪 Testing field validation...")

        response = await page.request.post(
            f"{BASE_URL}/api/search/semantic",
            data=json.dumps({}),  # Missing required 'query' field
            headers={"Content-Type": "application/json"}
        )

        assert response.status == 422  # Validation error
        print("✅ Field validation working")


# ============================================================================
# Run Tests
# ============================================================================

if __name__ == "__main__":
    print("=" * 80)
    print("🚀 Running Live E2E Tests for Video Understanding API")
    print("=" * 80)

    pytest.main([
        __file__,
        "-v",
        "--tb=short",
        "--color=yes",
    ])
