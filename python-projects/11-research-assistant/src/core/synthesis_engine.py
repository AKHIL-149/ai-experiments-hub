"""
Synthesis Engine for Research Assistant.

Combines information from multiple sources using map-reduce pattern:
1. Map: Extract key points from each source
2. Reduce: Synthesize into coherent findings with confidence scoring
"""

import logging
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime
import hashlib


@dataclass
class Finding:
    """Research finding with confidence score."""
    finding_text: str
    finding_type: str  # fact, argument, statistic, definition, opinion
    confidence: float  # 0-1 confidence score
    source_ids: List[str]  # Supporting source IDs
    citations: List[Dict[str, Any]]  # Citation details
    contradictions: Optional[List[str]] = None  # Contradicting source IDs


class SynthesisEngine:
    """Synthesizes research findings from multiple sources."""

    # Minimum sources required for high-confidence findings
    MIN_SOURCES_FOR_HIGH_CONFIDENCE = 3

    # Confidence thresholds
    CONFIDENCE_HIGH = 0.8
    CONFIDENCE_MEDIUM = 0.6
    CONFIDENCE_LOW = 0.4

    def __init__(
        self,
        llm_client,
        min_sources: int = 3,
        confidence_threshold: float = 0.8,
        detect_contradictions: bool = True
    ):
        """
        Initialize synthesis engine.

        Args:
            llm_client: LLM client for synthesis
            min_sources: Minimum sources per finding for high confidence
            confidence_threshold: Minimum confidence to include finding
            detect_contradictions: Whether to detect contradictions
        """
        self.llm_client = llm_client
        self.min_sources = min_sources
        self.confidence_threshold = confidence_threshold
        self.detect_contradictions = detect_contradictions

        self.stats = {
            'total_sources': 0,
            'findings_generated': 0,
            'high_confidence_findings': 0,
            'contradictions_detected': 0
        }

        logging.info(
            f"SynthesisEngine initialized "
            f"(min_sources={min_sources}, threshold={confidence_threshold})"
        )

    def synthesize(
        self,
        query: str,
        ranked_sources: List[Dict[str, Any]],
        max_findings: int = 10
    ) -> Tuple[str, List[Finding]]:
        """
        Synthesize research findings from ranked sources.

        Args:
            query: Research query
            ranked_sources: List of ranked source dictionaries
            max_findings: Maximum number of findings to generate

        Returns:
            Tuple of (summary_text, findings_list)
        """
        self.stats['total_sources'] = len(ranked_sources)

        if not ranked_sources:
            return "No sources found for the query.", []

        # Step 1: Map - Extract key points from each source
        logging.info(f"Map phase: Extracting key points from {len(ranked_sources)} sources")
        source_extractions = self._map_extract_points(ranked_sources, query)

        # Step 2: Reduce - Synthesize into coherent findings
        logging.info("Reduce phase: Synthesizing findings")
        findings = self._reduce_synthesize_findings(
            query,
            source_extractions,
            ranked_sources,
            max_findings
        )

        # Step 3: Detect contradictions (optional)
        if self.detect_contradictions:
            logging.info("Detecting contradictions")
            self._detect_contradictions(findings, ranked_sources)

        # Step 4: Filter by confidence
        findings = [f for f in findings if f.confidence >= self.confidence_threshold]

        # Step 5: Generate summary text
        summary = self._generate_summary(query, findings, ranked_sources)

        # Update stats
        self.stats['findings_generated'] = len(findings)
        self.stats['high_confidence_findings'] = sum(
            1 for f in findings if f.confidence >= self.CONFIDENCE_HIGH
        )

        logging.info(
            f"Synthesis complete: {len(findings)} findings "
            f"({self.stats['high_confidence_findings']} high-confidence)"
        )

        return summary, findings

    def _map_extract_points(
        self,
        sources: List[Dict[str, Any]],
        query: str
    ) -> List[Dict[str, Any]]:
        """
        Map phase: Extract key points from each source.

        Args:
            sources: List of source dictionaries
            query: Research query

        Returns:
            List of extraction dictionaries
        """
        extractions = []

        for i, source in enumerate(sources):
            logging.debug(f"Extracting from source {i+1}/{len(sources)}: {source['title'][:50]}")

            # Prepare content (title + content, truncate if too long)
            content = f"Title: {source['title']}\n\n{source['content']}"
            max_length = 4000  # LLM context limit
            if len(content) > max_length:
                content = content[:max_length] + "..."

            # LLM prompt for extraction
            messages = [
                {
                    'role': 'system',
                    'content': (
                        'You are a research assistant extracting key information. '
                        'Extract the most important facts, arguments, statistics, and definitions '
                        'relevant to the research query. Be concise and accurate.'
                    )
                },
                {
                    'role': 'user',
                    'content': (
                        f"Research query: {query}\n\n"
                        f"Source content:\n{content}\n\n"
                        f"Extract 3-5 key points that are most relevant to the query. "
                        f"For each point, specify the type (fact/argument/statistic/definition) "
                        f"and provide a brief quote or paraphrase."
                    )
                }
            ]

            try:
                response = self.llm_client.generate(
                    messages,
                    max_tokens=500,
                    temperature=0.3  # Low temperature for factual extraction
                )

                extractions.append({
                    'source_id': source['id'],
                    'source_type': source['source_type'],
                    'source_title': source['title'],
                    'source_url': source.get('url'),
                    'extraction': response['content'],
                    'composite_score': source.get('composite_score', 0.0)
                })

            except Exception as e:
                logging.error(f"Failed to extract from source {source['id']}: {e}")
                continue

        logging.info(f"Extracted key points from {len(extractions)}/{len(sources)} sources")
        return extractions

    def _reduce_synthesize_findings(
        self,
        query: str,
        extractions: List[Dict[str, Any]],
        sources: List[Dict[str, Any]],
        max_findings: int
    ) -> List[Finding]:
        """
        Reduce phase: Synthesize extractions into coherent findings.

        Args:
            query: Research query
            extractions: Extracted key points
            sources: Original sources
            max_findings: Maximum findings to generate

        Returns:
            List of Finding objects
        """
        if not extractions:
            return []

        # Combine all extractions
        combined_extractions = "\n\n".join([
            f"Source {i+1} ({ext['source_type']} - {ext['source_title'][:50]}):\n{ext['extraction']}"
            for i, ext in enumerate(extractions)
        ])

        # LLM prompt for synthesis
        messages = [
            {
                'role': 'system',
                'content': (
                    'You are a research synthesizer. Analyze extracted key points from multiple sources '
                    'and synthesize them into coherent findings.\n\n'
                    'IMPORTANT: Use this EXACT format for each finding:\n\n'
                    'Finding: [State the finding in 1-2 clear sentences]\n'
                    'Type: [fact/argument/statistic/definition]\n'
                    'Sources: [1, 3, 5]\n'
                    'Confidence: [0.0-1.0]\n\n'
                    f'Requirements:\n'
                    f'- Only include findings supported by at least {self.min_sources} sources\n'
                    f'- Use confidence ≥{self.CONFIDENCE_HIGH} only when 3+ sources agree\n'
                    f'- Be specific and factual\n'
                    f'- Answer the research question directly'
                )
            },
            {
                'role': 'user',
                'content': (
                    f"Research query: {query}\n\n"
                    f"Extracted key points from {len(extractions)} sources:\n\n"
                    f"{combined_extractions}\n\n"
                    f"Provide up to {max_findings} key findings using the EXACT format shown above.\n"
                    f"Each finding MUST start with 'Finding:' and include Type, Sources, and Confidence."
                )
            }
        ]

        try:
            response = self.llm_client.generate(
                messages,
                max_tokens=2000,
                temperature=0.5
            )

            # DEBUG: Log the raw LLM output
            llm_output = response['content']
            logging.debug(f"LLM synthesis output (first 500 chars): {llm_output[:500]}")

            # Parse LLM response into Finding objects
            findings = self._parse_findings_from_llm(
                llm_output,
                extractions,
                sources
            )

            return findings

        except Exception as e:
            logging.error(f"Failed to synthesize findings: {e}")
            return []

    def _parse_findings_from_llm(
        self,
        llm_output: str,
        extractions: List[Dict[str, Any]],
        sources: List[Dict[str, Any]]
    ) -> List[Finding]:
        """
        Parse LLM output into Finding objects.

        Args:
            llm_output: LLM response text
            extractions: Source extractions
            sources: Original sources

        Returns:
            List of Finding objects
        """
        import re
        findings = []

        # Try structured parsing first
        lines = llm_output.strip().split('\n')
        current_finding = {}

        for line in lines:
            line = line.strip()
            if not line:
                # End of finding
                if current_finding.get('finding_text'):
                    finding = self._create_finding_from_dict(
                        current_finding,
                        extractions,
                        sources
                    )
                    if finding:
                        findings.append(finding)
                current_finding = {}
                continue

            # Parse fields (more flexible patterns)
            if line.startswith('Finding:') or line.startswith('-') or line.startswith('•') or line.startswith('*'):
                text = line.split(':', 1)[-1].strip().lstrip('-•* ')
                if text:
                    current_finding['finding_text'] = text
            elif 'type:' in line.lower():
                finding_type = line.split(':', 1)[-1].strip().lower()
                current_finding['finding_type'] = finding_type
            elif 'sources:' in line.lower() or 'source' in line.lower():
                # Extract source numbers
                source_nums = re.findall(r'\d+', line)
                current_finding['source_nums'] = [int(n) for n in source_nums]
            elif 'confidence:' in line.lower():
                # Extract confidence score
                conf_match = re.search(r'(\d+\.?\d*)', line)
                if conf_match:
                    confidence = float(conf_match.group(1))
                    # Normalize if >1
                    if confidence > 1.0:
                        confidence = confidence / 100.0
                    current_finding['confidence'] = confidence
            elif re.match(r'^\d+\.', line):
                # Numbered list item
                text = re.sub(r'^\d+\.\s*', '', line)
                if text and not current_finding.get('finding_text'):
                    current_finding['finding_text'] = text

        # Add last finding
        if current_finding.get('finding_text'):
            finding = self._create_finding_from_dict(
                current_finding,
                extractions,
                sources
            )
            if finding:
                findings.append(finding)

        # Fallback: If no findings parsed, create simple findings from sentences
        if not findings and llm_output:
            logging.warning("Structured parsing failed, using fallback paragraph extraction")
            findings = self._fallback_parse_findings(llm_output, extractions, sources)

        logging.info(f"Parsed {len(findings)} findings from LLM output")
        return findings

    def _create_finding_from_dict(
        self,
        finding_dict: Dict[str, Any],
        extractions: List[Dict[str, Any]],
        sources: List[Dict[str, Any]]
    ) -> Optional[Finding]:
        """Create Finding object from parsed dictionary."""
        try:
            # Map source numbers to source IDs
            source_nums = finding_dict.get('source_nums', [])
            source_ids = []
            citations = []

            for num in source_nums:
                idx = num - 1  # Convert to 0-indexed
                if 0 <= idx < len(extractions):
                    source_id = extractions[idx]['source_id']
                    source_ids.append(source_id)

                    # Add citation
                    citations.append({
                        'source_id': source_id,
                        'title': extractions[idx]['source_title'],
                        'url': extractions[idx].get('source_url'),
                        'type': extractions[idx]['source_type']
                    })

            # Adjust confidence based on source count
            confidence = finding_dict.get('confidence', 0.5)
            num_sources = len(source_ids)

            # Enforce strict confidence rules
            if num_sources < self.min_sources:
                # Reduce confidence if insufficient sources
                confidence = min(confidence, self.CONFIDENCE_MEDIUM)

            if num_sources >= self.min_sources and confidence < self.CONFIDENCE_HIGH:
                # Boost confidence if many sources agree
                confidence = self.CONFIDENCE_HIGH

            return Finding(
                finding_text=finding_dict['finding_text'],
                finding_type=finding_dict.get('finding_type', 'fact'),
                confidence=confidence,
                source_ids=source_ids,
                citations=citations
            )

        except Exception as e:
            logging.warning(f"Failed to create finding from dict: {e}")
            return None

    def _fallback_parse_findings(
        self,
        llm_output: str,
        extractions: List[Dict[str, Any]],
        sources: List[Dict[str, Any]]
    ) -> List[Finding]:
        """
        Fallback parser: Extract findings from free-form text.

        Used when structured parsing fails (small models, creative outputs).
        """
        import re
        findings = []

        # Split into sentences
        sentences = re.split(r'[.!?]\s+', llm_output)

        for sentence in sentences:
            sentence = sentence.strip()

            # Skip short or meta sentences
            if len(sentence) < 30 or any(skip in sentence.lower() for skip in [
                'based on', 'according to', 'sources indicate', 'multiple sources',
                'let me', 'i will', 'here are', 'following', 'summarize'
            ]):
                continue

            # Extract source numbers if mentioned
            source_nums = re.findall(r'source\s+(\d+)|[\[\(](\d+)[\]\)]', sentence.lower())
            source_nums = [int(n[0] or n[1]) for n in source_nums if n]

            # Default to first 3 sources if not mentioned
            if not source_nums:
                source_nums = [1, 2, 3]

            # Map to source IDs
            source_ids = []
            for num in source_nums[:5]:  # Limit to 5 sources
                idx = num - 1
                if 0 <= idx < len(extractions):
                    source_ids.append(extractions[idx]['source_id'])

            if source_ids:
                # Create finding with moderate confidence
                confidence = 0.6 if len(source_ids) >= 3 else 0.4

                findings.append(Finding(
                    finding_text=sentence,
                    finding_type='fact',
                    confidence=confidence,
                    source_ids=source_ids,
                    citations=[]
                ))

        # Limit to top 5 findings
        return findings[:5]

    def _detect_contradictions(
        self,
        findings: List[Finding],
        sources: List[Dict[str, Any]]
    ):
        """
        Detect contradictions between findings.

        Args:
            findings: List of findings
            sources: Original sources
        """
        # Simple contradiction detection: check if findings have contradictory statements
        # In production, you'd use semantic similarity and LLM-based contradiction detection

        for i, finding1 in enumerate(findings):
            for j, finding2 in enumerate(findings[i+1:], start=i+1):
                # Check if findings are about the same topic but contradict
                if self._are_contradictory(finding1, finding2):
                    if finding1.contradictions is None:
                        finding1.contradictions = []
                    if finding2.contradictions is None:
                        finding2.contradictions = []

                    finding1.contradictions.extend(finding2.source_ids)
                    finding2.contradictions.extend(finding1.source_ids)

                    self.stats['contradictions_detected'] += 1

                    logging.warning(
                        f"Contradiction detected between findings:\n"
                        f"  1. {finding1.finding_text[:100]}\n"
                        f"  2. {finding2.finding_text[:100]}"
                    )

    def _are_contradictory(self, finding1: Finding, finding2: Finding) -> bool:
        """
        Check if two findings are contradictory.

        Simple heuristic: look for negation words or opposite numbers.
        In production, use LLM for semantic contradiction detection.
        """
        text1 = finding1.finding_text.lower()
        text2 = finding2.finding_text.lower()

        # Check for negation patterns
        negation_pairs = [
            ('is', 'is not'),
            ('does', 'does not'),
            ('has', 'has not'),
            ('will', 'will not'),
            ('can', 'cannot'),
            ('true', 'false'),
            ('increase', 'decrease'),
            ('higher', 'lower'),
            ('more', 'less')
        ]

        for pos, neg in negation_pairs:
            if (pos in text1 and neg in text2) or (neg in text1 and pos in text2):
                return True

        return False

    def _generate_summary(
        self,
        query: str,
        findings: List[Finding],
        sources: List[Dict[str, Any]]
    ) -> str:
        """
        Generate overall summary from findings.

        Args:
            query: Research query
            findings: List of findings
            sources: Original sources

        Returns:
            Summary text
        """
        if not findings:
            return "No high-confidence findings were generated from the sources."

        # Prepare findings for summary
        findings_text = "\n\n".join([
            f"{i+1}. {f.finding_text} (Confidence: {f.confidence:.2f}, "
            f"Type: {f.finding_type}, Sources: {len(f.source_ids)})"
            for i, f in enumerate(findings)
        ])

        # LLM prompt for summary
        messages = [
            {
                'role': 'system',
                'content': (
                    'You are a research summarizer. Create a coherent, well-structured summary '
                    'that synthesizes the key findings. Use clear paragraphs and maintain '
                    'academic tone. Prioritize high-confidence findings.'
                )
            },
            {
                'role': 'user',
                'content': (
                    f"Research query: {query}\n\n"
                    f"Key findings from {len(sources)} sources:\n\n"
                    f"{findings_text}\n\n"
                    f"Generate a comprehensive summary (3-5 paragraphs) that:\n"
                    f"1. Directly answers the research query\n"
                    f"2. Synthesizes the key findings\n"
                    f"3. Notes any contradictions or uncertainties\n"
                    f"4. Provides context and implications"
                )
            }
        ]

        try:
            response = self.llm_client.generate(
                messages,
                max_tokens=1000,
                temperature=0.7
            )

            return response['content']

        except Exception as e:
            logging.error(f"Failed to generate summary: {e}")
            # Fallback: simple concatenation
            return f"Research query: {query}\n\n" + findings_text

    def get_stats(self) -> Dict[str, Any]:
        """Get synthesis statistics."""
        stats = self.stats.copy()

        if stats['findings_generated'] > 0:
            stats['high_confidence_rate'] = (
                stats['high_confidence_findings'] / stats['findings_generated']
            )
        else:
            stats['high_confidence_rate'] = 0.0

        return stats

    def get_info(self) -> Dict[str, Any]:
        """Get information about the synthesis engine."""
        return {
            'min_sources': self.min_sources,
            'confidence_threshold': self.confidence_threshold,
            'detect_contradictions': self.detect_contradictions,
            'confidence_levels': {
                'high': self.CONFIDENCE_HIGH,
                'medium': self.CONFIDENCE_MEDIUM,
                'low': self.CONFIDENCE_LOW
            },
            'stats': self.get_stats()
        }
