"""
Chapter generator for detecting natural chapter boundaries
Generate chapter titles and descriptions for video navigation
"""

import logging
from typing import List, Optional, Dict, Any, Tuple
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class Chapter:
    """Video chapter"""
    chapter_number: int
    title: str
    start_time: float
    end_time: float
    duration: float

    # Content
    description: Optional[str] = None
    summary: Optional[str] = None

    # Scenes
    scene_ids: List[int] = field(default_factory=list)
    num_scenes: int = 0

    # Importance
    importance_score: float = 0.0

    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ChapterCollection:
    """Collection of chapters for a video"""
    video_id: str
    chapters: List[Chapter]
    total_duration: float

    # Generation info
    detection_method: str = "auto"
    tokens_used: Dict[str, int] = field(default_factory=dict)

    metadata: Dict[str, Any] = field(default_factory=dict)


class ChapterGenerator:
    """
    Detect natural chapter boundaries and generate chapters
    Use scene importance changes and content analysis
    """

    def __init__(
        self,
        llm_client=None,
        min_chapter_duration: float = 30.0,
        max_chapter_duration: float = 600.0,
        importance_threshold: float = 0.15,
        auto_generate_titles: bool = True,
    ):
        """
        Initialize chapter generator

        Args:
            llm_client: LLMClient instance
            min_chapter_duration: Minimum chapter duration (seconds)
            max_chapter_duration: Maximum chapter duration (seconds)
            importance_threshold: Threshold for importance changes
            auto_generate_titles: Generate chapter titles automatically
        """
        self.llm_client = llm_client
        self.min_chapter_duration = min_chapter_duration
        self.max_chapter_duration = max_chapter_duration
        self.importance_threshold = importance_threshold
        self.auto_generate_titles = auto_generate_titles

        logger.info(
            f"Initialized ChapterGenerator "
            f"(min_duration={min_chapter_duration}s, "
            f"max_duration={max_chapter_duration}s)"
        )

    def generate_chapters(
        self,
        video_id: str,
        duration: float,
        scenes: Optional[List[Dict[str, Any]]] = None,
        enriched_scenes: Optional[List[Any]] = None,
        scene_summaries: Optional[List[Any]] = None,
        method: str = "auto",
    ) -> ChapterCollection:
        """
        Generate chapters for video

        Args:
            video_id: Video identifier
            duration: Video duration
            scenes: Scene list
            enriched_scenes: Enriched scenes
            scene_summaries: Scene summaries
            method: Detection method (auto, importance, fixed, semantic)

        Returns:
            ChapterCollection
        """
        logger.info(f"Generating chapters for video {video_id} (method={method})")

        # Use enriched scenes if available
        if enriched_scenes:
            scenes_to_use = enriched_scenes
        elif scene_summaries:
            scenes_to_use = scene_summaries
        elif scenes:
            scenes_to_use = scenes
        else:
            # Fallback: single chapter for entire video
            return self._create_single_chapter(video_id, duration)

        # Detect chapter boundaries
        if method == "auto" or method == "importance":
            chapters = self._detect_by_importance_changes(scenes_to_use, duration)
        elif method == "fixed":
            chapters = self._detect_by_fixed_interval(scenes_to_use, duration)
        elif method == "semantic":
            chapters = self._detect_by_semantic_similarity(scenes_to_use, duration)
        else:
            logger.warning(f"Unknown method {method}, using auto")
            chapters = self._detect_by_importance_changes(scenes_to_use, duration)

        # Generate titles and descriptions
        if self.auto_generate_titles:
            chapters = self._generate_chapter_metadata(
                chapters, scenes_to_use
            )

        # Calculate importance scores
        for chapter in chapters:
            chapter.importance_score = self._calculate_chapter_importance(
                chapter, scenes_to_use
            )

        return ChapterCollection(
            video_id=video_id,
            chapters=chapters,
            total_duration=duration,
            detection_method=method,
            metadata={
                "num_chapters": len(chapters),
                "avg_chapter_duration": duration / len(chapters) if chapters else 0,
                "num_scenes": len(scenes_to_use),
            },
        )

    def _detect_by_importance_changes(
        self,
        scenes: List[Any],
        duration: float,
    ) -> List[Chapter]:
        """Detect chapters by importance score changes"""
        if not scenes:
            return []

        chapters = []
        current_chapter_start = 0.0
        current_chapter_scenes = []

        for i, scene in enumerate(scenes):
            # Get scene info
            scene_id = self._get_scene_id(scene)
            start_time = self._get_start_time(scene)
            end_time = self._get_end_time(scene)
            importance = self._get_importance_score(scene)

            current_chapter_scenes.append(scene)

            # Check if we should end chapter
            end_chapter = False

            # Check importance change with next scene
            if i < len(scenes) - 1:
                next_importance = self._get_importance_score(scenes[i + 1])
                importance_diff = abs(importance - next_importance)

                if importance_diff > self.importance_threshold:
                    # Significant importance change
                    chapter_duration = end_time - current_chapter_start
                    if chapter_duration >= self.min_chapter_duration:
                        end_chapter = True

            # Check max duration
            chapter_duration = end_time - current_chapter_start
            if chapter_duration >= self.max_chapter_duration:
                end_chapter = True

            # Last scene
            if i == len(scenes) - 1:
                end_chapter = True

            # Create chapter
            if end_chapter and current_chapter_scenes:
                chapter = self._create_chapter_from_scenes(
                    chapter_number=len(chapters) + 1,
                    scenes=current_chapter_scenes,
                )
                chapters.append(chapter)
                current_chapter_scenes = []
                current_chapter_start = end_time

        return chapters

    def _detect_by_fixed_interval(
        self,
        scenes: List[Any],
        duration: float,
        interval: Optional[float] = None,
    ) -> List[Chapter]:
        """Detect chapters at fixed intervals"""
        interval = interval or 120.0  # 2 minutes default

        chapters = []
        current_chapter_start = 0.0
        current_chapter_scenes = []

        for scene in scenes:
            end_time = self._get_end_time(scene)
            current_chapter_scenes.append(scene)

            # Check if interval reached
            if end_time - current_chapter_start >= interval:
                chapter = self._create_chapter_from_scenes(
                    chapter_number=len(chapters) + 1,
                    scenes=current_chapter_scenes,
                )
                chapters.append(chapter)
                current_chapter_scenes = []
                current_chapter_start = end_time

        # Add remaining scenes
        if current_chapter_scenes:
            chapter = self._create_chapter_from_scenes(
                chapter_number=len(chapters) + 1,
                scenes=current_chapter_scenes,
            )
            chapters.append(chapter)

        return chapters

    def _detect_by_semantic_similarity(
        self,
        scenes: List[Any],
        duration: float,
    ) -> List[Chapter]:
        """Detect chapters by semantic similarity of scene content"""
        # Group semantically similar scenes
        # For now, use description similarity as proxy
        if not scenes:
            return []

        chapters = []
        current_chapter_scenes = [scenes[0]]
        current_topic = self._extract_topic(scenes[0])

        for i in range(1, len(scenes)):
            scene = scenes[i]
            scene_topic = self._extract_topic(scene)

            # Check if topic changed
            if scene_topic != current_topic:
                # Create chapter for previous group
                chapter_duration = (
                    self._get_end_time(current_chapter_scenes[-1]) -
                    self._get_start_time(current_chapter_scenes[0])
                )

                if chapter_duration >= self.min_chapter_duration:
                    chapter = self._create_chapter_from_scenes(
                        chapter_number=len(chapters) + 1,
                        scenes=current_chapter_scenes,
                    )
                    chapters.append(chapter)
                    current_chapter_scenes = []
                    current_topic = scene_topic

            current_chapter_scenes.append(scene)

        # Add final chapter
        if current_chapter_scenes:
            chapter = self._create_chapter_from_scenes(
                chapter_number=len(chapters) + 1,
                scenes=current_chapter_scenes,
            )
            chapters.append(chapter)

        return chapters

    def _create_chapter_from_scenes(
        self,
        chapter_number: int,
        scenes: List[Any],
    ) -> Chapter:
        """Create chapter from list of scenes"""
        if not scenes:
            raise ValueError("Cannot create chapter from empty scene list")

        start_time = self._get_start_time(scenes[0])
        end_time = self._get_end_time(scenes[-1])
        duration = end_time - start_time

        scene_ids = [self._get_scene_id(s) for s in scenes]

        return Chapter(
            chapter_number=chapter_number,
            title=f"Chapter {chapter_number}",
            start_time=start_time,
            end_time=end_time,
            duration=duration,
            scene_ids=scene_ids,
            num_scenes=len(scenes),
        )

    def _generate_chapter_metadata(
        self,
        chapters: List[Chapter],
        scenes: List[Any],
    ) -> List[Chapter]:
        """Generate titles and descriptions for chapters"""
        # Create scene lookup
        scene_lookup = {}
        for scene in scenes:
            scene_id = self._get_scene_id(scene)
            scene_lookup[scene_id] = scene

        for chapter in chapters:
            # Get scenes in chapter
            chapter_scenes = [
                scene_lookup[sid] for sid in chapter.scene_ids
                if sid in scene_lookup
            ]

            if not chapter_scenes:
                continue

            # Generate title
            chapter.title = self._generate_chapter_title(
                chapter, chapter_scenes
            )

            # Generate description
            chapter.description = self._generate_chapter_description(
                chapter, chapter_scenes
            )

        return chapters

    def _generate_chapter_title(
        self,
        chapter: Chapter,
        scenes: List[Any],
    ) -> str:
        """Generate title for chapter"""
        if not scenes:
            return f"Chapter {chapter.chapter_number}"

        # Try to extract from first scene
        first_scene = scenes[0]

        # Check for title attribute
        if hasattr(first_scene, "title") and first_scene.title:
            # Extract topic from scene title
            title = first_scene.title
            if ":" in title:
                topic = title.split(":", 1)[1].strip()
                return f"Chapter {chapter.chapter_number}: {topic}"

        # Check for description
        if hasattr(first_scene, "description") and first_scene.description:
            desc = first_scene.description
            # Take first few words
            words = desc.split()[:4]
            return f"Chapter {chapter.chapter_number}: {' '.join(words)}"

        # Fallback
        return f"Chapter {chapter.chapter_number}"

    def _generate_chapter_description(
        self,
        chapter: Chapter,
        scenes: List[Any],
    ) -> str:
        """Generate description for chapter"""
        if not scenes:
            return ""

        # Collect scene descriptions
        descriptions = []
        for scene in scenes[:3]:  # First 3 scenes
            if hasattr(scene, "description") and scene.description:
                descriptions.append(scene.description)
            elif hasattr(scene, "summary_text") and scene.summary_text:
                descriptions.append(scene.summary_text)

        if descriptions:
            return " | ".join(descriptions)

        return f"Contains {len(scenes)} scenes"

    def _calculate_chapter_importance(
        self,
        chapter: Chapter,
        scenes: List[Any],
    ) -> float:
        """Calculate chapter importance score"""
        # Create scene lookup
        scene_lookup = {}
        for scene in scenes:
            scene_id = self._get_scene_id(scene)
            scene_lookup[scene_id] = scene

        # Get scenes in chapter
        chapter_scenes = [
            scene_lookup[sid] for sid in chapter.scene_ids
            if sid in scene_lookup
        ]

        if not chapter_scenes:
            return 0.0

        # Average importance of scenes
        importance_scores = [
            self._get_importance_score(s) for s in chapter_scenes
        ]

        return sum(importance_scores) / len(importance_scores)

    def _create_single_chapter(
        self,
        video_id: str,
        duration: float,
    ) -> ChapterCollection:
        """Create single chapter for entire video"""
        chapter = Chapter(
            chapter_number=1,
            title="Full Video",
            start_time=0.0,
            end_time=duration,
            duration=duration,
            scene_ids=[],
            num_scenes=0,
        )

        return ChapterCollection(
            video_id=video_id,
            chapters=[chapter],
            total_duration=duration,
            detection_method="fallback",
        )

    def _get_scene_id(self, scene: Any) -> int:
        """Extract scene ID from scene object"""
        if isinstance(scene, dict):
            return scene.get("scene_number", scene.get("scene_id", 0))
        else:
            return getattr(scene, "scene_id", 0)

    def _get_start_time(self, scene: Any) -> float:
        """Extract start time from scene object"""
        if isinstance(scene, dict):
            return scene.get("start_time", 0.0)
        else:
            return getattr(scene, "start_time", 0.0)

    def _get_end_time(self, scene: Any) -> float:
        """Extract end time from scene object"""
        if isinstance(scene, dict):
            return scene.get("end_time", 0.0)
        else:
            return getattr(scene, "end_time", 0.0)

    def _get_importance_score(self, scene: Any) -> float:
        """Extract importance score from scene object"""
        if isinstance(scene, dict):
            return scene.get("importance_score", 0.5)
        else:
            return getattr(scene, "importance_score", 0.5)

    def _extract_topic(self, scene: Any) -> str:
        """Extract topic from scene"""
        if isinstance(scene, dict):
            title = scene.get("title", "")
            if ":" in title:
                return title.split(":", 1)[1].strip()
            return ""
        else:
            if hasattr(scene, "title") and scene.title and ":" in scene.title:
                return scene.title.split(":", 1)[1].strip()
            return ""

    def export_chapters_to_dict(
        self,
        chapter_collection: ChapterCollection,
    ) -> Dict[str, Any]:
        """Export chapters to dictionary"""
        return {
            "video_id": chapter_collection.video_id,
            "total_duration": chapter_collection.total_duration,
            "detection_method": chapter_collection.detection_method,
            "chapters": [
                {
                    "chapter_number": ch.chapter_number,
                    "title": ch.title,
                    "start_time": ch.start_time,
                    "end_time": ch.end_time,
                    "duration": ch.duration,
                    "description": ch.description,
                    "summary": ch.summary,
                    "scene_ids": ch.scene_ids,
                    "num_scenes": ch.num_scenes,
                    "importance_score": ch.importance_score,
                    "metadata": ch.metadata,
                }
                for ch in chapter_collection.chapters
            ],
            "metadata": chapter_collection.metadata,
        }

    def export_chapters_to_vtt(
        self,
        chapter_collection: ChapterCollection,
    ) -> str:
        """Export chapters to WebVTT format"""
        lines = ["WEBVTT", ""]

        for chapter in chapter_collection.chapters:
            start = self._format_timestamp(chapter.start_time)
            end = self._format_timestamp(chapter.end_time)

            lines.append(f"{start} --> {end}")
            lines.append(chapter.title)
            if chapter.description:
                lines.append(chapter.description)
            lines.append("")

        return "\n".join(lines)

    def _format_timestamp(self, seconds: float) -> str:
        """Format seconds to HH:MM:SS.mmm"""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        millis = int((seconds % 1) * 1000)

        return f"{hours:02d}:{minutes:02d}:{secs:02d}.{millis:03d}"


def generate_chapters(
    video_id: str,
    duration: float,
    scenes: Optional[List[Dict[str, Any]]] = None,
    enriched_scenes: Optional[List[Any]] = None,
    method: str = "auto",
    llm_client=None,
) -> ChapterCollection:
    """
    Convenience function to generate chapters

    Args:
        video_id: Video identifier
        duration: Video duration
        scenes: Scene list
        enriched_scenes: Enriched scenes
        method: Detection method
        llm_client: LLMClient instance

    Returns:
        ChapterCollection
    """
    generator = ChapterGenerator(llm_client=llm_client)
    return generator.generate_chapters(
        video_id=video_id,
        duration=duration,
        scenes=scenes,
        enriched_scenes=enriched_scenes,
        method=method,
    )
