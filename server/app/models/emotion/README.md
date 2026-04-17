# Emotion Model

## Approach
Emotion recognition uses MediaPipe FaceLandmarker with blendshape threshold classification.
No trained ML model file is required in this directory.

## Model File Location
The required model file is:
  server/app/models/mediapipe/face_landmarker.task

It is already present in the repository. If missing, download it from:
  https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task

## Emotion Classes
  - confident
  - confused
  - bored
  - frustrated
  - neutral

## How It Works
MediaPipe FaceLandmarker detects 478 facial landmarks and outputs 52 blendshape scores 
per frame. A rule-based threshold classifier maps these scores to the 5 emotion classes above.
Single-frame inference — no frame sequence buffering required.

## Output Contract
  {"emotion": str, "confidence": float}
