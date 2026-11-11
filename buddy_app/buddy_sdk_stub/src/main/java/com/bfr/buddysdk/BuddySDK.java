package com.bfr.buddysdk;

import android.graphics.Color;
import android.os.Handler;
import android.os.Looper;
import android.util.Log;
import android.view.View;

import com.bfr.buddy.speech.shared.ITTSCallback;
import com.bfr.buddy.ui.shared.FacialEvent;
import com.bfr.buddy.ui.shared.FacialExpression;
import com.bfr.buddy.ui.shared.LabialExpression;
import com.bfr.buddy.usb.shared.IUsbCommadRsp;

/**
 * Stand-in for the Buddy SDK. Same names as the real API; calls are logged (tag "BuddySDK-stub"),
 * the face view changes colour per mood, and callbacks fire after a plausible delay.
 */
public final class BuddySDK {
    private static final String TAG = "BuddySDK-stub";
    private static final Handler MAIN = new Handler(Looper.getMainLooper());

    private BuddySDK() {
    }

    private static void later(long ms, Runnable r) {
        MAIN.postDelayed(() -> {
            try {
                r.run();
            } catch (Exception e) {
                Log.w(TAG, "callback failed", e);
            }
        }, ms);
    }

    private interface Call {
        void run() throws Exception;
    }

    private static Runnable safe(Call c) {
        return () -> {
            try {
                c.run();
            } catch (Exception e) {
                Log.w(TAG, "callback failed", e);
            }
        };
    }

    public static final class UI {
        private static View face;

        private UI() {
        }

        public static void setViewAsFace(View v) {
            face = v;
            Log.i(TAG, "UI.setViewAsFace");
        }

        public static void setMood(FacialExpression e) {
            Log.i(TAG, "UI.setMood " + e);
            if (face == null) return;
            int c;
            switch (e) {
                case HAPPY: c = Color.rgb(43, 182, 115); break;
                case SAD: c = Color.rgb(60, 90, 160); break;
                case ANGRY: c = Color.rgb(200, 50, 50); break;
                case SURPRISED: c = Color.rgb(245, 166, 35); break;
                case THINKING: c = Color.rgb(120, 90, 170); break;
                case LISTENING: c = Color.rgb(40, 140, 160); break;
                default: c = Color.rgb(40, 50, 70);
            }
            face.setBackgroundColor(c);
        }

        public static void setFacialExpression(FacialExpression e) {
            setMood(e);
        }

        public static void playFacialEvent(FacialEvent e) {
            Log.i(TAG, "UI.playFacialEvent " + e);
        }
    }

    public static final class Speech {
        private Speech() {
        }

        public static boolean isReadyToSpeak() {
            return true;
        }

        public static void loadReadSpeaker() {
            Log.i(TAG, "Speech.loadReadSpeaker");
        }

        public static void stopSpeaking() {
            Log.i(TAG, "Speech.stopSpeaking");
        }

        public static void startSpeaking(String text) {
            Log.i(TAG, "Speech.startSpeaking " + text);
        }

        public static void startSpeaking(String text, LabialExpression mouth, ITTSCallback cb) {
            Log.i(TAG, "Speech.startSpeaking [" + mouth + "] " + text);
            long ms = (long) (text.split("\\s+").length / 2.6 * 1000);
            if (cb != null) later(ms, safe(() -> cb.onSuccess("SPEECH_FINISHED")));
        }
    }

    public static final class USB {
        private USB() {
        }

        public static void enableYesMove(int state, IUsbCommadRsp cb) {
            Log.i(TAG, "USB.enableYesMove " + state);
            ok(cb, "OK", 50);
        }

        public static void enableNoMove(int state, IUsbCommadRsp cb) {
            Log.i(TAG, "USB.enableNoMove " + state);
            ok(cb, "OK", 50);
        }

        public static void buddySayYes(float speed, float angle, IUsbCommadRsp cb) {
            Log.i(TAG, "USB.buddySayYes speed=" + speed + " angle=" + angle);
            ok(cb, "YES_MOVE_FINISHED", 400);
        }

        public static void buddySayNo(float speed, float angle, IUsbCommadRsp cb) {
            Log.i(TAG, "USB.buddySayNo speed=" + speed + " angle=" + angle);
            ok(cb, "NO_MOVE_FINISHED", 400);
        }

        public static void updateAllLed(String color, IUsbCommadRsp cb) {
            Log.i(TAG, "USB.updateAllLed " + color);
            ok(cb, "OK", 20);
        }

        private static void ok(IUsbCommadRsp cb, String result, long ms) {
            if (cb != null) later(ms, safe(() -> cb.onSuccess(result)));
        }
    }
}
