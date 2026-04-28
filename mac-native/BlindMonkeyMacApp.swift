import SwiftUI

@main
struct BlindMonkeyMacApp: App {
    @StateObject private var model = MacCompanionModel()

    var body: some Scene {
        WindowGroup {
            MacDashboardView()
                .environmentObject(model)
                .frame(width: 820, height: 820)
        }
        .windowResizability(.contentSize)
    }
}

final class MacCompanionModel: ObservableObject {
    @Published var signedIn = false
    @Published var accessibilityReady = false
    @Published var relayConnected = false
    @Published var cursorWindows = 0

    var statusText: String {
        if !signedIn { return "Sign in to pair your iPhone" }
        if !accessibilityReady { return "Needs Mac access" }
        if !relayConnected { return "Relay disconnected" }
        if cursorWindows == 0 { return "No Cursor windows" }
        return "Ready"
    }
}

struct MacDashboardView: View {
    @EnvironmentObject private var model: MacCompanionModel

    var body: some View {
        VStack(alignment: .leading, spacing: 18) {
            HStack(spacing: 18) {
                Image(systemName: "macbook.and.iphone")
                    .font(.system(size: 54, weight: .semibold))
                    .foregroundStyle(.orange)
                VStack(alignment: .leading) {
                    Text("Blind Monkey")
                        .font(.largeTitle.bold())
                    Text("Voice and trackpad control for Cursor")
                        .foregroundStyle(.secondary)
                }
                Spacer()
                StatusPill(text: model.statusText)
            }

            Grid(horizontalSpacing: 16, verticalSpacing: 16) {
                GridRow {
                    SetupCard(title: "Account", value: model.signedIn ? "Signed in" : "Sign in required")
                    SetupCard(title: "Mac Access", value: model.accessibilityReady ? "Enabled" : "Needs access")
                }
                GridRow {
                    SetupCard(title: "Relay", value: model.relayConnected ? "Connected" : "Disconnected")
                    SetupCard(title: "Cursor", value: model.cursorWindows == 0 ? "No windows" : "\(model.cursorWindows) windows")
                }
            }

            Spacer()

            Button(model.signedIn ? "Open Phone App" : "Sign In") {
                model.signedIn = true
            }
            .buttonStyle(.borderedProminent)
            .controlSize(.large)
        }
        .padding(34)
        .background(Color.black)
        .foregroundStyle(.white)
    }
}

struct SetupCard: View {
    let title: String
    let value: String

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text(title.uppercased())
                .font(.caption.bold())
                .foregroundStyle(.secondary)
            Text(value)
                .font(.title3.bold())
            Spacer()
        }
        .padding(20)
        .frame(maxWidth: .infinity, minHeight: 150, alignment: .topLeading)
        .background(Color.white.opacity(0.08))
        .clipShape(RoundedRectangle(cornerRadius: 22, style: .continuous))
    }
}

struct StatusPill: View {
    let text: String

    var body: some View {
        Text(text)
            .font(.footnote.bold())
            .padding(.horizontal, 14)
            .padding(.vertical, 9)
            .background(Color.white.opacity(0.1))
            .clipShape(Capsule())
    }
}
