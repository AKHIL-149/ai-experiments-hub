import json
import os
import time

from core.cache_manager import CacheManager


def make(tmp_path, **kw):
    return CacheManager(cache_dir=str(tmp_path / "cache"), **kw)


class TestTranscriptionCache:
    def test_round_trip(self, tmp_path):
        cache = make(tmp_path)
        cache.set_transcription("abc", {"text": "hello", "duration": 60})
        assert cache.get_transcription("abc")["text"] == "hello"
        assert cache.get_transcription("missing") is None

    def test_variants_are_separate_entries(self, tmp_path):
        # The same audio transcribed with another model or language is a different
        # result; it used to come back as whatever was cached first.
        cache = make(tmp_path)
        cache.set_transcription("abc", {"text": "english"}, variant="whisper-cpp_base.en_default")
        cache.set_transcription("abc", {"text": "espanol"}, variant="whisper-cpp_base_es")
        assert cache.get_transcription("abc", "whisper-cpp_base.en_default")["text"] == "english"
        assert cache.get_transcription("abc", "whisper-cpp_base_es")["text"] == "espanol"
        assert cache.get_transcription("abc", "openai_whisper-1_default") is None
        assert cache.get_transcription("abc") is None

    def test_variant_cannot_escape_the_cache_directory(self, tmp_path):
        cache = make(tmp_path)
        cache.set_transcription("abc", {"text": "x"}, variant="../../evil/../name")
        files = list((tmp_path / "cache").rglob("*.json"))
        assert len(files) == 1
        assert (tmp_path / "cache" / "transcriptions") in files[0].parents

    def test_writes_are_atomic_and_leave_no_temp_files(self, tmp_path):
        cache = make(tmp_path)
        cache.set_transcription("abc", {"text": "x"})
        cache.set_summary("hash", "model", {"summary": "s"}, level="brief")
        leftovers = [p for p in (tmp_path / "cache").rglob("*") if p.suffix == ".tmp"]
        assert leftovers == []

    def test_corrupt_entry_is_a_miss_not_an_error(self, tmp_path):
        cache = make(tmp_path)
        (tmp_path / "cache" / "transcriptions" / "abc.json").write_text("{ not json")
        assert cache.get_transcription("abc") is None
        cache.set_transcription("abc", {"text": "fixed"})
        assert cache.get_transcription("abc")["text"] == "fixed"

    def test_expired_entry_is_removed(self, tmp_path):
        cache = make(tmp_path, transcription_ttl_days=1)
        cache.set_transcription("abc", {"text": "old"})
        f = tmp_path / "cache" / "transcriptions" / "abc.json"
        old = time.time() - 3 * 86400
        os.utime(f, (old, old))
        assert cache.get_transcription("abc") is None
        assert not f.exists()

    def test_stats(self, tmp_path):
        cache = make(tmp_path)
        cache.set_transcription("abc", {"text": "x", "duration": 600})
        cache.get_transcription("abc"); cache.get_transcription("zzz")
        stats = cache.get_stats()
        assert stats["transcription"]["hits"] == 1 and stats["transcription"]["misses"] == 1
        assert stats["estimated_cost_saved_usd"] == 0.06


class TestSummaryCache:
    def test_levels_do_not_evict_each_other(self, tmp_path):
        cache = make(tmp_path)
        for level in ("brief", "standard", "detailed"):
            cache.set_summary("h", "llama3.2:3b", {"summary": level, "level": level}, level=level)
        for level in ("brief", "standard", "detailed"):
            assert cache.get_summary("h", "llama3.2:3b", level=level)["summary"] == level

    def test_model_is_part_of_the_key(self, tmp_path):
        cache = make(tmp_path)
        cache.set_summary("h", "a/b:c", {"summary": "x"}, level="brief")
        assert cache.get_summary("h", "a/b:c", level="brief") is not None
        assert cache.get_summary("h", "other", level="brief") is None

    def test_cleanup_and_clear(self, tmp_path):
        cache = make(tmp_path, summary_ttl_days=1)
        cache.set_summary("h", "m", {"summary": "x"}, level="brief")
        f = next((tmp_path / "cache" / "summaries").glob("*.json"))
        old = time.time() - 3 * 86400
        os.utime(f, (old, old))
        cache.set_transcription("keep", {"text": "x"})
        assert cache.cleanup_expired()["removed_summaries"] == 1
        cache.clear_all()
        assert list((tmp_path / "cache").rglob("*.json")) == []

    def test_hash_text_is_stable(self):
        assert CacheManager.hash_text("a") == CacheManager.hash_text("a") != CacheManager.hash_text("b")
