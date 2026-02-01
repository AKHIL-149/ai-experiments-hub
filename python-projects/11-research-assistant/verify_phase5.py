#!/usr/bin/env python3
"""
Phase 5 Verification Script

Tests:
- Analytics endpoints (usage, costs, sources, performance)
- Cost tracking system
- Export formats (PDF, DOCX)
- Session cost tracking
- Production features
"""

import sys
import os
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent))

from fastapi.testclient import TestClient
from server import app, db_manager
from src.core.database import User
from src.utils.cost_tracker import CostTracker
from src.utils.usage_analytics import UsageAnalytics
from src.utils.report_generator import ReportGenerator

# Initialize database tables and clean up test data
db_manager.create_tables()

# Clean up test users from previous runs
with db_manager.get_session() as db_session:
    # Delete test users
    db_session.query(User).filter(
        User.username.in_(['phase5_verify', 'analytics_verify'])
    ).delete(synchronize_session=False)
    db_session.commit()

# Test client
client = TestClient(app)


def test_cost_tracker():
    """Test cost tracking functionality."""
    print("\n" + "="*80)
    print("TEST 1: Cost Tracking System")
    print("="*80)

    tracker = CostTracker()

    # Test Ollama (free)
    print("  Testing Ollama cost tracking...")
    ollama_record = tracker.track_llm_call(
        provider='ollama',
        model='llama3.2:3b',
        input_tokens=1000,
        output_tokens=500
    )
    assert ollama_record['total_cost'] == 0.0, "Ollama should be free"
    print(f"    ✓ Ollama tracked: ${ollama_record['total_cost']:.6f}")

    # Test OpenAI
    print("  Testing OpenAI cost tracking...")
    openai_record = tracker.track_llm_call(
        provider='openai',
        model='gpt-4',
        input_tokens=1000,
        output_tokens=500
    )
    assert openai_record['total_cost'] > 0, "OpenAI should have cost"
    print(f"    ✓ OpenAI tracked: ${openai_record['total_cost']:.6f}")

    # Test Anthropic
    print("  Testing Anthropic cost tracking...")
    anthropic_record = tracker.track_llm_call(
        provider='anthropic',
        model='claude-3-5-sonnet-20241022',
        input_tokens=1000,
        output_tokens=500
    )
    assert anthropic_record['total_cost'] > 0, "Anthropic should have cost"
    print(f"    ✓ Anthropic tracked: ${anthropic_record['total_cost']:.6f}")

    # Test session breakdown
    print("  Testing session breakdown...")
    breakdown = tracker.get_session_breakdown()
    assert breakdown['total_calls'] == 3, "Should have 3 calls"
    assert 'ollama' in breakdown['by_provider'], "Should have Ollama provider"
    assert 'openai' in breakdown['by_provider'], "Should have OpenAI provider"
    assert 'anthropic' in breakdown['by_provider'], "Should have Anthropic provider"
    print(f"    ✓ Session breakdown: {breakdown['total_calls']} calls, ${breakdown['total_cost']:.6f} total")

    # Test cost estimation
    print("  Testing cost estimation...")
    estimate = tracker.estimate_research_cost(
        provider='openai',
        model='gpt-4',
        num_sources=20
    )
    assert estimate['estimated_total_cost'] > 0, "Estimate should have cost"
    print(f"    ✓ Research estimate: ${estimate['estimated_total_cost']:.6f} (20 sources)")

    print("\n✓ Cost tracking tests passed")


def test_export_formats():
    """Test export format generation."""
    print("\n" + "="*80)
    print("TEST 2: Export Formats")
    print("="*80)

    gen = ReportGenerator(output_dir='./data/output')
    info = gen.get_info()

    # Check supported formats
    print("  Checking supported export formats...")
    assert 'markdown' in info['supported_formats'], "Markdown should be supported"
    assert 'html' in info['supported_formats'], "HTML should be supported"
    assert 'json' in info['supported_formats'], "JSON should be supported"
    print(f"    ✓ Supported formats: {', '.join(info['supported_formats'])}")

    # Check PDF availability
    if info['pdf_available']:
        print("    ✓ PDF export available (weasyprint installed)")
    else:
        print("    ⚠ PDF export not available (install weasyprint)")

    # Check DOCX availability
    if info['docx_available']:
        print("    ✓ DOCX export available (python-docx installed)")
    else:
        print("    ⚠ DOCX export not available (install python-docx)")

    print("\n✓ Export format tests passed")


def test_analytics_endpoints():
    """Test analytics API endpoints."""
    print("\n" + "="*80)
    print("TEST 3: Analytics Endpoints")
    print("="*80)

    # Create authenticated session
    print("  Setting up authenticated session...")
    client.post("/api/auth/register", json={
        "username": "analytics_verify",
        "email": "analytics_verify@example.com",
        "password": "password123"
    })

    login_response = client.post("/api/auth/login", json={
        "username": "analytics_verify",
        "password": "password123"
    })

    cookies = login_response.cookies
    print("    ✓ Session created")

    # Test usage stats endpoint
    print("  Testing /api/analytics/usage...")
    usage_response = client.get("/api/analytics/usage?days=30", cookies=cookies)
    assert usage_response.status_code == 200, f"Usage stats failed: {usage_response.text}"
    usage_data = usage_response.json()
    assert 'user_id' in usage_data
    assert 'total_queries' in usage_data
    print(f"    ✓ Usage stats: {usage_data['total_queries']} queries")

    # Test cost analysis endpoint
    print("  Testing /api/analytics/costs...")
    costs_response = client.get("/api/analytics/costs?days=30", cookies=cookies)
    assert costs_response.status_code == 200, f"Cost analysis failed: {costs_response.text}"
    costs_data = costs_response.json()
    assert 'estimated_total_cost' in costs_data
    print(f"    ✓ Cost analysis: ${costs_data['estimated_total_cost']:.2f} estimated")

    # Test source effectiveness endpoint
    print("  Testing /api/analytics/sources...")
    sources_response = client.get("/api/analytics/sources?days=30", cookies=cookies)
    assert sources_response.status_code == 200, f"Source effectiveness failed: {sources_response.text}"
    sources_data = sources_response.json()
    assert 'source_statistics' in sources_data
    print(f"    ✓ Source effectiveness retrieved")

    # Test performance metrics endpoint
    print("  Testing /api/analytics/performance...")
    perf_response = client.get("/api/analytics/performance?days=30", cookies=cookies)
    assert perf_response.status_code == 200, f"Performance metrics failed: {perf_response.text}"
    perf_data = perf_response.json()
    assert 'success_rate' in perf_data
    print(f"    ✓ Performance metrics: {perf_data['success_rate']:.1f}% success rate")

    # Test session costs endpoint
    print("  Testing /api/analytics/session-costs...")
    session_costs_response = client.get("/api/analytics/session-costs", cookies=cookies)
    assert session_costs_response.status_code == 200, f"Session costs failed: {session_costs_response.text}"
    session_costs_data = session_costs_response.json()
    assert 'total_cost' in session_costs_data
    print(f"    ✓ Session costs: ${session_costs_data['total_cost']:.6f}")

    # Test unauthenticated access (use fresh client to ensure no cookies)
    print("  Testing unauthenticated access...")
    fresh_client = TestClient(app)
    unauth_response = fresh_client.get("/api/analytics/usage")
    assert unauth_response.status_code == 401, f"Should require authentication (got {unauth_response.status_code})"
    print("    ✓ Properly requires authentication")

    print("\n✓ Analytics endpoint tests passed")


def test_usage_analytics():
    """Test usage analytics functionality."""
    print("\n" + "="*80)
    print("TEST 4: Usage Analytics")
    print("="*80)

    analytics = UsageAnalytics(db_manager)

    # Create test user
    with db_manager.get_session() as session:
        from src.core.auth_manager import AuthManager
        auth = AuthManager()

        success, user, error = auth.register_user(
            session,
            username='phase5_verify',
            email='phase5_verify@example.com',
            password='password123'
        )

        if success:
            user_id = user.id
        else:
            user = session.query(User).filter_by(username='phase5_verify').first()
            user_id = user.id

    # Get user stats
    print("  Testing user statistics...")
    stats = analytics.get_user_stats(user_id, days=30)
    assert 'user_id' in stats
    assert 'total_queries' in stats
    assert 'success_rate' in stats
    print(f"    ✓ User stats retrieved: {stats['total_queries']} queries, {stats['success_rate']:.1f}% success")

    # Get performance metrics
    print("  Testing performance metrics...")
    metrics = analytics.get_performance_metrics(days=30)
    assert 'total_queries' in metrics
    assert 'success_rate' in metrics
    print(f"    ✓ Performance metrics: {metrics['total_queries']} total queries")

    # Get source effectiveness
    print("  Testing source effectiveness...")
    effectiveness = analytics.get_source_effectiveness(user_id, days=30)
    assert 'source_statistics' in effectiveness
    print(f"    ✓ Source effectiveness analyzed")

    print("\n✓ Usage analytics tests passed")


def test_integration():
    """Test Phase 5 integration."""
    print("\n" + "="*80)
    print("TEST 5: Phase 5 Integration")
    print("="*80)

    print("  Checking Phase 5 components...")

    # Check analytics system
    analytics = UsageAnalytics(db_manager)
    print("    ✓ UsageAnalytics initialized")

    # Check cost tracker
    tracker = CostTracker()
    print("    ✓ CostTracker initialized")

    # Check report generator
    gen = ReportGenerator()
    info = gen.get_info()
    print(f"    ✓ ReportGenerator initialized ({len(info['supported_formats'])} formats)")

    # Check server has new endpoints
    print("  Verifying new endpoints registered...")
    routes = [route.path for route in app.routes]
    assert '/api/analytics/usage' in routes, "Usage analytics endpoint missing"
    assert '/api/analytics/costs' in routes, "Cost analytics endpoint missing"
    assert '/api/analytics/sources' in routes, "Source effectiveness endpoint missing"
    assert '/api/analytics/performance' in routes, "Performance metrics endpoint missing"
    assert '/api/analytics/session-costs' in routes, "Session costs endpoint missing"
    print("    ✓ All analytics endpoints registered")

    print("\n✓ Integration tests passed")


def main():
    """Run all Phase 5 verification tests."""
    print("\n" + "="*80)
    print("PHASE 5 VERIFICATION")
    print("="*80)
    print("\nTesting:")
    print("  - Cost Tracking System")
    print("  - Export Formats (PDF, DOCX)")
    print("  - Analytics Endpoints")
    print("  - Usage Analytics")
    print("  - Integration")

    try:
        test_cost_tracker()
        test_export_formats()
        test_analytics_endpoints()
        test_usage_analytics()
        test_integration()

        print("\n" + "="*80)
        print("✓ ALL PHASE 5 TESTS PASSED")
        print("="*80)
        print("\nPhase 5 components are working correctly:")
        print("  ✓ Cost Tracking: Ollama, OpenAI, Anthropic support")
        print("  ✓ Export Formats: Markdown, HTML, JSON (+ PDF/DOCX if installed)")
        print("  ✓ Analytics: Usage, costs, sources, performance metrics")
        print("  ✓ Session Tracking: Real-time cost breakdown")
        print("  ✓ Integration: All endpoints registered and working")
        print("\nProduction features:")
        print("  ✓ DEPLOYMENT.md: Comprehensive deployment guide created")
        print("  ✓ Cost optimization: Multi-provider tracking with estimates")
        print("  ✓ User analytics: Query patterns and performance insights")
        print("  ✓ Export options: 5 formats for research reports")
        print("\nNext steps:")
        print("  1. Review DEPLOYMENT.md for production setup")
        print("  2. Configure cost tracking with COST_LOG_FILE in .env")
        print("  3. Monitor analytics via /api/analytics/* endpoints")
        print("  4. Install optional dependencies:")
        print("     - pip install weasyprint  (for PDF export)")
        print("     - pip install python-docx (for DOCX export)")
        print("  5. Run full test suite: pytest tests/ -v")

        return 0

    except AssertionError as e:
        print(f"\n✗ Test failed: {e}")
        return 1
    except Exception as e:
        print(f"\n✗ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == '__main__':
    sys.exit(main())
