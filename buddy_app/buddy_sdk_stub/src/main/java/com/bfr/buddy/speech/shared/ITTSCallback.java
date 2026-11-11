package com.bfr.buddy.speech.shared;

import android.os.RemoteException;

/** Stand-in for the SDK's AIDL text-to-speech callback. */
public interface ITTSCallback {
    void onSuccess(String s) throws RemoteException;

    void onPause() throws RemoteException;

    void onResume() throws RemoteException;

    void onError(String s) throws RemoteException;

    abstract class Stub implements ITTSCallback {
    }
}
