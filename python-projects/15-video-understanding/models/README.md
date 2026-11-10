# Models

`face_detection_yunet_2023mar.onnx` (232,589 bytes) is YuNet, the face detector from OpenCV's model zoo
(https://github.com/opencv/opencv_zoo/tree/main/models/face_detection_yunet, MIT license). The platform finds
faces in keyframes with it through OpenCV's `FaceDetectorYN`.

SHA-256: `8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4`

Without the file the platform falls back to OpenCV's old Haar cascade, which reports false faces and misses
small and side-on ones (a warning is logged once). To fetch it again:

```bash
curl -L -o models/face_detection_yunet_2023mar.onnx \
  https://github.com/opencv/opencv_zoo/raw/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx
```
