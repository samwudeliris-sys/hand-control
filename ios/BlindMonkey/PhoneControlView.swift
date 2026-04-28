import SwiftUI

struct PhoneControlView: View {
    @EnvironmentObject private var session: BlindMonkeySession
    @State private var selectedWindow = 0

    private let sampleWindows = [
        "Cursor Agent",
        "Project Notes",
        "Refactor Thread",
    ]

    var body: some View {
        VStack(spacing: 14) {
            HStack {
                Circle()
                    .fill(statusDotColor)
                    .frame(width: 10, height: 10)
                Text(session.statusText)
                    .font(.footnote.weight(.semibold))
                Spacer()
            }

            onboardingStrip

            TabView(selection: $selectedWindow) {
                ForEach(sampleWindows.indices, id: \.self) { index in
                    VStack(spacing: 18) {
                        Text(sampleWindows[index])
                            .font(.title2.bold())
                        Image(systemName: "mic.circle.fill")
                            .font(.system(size: 76))
                            .foregroundStyle(.orange)
                        Text("Tap to talk")
                            .font(.headline)
                            .foregroundStyle(.secondary)
                    }
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
                    .background(.thinMaterial)
                    .clipShape(RoundedRectangle(cornerRadius: 28, style: .continuous))
                    .padding(.horizontal, 8)
                    .tag(index)
                }
            }
            .tabViewStyle(.page(indexDisplayMode: .never))

            VStack(spacing: 10) {
                Capsule()
                    .fill(Color.secondary.opacity(0.18))
                    .frame(height: 210)
                    .overlay {
                        VStack(spacing: 8) {
                            Image(systemName: "hand.tap.fill")
                                .font(.system(size: 34))
                            Text("Trackpad")
                                .font(.headline)
                            Text("Drag, tap, and two-finger scroll")
                                .font(.caption)
                                .foregroundStyle(.secondary)
                        }
                    }
            }
        }
        .padding(16)
        .background(Color.black.ignoresSafeArea())
    }

    private var statusDotColor: Color {
        if !session.relayConnected { return .red }
        if !session.macOnline { return .orange }
        if !session.macAccessOK { return .red }
        return .green
    }

    private var onboardingStrip: some View {
        HStack(spacing: 10) {
            chipBool("Sign in", ok: session.isSignedIn)
            chipBool("Relay", ok: session.relayConnected)
            chipBool("Mac", ok: session.macOnline)
            chipBool("Access", ok: session.macAccessOK)
            chipOpt("Mic", ok: session.micOK)
        }
        .font(.system(size: 9, weight: .bold))
        .textCase(.uppercase)
    }

    private func chipBool(_ title: String, ok: Bool) -> some View {
        Text(ok ? "\(title) ✓" : title)
            .foregroundStyle(ok ? .green : .red)
    }

    private func chipOpt(_ title: String, ok: Bool?) -> some View {
        let (color, label): (Color, String) = {
            if ok == true { return (.green, "\(title) ✓") }
            if ok == false { return (.red, title) }
            return (.gray, title)
        }()
        return Text(label)
            .foregroundStyle(color)
    }
}
