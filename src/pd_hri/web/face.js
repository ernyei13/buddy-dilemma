// Webcam facial expression via MediaPipe FaceLandmarker (blendshapes).
// Sends a subset of blendshape scores ~4x/s; the server classifies them.
// Needs internet the first time to load the model from the CDN.

const VERSION = "0.10.14";
const CDN = `https://cdn.jsdelivr.net/npm/@mediapipe/tasks-vision@${VERSION}`;
const MODEL =
  "https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task";

const KEEP = new Set([
  "mouthSmileLeft", "mouthSmileRight", "jawOpen", "eyeWideLeft", "eyeWideRight",
  "browInnerUp", "browDownLeft", "browDownRight", "mouthFrownLeft", "mouthFrownRight",
  "mouthPressLeft", "mouthPressRight",
]);

export async function startFaceTracking(video, onScores, intervalMs = 250) {
  const stream = await navigator.mediaDevices.getUserMedia({
    video: { width: 640, height: 480 },
    audio: false,
  });
  video.srcObject = stream;
  await video.play();

  const { FaceLandmarker, FilesetResolver } = await import(`${CDN}/vision_bundle.mjs`);
  const fileset = await FilesetResolver.forVisionTasks(`${CDN}/wasm`);
  const landmarker = await FaceLandmarker.createFromOptions(fileset, {
    baseOptions: { modelAssetPath: MODEL, delegate: "GPU" },
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
}
