"""Registry for managing code analyzers"""
from typing import Dict, List, Optional
from .base_analyzer import BaseAnalyzer, CodeIssue
from .security_analyzer import SecurityAnalyzer


class AnalyzerRegistry:
    """Registry for managing and running analyzers"""
    
    def __init__(self):
        """Initialize registry with default analyzers"""
        self._analyzers: Dict[str, BaseAnalyzer] = {}
        self._register_default_analyzers()
    
    def _register_default_analyzers(self):
        """Register built-in analyzers"""
        self.register_analyzer(SecurityAnalyzer())
    
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


# Singleton instance
_registry = AnalyzerRegistry()


def get_registry() -> AnalyzerRegistry:
    """
    Get the global analyzer registry instance.
    
    Returns:
        Singleton AnalyzerRegistry instance
    """
    return _registry
