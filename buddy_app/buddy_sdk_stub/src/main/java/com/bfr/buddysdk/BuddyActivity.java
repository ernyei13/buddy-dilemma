package com.bfr.buddysdk;

import android.app.Activity;
import android.os.Handler;
import android.os.Looper;

/** Stand-in. Calls onSDKReady() once the activity is visible, like the real SDK after binding. */
public class BuddyActivity extends Activity {
    private boolean ready = false;

    @Override
    protected void onResume() {
        super.onResume();
        if (!ready) {
            ready = true;
            new Handler(Looper.getMainLooper()).post(this::onSDKReady);
        }
    }

    public void onSDKReady() {
    }
}
