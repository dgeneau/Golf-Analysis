import SwiftUI
import WebKit

/// Hosts the SwingCoach web app (the same page GitHub Pages serves) and
/// bridges it to the native Bluetooth engine:
///   page  -> native : webkit.messageHandlers.swingcoach.postMessage({cmd})
///   native -> page  : window._nativeStatus(...) / window._nativeSamples([...])
struct WebContainer: UIViewRepresentable {
    let ble: DotBluetoothManager

    static let appURL = URL(string: "https://dgeneau.github.io/Golf-Analysis/")!

    func makeCoordinator() -> Coordinator { Coordinator(ble: ble) }

    func makeUIView(context: Context) -> WKWebView {
        let config = WKWebViewConfiguration()
        config.allowsInlineMediaPlayback = true

        let controller = WKUserContentController()
        controller.add(context.coordinator, name: "swingcoach")
        // Mark native mode before any page script runs.
        let flag = WKUserScript(source: "window.__SWINGCOACH_NATIVE = true;",
                                injectionTime: .atDocumentStart,
                                forMainFrameOnly: true)
        controller.addUserScript(flag)
        config.userContentController = controller

        let webView = WKWebView(frame: .zero, configuration: config)
        webView.scrollView.contentInsetAdjustmentBehavior = .never
        webView.isOpaque = false
        webView.backgroundColor = UIColor(red: 0.06, green: 0.07, blue: 0.06, alpha: 1)
        webView.navigationDelegate = context.coordinator
        #if DEBUG
        if #available(iOS 16.4, *) { webView.isInspectable = true }
        #endif

        // The BLE engine pushes JS into whichever page is loaded.
        ble.evaluator = { [weak webView] js in
            DispatchQueue.main.async {
                webView?.evaluateJavaScript(js, completionHandler: nil)
            }
        }

        webView.load(URLRequest(url: WebContainer.appURL))
        return webView
    }

    func updateUIView(_ uiView: WKWebView, context: Context) {}

    final class Coordinator: NSObject, WKScriptMessageHandler, WKNavigationDelegate {
        let ble: DotBluetoothManager
        init(ble: DotBluetoothManager) { self.ble = ble }

        func userContentController(_ userContentController: WKUserContentController,
                                   didReceive message: WKScriptMessage) {
            guard message.name == "swingcoach",
                  let body = message.body as? [String: Any],
                  let cmd = body["cmd"] as? String else { return }
            switch cmd {
            case "connect": ble.connect()
            case "pick": ble.pick(id: body["id"] as? String ?? "")
            case "disconnect": ble.disconnect()
            default: break
            }
        }

        // The webview is full-bleed and env(safe-area-inset-*) reads 0 inside
        // it, so hand the page the real insets as CSS variables instead.
        func webView(_ webView: WKWebView, didFinish navigation: WKNavigation!) {
            let ins = webView.safeAreaInsets
            let js = "document.documentElement.style.setProperty('--sat','\(max(ins.top, 20))px');"
                   + "document.documentElement.style.setProperty('--sab','\(max(ins.bottom, 16))px');"
            webView.evaluateJavaScript(js, completionHandler: nil)
        }

        // Simple offline fallback: show a retry page instead of a white screen.
        func webView(_ webView: WKWebView, didFailProvisionalNavigation navigation: WKNavigation!,
                     withError error: Error) {
            let html = """
            <!doctype html><meta name=viewport content="width=device-width,initial-scale=1">
            <body style="background:#101312;color:#f5f4ef;font-family:-apple-system;display:flex;\
            align-items:center;justify-content:center;height:100vh;margin:0;text-align:center">
            <div><h2>SwingCoach needs internet for first load</h2>
            <p style="color:#97968c">Connect once and the app is cached for the course.</p>
            <button style="font-size:17px;padding:12px 24px;border-radius:10px;border:0"
            onclick="location.href='\(WebContainer.appURL)'">Retry</button></div>
            """
            webView.loadHTMLString(html, baseURL: nil)
        }
    }
}
