import SwiftUI
import UIKit

struct ContentView: View {
    @StateObject private var ble = DotBluetoothManager()

    var body: some View {
        WebContainer(ble: ble)
            .ignoresSafeArea()
            .onAppear {
                // A golf session shouldn't die because the screen dimmed.
                UIApplication.shared.isIdleTimerDisabled = true
            }
            .onDisappear {
                UIApplication.shared.isIdleTimerDisabled = false
            }
    }
}
