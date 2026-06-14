"""Registry for managing code analyzers"""
from typing import Dict, List, Optional, Any
from .base_analyzer import BaseAnalyzer, CodeIssue
from .security_analyzer import SecurityAnalyzer
from .smell_analyzer import SmellAnalyzer
from .complexity_analyzer import ComplexityAnalyzer


class AnalyzerRegistry:
    """Registry for managing and running analyzers"""

    def __init__(self):
        """Initialize registry with default analyzers"""
        self._analyzers: Dict[str, BaseAnalyzer] = {}
        self._register_default_analyzers()

    def _register_default_analyzers(self):
        """Register built-in analyzers"""
        self.register_analyzer(SecurityAnalyzer())
        self.register_analyzer(SmellAnalyzer())
        self.register_analyzer(ComplexityAnalyzer())
    
    def register_analyzer(self, analyzer: BaseAnalyzer):
        """
        Register an analyzer.
        
        Args:
            analyzer: Analyzer instance to register
        """
        self._analyzers[analyzer.analyzer_id] = analyzer
    
    def get_analyzer(self, analyzer_id: str) -> Optional[BaseAnalyzer]:
        """
        Get analyzer by ID.
        
        Args:
            analyzer_id: Analyzer identifier
            
        Returns:
            Analyzer instance or None if not found
        """
        return self._analyzers.get(analyzer_id)
    
    def get_all_analyzers(self) -> List[BaseAnalyzer]:
        """
        Get all registered analyzers.
        
        Returns:
            List of analyzer instances
        """
        return list(self._analyzers.values())
    
    def get_enabled_analyzers(self) -> List[BaseAnalyzer]:
        """
        Get all enabled analyzers.
        
        Returns:
            List of enabled analyzer instances
        """
        return [a for a in self._analyzers.values() if a.is_enabled()]
    
    def analyze(self, parsed_module, source_code: str, analyzer_ids: Optional[List[str]] = None) -> List[CodeIssue]:
        """
        Run analysis with specified or all enabled analyzers.
        
        Args:
            parsed_module: Parsed module from parser
            source_code: Original source code
            analyzer_ids: Optional list of specific analyzer IDs to run
            
        Returns:
            List of all detected issues
        """
        issues = []
        
        if analyzer_ids:
            # Run specific analyzers
            analyzers = [self._analyzers[aid] for aid in analyzer_ids if aid in self._analyzers]
        else:
            # Run all enabled analyzers
            analyzers = self.get_enabled_analyzers()
        
        for analyzer in analyzers:
            try:
                analyzer_issues = analyzer.analyze(parsed_module, source_code)
                issues.extend(analyzer_issues)
            except Exception as e:
                # Log error but continue with other analyzers
                print(f"Error in {analyzer.analyzer_id}: {e}")
        
        return issues
    
    def get_supported_categories(self) -> List[str]:
        """
        Get all issue categories from registered analyzers.
        
        Returns:
            List of category names
        """
        categories = set()
        for analyzer in self._analyzers.values():
            categories.add(analyzer.category.value)
        return sorted(categories)
    
    def get_all_rule_ids(self) -> List[str]:
        """
        Get all rule IDs from registered analyzers.

        Returns:
            List of rule ID strings
        """
        rule_ids = []
        for analyzer in self._analyzers.values():
            rule_ids.extend(analyzer.get_rule_ids())
        return sorted(rule_ids)

    def calculate_health_score(self, issues: List[CodeIssue]) -> Dict[str, Any]:
        """
        Calculate overall code health score based on detected issues.

        Health score is 0-100 where:
        - 100 = perfect code (no issues)
        - 80-99 = good code (minor issues)
        - 60-79 = fair code (some problems)
        - 40-59 = poor code (many issues)
        - 0-39 = critical code (severe issues)

        Args:
            issues: List of detected CodeIssue objects

        Returns:
            Dictionary with health score and breakdown
        """
        from .base_analyzer import IssueSeverity

        if not issues:
            return {
                'overall_score': 100,
                'grade': 'A+',
                'total_issues': 0,
                'by_severity': {},
                'by_category': {},
                'description': 'Excellent! No issues detected.'
            }

        # Weight issues by severity
        severity_weights = {
            IssueSeverity.INFO: 1,
            IssueSeverity.WARNING: 3,
            IssueSeverity.ERROR: 7,
            IssueSeverity.CRITICAL: 15
        }

        # Count issues by severity and category
        severity_counts = {}
        category_counts = {}
        total_penalty = 0

        for issue in issues:
            # Count by severity
            severity = issue.severity
            severity_counts[severity.value] = severity_counts.get(severity.value, 0) + 1

            # Count by category
            category = issue.category.value
            category_counts[category] = category_counts.get(category, 0) + 1

            # Calculate penalty
            weight = severity_weights.get(severity, 1)
            confidence_factor = issue.confidence
            total_penalty += weight * confidence_factor

        # Calculate score (exponential decay for penalties)
        # Start at 100, reduce based on penalties
        # Use formula: score = 100 * e^(-penalty_factor * total_penalty)
        import math
        penalty_factor = 0.05  # Tuning parameter
        raw_score = 100 * math.exp(-penalty_factor * total_penalty)
        overall_score = max(0, min(100, round(raw_score, 1)))

        # Determine grade
        if overall_score >= 95:
            grade = 'A+'
        elif overall_score >= 90:
            grade = 'A'
        elif overall_score >= 85:
            grade = 'A-'
        elif overall_score >= 80:
            grade = 'B+'
        elif overall_score >= 75:
            grade = 'B'
        elif overall_score >= 70:
            grade = 'B-'
        elif overall_score >= 65:
            grade = 'C+'
        elif overall_score >= 60:
            grade = 'C'
        elif overall_score >= 55:
            grade = 'C-'
        elif overall_score >= 50:
            grade = 'D+'
        elif overall_score >= 45:
            grade = 'D'
        elif overall_score >= 40:
            grade = 'D-'
        else:
            grade = 'F'

        # Generate description
        if overall_score >= 90:
            description = 'Excellent code quality with minimal issues.'
        elif overall_score >= 80:
            description = 'Good code quality with minor issues.'
        elif overall_score >= 70:
            description = 'Fair code quality with some problems to address.'
        elif overall_score >= 60:
            description = 'Acceptable code quality but needs improvement.'
        elif overall_score >= 50:
            description = 'Poor code quality with many issues.'
        elif overall_score >= 40:
            description = 'Very poor code quality requiring significant work.'
        else:
            description = 'Critical code quality issues detected.'

        return {
            'overall_score': overall_score,
            'grade': grade,
            'total_issues': len(issues),
            'by_severity': severity_counts,
            'by_category': category_counts,
            'description': description
        }


# Singleton instance
_registry = AnalyzerRegistry()


def get_registry() -> AnalyzerRegistry:
    """
    Get the global analyzer registry instance.
    
    Returns:
        Singleton AnalyzerRegistry instance
    """
    return _registry
