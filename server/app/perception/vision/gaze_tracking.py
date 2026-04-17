"""
Gaze Tracking — REMOVED.

Server-side gaze tracking has been fully replaced by client-side
iris landmark tracking in useFaceMesh.js. The client uses MediaPipe
FaceLandmarker landmarks 473/468 (iris centers) and eye corner
landmarks 33/133/362/263 to compute gaze direction directly in
the browser.

This file is kept as a tombstone to prevent import errors from
any stale references.
"""
