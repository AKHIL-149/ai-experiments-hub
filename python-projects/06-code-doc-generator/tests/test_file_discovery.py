"""Finding the source files of a project."""
import os

import pytest

from src.utils.file_utils import FileDiscovery, validate_file_readable


def tree(tmp_path, names):
    for name in names:
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('x = 1\n')
    return tmp_path


def found(tmp_path, **kwargs):
    root = tmp_path.resolve()
    return sorted(os.path.relpath(f, root) for f in FileDiscovery().discover_files(str(tmp_path), **kwargs))


def test_finds_supported_files_recursively_in_sorted_order(tmp_path):
    tree(tmp_path, ['b.py', 'a.py', 'sub/c.js', 'sub/deep/D.java', 'sub/e.tsx', 'notes.txt', 'data.json'])
    assert found(tmp_path) == sorted(['a.py', 'b.py', 'sub/c.js', 'sub/deep/D.java', 'sub/e.tsx'])


def test_non_recursive_stays_in_the_top_folder(tmp_path):
    tree(tmp_path, ['a.py', 'sub/b.py'])
    assert found(tmp_path, recursive=False) == ['a.py']


def test_extensions_are_matched_ignoring_case(tmp_path):
    tree(tmp_path, ['UPPER.PY', 'Mixed.Java'])
    assert found(tmp_path) == ['Mixed.Java', 'UPPER.PY']


@pytest.mark.parametrize('folder', ['node_modules', '.git', 'venv', '.venv', '__pycache__', 'build', 'dist',
                                    'site-packages', '.tox', 'pkg.egg-info'])
def test_dependency_and_build_folders_are_skipped(tmp_path, folder):
    tree(tmp_path, ['keep.py', f'{folder}/skip.py', f'src/{folder}/skip2.py'])
    assert found(tmp_path) == ['keep.py']


def test_minified_bundles_are_skipped_in_a_search_but_taken_when_named(tmp_path):
    tree(tmp_path, ['app.js', 'app.min.js'])
    assert found(tmp_path) == ['app.js']
    assert FileDiscovery().discover_files(str(tmp_path / 'app.min.js')) != []


def test_modern_module_extensions(tmp_path):
    tree(tmp_path, ['a.mjs', 'b.cjs', 'c.mts', 'd.cts'])
    assert found(tmp_path) == ['a.mjs', 'b.cjs', 'c.mts', 'd.cts']
    assert FileDiscovery().get_language('c.mts') == 'typescript'


def test_a_symlink_back_to_a_parent_does_not_repeat_the_tree(tmp_path):
    tree(tmp_path, ['a.py', 'sub/b.py'])
    os.symlink(tmp_path, tmp_path / 'sub' / 'loop')
    assert found(tmp_path) == ['a.py', 'sub/b.py']


def test_a_file_reachable_by_two_names_is_listed_once(tmp_path):
    tree(tmp_path, ['a.py'])
    os.symlink(tmp_path / 'a.py', tmp_path / 'alias.py')
    assert len(found(tmp_path)) == 1


def test_a_broken_symlink_is_ignored(tmp_path):
    tree(tmp_path, ['a.py'])
    os.symlink(tmp_path / 'gone.py', tmp_path / 'dangling.py')
    assert found(tmp_path) == ['a.py']


def test_single_file_and_unsupported_file(tmp_path):
    tree(tmp_path, ['a.py', 'n.txt'])
    assert FileDiscovery().discover_files(str(tmp_path / 'a.py')) == [str((tmp_path / 'a.py').resolve())]
    assert FileDiscovery().discover_files(str(tmp_path / 'n.txt')) == []


def test_missing_path(tmp_path):
    with pytest.raises(FileNotFoundError):
        FileDiscovery().discover_files(str(tmp_path / 'nope'))


def test_unreadable_folder_is_skipped(tmp_path):
    tree(tmp_path, ['a.py', 'locked/b.py'])
    os.chmod(tmp_path / 'locked', 0)
    try:
        if os.access(tmp_path / 'locked', os.R_OK):
            pytest.skip('running as a user that ignores permissions')
        assert found(tmp_path) == ['a.py']
    finally:
        os.chmod(tmp_path / 'locked', 0o755)


def test_extra_ignore_dirs(tmp_path):
    tree(tmp_path, ['a.py', 'vendor/b.py'])
    files = FileDiscovery(ignore_dirs={'vendor'}).discover_files(str(tmp_path))
    assert [os.path.basename(f) for f in files] == ['a.py']


def test_group_by_language(tmp_path):
    groups = FileDiscovery().group_by_language(['a.py', 'b.JS', 'C.java', 'd.tsx', 'e.txt'])
    assert groups == {'python': ['a.py'], 'javascript': ['b.JS'], 'java': ['C.java'], 'typescript': ['d.tsx']}


def test_validate_file_readable(tmp_path):
    tree(tmp_path, ['a.py'])
    assert validate_file_readable(str(tmp_path / 'a.py'))
    assert not validate_file_readable(str(tmp_path))
    assert not validate_file_readable(str(tmp_path / 'missing.py'))


def test_symlinked_folders_are_not_followed(tmp_path):
    outside = tmp_path / 'outside'
    inside = tmp_path / 'project'
    outside.mkdir()
    inside.mkdir()
    (outside / 'other.py').write_text('x = 1\n')
    (inside / 'a.py').write_text('x = 1\n')
    os.symlink(outside, inside / 'linked')
    assert found(inside) == ['a.py']
