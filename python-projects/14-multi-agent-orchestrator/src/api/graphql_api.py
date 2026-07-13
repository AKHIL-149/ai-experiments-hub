"""
GraphQL API Endpoints
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field
from typing import Dict, List, Optional, Any
from datetime import datetime

from src.core.database import get_db_session
from src.services.graphql_api import GraphQLAPIService


router = APIRouter()


# Request Models
class GraphQLQueryRequest(BaseModel):
    """GraphQL query request"""
    query: str = Field(..., min_length=1)
    variables: Optional[Dict] = None
    operationName: Optional[str] = None


class ValidateQueryRequest(BaseModel):
    """Validate query request"""
    query: str = Field(..., min_length=1)


# Response Models
class GraphQLResponse(BaseModel):
    """GraphQL response"""
    data: Optional[Dict]
    errors: Optional[List[Dict]]
    extensions: Optional[Dict]


class SchemaResponse(BaseModel):
    """Schema response"""
    schema: str
    types: List[str]
    queries: List[str]
    mutations: List[str]
    subscriptions: List[str]
    directives: List[str]


# Endpoints
@router.post("/graphql", response_model=GraphQLResponse)
async def execute_graphql_query(
    request: GraphQLQueryRequest,
    session: Session = Depends(get_db_session)
):
    """
    Execute a GraphQL query.

    Supports queries, mutations, and subscriptions with variables and operation names.
    Returns data and errors in standard GraphQL response format.
    """
    try:
        result = GraphQLAPIService.execute_query(
            session=session,
            query=request.query,
            variables=request.variables,
            operation_name=request.operationName
        )
        return GraphQLResponse(**result)
    except Exception as e:
        return GraphQLResponse(
            data=None,
            errors=[{"message": str(e)}],
            extensions=None
        )


@router.get("/graphql/schema", response_model=SchemaResponse)
async def get_graphql_schema(
    session: Session = Depends(get_db_session)
):
    """
    Get the complete GraphQL schema.

    Returns the schema in SDL (Schema Definition Language) format along with
    lists of all types, queries, mutations, subscriptions, and directives.
    """
    try:
        result = GraphQLAPIService.get_schema(session=session)
        return SchemaResponse(**result)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/graphql/initialize")
async def initialize_schema(
    session: Session = Depends(get_db_session)
):
    """
    Initialize the default GraphQL schema.

    Sets up base types (Task, Workflow, Agent) and default queries and mutations.
    """
    try:
        result = GraphQLAPIService.initialize_schema(session=session)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/graphql/introspect")
async def introspect_schema(
    session: Session = Depends(get_db_session)
):
    """
    Perform GraphQL introspection.

    Returns the complete schema metadata including all types, fields, and their relationships.
    Used by GraphQL clients and tools like GraphiQL and Apollo DevTools.
    """
    try:
        result = GraphQLAPIService.introspect(session=session)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/graphql/validate")
async def validate_query(
    request: ValidateQueryRequest,
    session: Session = Depends(get_db_session)
):
    """
    Validate a GraphQL query.

    Checks query syntax, balanced braces, and basic structure without executing.
    """
    try:
        result = GraphQLAPIService.validate_query(
            session=session,
            query=request.query
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/graphql/analyze-complexity")
async def analyze_query_complexity(
    request: ValidateQueryRequest,
    session: Session = Depends(get_db_session)
):
    """
    Analyze query complexity.

    Calculates complexity score based on query depth and estimated field count.
    Helps identify potentially expensive queries.
    """
    try:
        result = GraphQLAPIService.analyze_query_complexity(
            session=session,
            query=request.query
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/graphql/statistics")
async def get_query_statistics(
    limit: int = 100,
    session: Session = Depends(get_db_session)
):
    """
    Get query execution statistics.

    Returns:
    - Total queries executed
    - Average execution time
    - Breakdown by operation type
    - Slowest queries
    """
    try:
        result = GraphQLAPIService.get_query_statistics(
            session=session,
            limit=limit
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/graphql/stats")
async def get_graphql_statistics(
    session: Session = Depends(get_db_session)
):
    """
    Get comprehensive GraphQL API statistics.

    Returns:
    - Schema statistics (types, queries, mutations count)
    - Query execution statistics
    - Schema version history
    """
    try:
        result = GraphQLAPIService.get_statistics(session=session)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# GraphiQL playground endpoint
@router.get("/graphql/playground")
async def graphql_playground():
    """
    GraphQL Playground interface.

    Returns an HTML page with GraphiQL for interactive query testing.
    """
    html = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>GraphQL Playground</title>
        <link rel="stylesheet" href="https://unpkg.com/graphiql/graphiql.min.css" />
    </head>
    <body style="margin: 0;">
        <div id="graphiql" style="height: 100vh;"></div>

        <script
            crossorigin
            src="https://unpkg.com/react/umd/react.production.min.js"
        ></script>
        <script
            crossorigin
            src="https://unpkg.com/react-dom/umd/react-dom.production.min.js"
        ></script>
        <script
            crossorigin
            src="https://unpkg.com/graphiql/graphiql.min.js"
        ></script>

        <script>
            const fetcher = GraphiQL.createFetcher({
                url: '/api/graphql',
            });

            ReactDOM.render(
                React.createElement(GraphiQL, { fetcher: fetcher }),
                document.getElementById('graphiql'),
            );
        </script>
    </body>
    </html>
    """
    from fastapi.responses import HTMLResponse
    return HTMLResponse(content=html)
