import { startFaceTracking } from "/static/face.js";

const $ = (id) => document.getElementById(id);
const PHASE_TITLES = {
  chat: "Talk with Buddy",
  vote: "Vote now!",
  result: "Result",
  end: "Game over — thank you!",
  aborted: "Session stopped",
};
const MANUAL_LABELS = { 1: "happy", 2: "neutral", 3: "doubtful", 4: "surprised" };

let ws;
let status = {};
let phase = null;
let timerHandle = null;
let manualLabel = null; // keyboard override for testing without a camera
let cameraOk = false;

// ---------------------------------------------------------------- socket
function connect() {
  ws = new WebSocket(`${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/ws/screen`);
  ws.onmessage = (ev) => handle(JSON.parse(ev.data));
  ws.onclose = () => {
    $("robot-status").textContent = "Disconnected from server — retrying…";
    setTimeout(connect, 1000);
  };
}
const send = (msg) => ws?.readyState === WebSocket.OPEN && ws.send(JSON.stringify(msg));

function handle(msg) {
  switch (msg.type) {
    case "status": return onStatus(msg);
    case "state": return onState(msg);
    case "robot": return onRobot(msg);
    case "vote_ack": return onVoteAck(msg);
    case "expression":
      $("expr").textContent = msg.label;
      $("expr-src").textContent = manualLabel ? "(keyboard)" : "(camera)";
      return;
  }
}

// ---------------------------------------------------------------- status / start
function onStatus(s) {
  status = s;
  const robotTxt = s.robot === "buddy"
    ? `Robot: Buddy — ${s.robots_connected ? "connected ✅" : "NOT connected ❌"}`
    : "Robot: mock avatar on this screen";
  $("robot-status").textContent = `${robotTxt} · ${s.config.rounds} rounds, ${s.config.chat_s}s chat, ${s.config.vote_s}s vote`;
  $("start-btn").disabled = s.running;
  $("avatar").classList.toggle("hidden", s.robot !== "mock");
  if (!s.running && (phase === "end" || phase === "aborted")) {
    setTimeout(showStart, 8000);
  }
}

function showStart() {
  if (status.running) return;
  phase = null;
  $("game").classList.add("hidden");
  $("start").classList.remove("hidden");
}

$("start-btn").onclick = () => {
  send({ type: "start", mode: $("mode").value, participant: $("participant").value.trim() });
};

// ---------------------------------------------------------------- game state
function onState(s) {
  phase = s.phase;
  $("start").classList.add("hidden");
  $("game").classList.remove("hidden");
  if (s.round) $("round").textContent = `Round ${s.round} / ${s.rounds}`;
  if (s.totals) {
    $("score-human").textContent = s.totals.human;
    $("score-robot").textContent = s.totals.robot;
  }
  $("phase-title").textContent = PHASE_TITLES[s.phase] ?? s.phase;
  $("vote").classList.toggle("hidden", s.phase !== "vote");
  $("vote-ack").classList.add("hidden");
  $("result").classList.toggle("hidden", s.phase !== "result");
  if (s.phase === "chat") $("subtitle").textContent = "";

  if (s.phase === "result") {
    showVote("res-human", s.human_vote);
    showVote("res-robot", s.robot_vote);
    $("pts-human").textContent = `+${s.points.human}`;
    $("pts-robot").textContent = `+${s.points.robot}`;
  }
  const showTimer = s.phase === "chat" || s.phase === "vote";
  $("timer").classList.toggle("hidden", !showTimer);
  startTimer(showTimer ? s.duration : 0);
}

function showVote(id, v) {
  const el = $(id);
  el.className = v;
  el.textContent = v === "C" ? "Cooperate" : v === "D" ? "Defect" : "No vote";
}

function startTimer(seconds) {
  clearInterval(timerHandle);
  const end = performance.now() + seconds * 1000;
  const tick = () => {
    const left = Math.max(0, Math.ceil((end - performance.now()) / 1000));
    $("timer").textContent = left;
    $("timer").classList.toggle("urgent", left <= 5);
    if (left <= 0) clearInterval(timerHandle);
  };
  tick();
  timerHandle = setInterval(tick, 200);
}

function vote(choice) {
  if (phase === "vote") send({ type: "vote", choice });
}
document.querySelectorAll(".vote-btn").forEach((b) => (b.onclick = () => vote(b.dataset.choice)));

function onVoteAck() {
  $("vote").classList.add("hidden");
  $("vote-ack").classList.remove("hidden");
}

// ---------------------------------------------------------------- robot (mock avatar + subtitles)
const MOODS = {
  //          eyeRy browL[y1,y2]  browR[y1,y2]  mouth path
  neutral:   [16, [48, 48], [48, 48], "M75 115 Q100 118 125 115"],
  happy:     [10, [46, 42], [42, 46], "M70 108 Q100 138 130 108"],
  sad:       [14, [50, 42], [42, 50], "M75 122 Q100 104 125 122"],
  angry:     [11, [40, 52], [52, 40], "M78 120 Q100 110 122 120"],
  surprised: [20, [36, 36], [36, 36], "M90 112 Q100 135 110 112 Q100 100 90 112"],
  thinking:  [12, [44, 44], [40, 48], "M80 116 L120 112"],
  listening: [16, [44, 44], [44, 44], "M80 114 Q100 120 120 114"],
};

function onRobot(cmd) {
  const mock = status.robot === "mock";
  if (cmd.cmd === "say") {
    $("subtitle").textContent = mock ? cmd.text : "";
    if (mock && "speechSynthesis" in window) {
      speechSynthesis.cancel();
      const u = new SpeechSynthesisUtterance(cmd.text);
      u.rate = 1.05;
      u.pitch = 1.3;
      speechSynthesis.speak(u);
    }
  } else if (cmd.cmd === "face" && mock) {
    const [ry, bl, br, mouth] = MOODS[cmd.mood] ?? MOODS.neutral;
    $("eye-l").setAttribute("ry", ry);
    $("eye-r").setAttribute("ry", ry);
    $("brow-l").setAttribute("y1", bl[0]); $("brow-l").setAttribute("y2", bl[1]);
    $("brow-r").setAttribute("y1", br[0]); $("brow-r").setAttribute("y2", br[1]);
    $("mouth").setAttribute("d", mouth);
  } else if (cmd.cmd === "gesture" && mock) {
    const av = $("avatar");
    av.className = "";
    void av.offsetWidth; // restart animation
    av.classList.add(`g-${cmd.name}`);
  } else if (cmd.cmd === "led" && mock) {
    document.documentElement.style.setProperty("--led", cmd.color);
  }
}

// ---------------------------------------------------------------- expression input
function sendExpression(scores) {
  if (manualLabel) return; // keyboard override wins
  if (scores) send({ type: "expression", scores });
  else send({ type: "expression", label: "no_face" });
}
setInterval(() => manualLabel && send({ type: "expression", label: manualLabel }), 250);

startFaceTracking($("cam"), sendExpression)
  .then(() => { cameraOk = true; $("camera-status").textContent = "Camera: face tracking on ✅"; })
  .catch((err) => {
    console.warn("face tracking unavailable", err);
    $("cam").classList.add("hidden");
    $("camera-status").textContent = "Camera: unavailable ❌ (use keys 1–4 to simulate)";
  });

// ---------------------------------------------------------------- keyboard
document.addEventListener("keydown", (e) => {
  if (e.target.tagName === "INPUT") return;
  const k = e.key.toLowerCase();
  if (k === "c" || k === "d") vote(k.toUpperCase());
  else if (MANUAL_LABELS[k]) manualLabel = MANUAL_LABELS[k];
  else if (k === "0") manualLabel = null;
  else if (k === "e") $("debug").classList.toggle("hidden");
  else if (k === "q" && e.shiftKey) send({ type: "abort" });
});

connect();
