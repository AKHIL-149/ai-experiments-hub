"""Action Extractor - AI-powered extraction of action items from transcripts"""

import json
import logging
import re
from typing import Dict, List, Optional
from datetime import datetime
from .llm_client import LLMClient

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are an expert at identifying action items from meeting transcripts.

Your task is to extract:
1. Action items (tasks, TODOs, commitments)
2. Decisions made
3. Follow-up items

Be thorough but only extract items that are explicitly mentioned or clearly implied.
If the recording is not a meeting (a story, lecture or monologue), there are usually no action items or decisions - return empty arrays rather than inventing some."""

# Text from the prompt's own example that models sometimes hand back when there is nothing to report
PLACEHOLDERS = {
    "Clear description of the action",
    "Clear statement of what was decided",
    "Follow-up item 1",
    "Follow-up item 2",
}


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

    def __init__(self, llm_client: LLMClient, chunk_size_words: int = 3000):
        """
        Initialize Action Extractor

        Args:
            llm_client: LLM client instance
            chunk_size_words: Most transcript words sent to the model in one request
        """
        self.llm_client = llm_client
        self.chunk_size_words = chunk_size_words

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

        if not transcript or not transcript.strip():
            raise ValueError("There is no transcript to extract action items from")

        # Only as much transcript as one prompt can hold goes in at a time - a model that is
        # handed more silently reads just part of it. Longer meetings are extracted a chunk
        # at a time and merged.
        chunks = self._split_transcript(transcript)
        tokens_used = {"prompt": 0, "completion": 0, "total": 0}
        merged = {"action_items": [], "decisions": [], "follow_ups": []}
        parse_failures = 0
        truncated = False

        for index, chunk in enumerate(chunks):
            # The summary is context for a single-pass extraction; with several chunks it
            # would describe the wrong part of the meeting for most of them.
            context = f"Meeting Summary:\n{summary}\n\n" if (summary and len(chunks) == 1) else ""
            response = self.llm_client.generate(
                prompt=self._build_prompt(chunk, context),
                max_tokens=2500,
                temperature=0.0,          # extraction should not vary from run to run
                system_prompt=SYSTEM_PROMPT,
                json_mode=True
            )

            for key in tokens_used:
                tokens_used[key] += (response.get("tokens") or {}).get(key, 0)
            truncated = truncated or bool(response.get("truncated"))

            try:
                extracted = self._normalize(self._parse_json_response(response["text"]))
            except Exception as e:
                parse_failures += 1
                logger.error(f"Failed to parse action extraction response (part {index + 1}): {e}")
                continue

            for key in merged:
                merged[key].extend(extracted[key])

        # Same item found in two chunks (or repeated by the model) is one item
        merged["action_items"] = self._dedupe(merged["action_items"], "description")
        merged["decisions"] = self._dedupe(merged["decisions"], "decision")
        merged["follow_ups"] = self._dedupe_text(merged["follow_ups"])

        # Add IDs and status to action items
        for i, action in enumerate(merged["action_items"], 1):
            action["id"] = i
            action["status"] = "pending"

        # Add IDs to decisions
        for i, decision in enumerate(merged["decisions"], 1):
            decision["id"] = i

        # Compile final result
        result = {
            "action_items": merged["action_items"],
            "decisions": merged["decisions"],
            "follow_ups": merged["follow_ups"],
            "total_actions": len(merged["action_items"]),
            "tokens_used": tokens_used,
            # Zero results because the model's answer could not be read is not the same as
            # "nothing was decided" - say so instead of reporting an empty meeting.
            "parse_failed": parse_failures == len(chunks),
            "truncated": truncated
        }

        logger.info(
            f"Extracted {result['total_actions']} actions, "
            f"{len(result['decisions'])} decisions, "
            f"{len(result['follow_ups'])} follow-ups"
        )

        return result

    # ------------------------------------------------------------------ helpers

    def _split_transcript(self, transcript: str) -> List[str]:
        """Chunks of at most chunk_size_words words, split between lines"""
        chunks, current, size = [], [], 0
        for line in transcript.split("\n"):
            words = line.split()
            if not words:
                continue
            if len(words) > self.chunk_size_words:
                if current:
                    chunks.append("\n".join(current))
                    current, size = [], 0
                chunks.extend(" ".join(words[i:i + self.chunk_size_words])
                              for i in range(0, len(words), self.chunk_size_words))
                continue
            if size + len(words) > self.chunk_size_words:
                chunks.append("\n".join(current))
                current, size = [], 0
            current.append(line.strip())
            size += len(words)
        if current:
            chunks.append("\n".join(current))
        return chunks

    @staticmethod
    def _build_prompt(transcript: str, context: str) -> str:
        return f"""{context}Meeting Transcript:
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

Only include items that are actually present in the transcript. Do not invent owners, dates or decisions. If no items of a certain type exist, use an empty array."""

    @staticmethod
    def _text(value, default: str) -> str:
        """A field as clean text; null / numbers / empty become the default"""
        if value is None:
            return default
        text = str(value).strip()
        return text if text else default

    def _normalize(self, extracted) -> Dict:
        """
        Whatever the model returned, as {"action_items": [dict], "decisions": [dict],
        "follow_ups": [str]} with every field present. Models return strings where
        objects were asked for, null for missing owners, a priority of "urgent", or
        simply the example text from the prompt - none of which should crash a report.
        """
        if not isinstance(extracted, dict):
            raise ValueError("The extraction response is not a JSON object")

        def as_list(value):
            return value if isinstance(value, list) else []

        actions = []
        for item in as_list(extracted.get("action_items")):
            if isinstance(item, str):
                item = {"description": item}
            if not isinstance(item, dict):
                continue
            description = self._text(item.get("description"), "")
            if not description or description in PLACEHOLDERS:
                continue
            priority = self._text(item.get("priority"), "medium").lower()
            actions.append({
                "description": description,
                "assignee": self._text(item.get("assignee"), "Unassigned"),
                "due_date": self._text(item.get("due_date"), "Not specified"),
                "priority": priority if priority in ("high", "medium", "low") else "medium",
                "category": self._text(item.get("category"), "General"),
            })

        decisions = []
        for item in as_list(extracted.get("decisions")):
            if isinstance(item, str):
                item = {"decision": item}
            if not isinstance(item, dict):
                continue
            decision = self._text(item.get("decision"), "")
            if not decision or decision in PLACEHOLDERS:
                continue
            decisions.append({
                "decision": decision,
                "context": self._text(item.get("context"), "Not specified"),
                "impact": self._text(item.get("impact"), "Not specified"),
            })

        follow_ups = []
        for item in as_list(extracted.get("follow_ups")):
            text = self._text(item if not isinstance(item, dict) else item.get("description") or item.get("item"), "")
            if text and text not in PLACEHOLDERS:
                follow_ups.append(text)

        return {"action_items": actions, "decisions": decisions, "follow_ups": follow_ups}

    @staticmethod
    def _key(text: str) -> str:
        return re.sub(r'\W+', ' ', text.lower()).strip()

    def _dedupe(self, items: List[Dict], field: str) -> List[Dict]:
        seen, unique = set(), []
        for item in items:
            key = self._key(item[field])
            if key not in seen:
                seen.add(key)
                unique.append(item)
        return unique

    def _dedupe_text(self, items: List[str]) -> List[str]:
        seen, unique = set(), []
        for item in items:
            key = self._key(item)
            if key not in seen:
                seen.add(key)
                unique.append(item)
        return unique

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
            key=lambda x: priority_order.get(str(x.get("priority") or "medium").lower(), 1)
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
        report.append(f"**Total Actions:** {actions_data.get('total_actions', 0)}")
        report.append(f"**Decisions:** {len(actions_data.get('decisions') or [])}")
        report.append(f"**Follow-ups:** {len(actions_data.get('follow_ups') or [])}")
        report.append("")

        if actions_data.get("parse_failed"):
            report.append("> **Note:** the model's answer could not be read, so these results may be incomplete. Try again.")
            report.append("")

        # Action Items
        if actions_data.get("action_items"):
            report.append("## Action Items")
            report.append("")

            for action in actions_data["action_items"]:
                report.append(f"### {action.get('id', '?')}. {action.get('description', 'N/A')}")
                report.append(f"- **Assignee:** {action.get('assignee', 'Unassigned')}")
                report.append(f"- **Due Date:** {action.get('due_date', 'Not specified')}")
                report.append(f"- **Priority:** {action.get('priority', 'medium')}")
                report.append(f"- **Category:** {action.get('category', 'General')}")
                report.append(f"- **Status:** {action.get('status', 'pending')}")
                report.append("")

        # Decisions
        if actions_data.get("decisions"):
            report.append("## Decisions Made")
            report.append("")

            for decision in actions_data["decisions"]:
                report.append(f"### {decision.get('id', '?')}. {decision.get('decision', 'N/A')}")
                report.append(f"**Context:** {decision.get('context', 'N/A')}")
                report.append(f"**Impact:** {decision.get('impact', 'Not specified')}")
                report.append("")

        # Follow-ups
        if actions_data.get("follow_ups"):
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
            has_description = bool(str(action.get("description") or "").strip())
            has_assignee = str(action.get("assignee") or "unassigned").lower() != "unassigned"

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
