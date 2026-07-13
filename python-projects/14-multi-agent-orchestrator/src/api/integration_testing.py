"""
Integration Testing and Validation API Endpoints
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field
from typing import Dict, List, Optional, Any
from datetime import datetime

from src.core.database import get_db_session
from src.services.integration_testing import (
    IntegrationTestingService,
    TestType,
    TestStatus,
    TestPriority
)


router = APIRouter()


# Request Models
class CreateTestSuiteRequest(BaseModel):
    """Request to create test suite"""
    suite_id: str
    name: str
    description: Optional[str] = None
    test_type: TestType = TestType.INTEGRATION
    tags: Optional[List[str]] = None
    metadata: Optional[Dict] = None


class AddTestCaseRequest(BaseModel):
    """Request to add test case"""
    suite_id: str
    test_id: str
    name: str
    description: Optional[str] = None
    priority: TestPriority = TestPriority.MEDIUM
    test_function: Optional[str] = None
    expected_result: Optional[Any] = None
    timeout_seconds: int = 30
    metadata: Optional[Dict] = None


class RunTestSuiteRequest(BaseModel):
    """Request to run test suite"""
    suite_id: str
    run_id: str
    parallel: bool = False
    fail_fast: bool = False


class ValidateEndpointsRequest(BaseModel):
    """Request to validate API endpoints"""
    validation_id: str
    endpoints: List[str]
    expected_status: int = 200


class PerformanceTestRequest(BaseModel):
    """Request to run performance test"""
    test_id: str
    target_endpoint: str
    duration_seconds: int = 60
    requests_per_second: int = 100


class LoadTestRequest(BaseModel):
    """Request to run load test"""
    test_id: str
    target_endpoint: str
    concurrent_users: int = 100
    ramp_up_seconds: int = 60


# Response Models
class TestSuiteResponse(BaseModel):
    """Test suite response"""
    suite_id: str
    name: str
    description: Optional[str]
    test_type: str
    tags: List[str]
    metadata: Dict
    test_cases: List[str]
    created_at: str
    updated_at: str
    last_run_at: Optional[str]
    total_runs: int
    pass_rate: float
    is_active: bool


# Endpoints
@router.post("/testing/suites", response_model=TestSuiteResponse)
async def create_test_suite(
    request: CreateTestSuiteRequest,
    session: Session = Depends(get_db_session)
):
    """
    Create a new test suite.

    Test suites organize related test cases for systematic testing.
    """
    try:
        result = IntegrationTestingService.create_test_suite(
            session=session,
            suite_id=request.suite_id,
            name=request.name,
            description=request.description,
            test_type=request.test_type,
            tags=request.tags,
            metadata=request.metadata
        )
        return TestSuiteResponse(**result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/testing/suites")
async def list_test_suites(
    session: Session = Depends(get_db_session)
):
    """List all test suites."""
    try:
        suites = list(IntegrationTestingService._test_suites.values())
        return {"suites": suites, "total": len(suites)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/testing/test-cases")
async def add_test_case(
    request: AddTestCaseRequest,
    session: Session = Depends(get_db_session)
):
    """
    Add a test case to a suite.

    Test cases define individual tests with expected results and validation.
    """
    try:
        result = IntegrationTestingService.add_test_case(
            session=session,
            suite_id=request.suite_id,
            test_id=request.test_id,
            name=request.name,
            description=request.description,
            priority=request.priority,
            test_function=request.test_function,
            expected_result=request.expected_result,
            timeout_seconds=request.timeout_seconds,
            metadata=request.metadata
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/testing/run")
async def run_test_suite(
    request: RunTestSuiteRequest,
    session: Session = Depends(get_db_session)
):
    """
    Execute a test suite.

    Runs all test cases in the suite and returns detailed results.
    Supports parallel execution and fail-fast mode.
    """
    try:
        result = IntegrationTestingService.run_test_suite(
            session=session,
            suite_id=request.suite_id,
            run_id=request.run_id,
            parallel=request.parallel,
            fail_fast=request.fail_fast
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/testing/validate-endpoints")
async def validate_api_endpoints(
    request: ValidateEndpointsRequest,
    session: Session = Depends(get_db_session)
):
    """
    Validate API endpoints.

    Checks that endpoints are accessible and return expected status codes.
    """
    try:
        result = IntegrationTestingService.validate_api_endpoints(
            session=session,
            validation_id=request.validation_id,
            endpoints=request.endpoints,
            expected_status=request.expected_status
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/testing/performance")
async def run_performance_test(
    request: PerformanceTestRequest,
    session: Session = Depends(get_db_session)
):
    """
    Run a performance test.

    Tests endpoint performance under sustained load with detailed metrics.
    Measures response times, throughput, and success rates.
    """
    try:
        result = IntegrationTestingService.run_performance_test(
            session=session,
            test_id=request.test_id,
            target_endpoint=request.target_endpoint,
            duration_seconds=request.duration_seconds,
            requests_per_second=request.requests_per_second
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/testing/load")
async def run_load_test(
    request: LoadTestRequest,
    session: Session = Depends(get_db_session)
):
    """
    Run a load test.

    Tests system behavior under high concurrent load.
    Simulates multiple users and measures resource utilization.
    """
    try:
        result = IntegrationTestingService.run_load_test(
            session=session,
            test_id=request.test_id,
            target_endpoint=request.target_endpoint,
            concurrent_users=request.concurrent_users,
            ramp_up_seconds=request.ramp_up_seconds
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/testing/coverage/{component}")
async def calculate_coverage(
    component: str,
    session: Session = Depends(get_db_session)
):
    """
    Calculate test coverage for a component.

    Returns line, branch, function, and statement coverage metrics.
    """
    try:
        result = IntegrationTestingService.calculate_coverage(
            session=session,
            component=component
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/testing/results")
async def get_test_results(
    suite_id: Optional[str] = None,
    status: Optional[TestStatus] = None,
    limit: int = 100,
    session: Session = Depends(get_db_session)
):
    """
    Get test results with filters.

    Filter by test suite, status, and limit results.
    """
    try:
        results = IntegrationTestingService.get_test_results(
            session=session,
            suite_id=suite_id,
            status=status,
            limit=limit
        )
        return {"results": results, "total": len(results)}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/testing/statistics")
async def get_statistics(
    session: Session = Depends(get_db_session)
):
    """
    Get comprehensive testing statistics.

    Returns:
    - Test suite and case counts
    - Test run metrics
    - Pass/fail rates
    - Coverage statistics
    - Recent activity
    """
    try:
        result = IntegrationTestingService.get_statistics(session=session)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
