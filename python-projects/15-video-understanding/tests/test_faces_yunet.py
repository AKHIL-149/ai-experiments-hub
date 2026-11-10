"""
Face detection with YuNet (src/services/face_detection.py).

On the keyframes of real videos the old Haar cascade reported faces on window frames, chairs and wall patterns
(643 "faces" where 452 are found now) and missed faces with sunglasses or turned away. YuNet found those faces and
reported none of the false ones at a score of 0.7. The sample pictures here come with scikit-image (a public
domain NASA portrait and the cameraman photo), so no test needs a download.
"""

from pathlib import Path

import cv2
import numpy as np
import pytest

from src.services.face_detection import (
    YUNET_FILE, YUNET_MAX_SIDE, YUNET_MIN_FACE_PX, DetectedFace, FaceDetectionService, default_yunet_path,
)

data = pytest.importorskip("skimage.data")
MODEL = default_yunet_path()
needs_model = pytest.mark.skipif(not MODEL.exists(), reason="the YuNet model file is not in models/")


@pytest.fixture
def pictures(tmp_path):
    out = {}
    for name in ("astronaut", "camera", "cat", "brick", "grass", "coins", "text"):
        image = getattr(data, name)()
        image = cv2.cvtColor(image, cv2.COLOR_RGB2BGR) if image.ndim == 3 else cv2.cvtColor(image, cv2.COLOR_GRAY2BGR)
        out[name] = tmp_path / f"{name}.png"
        cv2.imwrite(str(out[name]), image)
    return out


def yunet(**kw):
    return FaceDetectionService(backend="yunet", min_confidence=kw.pop("min_confidence", 0.7), **kw)


class TestTheModelFile:
    def test_the_model_ships_with_the_project(self):
        assert MODEL.name == YUNET_FILE and MODEL.parent.name == "models"
        assert MODEL.exists() and MODEL.stat().st_size == 232589

    def test_its_documented_checksum(self):
        import hashlib
        assert hashlib.sha256(MODEL.read_bytes()).hexdigest() == "8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4"
        assert "8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4" in (MODEL.parent / "README.md").read_text()

    def test_it_is_found_from_the_code_not_from_the_working_directory(self, monkeypatch, tmp_path):
        monkeypatch.chdir(tmp_path)
        assert default_yunet_path().exists()


@needs_model
class TestDetecting:
    def test_a_face_is_found_with_its_box_score_and_landmarks(self, pictures):
        result = yunet().detect_faces(pictures["astronaut"])
        assert result.model == "yunet" and result.num_faces == 1 and len(result.faces) == 1
        face = result.faces[0]
        x, y, w, h = face.bbox
        assert 150 < x < 210 and 40 < y < 90 and 70 < w < 110 and 90 < h < 135   # the astronaut's face
        assert 0.8 < face.confidence <= 1.0
        assert set(face.landmarks) == {"right_eye", "left_eye", "nose", "right_mouth", "left_mouth"}
        # the eyes are inside the box, above the nose and mouth
        assert all(x <= px <= x + w and y <= py <= y + h for px, py in face.landmarks.values())
        assert face.landmarks["right_eye"][1] < face.landmarks["nose"][1] < face.landmarks["right_mouth"][1]
        assert face.metadata == {"backend": "yunet"} and result.metadata["image_size"] == (512, 512)

    def test_a_small_face_that_the_haar_cascade_misses(self, pictures):
        yunet_faces = yunet().detect_faces(pictures["camera"]).faces
        haar_faces = FaceDetectionService(backend="opencv").detect_faces(pictures["camera"]).faces
        assert len(yunet_faces) == 1 and 55 < yunet_faces[0].bbox[2] < 70
        assert haar_faces == []

    @pytest.mark.parametrize("name", ["cat", "brick", "grass", "coins", "text"])
    def test_pictures_without_faces_have_none(self, pictures, name):
        assert yunet().detect_faces(pictures[name]).faces == []

    def test_the_haar_backend_still_works_and_is_chosen_by_name(self, pictures):
        result = FaceDetectionService(backend="opencv").detect_faces(pictures["astronaut"])
        assert result.model == "opencv-haar" and result.num_faces == 1

    def test_the_biggest_face_comes_first(self, pictures, tmp_path):
        face = cv2.imread(str(pictures["astronaut"]))[40:200, 150:300]
        canvas = np.full((600, 900, 3), 120, np.uint8)
        canvas[20:180, 20:170] = cv2.resize(face, (150, 160))
        canvas[100:420, 400:700] = cv2.resize(face, (300, 320))
        cv2.imwrite(str(tmp_path / "two.png"), canvas)
        faces = yunet().detect_faces(tmp_path / "two.png").faces
        assert len(faces) == 2 and faces[0].bbox[2] * faces[0].bbox[3] > faces[1].bbox[2] * faces[1].bbox[3]

    def test_large_pictures_are_shrunk_for_speed_and_the_box_scaled_back(self, pictures, tmp_path):
        original = cv2.imread(str(pictures["astronaut"]))
        small = yunet().detect_faces(pictures["astronaut"]).faces[0].bbox
        scale = 3 * YUNET_MAX_SIDE / 512
        cv2.imwrite(str(tmp_path / "big.png"), cv2.resize(original, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC))
        big = cv2.imread(str(tmp_path / "big.png"))
        assert max(big.shape[:2]) > YUNET_MAX_SIDE
        face = yunet().detect_faces(tmp_path / "big.png").faces[0]
        for found, expected in zip(face.bbox, small):
            assert found == pytest.approx(expected * scale, rel=0.12)
        assert all(0 <= px <= big.shape[1] and 0 <= py <= big.shape[0] for px, py in face.landmarks.values())

    def test_the_detector_can_be_used_for_many_pictures_of_different_sizes(self, pictures):
        service = yunet()
        for name in ("astronaut", "cat", "camera", "brick", "astronaut"):
            service.detect_faces(pictures[name])
        assert service.detect_faces(pictures["astronaut"]).num_faces == 1

    def test_a_missing_picture_and_an_unreadable_one(self, tmp_path):
        with pytest.raises(ValueError):
            yunet().detect_faces(tmp_path / "nope.png")
        bad = tmp_path / "bad.png"
        bad.write_bytes(b"not a picture")
        with pytest.raises(RuntimeError):
            yunet().detect_faces(bad)

    def test_batches_and_counts(self, pictures):
        service = yunet()
        results = service.detect_batch([pictures["astronaut"], pictures["cat"], pictures["camera"]])
        assert [r.num_faces for r in results] == [1, 0, 1]


class FakeYuNet:
    """Stands in for cv2.FaceDetectorYN: returns the rows it was given"""

    def __init__(self, rows):
        self.rows = rows
        self.sizes = []

    def setInputSize(self, size):
        self.sizes.append(size)

    def detect(self, image):
        return 1, (np.array(self.rows, dtype=np.float32) if self.rows else None)


def row(x, y, w, h, score, marks=None):
    marks = marks or [x + w * 0.3, y + h * 0.35, x + w * 0.7, y + h * 0.35, x + w * 0.5, y + h * 0.6,
                      x + w * 0.35, y + h * 0.8, x + w * 0.65, y + h * 0.8]
    return [x, y, w, h, *marks, score]


@needs_model
class TestFiltering:
    """The rules that keep false faces out, on rows a detector could return"""

    def run(self, rows, tmp_path, size=(200, 300), **kw):
        picture = tmp_path / "p.png"
        cv2.imwrite(str(picture), np.full((size[0], size[1], 3), 100, np.uint8))
        service = yunet(**kw)
        service.detector = FakeYuNet(rows)
        return service.detect_faces(picture)

    def test_a_low_score_is_not_a_face(self, tmp_path):
        result = self.run([row(50, 50, 60, 70, 0.69), row(150, 50, 60, 70, 0.71)], tmp_path)
        assert [f.bbox for f in result.faces] == [(150, 50, 60, 70)]

    def test_the_threshold_is_a_setting(self, tmp_path):
        rows = [row(50, 50, 60, 70, 0.65)]
        assert self.run(rows, tmp_path, min_confidence=0.6).num_faces == 1
        assert self.run(rows, tmp_path, min_confidence=0.9).num_faces == 0

    def test_a_speck_is_not_a_face(self, tmp_path):
        rows = [row(10, 10, YUNET_MIN_FACE_PX - 1, 30, 0.9), row(60, 10, 40, YUNET_MIN_FACE_PX - 1, 0.9),
                row(120, 10, YUNET_MIN_FACE_PX, YUNET_MIN_FACE_PX, 0.9)]
        assert [f.bbox[:2] for f in self.run(rows, tmp_path).faces] == [(120, 10)]

    def test_a_box_hanging_over_the_edge_is_cut_to_the_picture(self, tmp_path):
        face = self.run([row(250, 150, 80, 90, 0.9), row(-20, -10, 60, 60, 0.9)], tmp_path).faces
        boxes = sorted(f.bbox for f in face)
        assert boxes == [(0, 0, 60, 60), (250, 150, 50, 50)]

    def test_sorted_biggest_first_and_confidence_rounded(self, tmp_path):
        faces = self.run([row(10, 10, 30, 30, 0.8), row(100, 40, 90, 100, 0.912345)], tmp_path).faces
        assert [f.bbox[2] for f in faces] == [90, 30] and faces[0].confidence == 0.9123

    def test_no_detections(self, tmp_path):
        result = self.run([], tmp_path)
        assert result.faces == [] and result.num_faces == 0

    def test_the_input_size_follows_each_picture(self, tmp_path):
        picture = tmp_path / "p.png"
        cv2.imwrite(str(picture), np.zeros((120, 340, 3), np.uint8))
        service = yunet()
        service.detector = FakeYuNet([])
        service.detect_faces(picture)
        assert service.detector.sizes == [(340, 120)]


class TestChoosingTheBackend:
    @needs_model
    def test_auto_uses_yunet_when_the_model_is_there(self):
        assert FaceDetectionService(backend="auto").backend == "yunet"

    def test_auto_falls_back_to_haar_with_one_warning_when_it_is_not(self, tmp_path, caplog):
        import logging
        import src.services.face_detection as module
        module._warned_no_model = False
        with caplog.at_level(logging.WARNING, logger="src.services.face_detection"):
            first = FaceDetectionService(backend="auto", model_path=tmp_path / "missing.onnx")
            second = FaceDetectionService(backend="auto", model_path=tmp_path / "missing.onnx")
        assert first.backend == second.backend == "opencv"
        assert len([r for r in caplog.records if "Face model" in r.getMessage()]) == 1

    def test_a_missing_model_does_not_break_detection(self, tmp_path, pictures):
        service = FaceDetectionService(backend="yunet", model_path=tmp_path / "missing.onnx")
        result = service.detect_faces(pictures["astronaut"])
        assert result.model == "opencv-haar"

    def test_the_other_backends_keep_their_names(self):
        assert FaceDetectionService(backend="opencv").backend == "opencv"
        assert FaceDetectionService(backend="mtcnn").backend == "mtcnn"

    @needs_model
    def test_settings_choose_the_detector(self, monkeypatch):
        from src.core.config import settings
        monkeypatch.setattr(settings, "face_backend", "opencv")
        assert FaceDetectionService.from_settings().backend == "opencv"
        monkeypatch.setattr(settings, "face_backend", "auto")
        monkeypatch.setattr(settings, "face_min_confidence", 0.55)
        service = FaceDetectionService.from_settings()
        assert service.backend == "yunet" and service.min_confidence == 0.55

    def test_a_model_path_can_be_configured(self, monkeypatch, tmp_path):
        from src.core.config import settings
        monkeypatch.setattr(settings, "face_backend", "yunet")
        monkeypatch.setattr(settings, "face_model_path", str(tmp_path / "mine.onnx"))
        assert FaceDetectionService.from_settings().model_path == tmp_path / "mine.onnx"

    def test_defaults(self):
        from src.core.config import Settings
        defaults = Settings()
        assert defaults.face_backend == "auto" and defaults.face_min_confidence == 0.7 and defaults.scene_detector == "robust"


class TestNothingElseChanged:
    def test_the_detected_face_shape_the_pipeline_stores(self):
        face = DetectedFace(bbox=(1, 2, 3, 4), confidence=0.9)
        assert face.landmarks is None and face.embedding is None
