package se.kth.buddydilemma;

import android.content.SharedPreferences;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.util.Log;
import android.view.View;
import android.widget.Button;
import android.widget.EditText;
import android.widget.TextView;

import com.bfr.buddysdk.BuddyActivity;
import com.bfr.buddysdk.BuddySDK;

// SDK types. The class names come from the Buddy SDK 2.4 user guide, but the guide does not print
// their packages. If one of these lines is red in Android Studio, delete it, put the cursor on the
// class name in the code and press Alt+Enter -> "Import class".
import com.bfr.buddy.speech.shared.ITTSCallback;
import com.bfr.buddy.ui.shared.FacialEvent;
import com.bfr.buddy.ui.shared.FacialExpression;
import com.bfr.buddy.ui.shared.LabialExpression;
import com.bfr.buddy.usb.shared.IUsbCommadRsp;

import org.json.JSONObject;

import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.TimeUnit;

import okhttp3.OkHttpClient;
import okhttp3.Request;
import okhttp3.Response;
import okhttp3.WebSocket;
import okhttp3.WebSocketListener;

/**
 * Buddy's body for the Prisoner's Dilemma study.
 *
 * The laptop runs everything (camera, mic, speech recognition, LLM, game). This app connects to
 * it over Wi-Fi (ws://LAPTOP:8000/ws/robot) and turns its JSON commands into Buddy's NATIVE
 * face, voice, head movements and LEDs. Protocol: docs/protocol.md in the repo.
 *
 *   {"cmd":"say","text":"..."}      -> BuddySDK.Speech.startSpeaking (mouth moves)
 *   {"cmd":"face","mood":"happy"}   -> BuddySDK.UI.setMood(FacialExpression.HAPPY)
 *   {"cmd":"gesture","name":"nod"}  -> head "yes"/"no" motors + facial events
 *   {"cmd":"led","color":"#00BFFF"} -> BuddySDK.USB.updateAllLed
 */
public class MainActivity extends BuddyActivity {
    private static final String TAG = "BuddyDilemma";
    private static final String PREFS = "buddy_dilemma";
    private static final String KEY_URL = "server_url";

    // ---- HEAD NOTES -------------------------------------------------------------------------
    // The SDK guide calls the angle a "target angle", but its own example moves the head back by
    // sending the negative angle, which suggests angles are RELATIVE. We follow the example.
    // If nods drift or don't come back to center on the real robot, set this to false.
    private static final boolean HEAD_ANGLES_ARE_RELATIVE = true;
    private static final float YES_SPEED = 40f; // deg/s, max 49.2
    private static final float NO_SPEED = 80f;  // deg/s, max 140
    private static final long MOVE_TIMEOUT_MS = 2500;

    private final Handler main = new Handler(Looper.getMainLooper());
    private final OkHttpClient http = new OkHttpClient.Builder()
            .pingInterval(15, TimeUnit.SECONDS)
            .build();

    private WebSocket ws;
    private boolean sdkReady = false;
    private boolean paused = false;
    private String mood = "neutral";
    private int gestureGeneration = 0;
    private float yesAngle = 0f;
    private float noAngle = 0f;

    private TextView status;
    private EditText urlInput;
    private View panel;

    // =========================================================================================
    // Lifecycle
    // =========================================================================================
    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_main);
        status = findViewById(R.id.status);
        urlInput = findViewById(R.id.server_url);
        panel = findViewById(R.id.panel);

        urlInput.setText(prefs().getString(KEY_URL, ""));
        Button connect = findViewById(R.id.connect);
        connect.setOnClickListener(v -> {
            String url = urlInput.getText().toString().trim();
            prefs().edit().putString(KEY_URL, url).apply();
            connect();
        });
        // Long-press the status text to show the address panel again.
        status.setOnLongClickListener(v -> {
            panel.setVisibility(View.VISIBLE);
            return true;
        });
    }

    @Override
    public void onSDKReady() {
        super.onSDKReady();
        sdkReady = true;
        BuddySDK.UI.setViewAsFace(findViewById(R.id.view_face));
        if (!BuddySDK.Speech.isReadyToSpeak()) {
            BuddySDK.Speech.loadReadSpeaker();
        }
        BuddySDK.USB.enableYesMove(1, logRsp("enable yes motor"));
        BuddySDK.USB.enableNoMove(1, logRsp("enable no motor"));
        BuddySDK.UI.setMood(FacialExpression.NEUTRAL);
        setStatus("SDK ready");
        if (!savedUrl().isEmpty()) connect();
    }

    @Override
    protected void onResume() {
        super.onResume();
        paused = false;
        if (sdkReady && !savedUrl().isEmpty()) connect();
    }

    @Override
    protected void onPause() {
        // Guide: stop our processes on pause, and don't call the SDK here.
        paused = true;
        if (ws != null) ws.close(1000, "paused");
        ws = null;
        super.onPause();
    }

    // =========================================================================================
    // Connection to the laptop
    // =========================================================================================
    private void connect() {
        String url = savedUrl();
        if (url.isEmpty()) {
            setStatus("Enter the laptop address and press Connect");
            panel.setVisibility(View.VISIBLE);
            return;
        }
        if (ws != null) ws.close(1000, "reconnect");
        setStatus("Connecting to " + url + " …");
        ws = http.newWebSocket(new Request.Builder().url(url).build(), new WebSocketListener() {
            @Override
            public void onOpen(WebSocket socket, Response response) {
                socket.send("{\"type\":\"hello\",\"name\":\"buddy\"}");
                main.post(() -> {
                    setStatus("Connected ✓");
                    panel.setVisibility(View.GONE);
                });
            }

            @Override
            public void onMessage(WebSocket socket, String text) {
                main.post(() -> handle(text));
            }

            @Override
            public void onFailure(WebSocket socket, Throwable t, Response response) {
                Log.w(TAG, "connection failed", t);
                main.post(() -> retryLater("Connection failed: " + t.getMessage()));
            }

            @Override
            public void onClosed(WebSocket socket, int code, String reason) {
                main.post(() -> retryLater("Disconnected"));
            }
        });
    }

    private void retryLater(String why) {
        setStatus(why + " — retrying…");
        panel.setVisibility(View.VISIBLE);
        if (!paused) main.postDelayed(() -> { if (!paused) connect(); }, 3000);
    }

    private void send(String json) {
        if (ws != null) ws.send(json);
    }

    // =========================================================================================
    // Commands
    // =========================================================================================
    private void handle(String raw) {
        if (!sdkReady) return;
        try {
            JSONObject msg = new JSONObject(raw);
            switch (msg.optString("cmd")) {
                case "say": say(msg.optString("text")); break;
                case "face": face(msg.optString("mood")); break;
                case "gesture": gesture(msg.optString("name")); break;
                case "led": led(msg.optString("color")); break;
                default: Log.i(TAG, "ignoring " + raw);
            }
        } catch (Exception e) {
            Log.w(TAG, "bad command " + raw, e);
        }
    }

    /** Speak with Buddy's own voice; the native mouth animates while talking. */
    private void say(String text) {
        if (text.isEmpty()) return;
        BuddySDK.Speech.stopSpeaking();
        BuddySDK.Speech.startSpeaking(text, labialFor(mood), new ITTSCallback.Stub() {
            @Override
            public void onSuccess(String s) { speechDone(); }

            @Override
            public void onPause() { }

            @Override
            public void onResume() { }

            @Override
            public void onError(String s) {
                Log.w(TAG, "TTS error " + s);
                speechDone();
            }
        });
        // If the callback above does not compile with your SDK version, replace this method's
        // body with:  BuddySDK.Speech.stopSpeaking(); BuddySDK.Speech.startSpeaking(text);
        // (the laptop then estimates how long Buddy talks).
    }

    /** Tell the laptop Buddy finished talking, so it can unmute the participant's mic. */
    private void speechDone() {
        send("{\"type\":\"speech_done\"}");
    }

    /** Buddy's native facial expressions. setMood also sets the LEDs to match the mood. */
    private void face(String m) {
        mood = m;
        BuddySDK.UI.setMood(expressionFor(m));
    }

    private void led(String color) {
        if (!color.startsWith("#")) return; // the laptop sends #rrggbb
        BuddySDK.USB.updateAllLed(color, logRsp("led"));
    }

    // =========================================================================================
    // Gestures: head "yes" (up/down) and "no" (left/right) motors + native facial events
    // =========================================================================================
    private void gesture(String name) {
        int gen = ++gestureGeneration; // a new gesture cancels the rest of the previous one
        List<Move> moves = new ArrayList<>();
        switch (name) {
            case "nod":
                moves.add(yes(-12)); moves.add(yes(12)); moves.add(yes(-12)); moves.add(yes(12));
                break;
            case "shake":
                moves.add(no(20)); moves.add(no(-40)); moves.add(no(20));
                break;
            case "tilt": // curious look
                BuddySDK.UI.playFacialEvent(FacialEvent.WHAT);
                moves.add(no(15)); moves.add(pause(900)); moves.add(no(-15));
                break;
            case "look_down":
                moves.add(yes(-20)); moves.add(pause(1200)); moves.add(yes(20));
                break;
            case "celebrate":
                BuddySDK.UI.playFacialEvent(FacialEvent.SMILE);
                moves.add(yes(10)); moves.add(yes(-10)); moves.add(yes(10)); moves.add(yes(-10));
                break;
            default:
                return;
        }
        runMoves(moves, 0, gen);
    }

    private static final class Move {
        final char axis; // 'Y' yes motor, 'N' no motor, 'P' pause
        final float delta;

        Move(char axis, float delta) { this.axis = axis; this.delta = delta; }
    }

    private static Move yes(float d) { return new Move('Y', d); }
    private static Move no(float d) { return new Move('N', d); }
    private static Move pause(long ms) { return new Move('P', ms); }

    private void runMoves(List<Move> moves, int i, int gen) {
        if (gen != gestureGeneration || i >= moves.size()) return;
        Move m = moves.get(i);
        Runnable next = () -> runMoves(moves, i + 1, gen);
        if (m.axis == 'P') {
            main.postDelayed(next, (long) m.delta);
            return;
        }
        final boolean[] done = {false};
        Runnable once = () -> { if (!done[0]) { done[0] = true; next.run(); } };
        main.postDelayed(once, MOVE_TIMEOUT_MS); // safety net if no "finished" callback arrives

        IUsbCommadRsp rsp = new IUsbCommadRsp.Stub() {
            @Override
            public void onSuccess(String s) {
                if (s.endsWith("MOVE_FINISHED")) main.post(once);
            }

            @Override
            public void onFailed(String e) {
                Log.w(TAG, "head move failed: " + e);
                main.post(once);
            }
        };
        if (m.axis == 'Y') {
            yesAngle += m.delta;
            float angle = HEAD_ANGLES_ARE_RELATIVE ? m.delta : clamp(yesAngle, -35, 45);
            BuddySDK.USB.buddySayYes(YES_SPEED, angle, rsp);
        } else {
            noAngle += m.delta;
            float angle = HEAD_ANGLES_ARE_RELATIVE ? m.delta : clamp(noAngle, -90, 90);
            BuddySDK.USB.buddySayNo(NO_SPEED, angle, rsp);
        }
    }

    // =========================================================================================
    // Helpers
    // =========================================================================================
    private static FacialExpression expressionFor(String m) {
        switch (m) {
            case "happy": return FacialExpression.HAPPY;
            case "sad": return FacialExpression.SAD;
            case "angry": return FacialExpression.ANGRY;
            case "surprised": return FacialExpression.SURPRISED;
            case "thinking": return FacialExpression.THINKING;
            case "listening": return FacialExpression.LISTENING;
            default: return FacialExpression.NEUTRAL;
        }
    }

    private static LabialExpression labialFor(String m) {
        switch (m) {
            case "happy": return LabialExpression.SPEAK_HAPPY;
            case "angry": return LabialExpression.SPEAK_ANGRY;
            default: return LabialExpression.SPEAK_NEUTRAL;
        }
    }

    private static float clamp(float v, float lo, float hi) {
        return Math.max(lo, Math.min(hi, v));
    }

    private IUsbCommadRsp logRsp(String what) {
        return new IUsbCommadRsp.Stub() {
            @Override
            public void onSuccess(String s) { Log.i(TAG, what + ": " + s); }

            @Override
            public void onFailed(String e) { Log.w(TAG, what + " failed: " + e); }
        };
    }

    private SharedPreferences prefs() {
        return getSharedPreferences(PREFS, MODE_PRIVATE);
    }

    private String savedUrl() {
        return prefs().getString(KEY_URL, "").trim();
    }

    private void setStatus(String text) {
        status.setText(text);
        Log.i(TAG, text);
    }
}
