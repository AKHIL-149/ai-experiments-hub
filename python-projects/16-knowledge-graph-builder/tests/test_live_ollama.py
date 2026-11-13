"""Needs a running Ollama with the configured model. Run with:  python3 -m pytest -m ollama -s"""
import pytest

from src.core.config import get_settings
from src.services.extraction import extract_chunk
from src.services.llm import get_llm, llm_status

pytestmark = pytest.mark.ollama

TEXT = "Nordwind Robotics was founded in 2012 by Ingrid Solheim. In June 2019, Nordwind Robotics acquired Tessel AI."


def test_real_model_extracts_checked_facts_with_dates():
    status = llm_status()
    if not status["ready"]:
        pytest.skip(status["detail"])
    r = extract_chunk(get_llm(get_settings()), TEXT, verify=True, gleaning_passes=1)
    found = {(f.subject, f.object) for f in r.facts}
    assert ("Nordwind Robotics", "Tessel AI") in found
    acq = next(f for f in r.facts if f.object == "Tessel AI")
    assert acq.valid_from.startswith("2019") and acq.verified
    assert all(f.evidence in TEXT for f in r.facts)
