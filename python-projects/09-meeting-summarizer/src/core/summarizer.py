"""Summarizer - AI-powered meeting summarization with map-reduce for long transcripts"""

import logging
from typing import Dict, List, Optional
from .llm_client import LLMClient

logger = logging.getLogger(__name__)


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

            system_prompt = """You are summarizing a section of a meeting transcript.
Focus on key points, decisions, and important discussions.
Be concise but don't lose critical information."""

            user_prompt = f"""Summarize this portion of a meeting transcript:

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
        Split text into chunks by word count

        Tries to split on paragraph boundaries when possible.

        Args:
            text: Text to split

        Returns:
            List of text chunks
        """
        words = text.split()
        chunks = []

        current_chunk = []
        current_size = 0

        for word in words:
            current_chunk.append(word)
            current_size += 1

            if current_size >= self.chunk_size_words:
                # Try to split on paragraph boundary (double newline)
                chunk_text = " ".join(current_chunk)

                # Look for paragraph break near the end
                last_paragraph = chunk_text.rfind("\n\n", -500)  # Look in last 500 chars

                if last_paragraph > len(chunk_text) * 0.7:  # If found in last 30%
                    # Split at paragraph
                    chunks.append(chunk_text[:last_paragraph])
                    # Start next chunk with remainder
                    remainder = chunk_text[last_paragraph:].strip()
                    current_chunk = remainder.split() if remainder else []
                    current_size = len(current_chunk)
                else:
                    # No good break point, split at chunk size
                    chunks.append(chunk_text)
                    current_chunk = []
                    current_size = 0

        # Add remaining text
        if current_chunk:
            chunks.append(" ".join(current_chunk))

        return chunks

    def _get_system_prompt(self, level: str) -> str:
        """Get system prompt based on summary level"""
        base = """You are an expert meeting summarizer. Your task is to create clear, accurate summaries of meeting transcripts."""

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

        Args:
            transcript: Meeting transcript
            max_topics: Maximum number of topics to extract

        Returns:
            List of topic strings
        """
        system_prompt = """You are an expert at identifying key topics in meeting transcripts."""

        user_prompt = f"""Analyze this meeting transcript and extract the main topics discussed.

{transcript}

List the {max_topics} most important topics discussed, one per line.
Format: Just the topic name, no numbers or bullets."""

        response = self.llm_client.generate(
            prompt=user_prompt,
            max_tokens=500,
            temperature=0.3,
            system_prompt=system_prompt
        )

        # Parse topics from response
        topics = [
            line.strip()
            for line in response["text"].split("\n")
            if line.strip() and not line.strip().startswith(("#", "-", "*"))
        ]

        return topics[:max_topics]
