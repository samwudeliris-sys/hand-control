import SwiftUI

@main
struct BlindMonkeyApp: App {
    @StateObject private var session = BlindMonkeySession()

    var body: some Scene {
        WindowGroup {
            RootView()
                .environmentObject(session)
        }
    }
}

final class BlindMonkeySession: ObservableObject {
    @Published var isSignedIn = false
    @Published var macOnline = false
    @Published var relayConnected = false
    @Published var macAccessOK = true
    @Published var micOK: Bool? = nil
    @Published var statusText = "Sign in to connect your Mac"
}

struct RootView: View {
    @EnvironmentObject private var session: BlindMonkeySession

    var body: some View {
        Group {
            if session.isSignedIn {
                PhoneControlView()
            } else {
                SignInView()
            }
        }
        .preferredColorScheme(.dark)
    }
}

struct SignInView: View {
    @EnvironmentObject private var session: BlindMonkeySession
    @State private var email = ""

    var body: some View {
        VStack(spacing: 18) {
            Image(systemName: "iphone.and.arrow.forward")
                .font(.system(size: 56, weight: .semibold))
                .foregroundStyle(.orange)

            Text("Blind Monkey")
                .font(.largeTitle.bold())

            Text("Sign in with the same account on your Mac and iPhone. They will connect automatically.")
                .multilineTextAlignment(.center)
                .foregroundStyle(.secondary)

            TextField("Email", text: $email)
                .textContentType(.emailAddress)
                .keyboardType(.emailAddress)
                .textInputAutocapitalization(.never)
                .autocorrectionDisabled()
                .textFieldStyle(.roundedBorder)

            Button("Continue") {
                session.isSignedIn = true
                session.relayConnected = true
                session.macOnline = true
                session.macAccessOK = true
                session.statusText = "Connected (shell — wire Supabase + relay next)"
            }
            .buttonStyle(.borderedProminent)
        }
        .padding(28)
    }
}
