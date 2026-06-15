"""Configuration loader for analyzers"""
import os
from typing import Dict, List, Optional
from dotenv import load_dotenv

# Load environment variables
load_dotenv()


class AnalyzerConfig:
    """Loads and provides analyzer configuration from environment variables"""

    def __init__(self):
        """Initialize configuration from environment"""
        # Complexity thresholds
        self.cc_warning = int(os.getenv('COMPLEXITY_CC_WARN', '10'))
        self.cc_error = int(os.getenv('COMPLEXITY_CC_ERROR', '15'))
        self.mi_warning = int(os.getenv('COMPLEXITY_MI_WARN', '20'))
        self.mi_error = int(os.getenv('COMPLEXITY_MI_ERROR', '10'))
        self.cognitive_warning = int(os.getenv('COMPLEXITY_COGNITIVE_WARN', '15'))
        self.cognitive_error = int(os.getenv('COMPLEXITY_COGNITIVE_ERROR', '25'))

        # Disabled rules
        disabled_str = os.getenv('DISABLED_RULES', '')
        self.disabled_rules = set(r.strip() for r in disabled_str.split(',') if r.strip())

        # Severity overrides
        self.severity_overrides = self._load_severity_overrides()

    def _load_severity_overrides(self) -> Dict[str, str]:
        """Load severity overrides from environment variables"""
        overrides = {}

        # Look for SEVERITY_OVERRIDE_* environment variables
        for key, value in os.environ.items():
            if key.startswith('SEVERITY_OVERRIDE_') and value:
                rule_id = key.replace('SEVERITY_OVERRIDE_', '')
                severity = value.strip().upper()

                # Validate severity
                if severity in ['INFO', 'WARNING', 'ERROR', 'CRITICAL']:
                    overrides[rule_id] = severity

        return overrides

    def is_rule_enabled(self, rule_id: str) -> bool:
        """Check if a specific rule is enabled"""
        return rule_id not in self.disabled_rules

    def get_severity_override(self, rule_id: str) -> Optional[str]:
        """Get severity override for a rule, if any"""
        return self.severity_overrides.get(rule_id)

    def get_complexity_config(self) -> Dict:
        """Get complexity analyzer configuration"""
        return {
            'cc_warning': self.cc_warning,
            'cc_error': self.cc_error,
            'mi_warning': self.mi_warning,
            'mi_error': self.mi_error,
            'cognitive_warning': self.cognitive_warning,
            'cognitive_error': self.cognitive_error
        }


# Global config instance
_config = None


def get_config() -> AnalyzerConfig:
    """Get the global analyzer configuration instance"""
    global _config
    if _config is None:
        _config = AnalyzerConfig()
    return _config


def reload_config():
    """Reload configuration from environment (useful for testing)"""
    global _config
    _config = AnalyzerConfig()
    return _config
