"""Every task type the dashboard offers must map to an agent role that exists."""

import re
from pathlib import Path

import pytest

from src.models.agent import AgentRole
from src.services.task_service import TASK_TYPE_ROLES

DASHBOARD = Path(__file__).resolve().parents[2] / "templates" / "dashboard.html"

# "custom" has no obvious specialist: it is left unmapped on purpose and falls back to the Coordinator
# (so it is the one dropdown value that is allowed to resolve to COORDINATOR).
UNMAPPED_ON_PURPOSE = {"custom"}


def dashboard_task_types():
    html = DASHBOARD.read_text()
    select = re.search(r'<select[^>]*id="taskType"[^>]*>(.*?)</select>', html, re.S)
    assert select, "task type dropdown not found in dashboard.html"
    return [v for v in re.findall(r'<option value="([^"]*)"', select.group(1)) if v]


def test_dropdown_was_found_and_is_not_trivial():
    assert len(dashboard_task_types()) >= 10


@pytest.mark.parametrize("task_type", [t for t in dashboard_task_types() if t not in UNMAPPED_ON_PURPOSE])
def test_dashboard_task_type_has_an_agent_role(task_type):
    assert TASK_TYPE_ROLES.get(task_type) not in (None, AgentRole.COORDINATOR), task_type


@pytest.mark.parametrize("task_type", ["feature", "bugfix", "refactoring", "optimization", "deployment"])
def test_coding_work_goes_to_the_coder(task_type):
    assert TASK_TYPE_ROLES[task_type] == AgentRole.CODER


def test_every_mapped_role_is_a_real_role():
    assert all(isinstance(role, AgentRole) for role in TASK_TYPE_ROLES.values())
