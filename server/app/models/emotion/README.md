# Place your trained CNN-LSTM emotion model here.
#
# Expected filenames (checked in order):
#   - emotion_cnn_lstm.keras
#   - emotion_cnn_lstm.h5
#   - emotion_cnn_lstm.onnx
#
# Expected input shape:  (batch, seq_len=8, 48, 48, 1)
# Expected output shape: (batch, 5)
#
# Labels: ["confident", "confused", "bored", "frustrated", "neutral"]
#
# If no model is found, the pipeline falls back to a heuristic estimator.
