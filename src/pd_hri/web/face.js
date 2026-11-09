// Webcam facial expression via MediaPipe FaceLandmarker (blendshapes), run in the browser.
// Sends a subset of blendshape scores ~4x/s; the server classifies them.
// Uses local files from /static/vendor (fetch them with `uv run python tools/fetch_assets.py`)
// and falls back to the CDN if they are missing.

const VERSION = "0.10.14";
const LOCAL = {
  lib: "/static/vendor/tasks-vision/vision_bundle.mjs",
  wasm: "/static/vendor/tasks-vision/wasm",
  model: "/static/vendor/face_landmarker.task",
};
const CDN = {
  lib: `https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@${VERSION}/vision_bundle.mjs`,
  wasm: `https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@${VERSION}/wasm`,
  model:
    "https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task",
};

const KEEP = new Set([
  "mouthSmileLeft", "mouthSmileRight", "jawOpen", "eyeWideLeft", "eyeWideRight",
  "browInnerUp", "browDownLeft", "browDownRight", "mouthFrownLeft", "mouthFrownRight",
  "mouthPressLeft", "mouthPressRight",
]);

async function pickAssets() {
  try {
    const r = await fetch(LOCAL.model, { method: "HEAD" });
    if (r.ok) return { ...LOCAL, local: true };
  } catch { /* fall through */ }
  return { ...CDN, local: false };
}

/** @returns {Promise<boolean>} true if the model was loaded from local files */
export async function startFaceTracking(video, onScores, intervalMs = 250) {
  const assets = await pickAssets();
  const { FaceLandmarker, FilesetResolver } = await import(assets.lib);
  const fileset = await FilesetResolver.forVisionTasks(assets.wasm);
  const landmarker = await FaceLandmarker.createFromOptions(fileset, {
    baseOptions: { modelAssetPath: assets.model, delegate: "GPU" },
    outputFaceBlendshapes: true,
    runningMode: "VIDEO",
    numFaces: 1,
  });

  setInterval(() => {
    if (video.readyState < 2) return;
    const res = landmarker.detectForVideo(video, performance.now());
    const cats = res.faceBlendshapes?.[0]?.categories;
    if (!cats) return onScores(null); // no face in view
    const scores = {};
    for (const c of cats) if (KEEP.has(c.categoryName)) scores[c.categoryName] = c.score;
    onScores(scores);
  }, intervalMs);
  return assets.local;
}
