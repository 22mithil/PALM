"""
Standalone Emotion Classifier — MediaPipe FaceLandmarker + Blendshape Thresholds
with Face Mesh Overlay drawn via pure OpenCV (no mediapipe.solutions needed).

Run from server/ directory:
    python -m app.perception.classifier

Press 'q' to quit.
"""

import cv2
import mediapipe as mp
from mediapipe.tasks import python
from mediapipe.tasks.python import vision
import time
import os
import numpy as np

# Path to the FaceLandmarker model
TASK_MODEL_PATH = os.path.join(
    os.path.dirname(__file__),
    "..", "models", "mediapipe", "face_landmarker.task"
)

# ── Thresholds (matched with App.tsx) ───────────────────────────
THRESHOLDS = {
    "confident":  lambda b: (b.get("mouthSmileLeft", 0) > 0.25 or b.get("mouthSmileRight", 0) > 0.25) and b.get("eyeSquintLeft", 0) < 0.5,
    "confused":   lambda b: (b.get("browDownLeft", 0) > 0.3 and b.get("eyeSquintLeft", 0) > 0.3) or (b.get("browDownRight", 0) > 0.3 and b.get("eyeSquintRight", 0) > 0.3),
    "bored":      lambda b: (b.get("eyeLookDownLeft", 0) > 0.5 and b.get("eyeLookDownRight", 0) > 0.5) and b.get("mouthSmileLeft", 0) < 0.2,
    "frustrated": lambda b: (b.get("browInnerUp", 0) > 0.2 or b.get("browDownLeft", 0) > 0.2 or b.get("browDownRight", 0) > 0.2) and (b.get("mouthFrownLeft", 0) > 0.15 or b.get("mouthFrownRight", 0) > 0.15),
}

# Emotion display colors (BGR)
EMOTION_COLORS = {
    "confident":  (0, 200, 100),
    "confused":   (0, 180, 255),
    "bored":      (150, 150, 150),
    "frustrated": (80, 80, 255),
    "neutral":    (255, 180, 0),
    "no face":    (100, 100, 100),
}

# ── Face Mesh Connection Indices ────────────────────────────────
# These mirror the connections from FaceLandmarker.FACE_LANDMARKS_*
# used in App.tsx. Each is a list of (start_idx, end_idx) pairs.

# Face oval
FACE_OVAL = [
    (10, 338), (338, 297), (297, 332), (332, 284), (284, 251), (251, 389),
    (389, 356), (356, 454), (454, 323), (323, 361), (361, 288), (288, 397),
    (397, 365), (365, 379), (379, 378), (378, 400), (400, 377), (377, 152),
    (152, 148), (148, 176), (176, 149), (149, 150), (150, 136), (136, 172),
    (172, 58), (58, 132), (132, 93), (93, 234), (234, 127), (127, 162),
    (162, 21), (21, 54), (54, 103), (103, 67), (67, 109), (109, 10),
]

# Lips
LIPS = [
    (61, 146), (146, 91), (91, 181), (181, 84), (84, 17), (17, 314),
    (314, 405), (405, 321), (321, 375), (375, 291), (291, 409), (409, 270),
    (270, 269), (269, 267), (267, 0), (0, 37), (37, 39), (39, 40),
    (40, 185), (185, 61),
    # Inner lips
    (78, 95), (95, 88), (88, 178), (178, 87), (87, 14), (14, 317),
    (317, 402), (402, 318), (318, 324), (324, 308), (308, 415), (415, 310),
    (310, 311), (311, 312), (312, 13), (13, 82), (82, 81), (81, 80),
    (80, 191), (191, 78),
]

# Left eye
LEFT_EYE = [
    (263, 249), (249, 390), (390, 373), (373, 374), (374, 380), (380, 381),
    (381, 382), (382, 362), (362, 263), (263, 466), (466, 388), (388, 387),
    (387, 386), (386, 385), (385, 384), (384, 398), (398, 362),
]

# Right eye
RIGHT_EYE = [
    (33, 7), (7, 163), (163, 144), (144, 145), (145, 153), (153, 154),
    (154, 155), (155, 133), (133, 33), (33, 246), (246, 161), (161, 160),
    (160, 159), (159, 158), (158, 157), (157, 173), (173, 133),
]

# Left eyebrow
LEFT_EYEBROW = [
    (276, 283), (283, 282), (282, 295), (295, 285), (285, 300),
    (300, 293), (293, 334), (334, 296), (296, 336),
]

# Right eyebrow
RIGHT_EYEBROW = [
    (46, 53), (53, 52), (52, 65), (65, 55), (55, 70),
    (70, 63), (63, 105), (105, 66), (66, 107),
]

# Left iris
LEFT_IRIS = [(474, 475), (475, 476), (476, 477), (477, 474)]

# Right iris
RIGHT_IRIS = [(469, 470), (470, 471), (471, 472), (472, 469)]

# Tesselation — a subset for performance (full mesh has 468 triangles)
# We use the major triangulation lines that give a visible mesh effect
TESSELATION_SUBSET = [
    (10, 338), (10, 109), (338, 297), (109, 67), (297, 332), (67, 103),
    (332, 284), (103, 54), (284, 251), (54, 21), (251, 389), (21, 162),
    (389, 356), (162, 127), (356, 454), (127, 234), (454, 323), (234, 93),
    (323, 361), (93, 132), (361, 288), (132, 58), (288, 397), (58, 172),
    (397, 365), (172, 136), (365, 379), (136, 150), (379, 378), (150, 149),
    (378, 400), (149, 176), (400, 377), (176, 148), (377, 152), (148, 152),
    # Cross connections for mesh look
    (168, 6), (6, 197), (197, 195), (195, 5), (5, 4), (4, 1), (1, 19),
    (19, 94), (94, 2), (2, 164),
    (168, 8), (8, 9), (9, 151), (151, 10),
    # Nose bridge
    (168, 6), (6, 122), (122, 196), (196, 3), (3, 51), (51, 45),
    (6, 351), (351, 419), (419, 248), (248, 281), (281, 275),
    # Cheek lines
    (234, 227), (227, 137), (137, 177), (177, 215), (215, 138),
    (454, 447), (447, 366), (366, 401), (401, 435), (435, 367),
]


def _to_px(landmark, w, h):
    """Convert a normalized landmark to pixel coordinates."""
    return int(landmark.x * w), int(landmark.y * h)


def draw_connections(frame, landmarks, connections, color, thickness=1):
    """Draw a set of landmark connections on the frame."""
    h, w = frame.shape[:2]
    for start_idx, end_idx in connections:
        if start_idx < len(landmarks) and end_idx < len(landmarks):
            pt1 = _to_px(landmarks[start_idx], w, h)
            pt2 = _to_px(landmarks[end_idx], w, h)
            cv2.line(frame, pt1, pt2, color, thickness, cv2.LINE_AA)


def draw_face_mesh(frame, face_landmarks):
    """Draw face mesh overlay onto frame matching App.tsx style.

    Colors (BGR):
      - Tesselation: silver/gray (thin)
      - Right eye + eyebrow: red
      - Left eye + eyebrow: green
      - Face oval: white
      - Lips: white
      - Right iris: red
      - Left iris: green
    """
    # Tesselation — thin silver mesh
    draw_connections(frame, face_landmarks, TESSELATION_SUBSET, (192, 192, 192), 1)

    # Face oval — white
    draw_connections(frame, face_landmarks, FACE_OVAL, (224, 224, 224), 2)

    # Lips — white
    draw_connections(frame, face_landmarks, LIPS, (224, 224, 224), 2)

    # Right eye — red (BGR)
    draw_connections(frame, face_landmarks, RIGHT_EYE, (48, 48, 255), 2)

    # Right eyebrow — red
    draw_connections(frame, face_landmarks, RIGHT_EYEBROW, (48, 48, 255), 2)

    # Left eye — green (BGR)
    draw_connections(frame, face_landmarks, LEFT_EYE, (48, 255, 48), 2)

    # Left eyebrow — green
    draw_connections(frame, face_landmarks, LEFT_EYEBROW, (48, 255, 48), 2)

    # Right iris — red
    draw_connections(frame, face_landmarks, RIGHT_IRIS, (48, 48, 255), 2)

    # Left iris — green
    draw_connections(frame, face_landmarks, LEFT_IRIS, (48, 255, 48), 2)


def classify_emotion(blendshape_scores) -> str:
    """Classify facial expression based on blendshape scores."""
    scores = {b.category_name: b.score for b in blendshape_scores}
    for emotion, logic in THRESHOLDS.items():
        if logic(scores):
            return emotion
    return "neutral"


def main():
    # 1. Initialize FaceLandmarker
    model_path = os.path.normpath(TASK_MODEL_PATH)
    if not os.path.exists(model_path):
        print(f"ERROR: Model not found at {model_path}")
        print("Download from: https://storage.googleapis.com/mediapipe-models/"
              "face_landmarker/face_landmarker/float16/1/face_landmarker.task")
        return

    base_options = python.BaseOptions(model_asset_path=model_path)
    options = vision.FaceLandmarkerOptions(
        base_options=base_options,
        output_face_blendshapes=True,
        running_mode=vision.RunningMode.VIDEO,
        num_faces=1,
    )

    detector = vision.FaceLandmarker.create_from_options(options)

    # 2. Capture webcam
    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        print("ERROR: Could not open webcam")
        return

    fps_start_time = time.time()
    fps_counter = 0
    fps_display = 0

    print("+" + "=" * 49 + "+")
    print("|  PALM - Face Expression Classifier              |")
    print("|  MediaPipe FaceLandmarker + Blendshape Logic     |")
    print("|  Press 'q' to quit                               |")
    print("+" + "=" * 49 + "+")

    while cap.isOpened():
        success, frame = cap.read()
        if not success:
            continue

        # Flip for mirror effect
        frame = cv2.flip(frame, 1)

        # Convert to RGB for MediaPipe
        rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb_frame)
        timestamp_ms = int(time.time() * 1000)

        # 3. Detect landmarks and blendshapes
        result = detector.detect_for_video(mp_image, timestamp_ms)

        emotion = "no face"

        # 4. Classify emotion from blendshapes
        if result.face_blendshapes:
            emotion = classify_emotion(result.face_blendshapes[0])

        # 5. Draw face mesh overlay
        if result.face_landmarks:
            for face_lms in result.face_landmarks:
                draw_face_mesh(frame, face_lms)

        # 6. UI: Draw HUD Overlay
        h, w = frame.shape[:2]
        color = EMOTION_COLORS.get(emotion, (200, 200, 200))

        # Semi-transparent dark panel
        overlay = frame.copy()
        cv2.rectangle(overlay, (10, 10), (350, 110), (20, 20, 20), -1)
        cv2.addWeighted(overlay, 0.7, frame, 0.3, 0, frame)

        # Emotion state label
        cv2.putText(frame, f"STATE: {emotion.upper()}", (25, 50),
                    cv2.FONT_HERSHEY_DUPLEX, 0.9, color, 1, cv2.LINE_AA)

        # FPS counter
        fps_counter += 1
        if (time.time() - fps_start_time) > 1.0:
            fps_display = fps_counter
            fps_counter = 0
            fps_start_time = time.time()

        cv2.putText(frame, f"FPS: {fps_display}", (25, 90),
                    cv2.FONT_HERSHEY_DUPLEX, 0.6, (0, 255, 0), 1, cv2.LINE_AA)

        # Corner brackets (bottom-left HUD element)
        cv2.line(frame, (20, h - 20), (20, h - 100), (255, 255, 255), 2)
        cv2.line(frame, (20, h - 20), (100, h - 20), (255, 255, 255), 2)

        # Show frame
        cv2.imshow('PALM - Face Expression Classifier', frame)

        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

    # 7. Release resources
    detector.close()
    cap.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
