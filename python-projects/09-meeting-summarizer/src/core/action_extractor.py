"""Action Extractor - AI-powered extraction of action items from transcripts"""

import json
import logging
from typing import Dict, List, Optional
from datetime import datetime
from .llm_client import LLMClient

logger = logging.getLogger(__name__)


class ActionExtractor:
    """
    Extract action items, decisions, and follow-ups from meeting transcripts.

    Identifies:
    - Tasks and TODOs
    - Decisions made
    - Assignees/owners
    - Due dates
    - Priorities
    """

    def __init__(self, llm_client: LLMClient):
        """
        Initialize Action Extractor

        Args:
            llm_client: LLM client instance
        """
        self.llm_client = llm_client

    def extract_actions(self, transcript: str, summary: Optional[str] = None) -> Dict:
        """
        Extract all action items from transcript

        Args:
            transcript: Meeting transcript
            summary: Optional meeting summary (helps with context)

        Returns:
            dict with action items and metadata:
                {
                    "action_items": [
                        {
                            "id": int,
                            "description": str,
                            "assignee": str,
                            "due_date": str,
                            "priority": str,
                            "status": str,
                            "category": str
                        }
                    ],
                    "decisions": [
                        {
                            "id": int,
                            "decision": str,
                            "context": str,
                            "impact": str
                        }
                    ],
                    "follow_ups": [str],
                    "total_actions": int,
                    "tokens_used": dict
                }
        """
        logger.info("Extracting action items from transcript")

        # Prepare context
        context = ""
        if summary:
            context = f"Meeting Summary:\n{summary}\n\n"

        # Build prompt for action extraction
        system_prompt = """You are an expert at identifying action items from meeting transcripts.

Your task is to extract:
1. Action items (tasks, TODOs, commitments)
2. Decisions made
3. Follow-up items

Be thorough but only extract items that are explicitly mentioned or clearly implied."""

        user_prompt = f"""{context}Meeting Transcript:
{transcript}

Extract all action items, decisions, and follow-ups from this meeting.

Respond with valid JSON in this exact format:
{{
  "action_items": [
    {{
      "description": "Clear description of the action",
      "assignee": "Person responsible (or 'Unassigned' if not specified)",
      "due_date": "Due date if mentioned (or 'Not specified')",
      "priority": "high/medium/low based on context",
      "category": "Type of action (e.g., 'Development', 'Documentation', 'Meeting')"
    }}
  ],
  "decisions": [
    {{
      "decision": "Clear statement of what was decided",
      "context": "Brief context around the decision",
      "impact": "Expected impact (or 'Not specified')"
    }}
  ],
  "follow_ups": [
    "Follow-up item 1",
    "Follow-up item 2"
  ]
}}

Only include items that are actually present in the transcript. If no items of a certain type exist, use an empty array."""

        # Generate action extraction
        response = self.llm_client.generate(
            prompt=user_prompt,
            max_tokens=2500,
            temperature=0.2,  # Low temperature for structured extraction
            system_prompt=system_prompt
        )

        # Parse JSON response
        try:
            extracted = self._parse_json_response(response["text"])
        except Exception as e:
            logger.error(f"Failed to parse action extraction response: {str(e)}")
            # Return empty structure
            extracted = {
                "action_items": [],
                "decisions": [],
                "follow_ups": []
            }

        # Add IDs and status to action items
        for i, action in enumerate(extracted.get("action_items", []), 1):
            action["id"] = i
            action["status"] = "pending"

        # Add IDs to decisions
        for i, decision in enumerate(extracted.get("decisions", []), 1):
            decision["id"] = i

        # Compile final result
        result = {
            "action_items": extracted.get("action_items", []),
            "decisions": extracted.get("decisions", []),
            "follow_ups": extracted.get("follow_ups", []),
            "total_actions": len(extracted.get("action_items", [])),
            "tokens_used": response["tokens"]
        }

        logger.info(
            f"Extracted {result['total_actions']} actions, "
            f"{len(result['decisions'])} decisions, "
            f"{len(result['follow_ups'])} follow-ups"
        )

        return result

    def extract_assignees(self, transcript: str) -> List[str]:
        """
        Extract all participants/assignees mentioned in meeting

        Args:
            transcript: Meeting transcript

        Returns:
            List of participant names
        """
        system_prompt = """You are extracting participant names from a meeting transcript."""

        user_prompt = f"""List all people mentioned in this meeting transcript.

{transcript}

Provide ONLY the names, one per line, without any numbers, bullets, or additional text.
If a person is mentioned multiple times, list them only once."""

        response = self.llm_client.generate(
            prompt=user_prompt,
            max_tokens=500,
            temperature=0.1,
            system_prompt=system_prompt
        )

        # Parse names from response
        names = [
            line.strip()
            for line in response["text"].split("\n")
            if line.strip() and not line.strip().startswith(("#", "-", "*", "1", "2", "3"))
        ]

        return list(set(names))  # Remove duplicates

    def prioritize_actions(self, actions: List[Dict]) -> List[Dict]:
        """
        Re-analyze and prioritize action items

        Args:
            actions: List of action item dicts

        Returns:
            Sorted list by priority (high → low)
        """
        priority_order = {"high": 0, "medium": 1, "low": 2}

        return sorted(
            actions,
            key=lambda x: priority_order.get(x.get("priority", "medium").lower(), 1)
        )

    def generate_action_report(self, actions_data: Dict) -> str:
        """
        Generate human-readable action item report

        Args:
            actions_data: Result from extract_actions()

        Returns:
            Formatted markdown report
        """
        report = []

        # Header
        report.append("# Action Items & Decisions")
        report.append("")
        report.append(f"**Total Actions:** {actions_data['total_actions']}")
        report.append(f"**Decisions:** {len(actions_data['decisions'])}")
        report.append(f"**Follow-ups:** {len(actions_data['follow_ups'])}")
        report.append("")

        # Action Items
        if actions_data["action_items"]:
            report.append("## Action Items")
            report.append("")

            for action in actions_data["action_items"]:
                report.append(f"### {action['id']}. {action['description']}")
                report.append(f"- **Assignee:** {action.get('assignee', 'Unassigned')}")
                report.append(f"- **Due Date:** {action.get('due_date', 'Not specified')}")
                report.append(f"- **Priority:** {action.get('priority', 'medium')}")
                report.append(f"- **Category:** {action.get('category', 'General')}")
                report.append(f"- **Status:** {action.get('status', 'pending')}")
                report.append("")

        # Decisions
        if actions_data["decisions"]:
            report.append("## Decisions Made")
            report.append("")

            for decision in actions_data["decisions"]:
                report.append(f"### {decision['id']}. {decision['decision']}")
                report.append(f"**Context:** {decision.get('context', 'N/A')}")
                report.append(f"**Impact:** {decision.get('impact', 'Not specified')}")
                report.append("")

        # Follow-ups
        if actions_data["follow_ups"]:
            report.append("## Follow-up Items")
            report.append("")

            for i, item in enumerate(actions_data["follow_ups"], 1):
                report.append(f"{i}. {item}")

            report.append("")

        return "\n".join(report)

    def _parse_json_response(self, response_text: str) -> Dict:
        """
        Parse JSON from LLM response

        Handles cases where LLM includes markdown code blocks or extra text.

        Args:
            response_text: Raw response text

        Returns:
            Parsed JSON dict
        """
        # Remove markdown code blocks if present
        text = response_text.strip()

        if "```json" in text:
            # Extract JSON from code block
            start = text.find("```json") + 7
            end = text.find("```", start)
            text = text[start:end].strip()
        elif "```" in text:
            # Generic code block
            start = text.find("```") + 3
            end = text.find("```", start)
            text = text[start:end].strip()

        # Try to parse
        try:
            return json.loads(text)
        except json.JSONDecodeError as e:
            logger.warning(f"JSON parse error: {str(e)}")
            logger.debug(f"Response text: {text[:500]}")

            # Try to find JSON object in text
            start = text.find("{")
            end = text.rfind("}") + 1

            if start >= 0 and end > start:
                json_str = text[start:end]
                return json.loads(json_str)

            raise ValueError(f"Could not parse JSON from response: {text[:200]}")

    def validate_actions(self, actions: List[Dict]) -> Dict:
        """
        Validate extracted actions for completeness

        Args:
            actions: List of action item dicts

        Returns:
            Validation report:
                {
                    "valid": int,
                    "incomplete": int,
                    "issues": [str]
                }
        """
        valid = 0
        incomplete = 0
        issues = []

        for action in actions:
            has_description = bool(action.get("description", "").strip())
            has_assignee = action.get("assignee", "").lower() != "unassigned"

            if has_description and has_assignee:
                valid += 1
            else:
                incomplete += 1
                if not has_description:
                    issues.append(f"Action {action.get('id', '?')} missing description")
                if not has_assignee:
                    issues.append(f"Action {action.get('id', '?')} has no assignee")

        return {
            "valid": valid,
            "incomplete": incomplete,
            "issues": issues
        }
