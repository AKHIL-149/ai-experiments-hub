"""Tests for Git diff parsing utilities"""
import pytest
from src.utils.git_utils import (
    DiffParser,
    DiffFile,
    DiffHunk,
    analyze_diff_complexity
)


# Sample diff for a simple file modification
SIMPLE_DIFF = """diff --git a/test.py b/test.py
index 1234567..abcdefg 100644
--- a/test.py
+++ b/test.py
@@ -1,5 +1,6 @@
 def hello():
-    print("Hello")
+    print("Hello, World!")
+    return True

 def goodbye():
     print("Goodbye")
"""


# Diff with new file
NEW_FILE_DIFF = """diff --git a/new_file.py b/new_file.py
new file mode 100644
index 0000000..1234567
--- /dev/null
+++ b/new_file.py
@@ -0,0 +1,3 @@
+def new_function():
+    pass
+
"""


# Diff with deleted file
DELETED_FILE_DIFF = """diff --git a/old_file.py b/old_file.py
deleted file mode 100644
index 1234567..0000000
--- a/old_file.py
+++ /dev/null
@@ -1,3 +0,0 @@
-def old_function():
-    pass
-
"""


# Diff with renamed file
RENAMED_FILE_DIFF = """diff --git a/old_name.py b/new_name.py
similarity index 100%
rename from old_name.py
rename to new_name.py
"""


# Multi-file diff
MULTI_FILE_DIFF = """diff --git a/file1.py b/file1.py
index 1111111..2222222 100644
--- a/file1.py
+++ b/file1.py
@@ -1,3 +1,4 @@
+import os
 def func1():
     pass

diff --git a/file2.py b/file2.py
index 3333333..4444444 100644
--- a/file2.py
+++ b/file2.py
@@ -1,2 +1,2 @@
 def func2():
-    print("old")
+    print("new")
"""


# Complex diff with multiple hunks
MULTI_HUNK_DIFF = """diff --git a/complex.py b/complex.py
index abcd123..efgh456 100644
--- a/complex.py
+++ b/complex.py
@@ -1,5 +1,6 @@
 def first():
-    print("first")
+    print("First function")
+    return 1

 def second():
     pass
@@ -10,4 +11,5 @@ def third():
     pass

 def fourth():
-    print("fourth")
+    print("Fourth function")
+    return 4
"""


def test_parse_simple_diff():
    """Test parsing a simple diff with one file"""
    files = DiffParser.parse_diff(SIMPLE_DIFF)

    assert len(files) == 1
    assert files[0].old_path == "test.py"
    assert files[0].new_path == "test.py"
    assert files[0].path == "test.py"
    assert not files[0].is_new_file
    assert not files[0].is_deleted_file
    assert not files[0].is_renamed


def test_parse_new_file():
    """Test parsing diff with new file"""
    files = DiffParser.parse_diff(NEW_FILE_DIFF)

    assert len(files) == 1
    assert files[0].is_new_file
    assert files[0].path == "new_file.py"


def test_parse_deleted_file():
    """Test parsing diff with deleted file"""
    files = DiffParser.parse_diff(DELETED_FILE_DIFF)

    assert len(files) == 1
    assert files[0].is_deleted_file
    assert files[0].old_path == "old_file.py"


def test_parse_renamed_file():
    """Test parsing diff with renamed file"""
    files = DiffParser.parse_diff(RENAMED_FILE_DIFF)

    assert len(files) == 1
    assert files[0].is_renamed
    assert files[0].old_path == "old_name.py"
    assert files[0].new_path == "new_name.py"


def test_parse_multi_file_diff():
    """Test parsing diff with multiple files"""
    files = DiffParser.parse_diff(MULTI_FILE_DIFF)

    assert len(files) == 2
    assert files[0].path == "file1.py"
    assert files[1].path == "file2.py"


def test_parse_empty_diff():
    """Test parsing empty diff"""
    files = DiffParser.parse_diff("")
    assert len(files) == 0

    files = DiffParser.parse_diff("   \n  \n  ")
    assert len(files) == 0


def test_hunk_parsing():
    """Test parsing hunks in a diff"""
    files = DiffParser.parse_diff(SIMPLE_DIFF)

    assert len(files) == 1
    assert len(files[0].hunks) == 1

    hunk = files[0].hunks[0]
    assert hunk.old_start == 1
    assert hunk.old_count == 5
    assert hunk.new_start == 1
    assert hunk.new_count == 6


def test_multi_hunk_parsing():
    """Test parsing multiple hunks in one file"""
    files = DiffParser.parse_diff(MULTI_HUNK_DIFF)

    assert len(files) == 1
    assert len(files[0].hunks) == 2

    # First hunk
    assert files[0].hunks[0].old_start == 1
    assert files[0].hunks[0].old_count == 5

    # Second hunk
    assert files[0].hunks[1].old_start == 10
    assert files[0].hunks[1].old_count == 4


def test_get_added_lines():
    """Test extracting added lines from a hunk"""
    files = DiffParser.parse_diff(SIMPLE_DIFF)
    hunk = files[0].hunks[0]

    added = hunk.get_added_lines()

    # Should have 2 added lines
    assert len(added) == 2
    assert added[0][0] == 2  # Line number
    assert "Hello, World!" in added[0][1]  # Content
    assert added[1][0] == 3
    assert "return True" in added[1][1]


def test_get_removed_lines():
    """Test extracting removed lines from a hunk"""
    files = DiffParser.parse_diff(SIMPLE_DIFF)
    hunk = files[0].hunks[0]

    removed = hunk.get_removed_lines()

    # Should have 1 removed line
    assert len(removed) == 1
    assert removed[0][0] == 2  # Line number
    assert 'print("Hello")' in removed[0][1]  # Content


def test_get_modified_line_numbers():
    """Test getting all modified line numbers"""
    files = DiffParser.parse_diff(SIMPLE_DIFF)
    hunk = files[0].hunks[0]

    modified = hunk.get_modified_line_numbers()

    # Lines 2 and 3 were modified
    assert 2 in modified
    assert 3 in modified


def test_file_get_all_modified_lines():
    """Test getting all modified lines across all hunks"""
    files = DiffParser.parse_diff(MULTI_HUNK_DIFF)

    modified = files[0].get_all_modified_lines()

    # Should have modifications from both hunks
    assert len(modified) > 0
    assert 2 in modified  # From first hunk
    assert 3 in modified  # From first hunk


def test_file_is_line_modified():
    """Test checking if specific line was modified"""
    files = DiffParser.parse_diff(SIMPLE_DIFF)

    assert files[0].is_line_modified(2)  # Modified
    assert files[0].is_line_modified(3)  # Modified
    assert not files[0].is_line_modified(1)  # Not modified
    assert not files[0].is_line_modified(100)  # Doesn't exist


def test_file_added_removed_counts():
    """Test counting added and removed lines"""
    files = DiffParser.parse_diff(SIMPLE_DIFF)

    assert files[0].get_added_lines_count() == 2
    assert files[0].get_removed_lines_count() == 1


def test_get_changed_files():
    """Test extracting just file paths"""
    paths = DiffParser.get_changed_files(MULTI_FILE_DIFF)

    assert len(paths) == 2
    assert "file1.py" in paths
    assert "file2.py" in paths


def test_get_file_stats():
    """Test getting statistics for each file"""
    stats = DiffParser.get_file_stats(MULTI_FILE_DIFF)

    assert len(stats) == 2
    assert "file1.py" in stats
    assert "file2.py" in stats

    # Check file1.py stats
    assert stats["file1.py"]["added"] == 1
    assert stats["file1.py"]["removed"] == 0
    assert not stats["file1.py"]["is_new"]

    # Check file2.py stats
    assert stats["file2.py"]["added"] == 1
    assert stats["file2.py"]["removed"] == 1


def test_filter_by_extension():
    """Test filtering files by extension"""
    # Create diff with mixed extensions
    mixed_diff = """diff --git a/file.py b/file.py
index 1111111..2222222 100644
--- a/file.py
+++ b/file.py
@@ -1 +1 @@
-old
+new
diff --git a/file.js b/file.js
index 3333333..4444444 100644
--- a/file.js
+++ b/file.js
@@ -1 +1 @@
-old
+new
diff --git a/README.md b/README.md
index 5555555..6666666 100644
--- a/README.md
+++ b/README.md
@@ -1 +1 @@
-old
+new
"""

    # Filter only Python files
    py_files = DiffParser.filter_by_extension(mixed_diff, ['.py'])
    assert len(py_files) == 1
    assert py_files[0].path == "file.py"

    # Filter Python and JS files
    code_files = DiffParser.filter_by_extension(mixed_diff, ['.py', '.js'])
    assert len(code_files) == 2


def test_analyze_diff_complexity_empty():
    """Test complexity analysis with empty diff"""
    result = analyze_diff_complexity("")

    assert result['total_files'] == 0
    assert result['total_added'] == 0
    assert result['total_removed'] == 0
    assert result['complexity_score'] == 0.0


def test_analyze_diff_complexity_simple():
    """Test complexity analysis with simple diff"""
    result = analyze_diff_complexity(SIMPLE_DIFF)

    assert result['total_files'] == 1
    assert result['total_added'] == 2
    assert result['total_removed'] == 1
    assert result['total_modified'] == 3
    assert result['largest_file_changes'] == "test.py"
    assert result['complexity_score'] > 0


def test_analyze_diff_complexity_multi_file():
    """Test complexity analysis with multiple files"""
    result = analyze_diff_complexity(MULTI_FILE_DIFF)

    assert result['total_files'] == 2
    assert result['total_added'] == 2
    assert result['total_removed'] == 1
    assert result['complexity_score'] > 0


def test_hunk_with_no_changes():
    """Test hunk with only context lines"""
    diff = """diff --git a/test.py b/test.py
index 1234567..abcdefg 100644
--- a/test.py
+++ b/test.py
@@ -1,3 +1,3 @@
 line1
 line2
 line3
"""

    files = DiffParser.parse_diff(diff)
    assert len(files) == 1
    assert len(files[0].hunks) == 1

    # No added or removed lines
    assert files[0].get_added_lines_count() == 0
    assert files[0].get_removed_lines_count() == 0


def test_new_file_stats():
    """Test stats for new file"""
    stats = DiffParser.get_file_stats(NEW_FILE_DIFF)

    assert "new_file.py" in stats
    assert stats["new_file.py"]["is_new"]
    assert not stats["new_file.py"]["is_deleted"]
    assert stats["new_file.py"]["added"] == 3


def test_deleted_file_stats():
    """Test stats for deleted file"""
    stats = DiffParser.get_file_stats(DELETED_FILE_DIFF)

    assert "old_file.py" in stats
    assert not stats["old_file.py"]["is_new"]
    assert stats["old_file.py"]["is_deleted"]
    assert stats["old_file.py"]["removed"] == 3


def test_renamed_file_stats():
    """Test stats for renamed file"""
    stats = DiffParser.get_file_stats(RENAMED_FILE_DIFF)

    assert "new_name.py" in stats
    assert stats["new_name.py"]["is_renamed"]
    assert stats["new_name.py"]["old_path"] == "old_name.py"
    assert stats["new_name.py"]["new_path"] == "new_name.py"


def test_diff_file_dataclass():
    """Test DiffFile dataclass properties"""
    file = DiffFile(
        old_path="old.py",
        new_path="new.py",
        is_renamed=True
    )

    assert file.path == "new.py"
    assert file.old_path == "old.py"
    assert file.is_renamed

    # Test with only old path (deleted file)
    deleted = DiffFile(old_path="deleted.py", new_path=None, is_deleted_file=True)
    assert deleted.path == "deleted.py"


def test_diff_hunk_dataclass():
    """Test DiffHunk dataclass"""
    hunk = DiffHunk(
        old_start=10,
        old_count=5,
        new_start=10,
        new_count=6,
        lines=[
            " context",
            "-removed",
            "+added",
            " context"
        ]
    )

    assert hunk.old_start == 10
    assert hunk.new_count == 6
    assert len(hunk.lines) == 4


def test_large_line_numbers():
    """Test handling large line numbers"""
    diff = """diff --git a/large.py b/large.py
index 1234567..abcdefg 100644
--- a/large.py
+++ b/large.py
@@ -1000,3 +1000,4 @@
 line1000
-line1001
+line1001_modified
+line1002_new
 line1002
"""

    files = DiffParser.parse_diff(diff)
    assert len(files) == 1

    hunk = files[0].hunks[0]
    assert hunk.old_start == 1000
    assert hunk.new_start == 1000

    modified = hunk.get_modified_line_numbers()
    assert 1001 in modified
    assert 1002 in modified


def test_special_characters_in_path():
    """Test handling file paths with special characters"""
    diff = """diff --git a/src/utils/my-file.py b/src/utils/my-file.py
index 1234567..abcdefg 100644
--- a/src/utils/my-file.py
+++ b/src/utils/my-file.py
@@ -1 +1 @@
-old
+new
"""

    files = DiffParser.parse_diff(diff)
    assert len(files) == 1
    assert files[0].path == "src/utils/my-file.py"
