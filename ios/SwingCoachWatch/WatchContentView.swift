import SwiftUI

struct WatchContentView: View {
    @EnvironmentObject var motion: WatchMotionManager

    var body: some View {
        VStack(spacing: 8) {
            HStack(spacing: 6) {
                Circle()
                    .fill(dotColor)
                    .frame(width: 8, height: 8)
                Text(stateLabel)
                    .font(.system(size: 13, weight: .semibold))
                Spacer()
            }
            if !motion.detail.isEmpty {
                Text(motion.detail)
                    .font(.system(size: 11))
                    .foregroundStyle(.secondary)
                    .frame(maxWidth: .infinity, alignment: .leading)
            }
            Spacer()
            VStack(spacing: 0) {
                Text("\(motion.swingCount)")
                    .font(.system(size: 54, weight: .bold, design: .rounded))
                    .contentTransition(.numericText())
                Text(motion.swingCount == 1 ? "SWING SENT" : "SWINGS SENT")
                    .font(.system(size: 10, weight: .semibold))
                    .foregroundStyle(.secondary)
                    .kerning(1.2)
            }
            Spacer()
            Button(action: { motion.state == .capturing ? motion.stop() : motion.start() }) {
                Text(motion.state == .capturing ? "Stop" : "Start session")
                    .font(.system(size: 15, weight: .semibold))
            }
            .tint(motion.state == .capturing ? .red : .blue)
        }
        .padding(.horizontal, 4)
    }

    private var stateLabel: String {
        switch motion.state {
        case .idle: return "Ready"
        case .starting: return "Starting…"
        case .capturing: return motion.highRate ? "Capturing · 200 Hz" : "Capturing · 100 Hz"
        case .unsupported: return "Not supported"
        case .error: return "Error"
        }
    }

    private var dotColor: Color {
        switch motion.state {
        case .capturing: return .green
        case .error, .unsupported: return .orange
        default: return .gray
        }
    }
}
