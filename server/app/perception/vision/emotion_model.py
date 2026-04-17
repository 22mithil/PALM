import cv2
import mediapipe as mp
from mediapipe.tasks import python
from mediapipe.tasks.python import vision
import time
import os

TASK_MODEL_PATH = os.path.join(
    os.path.dirname(__file__),
    "../../models/mediapipe/face_landmarker.task"
)

THRESHOLDS = {
    "confident":  lambda b: (b.get("mouthSmileLeft", 0) > 0.25 or b.get("mouthSmileRight", 0) > 0.25) and b.get("eyeSquintLeft", 0) < 0.5,
    "confused":   lambda b: (b.get("browDownLeft", 0) > 0.3 and b.get("eyeSquintLeft", 0) > 0.3) or (b.get("browDownRight", 0) > 0.3 and b.get("eyeSquintRight", 0) > 0.3),
    "bored":      lambda b: (b.get("eyeLookDownLeft", 0) > 0.5 and b.get("eyeLookDownRight", 0) > 0.5) and b.get("mouthSmileLeft", 0) < 0.2,
    "frustrated": lambda b: (b.get("browInnerUp", 0) > 0.2 or b.get("browDownLeft", 0) > 0.2 or b.get("browDownRight", 0) > 0.2) and (b.get("mouthFrownLeft", 0) > 0.15 or b.get("mouthFrownRight", 0) > 0.15),
}

class EmotionModel:
    def __init__(self):
        base_options = python.BaseOptions(model_asset_path=TASK_MODEL_PATH)
        options = vision.FaceLandmarkerOptions(
            base_options=base_options,
            output_face_blendshapes=True,
            running_mode=vision.RunningMode.VIDEO,
            num_faces=1
        )
        self.detector = vision.FaceLandmarker.create_from_options(options)

    def classify_emotion(self, blendshape_categories) -> str:
        scores = {b.category_name: b.score for b in blendshape_categories}
        for emotion, logic in THRESHOLDS.items():
            if logic(scores):
                return emotion
        return "neutral"

    def predict(self, frame_bgr) -> dict:
        """
        Accepts a single BGR numpy frame.
        Returns {"emotion": str, "confidence": float}
        This is the ONLY public method the rest of the system should call.
        """
        rgb_frame = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb_frame)
        timestamp_ms = int(time.time() * 1000)
        result = self.detector.detect_for_video(mp_image, timestamp_ms)

        if result.face_blendshapes:
            emotion = self.classify_emotion(result.face_blendshapes[0])
        else:
            emotion = "neutral"

        return {"emotion": emotion, "confidence": 1.0}

    def close(self):
        self.detector.close()
