"""Summarizer - AI-powered meeting summarization with map-reduce for long transcripts"""

import logging
import re
from typing import Dict, List, Optional
from .llm_client import LLMClient

logger = logging.getLogger(__name__)

# Rules every prompt shares. Small local models happily fill gaps: they describe a
# "meeting" for an audiobook, add participants, and invent decisions or owners.
GROUNDING_RULES = """Rules:
- Use ONLY what is in the transcript. Never invent participants, names, decisions, owners, numbers or dates.
- If something is not stated, leave it out (or say it was not discussed).
- If the recording is not a meeting (a story, lecture, interview or monologue), say what it actually is and summarize its content - do not describe a meeting that did not happen.
- Speech recognition makes mistakes; do not build conclusions on a single odd-looking word."""

# Lines that introduce a list rather than being an item of it ("Here are the 10 main topics:")
_PREAMBLE = re.compile(r'^(here (are|is)|sure|okay|certainly|the (main|key|most important) topics|topics?\b.*:$)', re.I)


class Summarizer:
    """
    Generate meeting summaries using AI with map-reduce strategy for long transcripts.

    Strategy:
    1. Short transcripts (<4000 words): Direct summarization
    2. Long transcripts (>4000 words): Map-reduce approach
       - Split into chunks
       - Summarize each chunk (map)
       - Combine summaries (reduce)
    """

    def __init__(self, llm_client: LLMClient, chunk_size_words: int = 3000):
        """
        Initialize Summarizer

        Args:
            llm_client: LLM client instance
            chunk_size_words: Size of text chunks for map-reduce
        """
        self.llm_client = llm_client
        self.chunk_size_words = chunk_size_words

    def summarize(
        self,
        transcript: str,
        level: str = "standard",
        include_timestamps: bool = False
    ) -> Dict:
        """
        Generate meeting summary

        Args:
            transcript: Full meeting transcript
            level: Summary detail level ("brief", "standard", "detailed")
            include_timestamps: Whether to include timestamps (if available)

        Returns:
            dict with summary and metadata:
                {
                    "summary": str,
                    "level": str,
                    "word_count": int,
                    "chunks_processed": int,
                    "tokens_used": dict,
                    "estimated_cost": float
                }
        """
        if not transcript or not transcript.strip():
            raise ValueError("There is no transcript to summarize")
        if level not in ("brief", "standard", "detailed"):
            raise ValueError(f"Unknown summary level '{level}'. Use brief, standard or detailed.")

        word_count = len(transcript.split())
        logger.info(f"Summarizing transcript: {word_count} words, level={level}")

        # Choose strategy based on transcript length
        if word_count <= self.chunk_size_words:
            logger.info("Using direct summarization (short transcript)")
            result = self._summarize_direct(transcript, level)
            chunks_processed = 1
        else:
            logger.info("Using map-reduce summarization (long transcript)")
            result = self._summarize_map_reduce(transcript, level)
            chunks_processed = result.get("chunks_processed", 0)

        return {
            "summary": result["text"],
            "level": level,
            "word_count": word_count,
            "chunks_processed": chunks_processed,
            "tokens_used": result.get("tokens", {}),
            "estimated_cost": result.get("cost", 0.0)
        }

    def _summarize_direct(self, transcript: str, level: str) -> Dict:
        """
        Direct summarization for short transcripts

        Args:
            transcript: Meeting transcript
            level: Summary level

        Returns:
            dict with text, tokens, and cost
        """
        system_prompt = self._get_system_prompt(level)
        user_prompt = self._format_transcript_prompt(transcript)

        response = self.llm_client.generate(
            prompt=user_prompt,
            max_tokens=self._get_max_tokens(level),
            temperature=0.3,  # Lower temperature for factual summarization
            system_prompt=system_prompt
        )

        cost = self.llm_client.estimate_cost(response["tokens"])

        return {
            "text": response["text"],
            "tokens": response["tokens"],
            "cost": cost
        }

    def _summarize_map_reduce(self, transcript: str, level: str) -> Dict:
        """
        Map-reduce summarization for long transcripts

        Strategy:
        1. Map: Split transcript into chunks and summarize each
        2. Reduce: Combine chunk summaries into final summary

        Args:
            transcript: Long meeting transcript
            level: Summary level

        Returns:
            dict with text, tokens, cost, and chunks_processed
        """
        # Step 1: Split transcript into chunks
        chunks = self._split_into_chunks(transcript)
        logger.info(f"Split transcript into {len(chunks)} chunks")

        # Step 2: Map - Summarize each chunk
        chunk_summaries = []
        total_tokens = {"prompt": 0, "completion": 0, "total": 0}

        for i, chunk in enumerate(chunks):
            logger.info(f"Summarizing chunk {i+1}/{len(chunks)}")

            system_prompt = f"""You are summarizing a section of a longer recording's transcript.
Focus on key points, decisions, and important discussions.
Be concise but don't lose critical information.

{GROUNDING_RULES}"""

            user_prompt = f"""Summarize this portion of a transcript:

{chunk}

Provide a concise summary focusing on:
- Main topics discussed
- Key points and decisions
- Important action items or commitments
"""

            response = self.llm_client.generate(
                prompt=user_prompt,
                max_tokens=800,
                temperature=0.3,
                system_prompt=system_prompt
            )

            chunk_summaries.append(response["text"])

            # Accumulate token usage
            for key in total_tokens:
                total_tokens[key] += response["tokens"].get(key, 0)

        # Step 3: Reduce - Combine chunk summaries into final summary
        logger.info("Combining chunk summaries into final summary")

        combined_text = "\n\n---\n\n".join([
            f"Section {i+1}:\n{summary}"
            for i, summary in enumerate(chunk_summaries)
        ])

        system_prompt = self._get_system_prompt(level)
        user_prompt = f"""Below are summaries of different sections of a meeting transcript.
Create a cohesive final summary that synthesizes all sections.

{combined_text}

Provide a {level} summary of the entire meeting."""

        final_response = self.llm_client.generate(
            prompt=user_prompt,
            max_tokens=self._get_max_tokens(level),
            temperature=0.3,
            system_prompt=system_prompt
        )

        # Accumulate final tokens
        for key in total_tokens:
            total_tokens[key] += final_response["tokens"].get(key, 0)

        cost = self.llm_client.estimate_cost(total_tokens)

        return {
            "text": final_response["text"],
            "tokens": total_tokens,
            "cost": cost,
            "chunks_processed": len(chunks)
        }

    def _split_into_chunks(self, text: str) -> List[str]:
        """
        Split text into chunks of at most chunk_size_words words, breaking between lines
        (the transcript has one segment per line) so a sentence is not cut in half.
        A single line longer than a chunk is split by words.

        Args:
            text: Text to split

        Returns:
            List of text chunks
        """
        chunks: List[str] = []
        current: List[str] = []
        size = 0

        def flush():
            nonlocal current, size
            if current:
                chunks.append("\n".join(current))
            current, size = [], 0

        for line in text.split("\n"):
            words = line.split()
            if not words:
                continue

            if len(words) > self.chunk_size_words:
                flush()
                for i in range(0, len(words), self.chunk_size_words):
                    chunks.append(" ".join(words[i:i + self.chunk_size_words]))
                continue

            if size + len(words) > self.chunk_size_words:
                flush()
            current.append(line.strip())
            size += len(words)

        flush()
        return chunks

    def _get_system_prompt(self, level: str) -> str:
        """Get system prompt based on summary level"""
        base = f"""You are an expert meeting summarizer. Your task is to create clear, accurate summaries of meeting transcripts.

{GROUNDING_RULES}"""

        if level == "brief":
            return base + """

Create a BRIEF summary (2-3 paragraphs) covering:
- Main purpose of the meeting
- Key decisions made
- Critical action items

Be extremely concise."""

        elif level == "detailed":
            return base + """

Create a DETAILED summary covering:
- Meeting context and participants
- All major topics discussed
- Key points and arguments for each topic
- All decisions made with rationale
- All action items with owners and deadlines
- Important follow-up items
- Any risks or concerns raised

Be thorough and comprehensive."""

        else:  # standard
            return base + """

Create a STANDARD summary covering:
- Meeting overview and main topics
- Key discussions and decisions
- Action items and next steps
- Important takeaways

Balance detail with readability."""

    def _format_transcript_prompt(self, transcript: str) -> str:
        """Format transcript into prompt"""
        return f"""Please summarize the following meeting transcript:

{transcript}

Provide a clear, well-structured summary."""

    def _get_max_tokens(self, level: str) -> int:
        """Get max tokens based on summary level"""
        token_limits = {
            "brief": 500,
            "standard": 1500,
            "detailed": 3000
        }
        return token_limits.get(level, 1500)

    def generate_multi_level_summary(self, transcript: str) -> Dict:
        """
        Generate all three summary levels

        Args:
            transcript: Meeting transcript

        Returns:
            dict with all summary levels:
                {
                    "brief": {...},
                    "standard": {...},
                    "detailed": {...},
                    "total_cost": float
                }
        """
        logger.info("Generating multi-level summaries")

        results = {}
        total_cost = 0.0

        for level in ["brief", "standard", "detailed"]:
            logger.info(f"Generating {level} summary")
            result = self.summarize(transcript, level=level)
            results[level] = result
            total_cost += result.get("estimated_cost", 0.0)

        results["total_cost"] = total_cost

        return results

    def extract_key_topics(self, transcript: str, max_topics: int = 10) -> List[str]:
        """
        Extract key topics discussed in meeting

        A transcript longer than one prompt can hold is handled a chunk at a time (the
        model only ever sees what fits) and the per-chunk topics are merged.

        Args:
            transcript: Meeting transcript
            max_topics: Maximum number of topics to extract

        Returns:
            List of topic strings
        """
        chunks = self._split_into_chunks(transcript)
        if not chunks:
            return []

        if len(chunks) == 1:
            return self._topics_from_text(chunks[0], max_topics)

        per_chunk = max(3, -(-max_topics * 2 // len(chunks)))   # ceil: a fair share, at least 3
        merged: List[str] = []
        seen = set()
        for chunk in chunks:
            for topic in self._topics_from_text(chunk, per_chunk):
                key = re.sub(r'\W+', ' ', topic.lower()).strip()
                if key and key not in seen:
                    seen.add(key)
                    merged.append(topic)

        return merged[:max_topics]

    def _topics_from_text(self, text: str, max_topics: int) -> List[str]:
        system_prompt = f"""You are an expert at identifying key topics in transcripts.

{GROUNDING_RULES}"""

        user_prompt = f"""Analyze this transcript and extract the main topics discussed.

{text}

List the {max_topics} most important topics discussed, one per line.
Format: Just the topic name, no numbers or bullets, no introduction."""

        response = self.llm_client.generate(
            prompt=user_prompt,
            max_tokens=500,
            temperature=0.3,
            system_prompt=system_prompt
        )

        return self._parse_topic_lines(response["text"], max_topics)

    @staticmethod
    def _parse_topic_lines(text: str, max_topics: int) -> List[str]:
        """
        One topic per line. Models add bullets or numbers ("- topic", "1. topic") and an
        introduction ("Here are the main topics:") despite being told not to: strip the
        first, drop the second. (Bulleted lines used to be thrown away, leaving no topics.)
        """
        topics = []
        for line in text.split("\n"):
            line = re.sub(r'\*\*(.+?)\*\*', r'\1', line.strip())                  # **bold**
            line = re.sub(r'^(?:[-*#\u2022]+\s+|\d+[.)]\s+)', '', line).strip(' "\'')   # bullets, numbers
            if not line or _PREAMBLE.match(line) or line.endswith(':'):
                continue
            topics.append(line)
        return topics[:max_topics]

    def extract_speaker_key_points(
        self, speaker_transcript: List[Dict], max_points: int = 3
    ) -> Dict[str, List[str]]:
        """
        Extract each speaker's key points from their attributed transcript
        lines (see SpeakerDiarization.assign_transcript_to_speakers) - one
        LLM call per speaker, since each needs its own prompt/response.

        Args:
            speaker_transcript: Speaker-attributed segments, each with at
                least 'speaker' and 'text' keys
            max_points: Maximum key points to extract per speaker

        Returns:
            {"Speaker 1": ["point one", "point two", ...], ...} - a speaker
            with no substantive text is omitted rather than given an empty list
        """
        lines_by_speaker: Dict[str, List[str]] = {}
        for seg in speaker_transcript:
            lines_by_speaker.setdefault(seg['speaker'], []).append(seg['text'])

        system_prompt = (
            "You are an expert at distilling what one meeting participant "
            "said into their key points."
        )

        key_points: Dict[str, List[str]] = {}
        for speaker, lines in lines_by_speaker.items():
            text = " ".join(line.strip() for line in lines if line.strip())
            if not text:
                continue

            user_prompt = f"""Below are all the lines spoken by one meeting participant ({speaker}).

{text}

List up to {max_points} of the most important points this person made, one per line.
Format: just the point itself, no numbering or bullets. If they made fewer than {max_points} substantive points, list only those. If they made no substantive point (e.g. only small talk or a greeting), respond with NONE."""

            response = self.llm_client.generate(
                prompt=user_prompt,
                max_tokens=300,
                temperature=0.3,
                system_prompt=system_prompt
            )

            # Same clean-up as topics: bullets and numbers stripped, "Here are the points:" dropped
            points = [p for p in self._parse_topic_lines(response["text"], max_points + 5) if p.upper() != 'NONE']

            if points:
                key_points[speaker] = points[:max_points]

        return key_points
