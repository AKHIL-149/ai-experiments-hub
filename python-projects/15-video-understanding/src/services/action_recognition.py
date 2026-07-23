"""
Action recognition service
Recognizes actions and activities in video frames
"""

import logging
from pathlib import Path
from typing import List, Optional, Dict, Tuple
from dataclasses import dataclass
import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class RecognizedAction:
    """A recognized action in a video segment"""
    action: str
    confidence: float
    start_frame: int
    end_frame: int
    start_time: float
    end_time: float
    metadata: Optional[Dict[str, any]] = None


@dataclass
class ActionRecognitionResult:
    """Action recognition result for a video or segment"""
    video_path: Path
    actions: List[RecognizedAction]
    num_actions: int
    model: str
    metadata: Optional[Dict[str, any]] = None


class ActionRecognitionService:
    """
    Recognize actions and activities in videos
    Supports rule-based and model-based recognition
    """

    def __init__(
        self,
        method: str = "motion_based",
        min_confidence: float = 0.5,
        min_duration_frames: int = 5
    ):
        """
        Initialize action recognition service

        Args:
            method: Recognition method (motion_based, pose_based, model_based)
            min_confidence: Minimum confidence threshold
            min_duration_frames: Minimum frames for an action
        """
        self.method = method
        self.min_confidence = min_confidence
        self.min_duration_frames = min_duration_frames
        self.model = None

    def recognize_actions(
        self,
        video_path: Path,
        frame_paths: Optional[List[Path]] = None,
        fps: float = 30.0
    ) -> ActionRecognitionResult:
        """
        Recognize actions in video

        Args:
            video_path: Path to video file
            frame_paths: Optional list of extracted frame paths
            fps: Frames per second for timestamp calculation

        Returns:
            ActionRecognitionResult

        Raises:
            ValueError: If video not found
            RuntimeError: If recognition fails
        """
        if not video_path.exists():
            raise ValueError(f"Video not found: {video_path}")

        logger.info(f"Recognizing actions in {video_path}")

        try:
            if self.method == "motion_based":
                result = self._recognize_motion_based(video_path, fps)
            elif self.method == "pose_based":
                result = self._recognize_pose_based(video_path, frame_paths, fps)
            elif self.method == "model_based":
                result = self._recognize_model_based(video_path, fps)
            else:
                result = self._recognize_motion_based(video_path, fps)

            logger.info(
                f"Recognized {result.num_actions} actions in {video_path.name}"
            )

            return result

        except Exception as e:
            raise RuntimeError(f"Action recognition failed: {e}") from e

    def _recognize_motion_based(
        self,
        video_path: Path,
        fps: float
    ) -> ActionRecognitionResult:
        """
        Recognize actions based on motion analysis

        Classifies actions based on motion intensity:
        - Low motion: static, talking
        - Medium motion: walking, gesturing
        - High motion: running, jumping, action
        """
        import cv2

        cap = cv2.VideoCapture(str(video_path))
        actions = []

        frame_count = 0
        prev_frame = None
        motion_scores = []

        while cap.isOpened():
            ret, frame = cap.read()
            if not ret:
                break

            # Convert to grayscale
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

            if prev_frame is not None:
                # Calculate frame difference
                diff = cv2.absdiff(prev_frame, gray)
                motion_score = np.mean(diff)
                motion_scores.append((frame_count, motion_score))

            prev_frame = gray
            frame_count += 1

        cap.release()

        # Analyze motion patterns
        if motion_scores:
            actions = self._classify_motion_patterns(motion_scores, fps)

        return ActionRecognitionResult(
            video_path=video_path,
            actions=actions,
            num_actions=len(actions),
            model="motion_based",
            metadata={'total_frames': frame_count, 'fps': fps}
        )

    def _classify_motion_patterns(
        self,
        motion_scores: List[Tuple[int, float]],
        fps: float
    ) -> List[RecognizedAction]:
        """
        Classify actions based on motion score patterns
        """
        actions = []

        # Calculate motion statistics
        scores = [score for _, score in motion_scores]
        mean_motion = np.mean(scores)
        std_motion = np.std(scores)

        # Define thresholds
        low_threshold = mean_motion - 0.5 * std_motion
        high_threshold = mean_motion + 0.5 * std_motion

        # Detect continuous action segments
        current_action = None
        start_frame = 0

        for frame_num, score in motion_scores:
            # Classify motion level
            if score < low_threshold:
                action_type = "static"
                confidence = 0.8
            elif score > high_threshold:
                action_type = "high_motion"
                confidence = 0.9
            else:
                action_type = "medium_motion"
                confidence = 0.7

            # Track action segments
            if current_action is None:
                current_action = action_type
                start_frame = frame_num
            elif current_action != action_type:
                # End previous action
                if frame_num - start_frame >= self.min_duration_frames:
                    actions.append(RecognizedAction(
                        action=self._map_motion_to_action(current_action),
                        confidence=confidence,
                        start_frame=start_frame,
                        end_frame=frame_num - 1,
                        start_time=start_frame / fps,
                        end_time=(frame_num - 1) / fps,
                        metadata={'motion_level': current_action}
                    ))

                current_action = action_type
                start_frame = frame_num

        # Add final action
        if current_action and len(motion_scores) - start_frame >= self.min_duration_frames:
            last_frame = motion_scores[-1][0]
            actions.append(RecognizedAction(
                action=self._map_motion_to_action(current_action),
                confidence=0.7,
                start_frame=start_frame,
                end_frame=last_frame,
                start_time=start_frame / fps,
                end_time=last_frame / fps,
                metadata={'motion_level': current_action}
            ))

        return actions

    def _map_motion_to_action(self, motion_level: str) -> str:
        """Map motion level to action label"""
        mapping = {
            'static': 'stationary',
            'medium_motion': 'walking/gesturing',
            'high_motion': 'running/action'
        }
        return mapping.get(motion_level, 'unknown')

    def _recognize_pose_based(
        self,
        video_path: Path,
        frame_paths: Optional[List[Path]],
        fps: float
    ) -> ActionRecognitionResult:
        """
        Recognize actions based on pose estimation
        Requires mediapipe or similar pose detection
        """
        try:
            import mediapipe as mp

            mp_pose = mp.solutions.pose
            pose = mp_pose.Pose(
                static_image_mode=False,
                min_detection_confidence=self.min_confidence,
                min_tracking_confidence=self.min_confidence
            )

            import cv2
            cap = cv2.VideoCapture(str(video_path))

            actions = []
            frame_count = 0
            pose_sequences = []

            while cap.isOpened():
                ret, frame = cap.read()
                if not ret:
                    break

                # Convert to RGB
                frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

                # Process pose
                results = pose.process(frame_rgb)

                if results.pose_landmarks:
                    # Extract key pose features
                    landmarks = results.pose_landmarks.landmark
                    pose_features = self._extract_pose_features(landmarks)
                    pose_sequences.append((frame_count, pose_features))

                frame_count += 1

            cap.release()
            pose.close()

            # Classify actions from pose sequences
            if pose_sequences:
                actions = self._classify_pose_sequences(pose_sequences, fps)

            return ActionRecognitionResult(
                video_path=video_path,
                actions=actions,
                num_actions=len(actions),
                model="pose_based",
                metadata={'total_frames': frame_count}
            )

        except ImportError:
            logger.warning("mediapipe not available, falling back to motion-based")
            return self._recognize_motion_based(video_path, fps)

    def _extract_pose_features(self, landmarks) -> Dict[str, float]:
        """Extract relevant pose features from landmarks"""
        features = {}

        # Calculate key angles and positions
        # Shoulder-hip angle (standing vs sitting)
        left_shoulder = landmarks[11]
        left_hip = landmarks[23]
        features['body_angle'] = abs(left_shoulder.y - left_hip.y)

        # Hand position (relative to body)
        left_wrist = landmarks[15]
        features['left_hand_height'] = left_shoulder.y - left_wrist.y

        right_wrist = landmarks[16]
        features['right_hand_height'] = landmarks[12].y - right_wrist.y

        # Leg movement
        left_knee = landmarks[25]
        left_ankle = landmarks[27]
        features['left_leg_bend'] = abs(left_hip.y - left_knee.y) + abs(left_knee.y - left_ankle.y)

        return features

    def _classify_pose_sequences(
        self,
        pose_sequences: List[Tuple[int, Dict[str, float]]],
        fps: float
    ) -> List[RecognizedAction]:
        """Classify actions from pose feature sequences"""
        actions = []

        # Simple rule-based classification
        for i, (frame_num, features) in enumerate(pose_sequences):
            # Detect raising hands
            if features.get('left_hand_height', 0) > 0.3 or features.get('right_hand_height', 0) > 0.3:
                action_type = "raising_hand"
                confidence = 0.85
            # Detect sitting/standing based on body angle
            elif features.get('body_angle', 0) < 0.3:
                action_type = "sitting"
                confidence = 0.8
            else:
                action_type = "standing"
                confidence = 0.75

            # Group consecutive frames with same action
            if not actions or actions[-1].action != action_type:
                actions.append(RecognizedAction(
                    action=action_type,
                    confidence=confidence,
                    start_frame=frame_num,
                    end_frame=frame_num,
                    start_time=frame_num / fps,
                    end_time=frame_num / fps,
                    metadata={'features': features}
                ))
            else:
                # Extend last action
                actions[-1].end_frame = frame_num
                actions[-1].end_time = frame_num / fps

        # Filter short actions
        actions = [
            a for a in actions
            if a.end_frame - a.start_frame >= self.min_duration_frames
        ]

        return actions

    def _recognize_model_based(
        self,
        video_path: Path,
        fps: float
    ) -> ActionRecognitionResult:
        """
        Recognize actions using pre-trained models (I3D, SlowFast, etc.)
        Placeholder for future model integration
        """
        logger.warning("Model-based recognition not yet implemented, using motion-based")
        return self._recognize_motion_based(video_path, fps)

    def filter_by_action(
        self,
        result: ActionRecognitionResult,
        action_types: List[str]
    ) -> ActionRecognitionResult:
        """
        Filter recognized actions by type

        Args:
            result: ActionRecognitionResult
            action_types: List of action types to keep

        Returns:
            Filtered ActionRecognitionResult
        """
        filtered_actions = [
            action for action in result.actions
            if action.action in action_types
        ]

        return ActionRecognitionResult(
            video_path=result.video_path,
            actions=filtered_actions,
            num_actions=len(filtered_actions),
            model=result.model,
            metadata=result.metadata
        )

    def get_dominant_action(
        self,
        result: ActionRecognitionResult
    ) -> Optional[RecognizedAction]:
        """
        Get the longest duration action

        Args:
            result: ActionRecognitionResult

        Returns:
            RecognizedAction with longest duration or None
        """
        if not result.actions:
            return None

        longest = max(
            result.actions,
            key=lambda a: a.end_time - a.start_time
        )

        return longest

    def get_action_timeline(
        self,
        result: ActionRecognitionResult
    ) -> List[Dict[str, any]]:
        """
        Get timeline of actions with timestamps

        Args:
            result: ActionRecognitionResult

        Returns:
            List of action timeline events
        """
        timeline = []

        for action in result.actions:
            timeline.append({
                'action': action.action,
                'start_time': action.start_time,
                'end_time': action.end_time,
                'duration': action.end_time - action.start_time,
                'confidence': action.confidence
            })

        # Sort by start time
        timeline.sort(key=lambda x: x['start_time'])

        return timeline

    def visualize_actions(
        self,
        result: ActionRecognitionResult,
        output_path: Optional[Path] = None
    ) -> Optional[Path]:
        """
        Create visualization of recognized actions on video

        Args:
            result: ActionRecognitionResult
            output_path: Optional output path for annotated video

        Returns:
            Path to annotated video
        """
        try:
            import cv2

            cap = cv2.VideoCapture(str(result.video_path))

            if output_path is None:
                output_path = result.video_path.parent / f"{result.video_path.stem}_actions.mp4"

            # Get video properties
            fps = cap.get(cv2.CAP_PROP_FPS)
            width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

            # Create video writer
            fourcc = cv2.VideoWriter_fourcc(*'mp4v')
            out = cv2.VideoWriter(str(output_path), fourcc, fps, (width, height))

            frame_count = 0

            while cap.isOpened():
                ret, frame = cap.read()
                if not ret:
                    break

                # Find current action
                current_action = None
                for action in result.actions:
                    if action.start_frame <= frame_count <= action.end_frame:
                        current_action = action
                        break

                # Draw action label
                if current_action:
                    label = f"{current_action.action} ({current_action.confidence:.2f})"
                    cv2.putText(
                        frame,
                        label,
                        (10, 30),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        1,
                        (0, 255, 0),
                        2
                    )

                out.write(frame)
                frame_count += 1

            cap.release()
            out.release()

            logger.info(f"Annotated video saved to {output_path}")
            return output_path

        except Exception as e:
            logger.error(f"Visualization failed: {e}")
            return None


def recognize_actions(
    video_path: Path,
    method: str = "motion_based",
    min_confidence: float = 0.5
) -> ActionRecognitionResult:
    """
    Convenience function to recognize actions in video

    Args:
        video_path: Path to video file
        method: Recognition method
        min_confidence: Minimum confidence

    Returns:
        ActionRecognitionResult
    """
    service = ActionRecognitionService(
        method=method,
        min_confidence=min_confidence
    )
    return service.recognize_actions(video_path)
