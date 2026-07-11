"""
Testing Framework and Validation API

REST API endpoints for test management, execution, and validation.
"""

from typing import Optional, List, Any
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from src.core.database import get_db_session
from src.services.testing_framework import (
    TestingFramework,
    TestType,
    TestStatus,
    TestPriority,
    ValidationLevel
)


router = APIRouter()


# Request/Response Models
class CreateTestSuiteRequest(BaseModel):
    suite_name: str = Field(..., description="Test suite name")
    test_type: str = Field(..., description="Type of tests in suite")
    description: Optional[str] = Field(None, description="Suite description")
    tags: Optional[List[str]] = Field(None, description="Test tags")
    configuration: Optional[dict] = Field(None, description="Suite configuration")


class AddTestCaseRequest(BaseModel):
    test_name: str = Field(..., description="Test case name")
    test_function: str = Field(..., description="Test function reference")
    priority: str = Field(TestPriority.MEDIUM, description="Test priority")
    timeout_seconds: int = Field(30, description="Execution timeout")
    setup_function: Optional[str] = Field(None, description="Setup function")
    teardown_function: Optional[str] = Field(None, description="Teardown function")
    dependencies: Optional[List[str]] = Field(None, description="Test dependencies")
    description: Optional[str] = Field(None, description="Test description")
    expected_result: Optional[Any] = Field(None, description="Expected result")


class RunTestSuiteRequest(BaseModel):
    parallel: bool = Field(False, description="Run tests in parallel")
    fail_fast: bool = Field(False, description="Stop on first failure")
    filters: Optional[dict] = Field(None, description="Test filters")


class CreateValidationRuleRequest(BaseModel):
    rule_name: str = Field(..., description="Rule name")
    validation_type: str = Field(..., description="Type of validation")
    validation_function: str = Field(..., description="Validation function")
    level: str = Field(ValidationLevel.STANDARD, description="Validation strictness level")
    error_message: Optional[str] = Field(None, description="Custom error message")
    metadata: Optional[dict] = Field(None, description="Additional metadata")


class ValidateDataRequest(BaseModel):
    data: Any = Field(..., description="Data to validate")
    rule_ids: List[str] = Field(..., description="Validation rule IDs")


class CreateMockDataRequest(BaseModel):
    mock_name: str = Field(..., description="Mock data name")
    mock_type: str = Field(..., description="Type of mock data")
    data_schema: dict = Field(..., description="Data schema")
    sample_data: Optional[List[dict]] = Field(None, description="Optional sample data")


@router.post("/test-suites")
def create_test_suite(
    request: CreateTestSuiteRequest,
    session: Session = Depends(get_db_session)
):
    """
    Create test suite.

    Creates a test suite for organizing and running tests.
    """
    try:
        test_suite = TestingFramework.create_test_suite(
            session=session,
            suite_name=request.suite_name,
            test_type=request.test_type,
            description=request.description,
            tags=request.tags,
            configuration=request.configuration
        )

        return {
            "success": True,
            "test_suite": test_suite,
            "message": f"Test suite created: {test_suite['id']}"
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/test-suites/{suite_id}/tests")
def add_test_case(
    suite_id: str,
    request: AddTestCaseRequest,
    session: Session = Depends(get_db_session)
):
    """
    Add test case.

    Adds a test case to a test suite.
    """
    try:
        test_case = TestingFramework.add_test_case(
            session=session,
            suite_id=suite_id,
            test_name=request.test_name,
            test_function=request.test_function,
            priority=request.priority,
            timeout_seconds=request.timeout_seconds,
            setup_function=request.setup_function,
            teardown_function=request.teardown_function,
            dependencies=request.dependencies,
            description=request.description,
            expected_result=request.expected_result
        )

        return {
            "success": True,
            "test_case": test_case,
            "message": f"Test case added: {test_case['id']}"
        }

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/test-suites/{suite_id}/run")
def run_test_suite(
    suite_id: str,
    request: RunTestSuiteRequest,
    session: Session = Depends(get_db_session)
):
    """
    Run test suite.

    Executes all tests in the suite and returns results.
    """
    try:
        test_run = TestingFramework.run_test_suite(
            session=session,
            suite_id=suite_id,
            parallel=request.parallel,
            fail_fast=request.fail_fast,
            filters=request.filters
        )

        return {
            "success": True,
            "test_run": test_run,
            "message": f"Test run completed: {test_run['id']}"
        }

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/test-suites/{suite_id}/runs/{run_id}/coverage")
def generate_coverage_report(
    suite_id: str,
    run_id: str,
    session: Session = Depends(get_db_session)
):
    """
    Generate coverage report.

    Generates code coverage report for a test run.
    """
    try:
        coverage_report = TestingFramework.generate_coverage_report(
            session=session,
            suite_id=suite_id,
            run_id=run_id
        )

        return {
            "success": True,
            "coverage_report": coverage_report,
            "message": f"Coverage report generated: {coverage_report['id']}"
        }

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/validation-rules")
def create_validation_rule(
    request: CreateValidationRuleRequest,
    session: Session = Depends(get_db_session)
):
    """
    Create validation rule.

    Creates a validation rule for data validation.
    """
    try:
        validation_rule = TestingFramework.create_validation_rule(
            session=session,
            rule_name=request.rule_name,
            validation_type=request.validation_type,
            validation_function=request.validation_function,
            level=request.level,
            error_message=request.error_message,
            metadata=request.metadata
        )

        return {
            "success": True,
            "validation_rule": validation_rule,
            "message": f"Validation rule created: {validation_rule['id']}"
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/validate")
def validate_data(
    request: ValidateDataRequest,
    session: Session = Depends(get_db_session)
):
    """
    Validate data.

    Validates data against specified validation rules.
    """
    try:
        validation_result = TestingFramework.validate_data(
            session=session,
            data=request.data,
            rule_ids=request.rule_ids
        )

        return {
            "success": True,
            "validation": validation_result,
            "message": "Validation completed"
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/mock-data")
def create_mock_data(
    request: CreateMockDataRequest,
    session: Session = Depends(get_db_session)
):
    """
    Create mock data.

    Creates mock data for testing purposes.
    """
    try:
        mock_data = TestingFramework.create_mock_data(
            session=session,
            mock_name=request.mock_name,
            mock_type=request.mock_type,
            data_schema=request.data_schema,
            sample_data=request.sample_data
        )

        return {
            "success": True,
            "mock_data": mock_data,
            "message": f"Mock data created: {mock_data['id']}"
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/test-results")
def get_test_results(
    suite_id: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = 50,
    session: Session = Depends(get_db_session)
):
    """
    Get test results.

    Returns test execution results with optional filters.
    """
    try:
        result = TestingFramework.get_test_results(
            session=session,
            suite_id=suite_id,
            status=status,
            limit=limit
        )

        return {
            "success": True,
            **result
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/statistics")
def get_statistics(
    session: Session = Depends(get_db_session)
):
    """
    Get testing statistics.

    Returns aggregate testing metrics including test counts,
    pass rates, and coverage data.
    """
    try:
        stats = TestingFramework.get_statistics(session=session)

        return {
            "success": True,
            "statistics": stats
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/test-types")
def list_test_types():
    """
    List all test types.

    Returns all available test types.
    """
    return {
        "success": True,
        "test_types": [
            {"type": TestType.UNIT, "description": "Unit tests for individual components"},
            {"type": TestType.INTEGRATION, "description": "Integration tests for component interactions"},
            {"type": TestType.END_TO_END, "description": "End-to-end workflow tests"},
            {"type": TestType.PERFORMANCE, "description": "Performance and load tests"},
            {"type": TestType.REGRESSION, "description": "Regression tests for bug prevention"},
            {"type": TestType.SMOKE, "description": "Smoke tests for basic functionality"},
            {"type": TestType.SECURITY, "description": "Security and vulnerability tests"}
        ]
    }


@router.get("/test-statuses")
def list_test_statuses():
    """
    List all test statuses.

    Returns all possible test execution status values.
    """
    return {
        "success": True,
        "test_statuses": [
            {"status": TestStatus.PENDING, "description": "Test is pending execution"},
            {"status": TestStatus.RUNNING, "description": "Test is currently running"},
            {"status": TestStatus.PASSED, "description": "Test passed successfully"},
            {"status": TestStatus.FAILED, "description": "Test failed"},
            {"status": TestStatus.SKIPPED, "description": "Test was skipped"},
            {"status": TestStatus.ERROR, "description": "Test encountered an error"}
        ]
    }


@router.get("/test-priorities")
def list_test_priorities():
    """
    List all test priorities.

    Returns all available test priority levels.
    """
    return {
        "success": True,
        "test_priorities": [
            {"priority": TestPriority.CRITICAL, "description": "Critical tests - must pass"},
            {"priority": TestPriority.HIGH, "description": "High priority tests"},
            {"priority": TestPriority.MEDIUM, "description": "Medium priority tests"},
            {"priority": TestPriority.LOW, "description": "Low priority tests"}
        ]
    }


@router.get("/validation-levels")
def list_validation_levels():
    """
    List all validation levels.

    Returns all validation strictness levels.
    """
    return {
        "success": True,
        "validation_levels": [
            {"level": ValidationLevel.STRICT, "description": "Strict validation - no tolerance"},
            {"level": ValidationLevel.STANDARD, "description": "Standard validation"},
            {"level": ValidationLevel.RELAXED, "description": "Relaxed validation - more tolerant"}
        ]
    }
