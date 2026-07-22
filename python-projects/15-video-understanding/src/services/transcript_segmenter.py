"""
Transcript segmentation service
Segments transcripts by sentences, topics, and semantic boundaries
"""

import logging
from typing import List, Optional, Dict, Tuple
from dataclasses import dataclass
import re

logger = logging.getLogger(__name__)


@dataclass
class TranscriptSegment:
    """A segment of transcript text"""
    id: int
    start: float
    end: float
    text: str
    segment_type: str  # sentence, paragraph, topic
    speaker: Optional[str] = None
    keywords: Optional[List[str]] = None
    metadata: Optional[Dict[str, any]] = None


class TranscriptSegmenter:
    """
    Segment transcripts into meaningful units
    Supports sentence, paragraph, and topic-based segmentation
    """

    def __init__(self):
        """Initialize transcript segmenter"""
        pass

    def segment_by_sentences(
        self,
        transcription_segments: List,
        merge_short: bool = True,
        min_words: int = 3
    ) -> List[TranscriptSegment]:
        """
        Segment transcript by sentences

        Args:
            transcription_segments: List of transcription segments
            merge_short: Merge very short sentences
            min_words: Minimum words for a segment

        Returns:
            List of sentence segments
        """
        logger.info(f"Segmenting {len(transcription_segments)} transcript segments by sentences")

        sentences = []

        for trans_seg in transcription_segments:
            # Split text into sentences
            text_sentences = self._split_sentences(trans_seg.text)

            # Calculate approximate timing for each sentence
            if len(text_sentences) > 1:
                duration = trans_seg.end - trans_seg.start
                chars_total = sum(len(s) for s in text_sentences)

                current_time = trans_seg.start

                for idx, sent in enumerate(text_sentences):
                    # Estimate duration based on character count
                    sent_duration = (len(sent) / chars_total) * duration if chars_total > 0 else duration / len(text_sentences)
                    sent_end = min(current_time + sent_duration, trans_seg.end)

                    segment = TranscriptSegment(
                        id=len(sentences),
                        start=current_time,
                        end=sent_end,
                        text=sent.strip(),
                        segment_type='sentence',
                        speaker=getattr(trans_seg, 'speaker', None),
                        metadata={'original_segment_id': trans_seg.id}
                    )

                    sentences.append(segment)
                    current_time = sent_end
            else:
                # Single sentence
                segment = TranscriptSegment(
                    id=len(sentences),
                    start=trans_seg.start,
                    end=trans_seg.end,
                    text=trans_seg.text.strip(),
                    segment_type='sentence',
                    speaker=getattr(trans_seg, 'speaker', None),
                    metadata={'original_segment_id': trans_seg.id}
                )
                sentences.append(segment)

        # Merge short sentences if requested
        if merge_short:
            sentences = self._merge_short_segments(sentences, min_words)

        # Renumber
        for idx, seg in enumerate(sentences):
            seg.id = idx

        logger.info(f"Created {len(sentences)} sentence segments")

        return sentences

    def segment_by_paragraphs(
        self,
        transcription_segments: List,
        pause_threshold: float = 2.0,
        speaker_change: bool = True
    ) -> List[TranscriptSegment]:
        """
        Segment transcript by paragraphs

        Args:
            transcription_segments: List of transcription segments
            pause_threshold: Pause duration to indicate paragraph break
            speaker_change: Break on speaker changes

        Returns:
            List of paragraph segments
        """
        logger.info("Segmenting transcript by paragraphs")

        if not transcription_segments:
            return []

        paragraphs = []
        current_paragraph = {
            'start': transcription_segments[0].start,
            'end': transcription_segments[0].end,
            'text': transcription_segments[0].text,
            'speaker': getattr(transcription_segments[0], 'speaker', None),
            'segments': [0]
        }

        for idx in range(1, len(transcription_segments)):
            prev_seg = transcription_segments[idx - 1]
            curr_seg = transcription_segments[idx]

            # Check for paragraph break
            pause = curr_seg.start - prev_seg.end
            speaker_changed = (
                speaker_change and
                hasattr(prev_seg, 'speaker') and
                hasattr(curr_seg, 'speaker') and
                prev_seg.speaker != curr_seg.speaker
            )

            if pause > pause_threshold or speaker_changed:
                # Save current paragraph
                paragraph = TranscriptSegment(
                    id=len(paragraphs),
                    start=current_paragraph['start'],
                    end=current_paragraph['end'],
                    text=current_paragraph['text'].strip(),
                    segment_type='paragraph',
                    speaker=current_paragraph['speaker'],
                    metadata={
                        'num_segments': len(current_paragraph['segments']),
                        'segment_ids': current_paragraph['segments']
                    }
                )
                paragraphs.append(paragraph)

                # Start new paragraph
                current_paragraph = {
                    'start': curr_seg.start,
                    'end': curr_seg.end,
                    'text': curr_seg.text,
                    'speaker': getattr(curr_seg, 'speaker', None),
                    'segments': [idx]
                }
            else:
                # Continue current paragraph
                current_paragraph['end'] = curr_seg.end
                current_paragraph['text'] += ' ' + curr_seg.text
                current_paragraph['segments'].append(idx)

        # Add last paragraph
        if current_paragraph['text']:
            paragraph = TranscriptSegment(
                id=len(paragraphs),
                start=current_paragraph['start'],
                end=current_paragraph['end'],
                text=current_paragraph['text'].strip(),
                segment_type='paragraph',
                speaker=current_paragraph['speaker'],
                metadata={
                    'num_segments': len(current_paragraph['segments']),
                    'segment_ids': current_paragraph['segments']
                }
            )
            paragraphs.append(paragraph)

        logger.info(f"Created {len(paragraphs)} paragraph segments")

        return paragraphs

    def segment_by_topics(
        self,
        transcription_segments: List,
        num_topics: Optional[int] = None,
        window_size: int = 5
    ) -> List[TranscriptSegment]:
        """
        Segment transcript by topics using semantic similarity

        Args:
            transcription_segments: List of transcription segments
            num_topics: Optional number of topics
            window_size: Window size for topic detection

        Returns:
            List of topic segments
        """
        logger.info("Segmenting transcript by topics")

        # Fallback to paragraph-based segmentation
        # In production, this would use NLP models for topic detection
        logger.info("Using paragraph-based segmentation as topic proxy")

        paragraphs = self.segment_by_paragraphs(transcription_segments)

        # Group paragraphs into topics using simple keyword similarity
        topics = self._group_paragraphs_by_similarity(
            paragraphs,
            num_topics=num_topics
        )

        logger.info(f"Created {len(topics)} topic segments")

        return topics

    def _split_sentences(self, text: str) -> List[str]:
        """
        Split text into sentences

        Args:
            text: Input text

        Returns:
            List of sentences
        """
        # Simple sentence splitting using regex
        # Splits on . ! ? followed by space and capital letter
        sentence_pattern = r'(?<=[.!?])\s+(?=[A-Z])'
        sentences = re.split(sentence_pattern, text)

        # Also split on . ! ? at end of string
        result = []
        for sent in sentences:
            sent = sent.strip()
            if sent:
                result.append(sent)

        return result if result else [text]

    def _merge_short_segments(
        self,
        segments: List[TranscriptSegment],
        min_words: int = 3
    ) -> List[TranscriptSegment]:
        """
        Merge very short segments with adjacent ones

        Args:
            segments: List of segments
            min_words: Minimum words threshold

        Returns:
            List of merged segments
        """
        if not segments:
            return []

        merged = []
        current = segments[0]

        for i in range(1, len(segments)):
            next_seg = segments[i]

            # Check if current is too short
            word_count = len(current.text.split())

            if word_count < min_words:
                # Merge with next
                current = TranscriptSegment(
                    id=current.id,
                    start=current.start,
                    end=next_seg.end,
                    text=f"{current.text} {next_seg.text}",
                    segment_type=current.segment_type,
                    speaker=current.speaker,
                    metadata=current.metadata
                )
            else:
                # Save current and start new
                merged.append(current)
                current = next_seg

        # Add last segment
        merged.append(current)

        return merged

    def _group_paragraphs_by_similarity(
        self,
        paragraphs: List[TranscriptSegment],
        num_topics: Optional[int] = None
    ) -> List[TranscriptSegment]:
        """
        Group paragraphs into topics using keyword similarity

        Args:
            paragraphs: List of paragraph segments
            num_topics: Optional number of topics

        Returns:
            List of topic segments
        """
        # Simple keyword-based grouping
        # In production, use embeddings and clustering

        topics = []
        current_topic = {
            'start': paragraphs[0].start,
            'end': paragraphs[0].end,
            'text': paragraphs[0].text,
            'speaker': paragraphs[0].speaker,
            'paragraphs': [0]
        }

        for idx in range(1, len(paragraphs)):
            para = paragraphs[idx]

            # Simple heuristic: start new topic if speaker changes significantly
            # or paragraph is very different in length
            prev_para = paragraphs[idx - 1]

            # Calculate simple similarity
            should_merge = True

            # Split into new topic if speaker changes
            if para.speaker != prev_para.speaker and para.speaker is not None:
                should_merge = False

            if should_merge:
                # Continue current topic
                current_topic['end'] = para.end
                current_topic['text'] += '\n\n' + para.text
                current_topic['paragraphs'].append(idx)
            else:
                # Save current topic
                topic = TranscriptSegment(
                    id=len(topics),
                    start=current_topic['start'],
                    end=current_topic['end'],
                    text=current_topic['text'].strip(),
                    segment_type='topic',
                    speaker=current_topic['speaker'],
                    metadata={
                        'num_paragraphs': len(current_topic['paragraphs']),
                        'paragraph_ids': current_topic['paragraphs']
                    }
                )
                topics.append(topic)

                # Start new topic
                current_topic = {
                    'start': para.start,
                    'end': para.end,
                    'text': para.text,
                    'speaker': para.speaker,
                    'paragraphs': [idx]
                }

        # Add last topic
        if current_topic['text']:
            topic = TranscriptSegment(
                id=len(topics),
                start=current_topic['start'],
                end=current_topic['end'],
                text=current_topic['text'].strip(),
                segment_type='topic',
                speaker=current_topic['speaker'],
                metadata={
                    'num_paragraphs': len(current_topic['paragraphs']),
                    'paragraph_ids': current_topic['paragraphs']
                }
            )
            topics.append(topic)

        return topics

    def extract_keywords(
        self,
        segment: TranscriptSegment,
        num_keywords: int = 5
    ) -> List[str]:
        """
        Extract keywords from segment

        Args:
            segment: TranscriptSegment
            num_keywords: Number of keywords to extract

        Returns:
            List of keywords
        """
        # Simple keyword extraction using word frequency
        # Filter common words and short words

        stopwords = {
            'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for',
            'of', 'with', 'is', 'was', 'are', 'were', 'be', 'been', 'being',
            'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would', 'could',
            'should', 'may', 'might', 'can', 'this', 'that', 'these', 'those',
            'i', 'you', 'he', 'she', 'it', 'we', 'they', 'my', 'your', 'his',
            'her', 'its', 'our', 'their'
        }

        # Tokenize and clean
        words = re.findall(r'\b[a-zA-Z]+\b', segment.text.lower())

        # Filter stopwords and short words
        words = [w for w in words if w not in stopwords and len(w) > 3]

        # Count frequency
        from collections import Counter
        word_freq = Counter(words)

        # Get top keywords
        keywords = [word for word, _ in word_freq.most_common(num_keywords)]

        return keywords

    def get_segment_summary(
        self,
        segment: TranscriptSegment,
        max_length: int = 100
    ) -> str:
        """
        Get summary of segment

        Args:
            segment: TranscriptSegment
            max_length: Maximum summary length

        Returns:
            Summary text
        """
        text = segment.text.strip()

        if len(text) <= max_length:
            return text

        # Simple truncation with ellipsis
        # In production, use extractive/abstractive summarization
        return text[:max_length - 3] + '...'

    def save_segments(
        self,
        segments: List[TranscriptSegment],
        output_path,
        format: str = 'json'
    ):
        """
        Save segments to file

        Args:
            segments: List of segments
            output_path: Output file path
            format: Output format (json, txt)
        """
        logger.info(f"Saving {len(segments)} segments to {output_path}")

        if format == 'json':
            import json

            data = {
                'segments': [
                    {
                        'id': s.id,
                        'start': s.start,
                        'end': s.end,
                        'text': s.text,
                        'type': s.segment_type,
                        'speaker': s.speaker,
                        'keywords': s.keywords,
                        'metadata': s.metadata
                    }
                    for s in segments
                ]
            }

            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)

        else:  # txt
            with open(output_path, 'w', encoding='utf-8') as f:
                for segment in segments:
                    timestamp = self._format_timestamp(segment.start)
                    speaker_prefix = f"[{segment.speaker}] " if segment.speaker else ""
                    f.write(f"[{timestamp}] {speaker_prefix}{segment.text}\n\n")

        logger.info(f"Segments saved to {output_path}")

    def _format_timestamp(self, seconds: float) -> str:
        """Format timestamp as HH:MM:SS"""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)

        return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def segment_transcript(
    transcription_segments: List,
    method: str = 'sentence'
) -> List[TranscriptSegment]:
    """
    Convenience function to segment transcript

    Args:
        transcription_segments: List of transcription segments
        method: Segmentation method (sentence, paragraph, topic)

    Returns:
        List of transcript segments
    """
    segmenter = TranscriptSegmenter()

    if method == 'sentence':
        return segmenter.segment_by_sentences(transcription_segments)
    elif method == 'paragraph':
        return segmenter.segment_by_paragraphs(transcription_segments)
    elif method == 'topic':
        return segmenter.segment_by_topics(transcription_segments)
    else:
        raise ValueError(f"Unknown segmentation method: {method}")
