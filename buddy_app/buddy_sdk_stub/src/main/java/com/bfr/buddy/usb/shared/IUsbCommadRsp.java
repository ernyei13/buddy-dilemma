package com.bfr.buddy.usb.shared;

import android.os.RemoteException;

/** Stand-in for the SDK's AIDL motor/LED response callback (the SDK spells it "Commad"). */
public interface IUsbCommadRsp {
    void onSuccess(String s) throws RemoteException;

    void onFailed(String s) throws RemoteException;

    abstract class Stub implements IUsbCommadRsp {
    }
}
