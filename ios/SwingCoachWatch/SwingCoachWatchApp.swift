import SwiftUI

@main
struct SwingCoachWatchApp: App {
    @StateObject private var motion = WatchMotionManager()

    var body: some Scene {
        WindowGroup {
            WatchContentView()
                .environmentObject(motion)
        }
    }
}
