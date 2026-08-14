/*
 * Frida SSL/TLS certificate pinning bypass for Android.
 * Targets common Java/OkHttp/Flutter patterns, including the SecNeo/DexHelper
 * wrapper used by the Chery Europe app.
 *
 * Usage:
 *   1. Root your Android device or use a rooted emulator.
 *   2. Install frida-server on the device (adb push frida-server /data/local/tmp/).
 *   3. Run: adb shell "su -c /data/local/tmp/frida-server"
 *   4. On your PC: frida -U -f com.chery.eu.chery -l scripts/ssl_unpin.js --no-pause
 *
 * After the app starts, set the device proxy to this PC (192.168.0.115:8080)
 * and log in. MITM traffic should now be decrypted.
 */

function log(msg) {
    console.log("[ssl-unpin] " + msg);
}

function bypassJavaSSL() {
    try {
        var X509TrustManager = Java.use("javax.net.ssl.X509TrustManager");
        var SSLContext = Java.use("javax.net.ssl.SSLContext");

        var TrustManager = Java.registerClass({
            name: "com.chery.erp.TrustManager",
            implements: [X509TrustManager],
            methods: {
                checkClientTrusted: function () {},
                checkServerTrusted: function () {},
                getAcceptedIssuers: function () { return []; }
            }
        });

        var TrustManagers = [TrustManager.$new()];
        var SSLContext_init = SSLContext.init.overload(
            "[Ljavax/net/ssl/KeyManager;",
            "[Ljavax/net/ssl/TrustManager;",
            "java.security.SecureRandom"
        );
        SSLContext_init.implementation = function (km, tm, random) {
            log("SSLContext.init() hooked");
            SSLContext_init.call(this, km, TrustManagers, random);
        };
        log("Java SSLContext hook installed");
    } catch (e) {
        log("Java SSLContext hook failed: " + e);
    }
}

function bypassOkHttp() {
    try {
        var CertificatePinner = Java.use("okhttp3.CertificatePinner");
        CertificatePinner.check.overload("java.lang.String", "java.util.List").implementation = function () {
            log("OkHttp CertificatePinner.check() bypassed");
        };
        CertificatePinner.check.overload("java.lang.String", "[Ljava/security/cert/Certificate;").implementation = function () {
            log("OkHttp CertificatePinner.check(Certificate[]) bypassed");
        };
        log("OkHttp3 hook installed");
    } catch (e) {
        log("OkHttp3 hook failed: " + e);
    }

    try {
        var OkHostnameVerifier = Java.use("okhttp3.internal.tls.OkHostnameVerifier");
        OkHostnameVerifier.verify.overload("java.lang.String", "javax.net.ssl.SSLSession").implementation = function () {
            log("OkHostnameVerifier.verify() bypassed");
            return true;
        };
        log("OkHostnameVerifier hook installed");
    } catch (e) {
        log("OkHostnameVerifier hook failed: " + e);
    }
}

function bypassTrustManagerImpl() {
    try {
        var TrustManagerImpl = Java.use("com.android.org.conscrypt.TrustManagerImpl");
        TrustManagerImpl.verifyChain.implementation = function (untrustedChain, trustAnchorChain, host, clientAuth, ocspData, tlsSctData) {
            log("TrustManagerImpl.verifyChain() bypassed for " + host);
            return untrustedChain;
        };
        log("Conscrypt TrustManagerImpl hook installed");
    } catch (e) {
        log("Conscrypt TrustManagerImpl hook failed: " + e);
    }
}

function bypassWebViewSSL() {
    try {
        var SslErrorHandler = Java.use("android.webkit.SslErrorHandler");
        var WebViewClient = Java.use("android.webkit.WebViewClient");
        WebViewClient.onReceivedSslError.implementation = function (view, handler, error) {
            log("WebViewClient.onReceivedSslError() bypassed");
            handler.proceed();
        };
        log("WebView SSL hook installed");
    } catch (e) {
        log("WebView SSL hook failed: " + e);
    }
}

function hookFlutter() {
    try {
        var flutterModule = Process.findModuleByName("libflutter.so");
        if (flutterModule) {
            log("libflutter.so found at " + flutterModule.base);
            // Symbol names vary by Flutter version; these are common patterns.
            var symbols = ["SSL_CTX_set_custom_verify", "SSL_CTX_set_verify"];
            symbols.forEach(function (sym) {
                try {
                    var addr = Module.findExportByName("libflutter.so", sym);
                    if (addr && !addr.isNull()) {
                        Interceptor.attach(addr, {
                            onEnter: function (args) {
                                log("Flutter " + sym + " hooked");
                                args[2] = ptr(0);
                            }
                        });
                        log("Flutter " + sym + " attached");
                    }
                } catch (inner) {
                    log("Flutter symbol " + sym + ": " + inner);
                }
            });
        } else {
            log("libflutter.so not loaded yet");
        }
    } catch (e) {
        log("Flutter hook failed: " + e);
    }
}

if (Java.available) {
    Java.perform(function () {
        log("Starting SSL pinning bypass");
        bypassJavaSSL();
        bypassOkHttp();
        bypassTrustManagerImpl();
        bypassWebViewSSL();
        hookFlutter();
        log("All hooks installed");
    });
} else {
    log("Java runtime not available");
}
