"""Tests for diff analyzer service"""
import pytest
from src.services.diff_analyzer_service import DiffAnalyzerService


@pytest.fixture
def diff_analyzer():
    """Create diff analyzer service"""
    return DiffAnalyzerService()


@pytest.fixture
def sample_python_diff():
    """Sample Python diff with security issues"""
    return """diff --git a/app.py b/app.py
index 1234567..abcdefg 100644
--- a/app.py
+++ b/app.py
@@ -1,5 +1,10 @@
 import os
+import subprocess

 def main():
-    print("Hello")
+    # Security issue: command injection
+    user_input = input("Enter command: ")
+    subprocess.call(user_input, shell=True)
+
+    # Hardcoded credential
+    password = "admin123"
"""


@pytest.fixture
def sample_multi_file_diff():
    """Sample diff with multiple files"""
    return """diff --git a/file1.py b/file1.py
index 1234567..abcdefg 100644
--- a/file1.py
+++ b/file1.py
@@ -1,3 +1,5 @@
 def hello():
-    print("hello")
+    # Added new line
+    x = 10
+    print("hello world")

diff --git a/file2.py b/file2.py
index 9876543..fedcba9 100644
--- a/file2.py
+++ b/file2.py
@@ -1,2 +1,3 @@
 def world():
     print("world")
+    return True
"""


def test_analyze_diff_success(diff_analyzer, sample_python_diff):
    """Test successfully analyzing a diff"""
    success, result, error = diff_analyzer.analyze_diff(sample_python_diff, file_filter='.py')

    assert success is True
    assert error is None
    assert result is not None
    assert result['total_files'] == 1
    assert result['analyzed_files'] == 1
    assert 'files' in result


def test_analyze_diff_empty(diff_analyzer):
    """Test analyzing empty diff"""
    success, result, error = diff_analyzer.analyze_diff("")

    assert success is True
    assert result['total_files'] == 0
    assert result['analyzed_files'] == 0
    assert result['total_issues'] == 0


def test_analyze_diff_with_filter(diff_analyzer, sample_multi_file_diff):
    """Test analyzing diff with file filter"""
    success, result, error = diff_analyzer.analyze_diff(
        sample_multi_file_diff,
        file_filter='.py'
    )

    assert success is True
    assert result['total_files'] == 2
    assert all(f['file_path'].endswith('.py') for f in result['files'])


def test_analyze_diff_no_python_files(diff_analyzer):
    """Test analyzing diff with no Python files"""
    diff = """diff --git a/README.md b/README.md
index 1234567..abcdefg 100644
--- a/README.md
+++ b/README.md
@@ -1,2 +1,3 @@
 # Title
 Content
+More content
"""
    success, result, error = diff_analyzer.analyze_diff(diff, file_filter='.py')

    assert success is True
    assert result['total_files'] == 0


def test_analyze_pr_diff(diff_analyzer, sample_python_diff):
    """Test analyzing PR diff"""
    success, result, error = diff_analyzer.analyze_pr_diff(
        sample_python_diff,
        language='python'
    )

    assert success is True
    assert result is not None
    assert result['total_files'] >= 0


def test_analyze_pr_diff_javascript(diff_analyzer):
    """Test analyzing JavaScript diff"""
    js_diff = """diff --git a/app.js b/app.js
index 1234567..abcdefg 100644
--- a/app.js
+++ b/app.js
@@ -1,2 +1,3 @@
 function main() {
   console.log("hello");
+  return true;
 }
"""
    success, result, error = diff_analyzer.analyze_pr_diff(js_diff, language='javascript')

    assert success is True
    assert result is not None


def test_get_changed_files(diff_analyzer, sample_multi_file_diff):
    """Test getting list of changed files"""
    success, files, error = diff_analyzer.get_changed_files(sample_multi_file_diff)

    assert success is True
    assert error is None
    assert len(files) == 2
    assert 'file1.py' in files
    assert 'file2.py' in files


def test_get_changed_files_with_filter(diff_analyzer, sample_multi_file_diff):
    """Test getting changed files with filter"""
    success, files, error = diff_analyzer.get_changed_files(
        sample_multi_file_diff,
        file_filter='.py'
    )

    assert success is True
    assert all(f.endswith('.py') for f in files)


def test_get_changed_files_deleted(diff_analyzer):
    """Test that deleted files are excluded"""
    diff = """diff --git a/deleted.py b/deleted.py
deleted file mode 100644
index 1234567..0000000
--- a/deleted.py
+++ /dev/null
@@ -1,3 +0,0 @@
-def old():
-    pass
-
"""
    success, files, error = diff_analyzer.get_changed_files(diff)

    assert success is True
    assert len(files) == 0  # Deleted files excluded


def test_get_diff_stats(diff_analyzer, sample_python_diff):
    """Test getting diff statistics"""
    stats = diff_analyzer.get_diff_stats(sample_python_diff)

    assert 'files_changed' in stats
    assert 'additions' in stats
    assert 'deletions' in stats
    assert 'files' in stats
    assert stats['files_changed'] == 1
    assert stats['additions'] > 0


def test_get_diff_stats_multi_file(diff_analyzer, sample_multi_file_diff):
    """Test diff stats for multiple files"""
    stats = diff_analyzer.get_diff_stats(sample_multi_file_diff)

    assert stats['files_changed'] == 2
    assert len(stats['files']) == 2

    # Check file details
    for file_stat in stats['files']:
        assert 'path' in file_stat
        assert 'additions' in file_stat
        assert 'deletions' in file_stat
        assert 'is_new' in file_stat
        assert 'is_deleted' in file_stat


def test_get_diff_stats_new_file(diff_analyzer):
    """Test diff stats for new file"""
    diff = """diff --git a/new.py b/new.py
new file mode 100644
index 0000000..1234567
--- /dev/null
+++ b/new.py
@@ -0,0 +1,3 @@
+def new_function():
+    pass
+
"""
    stats = diff_analyzer.get_diff_stats(diff)

    assert stats['files_changed'] == 1
    file_stat = stats['files'][0]
    assert file_stat['is_new'] is True
    assert file_stat['is_deleted'] is False


def test_reconstruct_code_from_hunks(diff_analyzer):
    """Test code reconstruction from hunks"""
    from src.utils.git_utils import DiffParser

    diff = """diff --git a/test.py b/test.py
index 1234567..abcdefg 100644
--- a/test.py
+++ b/test.py
@@ -1,3 +1,4 @@
 def test():
+    x = 10
     pass

"""
    files = DiffParser.parse_diff(diff)
    code = diff_analyzer._reconstruct_code_from_hunks(files[0].hunks)

    assert 'def test():' in code
    assert 'x = 10' in code
    assert 'pass' in code


def test_filter_issues_by_lines(diff_analyzer):
    """Test filtering issues by changed line numbers"""
    issues = [
        {'line_number': 5, 'message': 'Issue on line 5'},
        {'line_number': 10, 'message': 'Issue on line 10'},
        {'line_number': 15, 'message': 'Issue on line 15'},
        {'message': 'File-level issue'}  # No line number
    ]

    changed_lines = [5, 15]

    filtered = diff_analyzer._filter_issues_by_lines(issues, changed_lines)

    # Should include line 5, line 15, and file-level issue
    assert len(filtered) >= 2

    # Check that line 5 and 15 are included
    line_numbers = [i.get('line_number') for i in filtered if 'line_number' in i]
    assert 5 in line_numbers
    assert 15 in line_numbers


def test_filter_issues_context_lines(diff_analyzer):
    """Test that issues near changed lines are included"""
    issues = [
        {'line_number': 10, 'message': 'Issue near change'},
    ]

    # Changed line is 12, but issue is on 10 (within 2 lines)
    changed_lines = [12]

    filtered = diff_analyzer._filter_issues_by_lines(issues, changed_lines)

    # Should include the issue due to proximity
    assert len(filtered) == 1


def test_analyze_diff_file_no_changes(diff_analyzer):
    """Test analyzing file with no actual code changes"""
    from src.utils.git_utils import DiffFile, DiffHunk

    # Create a diff file with only deletions
    diff_file = DiffFile(old_path='test.py', new_path='test.py')
    hunk = DiffHunk(old_start=1, old_count=2, new_start=1, new_count=0)
    hunk.lines = ['-def old():', '-    pass']
    diff_file.hunks = [hunk]

    success, result, error = diff_analyzer._analyze_diff_file(diff_file)

    assert success is True
    assert result['issues_count'] == 0
    assert result['changed_lines'] == 0


def test_invalid_diff_text(diff_analyzer):
    """Test handling invalid diff text"""
    # Malformed diff should still parse (might just be empty)
    success, result, error = diff_analyzer.analyze_diff("not a valid diff")

    # Should handle gracefully
    assert success is True or error is not None
