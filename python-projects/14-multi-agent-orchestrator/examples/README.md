# Multi-Agent Orchestrator - Example Workflows

This directory contains example workflows that demonstrate the capabilities of the Multi-Agent Task Orchestrator.

## Available Workflows

### 1. Code Review Workflows

**File**: `workflows/code_review_workflow.py`

- **Full Code Review**: Comprehensive code analysis with security scanning, performance analysis, and refactoring suggestions
- **Quick Code Review**: Fast feedback on critical issues

**Use Cases**:
- Pre-commit code quality checks
- Pull request reviews
- Security audits
- Performance optimization

**Agents Used**: Code, Research, Data Analyst, Writer

### 2. Data Analysis Workflows

**File**: `workflows/data_analysis_workflow.py`

- **Full Data Analysis**: Complete data analysis pipeline with validation, EDA, pattern detection, and reporting
- **Quick Data Summary**: Fast statistical summary
- **Predictive Analysis**: Machine learning model development and evaluation

**Use Cases**:
- Business intelligence reports
- Data quality assessment
- Predictive modeling
- Statistical analysis

**Agents Used**: Data Analyst, Research, Code, Writer

### 3. Content Generation Workflows

**File**: `workflows/content_generation_workflow.py`

- **Blog Post Generation**: Research-backed blog posts with SEO optimization
- **Technical Documentation**: Comprehensive API and developer documentation
- **Social Media Content**: Multi-platform social media content calendar

**Use Cases**:
- Content marketing
- Developer documentation
- Social media campaigns
- Technical writing

**Agents Used**: Research, Planner, Writer, Code

## Using Workflows

### Method 1: Via API

```bash
# Submit a workflow using the API
curl -X POST http://localhost:8001/api/workflow-engine/workflows \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Code Review Workflow",
    "description": "Automated code review",
    "steps": [...]
  }'
```

### Method 2: Via Python

```python
import sys
sys.path.append('/path/to/multi-agent-orchestrator')

from examples.workflows.code_review_workflow import create_code_review_workflow
from src.services.workflow_engine import WorkflowEngine
from src.core.database import get_db_session

# Create workflow configuration
workflow_config = create_code_review_workflow()

# Execute workflow
with get_db_session() as session:
    workflow = WorkflowEngine.create_workflow(
        session=session,
        name=workflow_config["name"],
        description=workflow_config["description"],
        steps=workflow_config["steps"],
        metadata=workflow_config["metadata"]
    )

    # Start execution
    execution = WorkflowEngine.execute_workflow(
        session=session,
        workflow_id=workflow["workflow_id"]
    )

    print(f"Workflow started: {execution['workflow_id']}")
```

### Method 3: Using the Helper Script

```python
python examples/run_workflow.py --workflow code_review --input code_file.py
python examples/run_workflow.py --workflow data_analysis --input data.csv
python examples/run_workflow.py --workflow blog_post --topic "AI Trends 2026"
```

## Workflow Structure

All workflows follow this structure:

```python
{
    "name": "Workflow Name",
    "description": "What the workflow does",
    "workflow_type": "custom",  # or "simple", "default"
    "steps": [
        {
            "step_name": "unique_step_id",
            "step_type": "agent",  # or "approval_gate", "decision", "parallel"
            "agent_role": "code",  # or "research", "data_analyst", "writer", "planner"
            "config": {
                "task": "What this step should do",
                # ... step-specific configuration
            },
            "dependencies": []  # List of step names this depends on
        }
    ],
    "metadata": {
        "category": "workflow_category",
        "estimated_duration_minutes": 20,
        "required_agents": ["agent1", "agent2"],
        "tags": ["tag1", "tag2"]
    }
}
```

## Step Types

### Agent Step
Executes a task using a specific agent role:
- `code`: Code generation, analysis, refactoring
- `research`: Information gathering, trend analysis
- `data_analyst`: Data processing, statistical analysis
- `writer`: Content creation, documentation
- `planner`: Task planning, organization

### Approval Gate
Pauses workflow for human review:
```python
{
    "step_type": "approval_gate",
    "config": {
        "approval_type": "review_acceptance",
        "timeout_hours": 24,
        "reviewers": ["user@example.com"]
    }
}
```

### Decision Step (Future)
Branches workflow based on conditions

### Parallel Step (Future)
Executes multiple sub-steps in parallel

## Customizing Workflows

### 1. Modify Existing Workflows

```python
from examples.workflows.code_review_workflow import create_code_review_workflow

# Get base workflow
workflow = create_code_review_workflow()

# Add custom step
workflow["steps"].append({
    "step_name": "custom_analysis",
    "step_type": "agent",
    "agent_role": "code",
    "config": {
        "task": "Custom analysis task"
    },
    "dependencies": ["analyze_code_quality"]
})
```

### 2. Create New Workflows

```python
def create_custom_workflow():
    return {
        "name": "My Custom Workflow",
        "description": "Custom task automation",
        "workflow_type": "custom",
        "steps": [
            # Define your steps here
        ],
        "metadata": {
            "category": "custom",
            "estimated_duration_minutes": 10,
            "required_agents": ["research", "writer"],
            "tags": ["custom"]
        }
    }
```

## Monitoring Workflow Execution

### Via API

```bash
# Get workflow status
curl http://localhost:8001/api/workflow-engine/workflows/{workflow_id}

# Get step status
curl http://localhost:8001/api/workflow-engine/workflows/{workflow_id}/steps
```

### Via WebSocket

```javascript
const ws = new WebSocket('ws://localhost:8001/ws/workflows/{workflow_id}');

ws.onmessage = (event) => {
    const update = JSON.parse(event.data);
    console.log('Workflow update:', update);
};
```

## Performance Tips

1. **Parallel Execution**: Steps without dependencies run in parallel automatically
2. **Agent Selection**: Use appropriate agents for each task type
3. **Step Granularity**: Balance between too many small steps and too few large steps
4. **Timeouts**: Set reasonable timeouts to prevent hanging workflows
5. **Caching**: Reuse common research results across similar workflows

## Common Patterns

### Sequential Processing
```python
steps = [
    {"step_name": "step1", "dependencies": []},
    {"step_name": "step2", "dependencies": ["step1"]},
    {"step_name": "step3", "dependencies": ["step2"]}
]
```

### Fan-Out (Parallel Processing)
```python
steps = [
    {"step_name": "prepare", "dependencies": []},
    {"step_name": "task1", "dependencies": ["prepare"]},
    {"step_name": "task2", "dependencies": ["prepare"]},
    {"step_name": "task3", "dependencies": ["prepare"]},
    {"step_name": "combine", "dependencies": ["task1", "task2", "task3"]}
]
```

### Conditional with Human Approval
```python
steps = [
    {"step_name": "analysis", "dependencies": []},
    {"step_name": "approval", "step_type": "approval_gate", "dependencies": ["analysis"]},
    {"step_name": "execution", "dependencies": ["approval"]}
]
```

## Troubleshooting

### Workflow Stuck
- Check step dependencies for circular references
- Verify all required agents are available
- Check approval gate timeouts

### Poor Quality Results
- Refine task descriptions to be more specific
- Break complex steps into smaller sub-steps
- Use appropriate agent roles for each task

### Long Execution Times
- Identify bottleneck steps
- Consider parallel execution where possible
- Set appropriate timeouts

## Next Steps

1. Try running the example workflows
2. Modify them for your use cases
3. Create custom workflows
4. Share your workflows with the community

## Support

For questions or issues:
- Check the main [README.md](../README.md)
- Review [STARTUP.md](../STARTUP.md) for setup help
- See API documentation at http://localhost:8001/docs
