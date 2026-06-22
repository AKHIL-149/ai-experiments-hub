"""
Custom Rule Service - Test and apply custom user-defined rules
"""

import re
import ast
from typing import Dict, List, Any, Optional


class CustomRuleService:
    """Service for testing custom analysis rules."""

    def test_rule(self, rule: Dict[str, Any], code: str, language: str) -> List[Dict[str, Any]]:
        """
        Test a custom rule against code.

        Args:
            rule: Rule configuration dictionary
            code: Code to analyze
            language: Programming language (python, javascript, etc.)

        Returns:
            List of matches found by the rule
        """
        matches = []
        pattern_type = rule.get('pattern_type', 'regex')

        try:
            if pattern_type == 'regex' or pattern_type == 'both':
                regex_matches = self._test_regex_pattern(rule, code)
                matches.extend(regex_matches)

            if pattern_type == 'ast' or pattern_type == 'both':
                if language == 'python':
                    ast_matches = self._test_python_ast_pattern(rule, code)
                    matches.extend(ast_matches)
                elif language in ['javascript', 'typescript']:
                    # JavaScript/TypeScript AST testing would need a JS AST parser
                    # For now, fall back to regex or return empty
                    pass

            # Remove duplicates based on line number
            unique_matches = []
            seen_lines = set()
            for match in matches:
                line = match.get('line')
                if line not in seen_lines:
                    unique_matches.append(match)
                    seen_lines.add(line)

            return unique_matches

        except Exception as e:
            raise Exception(f"Error testing rule: {str(e)}")

    def _test_regex_pattern(self, rule: Dict[str, Any], code: str) -> List[Dict[str, Any]]:
        """
        Test regex pattern against code.

        Args:
            rule: Rule configuration
            code: Code to analyze

        Returns:
            List of matches
        """
        matches = []
        regex_pattern = rule.get('regex_pattern', {})

        if not regex_pattern:
            return matches

        pattern_str = regex_pattern.get('pattern', '')
        if not pattern_str:
            return matches

        flags_config = regex_pattern.get('flags', {})

        # Build regex flags
        flags = 0
        if flags_config.get('case_insensitive'):
            flags |= re.IGNORECASE
        if flags_config.get('multiline'):
            flags |= re.MULTILINE
        if flags_config.get('dotall'):
            flags |= re.DOTALL

        try:
            pattern = re.compile(pattern_str, flags)

            # Split code into lines for line number tracking
            lines = code.split('\n')

            for line_num, line in enumerate(lines, 1):
                for match in pattern.finditer(line):
                    matches.append({
                        'line': line_num,
                        'column': match.start() + 1,
                        'message': rule.get('message', '').format(matched_text=match.group()),
                        'code_snippet': line.strip(),
                        'severity': rule.get('severity', 'warning'),
                        'category': rule.get('category', 'custom'),
                        'rule_id': rule.get('id', 'CUSTOM')
                    })

        except re.error as e:
            raise Exception(f"Invalid regex pattern: {str(e)}")

        return matches

    def _test_python_ast_pattern(self, rule: Dict[str, Any], code: str) -> List[Dict[str, Any]]:
        """
        Test AST pattern against Python code.

        Args:
            rule: Rule configuration
            code: Python code to analyze

        Returns:
            List of matches
        """
        matches = []
        ast_patterns = rule.get('ast_patterns', [])

        if not ast_patterns:
            return matches

        try:
            tree = ast.parse(code)

            for pattern in ast_patterns:
                node_type = pattern.get('nodeType', '')
                attributes = pattern.get('attributes', {})

                # Find matching nodes in AST
                for node in ast.walk(tree):
                    if node.__class__.__name__ == node_type:
                        if self._matches_attributes(node, attributes):
                            line_num = getattr(node, 'lineno', 0)
                            col_offset = getattr(node, 'col_offset', 0)

                            # Extract code snippet
                            code_lines = code.split('\n')
                            snippet = code_lines[line_num - 1] if line_num > 0 and line_num <= len(code_lines) else ''

                            matches.append({
                                'line': line_num,
                                'column': col_offset + 1,
                                'message': rule.get('message', 'Pattern matched'),
                                'code_snippet': snippet.strip(),
                                'severity': rule.get('severity', 'warning'),
                                'category': rule.get('category', 'custom'),
                                'rule_id': rule.get('id', 'CUSTOM'),
                                'node_type': node_type
                            })

        except SyntaxError as e:
            raise Exception(f"Invalid Python code: {str(e)}")

        return matches

    def _matches_attributes(self, node: ast.AST, attributes: Dict[str, Any]) -> bool:
        """
        Check if AST node matches specified attributes.

        Args:
            node: AST node
            attributes: Dictionary of attribute patterns to match

        Returns:
            True if node matches all attributes
        """
        if not attributes:
            return True

        for attr_name, attr_value in attributes.items():
            if not hasattr(node, attr_name):
                return False

            node_value = getattr(node, attr_name)

            # Handle different comparison types
            if isinstance(attr_value, str):
                if isinstance(node_value, str):
                    if node_value != attr_value:
                        return False
                else:
                    # Try to compare string representation
                    if str(node_value) != attr_value:
                        return False

            elif isinstance(attr_value, dict):
                # Handle comparisons like {"length": ">0"}
                if 'length' in attr_value:
                    length_condition = attr_value['length']
                    if isinstance(node_value, list):
                        actual_length = len(node_value)
                        if not self._evaluate_condition(actual_length, length_condition):
                            return False

            else:
                # Direct comparison
                if node_value != attr_value:
                    return False

        return True

    def _evaluate_condition(self, value: Any, condition: str) -> bool:
        """
        Evaluate a condition like ">0", "==5", etc.

        Args:
            value: Actual value
            condition: Condition string

        Returns:
            True if condition is met
        """
        condition = str(condition).strip()

        # Parse condition
        if condition.startswith('>'):
            threshold = int(condition[1:].strip())
            return value > threshold
        elif condition.startswith('<'):
            threshold = int(condition[1:].strip())
            return value < threshold
        elif condition.startswith('>='):
            threshold = int(condition[2:].strip())
            return value >= threshold
        elif condition.startswith('<='):
            threshold = int(condition[2:].strip())
            return value <= threshold
        elif condition.startswith('=='):
            threshold = int(condition[2:].strip())
            return value == threshold
        elif condition.startswith('!='):
            threshold = int(condition[2:].strip())
            return value != threshold
        else:
            # Try direct comparison
            try:
                threshold = int(condition)
                return value == threshold
            except ValueError:
                return False

    def apply_custom_rules(self, user_id: str, code: str, language: str) -> List[Dict[str, Any]]:
        """
        Apply all enabled custom rules for a user to code.

        Args:
            user_id: User ID
            code: Code to analyze
            language: Programming language

        Returns:
            List of all matches from all enabled rules
        """
        from src.core.database import DatabaseManager, CustomRule

        all_matches = []

        db_manager = DatabaseManager()
        with db_manager.get_session() as db:
            # Get all enabled rules for this user and language
            rules = db.query(CustomRule).filter(
                CustomRule.user_id == user_id,
                CustomRule.enabled == True
            ).all()

            for rule_model in rules:
                # Check if rule applies to this language
                rule_languages = rule_model.languages.split(',')
                if language not in rule_languages:
                    continue

                # Convert rule to dict
                rule_dict = rule_model.to_dict()

                # Test rule
                try:
                    matches = self.test_rule(rule_dict, code, language)
                    all_matches.extend(matches)

                    # Update usage stats
                    if matches:
                        rule_model.use_count = rule_model.use_count + 1
                        from datetime import datetime, timezone
                        rule_model.last_used_at = datetime.now(timezone.utc)

                except Exception as e:
                    # Log error but continue with other rules
                    print(f"Error applying rule {rule_model.id}: {str(e)}")

            db.commit()

        return all_matches
