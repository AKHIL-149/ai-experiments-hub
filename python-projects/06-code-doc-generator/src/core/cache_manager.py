"""Cache manager for AST and AI-generated content"""
import hashlib
import json
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, Any, Dict


class CacheManager:
    """
    Manages two-level caching:
    1. AST cache - Parsed code structures
    2. AI cache - LLM-generated explanations
    """

    def __init__(self, cache_dir: str = './data/cache', expiry_days: int = 7):
        """
        Initialize cache manager.

        Args:
            cache_dir: Directory for cache storage
            expiry_days: Days before cache expires
        """
        self.cache_dir = Path(cache_dir)
        self.ast_cache_dir = self.cache_dir / 'ast'
        self.ai_cache_dir = self.cache_dir / 'ai'
        self.expiry = timedelta(days=expiry_days)

        # Create cache directories
        self.ast_cache_dir.mkdir(parents=True, exist_ok=True)
        self.ai_cache_dir.mkdir(parents=True, exist_ok=True)

    def get_ast_cache(self, file_path: str) -> Optional[Dict[str, Any]]:
        """
        Get cached AST if available and fresh.

        Args:
            file_path: Path to the source file

        Returns:
            Cached parsed data or None if not available/expired
        """
        cache_key = self._file_hash(file_path)
        cache_file = self.ast_cache_dir / f"{cache_key}.json"

        if cache_file.exists():
            # Check if cache is fresh
            if self._is_fresh(cache_file):
                try:
                    return json.loads(cache_file.read_text())
                except json.JSONDecodeError:
                    # Corrupted cache, ignore
                    return None

        return None

    def set_ast_cache(self, file_path: str, parsed_data: Dict[str, Any]) -> None:
        """
        Save parsed AST to cache.

        Args:
            file_path: Path to the source file
            parsed_data: Parsed module data (as dict)
        """
        cache_key = self._file_hash(file_path)
        cache_file = self.ast_cache_dir / f"{cache_key}.json"

        try:
            cache_file.write_text(json.dumps(parsed_data, indent=2))
        except Exception as e:
            # Cache write failure shouldn't break parsing
            print(f"Warning: Failed to write AST cache: {e}")

    def get_ai_cache(self, code_element: str, model: str) -> Optional[str]:
        """
        Get cached AI explanation.

        Args:
            code_element: Code element to explain (function signature, etc.)
            model: LLM model used

        Returns:
            Cached explanation or None if not available/expired
        """
        cache_key = hashlib.sha256(f"{code_element}:{model}".encode()).hexdigest()
        cache_file = self.ai_cache_dir / f"{cache_key}.txt"

        if cache_file.exists() and self._is_fresh(cache_file):
            return cache_file.read_text()

        return None

    def set_ai_cache(self, code_element: str, model: str, explanation: str) -> None:
        """
        Save AI-generated explanation to cache.

        Args:
            code_element: Code element that was explained
            model: LLM model used
            explanation: Generated explanation
        """
        cache_key = hashlib.sha256(f"{code_element}:{model}".encode()).hexdigest()
        cache_file = self.ai_cache_dir / f"{cache_key}.txt"

        try:
            cache_file.write_text(explanation)
        except Exception as e:
            # Cache write failure shouldn't break generation
            print(f"Warning: Failed to write AI cache: {e}")

    def clear_cache(self, cache_type: Optional[str] = None) -> int:
        """
        Clear cache files.

        Args:
            cache_type: Type of cache to clear ('ast', 'ai', or None for both)

        Returns:
            Number of files deleted
        """
        deleted = 0

        if cache_type in (None, 'ast'):
            for cache_file in self.ast_cache_dir.glob('*.json'):
                cache_file.unlink()
                deleted += 1

        if cache_type in (None, 'ai'):
            for cache_file in self.ai_cache_dir.glob('*.txt'):
                cache_file.unlink()
                deleted += 1

        return deleted

    def clear_expired_cache(self) -> int:
        """
        Remove expired cache entries.

        Returns:
            Number of files deleted
        """
        deleted = 0

        # Check AST cache
        for cache_file in self.ast_cache_dir.glob('*.json'):
            if not self._is_fresh(cache_file):
                cache_file.unlink()
                deleted += 1

        # Check AI cache
        for cache_file in self.ai_cache_dir.glob('*.txt'):
            if not self._is_fresh(cache_file):
                cache_file.unlink()
                deleted += 1

        return deleted

    def get_cache_stats(self) -> Dict[str, Any]:
        """
        Get cache statistics.

        Returns:
            Dictionary with cache stats
        """
        ast_files = list(self.ast_cache_dir.glob('*.json'))
        ai_files = list(self.ai_cache_dir.glob('*.txt'))

        ast_size = sum(f.stat().st_size for f in ast_files)
        ai_size = sum(f.stat().st_size for f in ai_files)

        # Count fresh vs expired
        ast_fresh = sum(1 for f in ast_files if self._is_fresh(f))
        ai_fresh = sum(1 for f in ai_files if self._is_fresh(f))

        return {
            'ast_cache': {
                'total_files': len(ast_files),
                'fresh_files': ast_fresh,
                'expired_files': len(ast_files) - ast_fresh,
                'total_size_bytes': ast_size,
                'total_size_mb': round(ast_size / (1024 * 1024), 2)
            },
            'ai_cache': {
                'total_files': len(ai_files),
                'fresh_files': ai_fresh,
                'expired_files': len(ai_files) - ai_fresh,
                'total_size_bytes': ai_size,
                'total_size_mb': round(ai_size / (1024 * 1024), 2)
            }
        }

    def _file_hash(self, file_path: str) -> str:
        """
        Generate hash of file contents.

        Args:
            file_path: Path to file

        Returns:
            SHA256 hash of file contents
        """
        try:
            content = Path(file_path).read_bytes()
            return hashlib.sha256(content).hexdigest()
        except Exception:
            # If file can't be read, use path hash
            return hashlib.sha256(file_path.encode()).hexdigest()

    def _is_fresh(self, cache_file: Path) -> bool:
        """
        Check if cache file is within expiry period.

        Args:
            cache_file: Path to cache file

        Returns:
            True if cache is fresh, False if expired
        """
        try:
            mtime = datetime.fromtimestamp(cache_file.stat().st_mtime)
            return datetime.now() - mtime < self.expiry
        except Exception:
            return False
