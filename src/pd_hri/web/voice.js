// Microphone capture with a simple energy-based voice activity detector.
// Each detected utterance is sent as 16 kHz mono 16-bit PCM (base64) to the laptop,
// where faster-whisper transcribes it locally. No audio leaves the machine.

const TARGET_RATE = 16000;
const FRAME = 2048;
const START_FRAMES = 2; // loud frames needed to start an utterance
const END_SILENCE_MS = 800; // quiet time that ends an utterance
const MIN_UTTER_MS = 400;
const MAX_UTTER_MS = 15000;
const PREROLL_FRAMES = 4;

function downsample(buf, fromRate) {
  const ratio = fromRate / TARGET_RATE;
  const out = new Float32Array(Math.floor(buf.length / ratio));
  for (let i = 0; i < out.length; i++) {
    const start = Math.floor(i * ratio);
    const end = Math.min(buf.length, Math.floor((i + 1) * ratio));
    let sum = 0;
    for (let j = start; j < end; j++) sum += buf[j];
    out[i] = sum / Math.max(1, end - start);
  }
  return out;
}

function toBase64Pcm16(chunks) {
  const len = chunks.reduce((n, c) => n + c.length, 0);
  const pcm = new Int16Array(len);
  let o = 0;
  for (const c of chunks) for (let i = 0; i < c.length; i++) {
    pcm[o++] = Math.max(-1, Math.min(1, c[i])) * 0x7fff;
  }
  const bytes = new Uint8Array(pcm.buffer);
  let bin = "";
  for (let i = 0; i < bytes.length; i += 0x8000) {
    bin += String.fromCharCode.apply(null, bytes.subarray(i, i + 0x8000));
  }
  return btoa(bin);
}

/**
 * @param {MediaStream} stream  stream with an audio track
 * @param {{onUtterance:(b64:string)=>void, onLevel:(rms:number, state:string)=>void,
 *          isMuted:()=>boolean, isActive:()=>boolean}} cb
 */
export function startVoice(stream, cb) {
  const ctx = new AudioContext();
  const src = ctx.createMediaStreamSource(stream);
  const proc = ctx.createScriptProcessor(FRAME, 1, 1);
  const frameMs = (FRAME / ctx.sampleRate) * 1000;

  let noise = 0.01;
  let loud = 0;
  let speaking = false;
  let quietMs = 0;
  let chunks = [];
  let preroll = [];

  const finish = () => {
    const ms = chunks.length * frameMs;
    if (ms >= MIN_UTTER_MS) cb.onUtterance(toBase64Pcm16(chunks));
    speaking = false;
    chunks = [];
    quietMs = 0;
  };

  proc.onaudioprocess = (e) => {
    const input = e.inputBuffer.getChannelData(0);
    let sum = 0;
    for (let i = 0; i < input.length; i++) sum += input[i] * input[i];
    const rms = Math.sqrt(sum / input.length);
    const frame = downsample(input, ctx.sampleRate);

    if (!cb.isActive() || cb.isMuted()) {
      if (speaking) { speaking = false; chunks = []; } // drop robot echo / out-of-phase audio
      loud = 0;
      cb.onLevel(rms, cb.isActive() ? "muted" : "off");
      return;
    }

    const threshold = Math.max(0.015, noise * 3);
    if (!speaking) {
      noise = 0.95 * noise + 0.05 * Math.min(rms, 0.05); // track background level
      preroll.push(frame);
      if (preroll.length > PREROLL_FRAMES) preroll.shift();
      loud = rms > threshold ? loud + 1 : 0;
      if (loud >= START_FRAMES) {
        speaking = true;
        chunks = [...preroll];
        preroll = [];
      }
    } else {
      chunks.push(frame);
      quietMs = rms > threshold * 0.7 ? 0 : quietMs + frameMs;
      if (quietMs >= END_SILENCE_MS || chunks.length * frameMs >= MAX_UTTER_MS) finish();
    }
    cb.onLevel(rms, speaking ? "speaking" : "listening");
  };

  src.connect(proc);
  proc.connect(ctx.destination); // required for onaudioprocess to fire; output is silent
  const resume = () => ctx.state === "suspended" && ctx.resume();
  document.addEventListener("click", resume);
  document.addEventListener("keydown", resume);
  return ctx;
}
