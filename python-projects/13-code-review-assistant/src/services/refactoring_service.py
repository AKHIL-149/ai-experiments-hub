"""
Refactoring Service

Manages refactoring suggestions including:
- Creating refactoring suggestions from AI analysis
- Storing and retrieving refactorings
- Generating diffs for proposed changes
- Managing refactoring status (suggested/accepted/rejected/applied)
"""

from typing import Optional, List, Tuple, Dict, Any
from sqlalchemy.orm import Session
import difflib
from datetime import datetime

from ..core.database import (
    Refactoring,
    RefactoringStatus,
    Issue,
    CodeFile
)
from .ai_analysis_service import AIAnalysisService


class RefactoringService:
    """Service for managing code refactorings."""

    def __init__(self, db: Session, ai_service: Optional[AIAnalysisService] = None):
        """
        Initialize refactoring service.

        Args:
            db: Database session
            ai_service: Optional AI analysis service for generating suggestions
        """
        self.db = db
        self.ai_service = ai_service

    def create_refactoring(
        self,
        issue_id: str,
        code_file_id: str,
        refactoring_type: str,
        original_code: str,
        refactored_code: str,
        explanation: str,
        benefits: Optional[str] = None,
        confidence: float = 0.5
    ) -> Tuple[bool, Optional[Refactoring], Optional[str]]:
        """
        Create a new refactoring suggestion.

        Args:
            issue_id: Associated issue ID
            code_file_id: Code file ID
            refactoring_type: Type of refactoring (extract_method, simplify, etc)
            original_code: Original code snippet
            refactored_code: Refactored code snippet
            explanation: Explanation of the refactoring
            benefits: Benefits of applying this refactoring
            confidence: Confidence score (0.0-1.0)

        Returns:
            Tuple of (success, refactoring, error_message)
        """
        try:
            # Generate diff
            diff = self._generate_diff(original_code, refactored_code)

            # Create refactoring
            refactoring = Refactoring(
                issue_id=issue_id,
                code_file_id=code_file_id,
                refactoring_type=refactoring_type,
                original_code=original_code,
                refactored_code=refactored_code,
                diff=diff,
                explanation=explanation,
                benefits=benefits,
                confidence=confidence,
                status=RefactoringStatus.SUGGESTED
            )

            self.db.add(refactoring)
            self.db.commit()
            self.db.refresh(refactoring)

            return True, refactoring, None

        except Exception as e:
            self.db.rollback()
            return False, None, str(e)

    def generate_refactoring_from_issue(
        self,
        issue_id: str,
        code_file_id: str,
        code_snippet: str,
        language: str = "python"
    ) -> Tuple[bool, Optional[Refactoring], Optional[str]]:
        """
        Generate refactoring suggestion using AI for an issue.

        Args:
            issue_id: Issue ID
            code_file_id: Code file ID
            code_snippet: Code snippet to refactor
            language: Programming language

        Returns:
            Tuple of (success, refactoring, error_message)
        """
        if not self.ai_service:
            return False, None, "AI service not configured"

        try:
            # Get issue details
            issue = self.db.query(Issue).filter(Issue.id == issue_id).first()
            if not issue:
                return False, None, f"Issue {issue_id} not found"

            # Determine refactoring type from issue category
            refactoring_type = self._get_refactoring_type(
                issue.category,
                issue.title
            )

            # Generate refactoring suggestion using AI
            refactoring_result = self.ai_service.suggest_refactoring(
                code_snippet,
                issue_type=issue.category,
                language=language
            )

            if refactoring_result.get("refactored_code"):
                return self.create_refactoring(
                    issue_id=issue_id,
                    code_file_id=code_file_id,
                    refactoring_type=refactoring_type,
                    original_code=code_snippet,
                    refactored_code=refactoring_result["refactored_code"],
                    explanation=refactoring_result.get("explanation", ""),
                    benefits=self._extract_benefits(
                        refactoring_result.get("refactoring_suggestion", "")
                    ),
                    confidence=refactoring_result.get("confidence_score", 0.5)
                )
            else:
                return False, None, "AI failed to generate refactoring"

        except Exception as e:
            return False, None, str(e)

    def get_refactoring(
        self,
        refactoring_id: str
    ) -> Tuple[bool, Optional[Refactoring], Optional[str]]:
        """
        Get refactoring by ID.

        Args:
            refactoring_id: Refactoring ID

        Returns:
            Tuple of (success, refactoring, error_message)
        """
        try:
            refactoring = self.db.query(Refactoring).filter(
                Refactoring.id == refactoring_id
            ).first()

            if not refactoring:
                return False, None, f"Refactoring {refactoring_id} not found"

            return True, refactoring, None

        except Exception as e:
            return False, None, str(e)

    def get_issue_refactorings(
        self,
        issue_id: str
    ) -> Tuple[bool, List[Refactoring], Optional[str]]:
        """
        Get all refactorings for an issue.

        Args:
            issue_id: Issue ID

        Returns:
            Tuple of (success, refactorings_list, error_message)
        """
        try:
            refactorings = self.db.query(Refactoring).filter(
                Refactoring.issue_id == issue_id
            ).all()

            return True, refactorings, None

        except Exception as e:
            return False, [], str(e)

    def get_file_refactorings(
        self,
        code_file_id: str,
        status: Optional[RefactoringStatus] = None
    ) -> Tuple[bool, List[Refactoring], Optional[str]]:
        """
        Get all refactorings for a code file.

        Args:
            code_file_id: Code file ID
            status: Optional status filter

        Returns:
            Tuple of (success, refactorings_list, error_message)
        """
        try:
            query = self.db.query(Refactoring).filter(
                Refactoring.code_file_id == code_file_id
            )

            if status:
                query = query.filter(Refactoring.status == status)

            refactorings = query.all()
            return True, refactorings, None

        except Exception as e:
            return False, [], str(e)

    def update_refactoring_status(
        self,
        refactoring_id: str,
        new_status: RefactoringStatus
    ) -> Tuple[bool, Optional[Refactoring], Optional[str]]:
        """
        Update refactoring status.

        Args:
            refactoring_id: Refactoring ID
            new_status: New status

        Returns:
            Tuple of (success, refactoring, error_message)
        """
        try:
            refactoring = self.db.query(Refactoring).filter(
                Refactoring.id == refactoring_id
            ).first()

            if not refactoring:
                return False, None, f"Refactoring {refactoring_id} not found"

            refactoring.status = new_status
            self.db.commit()
            self.db.refresh(refactoring)

            return True, refactoring, None

        except Exception as e:
            self.db.rollback()
            return False, None, str(e)

    def accept_refactoring(
        self,
        refactoring_id: str
    ) -> Tuple[bool, Optional[Refactoring], Optional[str]]:
        """
        Accept a refactoring suggestion.

        Args:
            refactoring_id: Refactoring ID

        Returns:
            Tuple of (success, refactoring, error_message)
        """
        return self.update_refactoring_status(
            refactoring_id,
            RefactoringStatus.ACCEPTED
        )

    def reject_refactoring(
        self,
        refactoring_id: str
    ) -> Tuple[bool, Optional[Refactoring], Optional[str]]:
        """
        Reject a refactoring suggestion.

        Args:
            refactoring_id: Refactoring ID

        Returns:
            Tuple of (success, refactoring, error_message)
        """
        return self.update_refactoring_status(
            refactoring_id,
            RefactoringStatus.REJECTED
        )

    def mark_refactoring_applied(
        self,
        refactoring_id: str
    ) -> Tuple[bool, Optional[Refactoring], Optional[str]]:
        """
        Mark a refactoring as applied.

        Args:
            refactoring_id: Refactoring ID

        Returns:
            Tuple of (success, refactoring, error_message)
        """
        return self.update_refactoring_status(
            refactoring_id,
            RefactoringStatus.APPLIED
        )

    def _generate_diff(self, original: str, refactored: str) -> str:
        """
        Generate unified diff between original and refactored code.

        Args:
            original: Original code
            refactored: Refactored code

        Returns:
            Unified diff string
        """
        original_lines = original.splitlines(keepends=True)
        refactored_lines = refactored.splitlines(keepends=True)

        diff = difflib.unified_diff(
            original_lines,
            refactored_lines,
            fromfile='original',
            tofile='refactored',
            lineterm=''
        )

        return ''.join(diff)

    def _get_refactoring_type(
        self,
        category: str,
        title: str
    ) -> str:
        """
        Determine refactoring type from issue category and title.

        Args:
            category: Issue category
            title: Issue title

        Returns:
            Refactoring type string
        """
        title_lower = title.lower()

        # Map keywords to refactoring types
        if "extract" in title_lower or "long method" in title_lower:
            return "extract_method"
        elif "rename" in title_lower:
            return "rename"
        elif "simplify" in title_lower or "complex" in title_lower:
            return "simplify"
        elif "duplicate" in title_lower:
            return "remove_duplication"
        elif "parameter" in title_lower:
            return "reduce_parameters"
        elif category == "smell":
            return "refactor_smell"
        elif category == "complexity":
            return "reduce_complexity"
        else:
            return "general_refactoring"

    def _extract_benefits(self, refactoring_text: str) -> str:
        """
        Extract benefits from refactoring suggestion text.

        Args:
            refactoring_text: Full refactoring suggestion

        Returns:
            Benefits text
        """
        # Look for common benefit indicators
        keywords = ["benefit", "advantage", "improve", "better", "cleaner"]

        lines = refactoring_text.split("\n")
        benefits = []

        for line in lines:
            line_lower = line.lower()
            if any(keyword in line_lower for keyword in keywords):
                benefits.append(line.strip())

        if benefits:
            return "\n".join(benefits)
        else:
            return "Improves code quality and maintainability"

    def get_stats(self) -> Dict[str, Any]:
        """
        Get refactoring statistics.

        Returns:
            Dict with statistics
        """
        try:
            total = self.db.query(Refactoring).count()
            suggested = self.db.query(Refactoring).filter(
                Refactoring.status == RefactoringStatus.SUGGESTED
            ).count()
            accepted = self.db.query(Refactoring).filter(
                Refactoring.status == RefactoringStatus.ACCEPTED
            ).count()
            rejected = self.db.query(Refactoring).filter(
                Refactoring.status == RefactoringStatus.REJECTED
            ).count()
            applied = self.db.query(Refactoring).filter(
                Refactoring.status == RefactoringStatus.APPLIED
            ).count()

            return {
                "total": total,
                "suggested": suggested,
                "accepted": accepted,
                "rejected": rejected,
                "applied": applied,
                "acceptance_rate": (accepted / total * 100) if total > 0 else 0.0,
                "application_rate": (applied / total * 100) if total > 0 else 0.0
            }

        except Exception:
            return {
                "total": 0,
                "suggested": 0,
                "accepted": 0,
                "rejected": 0,
                "applied": 0,
                "acceptance_rate": 0.0,
                "application_rate": 0.0
            }
