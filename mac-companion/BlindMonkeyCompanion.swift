import Cocoa
import ApplicationServices
import Security

enum BMKeychain {
    private static let service = "com.blindmonkey.launcher.auth"

    static func set(_ value: String, account: String) {
        let data = Data(value.utf8)
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: account,
        ]
        SecItemDelete(query as CFDictionary)
        var toAdd = query
        toAdd[kSecValueData as String] = data
        SecItemAdd(toAdd as CFDictionary, nil)
    }

    static func get(account: String) -> String? {
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: account,
            kSecReturnData as String: kCFBooleanTrue!,
            kSecMatchLimit as String: kSecMatchLimitOne,
        ]
        var out: AnyObject?
        let status = SecItemCopyMatching(query as CFDictionary, &out)
        guard status == errSecSuccess, let data = out as? Data,
              let s = String(data: data, encoding: .utf8) else { return nil }
        return s
    }
}

final class AppDelegate: NSObject, NSApplicationDelegate {
    private let repoDir: String
    private let port = "8000"
    private let squareWindowSize = NSSize(width: 820, height: 820)
    private var process: Process?
    private var window: NSWindow!
    private var statusLabel: NSTextField!
    private var statusDot: NSView!
    private var phoneURLField: NSTextField!
    private var permissionLabel: NSTextField!
    private var accountTokenField: NSTextField?
    private var logView: NSTextView?
    private var logFileURL: URL
    private var permissionPollTimer: Timer?

    private struct ServerHealth {
        let trusted: Bool
        let windowsCount: Int
        let pythonExecutable: String?
        let accessibilityHint: String?
    }

    override init() {
        let bundledRepo = Bundle.main.object(forInfoDictionaryKey: "BMRepoDir") as? String
        self.repoDir = bundledRepo ?? FileManager.default.currentDirectoryPath
        let logDir = FileManager.default.homeDirectoryForCurrentUser
            .appendingPathComponent("Library/Logs/BlindMonkey", isDirectory: true)
        try? FileManager.default.createDirectory(at: logDir, withIntermediateDirectories: true)
        self.logFileURL = logDir.appendingPathComponent("server.log")
        super.init()
    }

    func applicationDidFinishLaunching(_ notification: Notification) {
        buildWindow()
        window.makeKeyAndOrderFront(nil)
        forceSquareWindow()
        NSApp.activate(ignoringOtherApps: true)
        startServerIfNeeded()
        permissionPollTimer = Timer.scheduledTimer(withTimeInterval: 2.0, repeats: true) { [weak self] _ in
            self?.refreshPermissionStatus(prompt: false)
        }
        if let t = permissionPollTimer {
            RunLoop.main.add(t, forMode: .common)
        }
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.15) { [weak self] in
            self?.forceSquareWindow()
        }
    }

    func applicationShouldTerminate(_ sender: NSApplication) -> NSApplication.TerminateReply {
        permissionPollTimer?.invalidate()
        permissionPollTimer = nil
        stopOwnedServer()
        return .terminateNow
    }

    private func buildWindow() {
        window = NSWindow(
            contentRect: NSRect(origin: .zero, size: squareWindowSize),
            styleMask: [.titled, .closable, .miniaturizable, .fullSizeContentView],
            backing: .buffered,
            defer: false
        )
        window.title = "Blind Monkey"
        window.titlebarAppearsTransparent = true
        window.isMovableByWindowBackground = true
        window.minSize = squareWindowSize
        window.maxSize = squareWindowSize
        window.contentMinSize = squareWindowSize
        window.contentMaxSize = squareWindowSize
        window.setFrame(NSRect(origin: .zero, size: squareWindowSize), display: true)
        window.center()

        let content = NSView(frame: NSRect(origin: .zero, size: squareWindowSize))
        content.translatesAutoresizingMaskIntoConstraints = false
        content.wantsLayer = true
        content.layer?.backgroundColor = NSColor(red: 0.035, green: 0.035, blue: 0.035, alpha: 1).cgColor
        window.contentView = content
        NSLayoutConstraint.activate([
            content.widthAnchor.constraint(equalToConstant: squareWindowSize.width),
            content.heightAnchor.constraint(equalToConstant: squareWindowSize.height),
        ])

        let icon = NSImageView()
        icon.translatesAutoresizingMaskIntoConstraints = false
        icon.image = NSImage(contentsOfFile: "\(repoDir)/phone/icon-512.png")
        icon.imageScaling = .scaleProportionallyUpOrDown
        icon.wantsLayer = true
        icon.layer?.cornerRadius = 24

        let title = NSTextField(labelWithString: "Blind Monkey")
        title.font = NSFont.boldSystemFont(ofSize: 32)
        title.textColor = .white
        title.translatesAutoresizingMaskIntoConstraints = false

        let subtitle = NSTextField(labelWithString: "Voice and trackpad control for Cursor")
        subtitle.font = NSFont.systemFont(ofSize: 15, weight: .medium)
        subtitle.textColor = NSColor(white: 0.68, alpha: 1)
        subtitle.translatesAutoresizingMaskIntoConstraints = false

        let statusPill = NSView()
        statusPill.translatesAutoresizingMaskIntoConstraints = false
        statusPill.wantsLayer = true
        statusPill.layer?.backgroundColor = NSColor(white: 0.12, alpha: 1).cgColor
        statusPill.layer?.cornerRadius = 18

        statusDot = NSView()
        statusDot.translatesAutoresizingMaskIntoConstraints = false
        statusDot.wantsLayer = true
        statusDot.layer?.cornerRadius = 5
        statusDot.layer?.backgroundColor = NSColor.systemOrange.cgColor

        statusLabel = NSTextField(labelWithString: "Starting...")
        statusLabel.font = NSFont.systemFont(ofSize: 13, weight: .semibold)
        statusLabel.textColor = NSColor(white: 0.86, alpha: 1)
        statusLabel.translatesAutoresizingMaskIntoConstraints = false

        let statusStack = NSStackView(views: [statusDot, statusLabel])
        statusStack.orientation = .horizontal
        statusStack.alignment = .centerY
        statusStack.spacing = 8
        statusStack.translatesAutoresizingMaskIntoConstraints = false
        statusPill.addSubview(statusStack)

        let connectCard = panelView()
        let connectEyebrow = sectionTitle("Phone")
        let connectTitle = NSTextField(labelWithString: "Connect your iPhone")
        connectTitle.font = NSFont.boldSystemFont(ofSize: 22)
        connectTitle.textColor = .white
        connectTitle.translatesAutoresizingMaskIntoConstraints = false

        let connectHint = helperText(
            usesAccountPairing()
                ? "On your iPhone, open the link below and sign in with the same account. No shared relay password is required."
                : "Use your iPhone camera to scan the QR code, or open/copy the link below."
        )

        phoneURLField = NSTextField(labelWithString: phoneURL())
        phoneURLField.font = NSFont.systemFont(ofSize: 15, weight: .semibold)
        phoneURLField.textColor = NSColor(red: 1.0, green: 0.45, blue: 0.27, alpha: 1)
        phoneURLField.lineBreakMode = .byTruncatingMiddle
        phoneURLField.translatesAutoresizingMaskIntoConstraints = false
        phoneURLField.wantsLayer = true
        phoneURLField.layer?.backgroundColor = NSColor(white: 0.12, alpha: 1).cgColor
        phoneURLField.layer?.cornerRadius = 12

        let openButton = primaryButton("Open Phone", #selector(openPhoneURL))
        let copyButton = secondaryButton("Copy Link", #selector(copyPhoneURL))
        let qrButton = secondaryButton("Scan QR", #selector(showQR))
        let connectActions = buttonRow([openButton, copyButton, qrButton])

        let permissionCard = panelView()
        let permissionTitle = sectionTitle("Permissions")
        let permissionHeading = NSTextField(labelWithString: "Mac control access")
        permissionHeading.font = NSFont.boldSystemFont(ofSize: 18)
        permissionHeading.textColor = .white
        permissionHeading.translatesAutoresizingMaskIntoConstraints = false
        permissionLabel = helperText("Checking Accessibility permission...")
        let permissionButton = primaryButton("Enable Access", #selector(openAccessibilitySettings))

        let serverCard = panelView()
        let serverTitle = sectionTitle("Connection")
        let serverHeading = NSTextField(labelWithString: "Connection")
        serverHeading.font = NSFont.boldSystemFont(ofSize: 18)
        serverHeading.textColor = .white
        serverHeading.translatesAutoresizingMaskIntoConstraints = false
        let restartButton = secondaryButton("Restart", #selector(restartServer))
        let logsButton = secondaryButton("Logs", #selector(openLogs))
        let serverHint = helperText("Blind Monkey is ready. Restart only if your phone stops connecting.")
        let serverActions = buttonRow([restartButton, logsButton])

        let guideCard = panelView()
        let guideTitle = sectionTitle(usesAccountPairing() ? "Account" : "How To Use")
        let guideHeading = NSTextField(
            labelWithString: usesAccountPairing() ? "Supabase access token" : "You are ready"
        )
        guideHeading.font = NSFont.boldSystemFont(ofSize: 18)
        guideHeading.textColor = .white
        guideHeading.translatesAutoresizingMaskIntoConstraints = false
        var guideText = helperText(
            usesAccountPairing()
                ? "Paste a current access token from a signed-in session (or keep it in ~/.hand-control.env). The server restarts when you save."
                : "Open the phone link, allow microphone access, then swipe between Cursor windows and tap to dictate."
        )
        if usesAccountPairing() {
            let field = NSTextField(string: BMKeychain.get(account: "supabase_access") ?? "")
            field.font = NSFont.systemFont(ofSize: 12, weight: .regular)
            field.textColor = .white
            field.backgroundColor = NSColor(white: 0.08, alpha: 1)
            field.isBordered = true
            field.isEditable = true
            field.isSelectable = true
            field.translatesAutoresizingMaskIntoConstraints = false
            field.cell?.sendsActionOnEndEditing = true
            field.toolTip = "Supabase access token (JWT) for the same user as the phone app"
            accountTokenField = field
            guideText = helperText("Saved to the Keychain. You can also set BLIND_SUPABASE_ACCESS_TOKEN in ~/.hand-control.env")
        }

        connectCard.addSubview(connectEyebrow)
        connectCard.addSubview(connectTitle)
        connectCard.addSubview(connectHint)
        connectCard.addSubview(phoneURLField)
        connectCard.addSubview(connectActions)

        permissionCard.addSubview(permissionTitle)
        permissionCard.addSubview(permissionHeading)
        permissionCard.addSubview(permissionLabel)
        permissionCard.addSubview(permissionButton)

        serverCard.addSubview(serverTitle)
        serverCard.addSubview(serverHeading)
        serverCard.addSubview(serverHint)
        serverCard.addSubview(serverActions)

        guideCard.addSubview(guideTitle)
        guideCard.addSubview(guideHeading)
        if let field = accountTokenField {
            let saveToken = primaryButton("Save to Keychain & restart", #selector(saveAccountToken))
            guideCard.addSubview(field)
            guideCard.addSubview(saveToken)
            guideCard.addSubview(guideText)
            NSLayoutConstraint.activate([
                guideHeading.leadingAnchor.constraint(equalTo: guideTitle.leadingAnchor),
                guideHeading.topAnchor.constraint(equalTo: guideTitle.bottomAnchor, constant: 8),
                field.leadingAnchor.constraint(equalTo: guideTitle.leadingAnchor),
                field.trailingAnchor.constraint(equalTo: guideCard.trailingAnchor, constant: -24),
                field.topAnchor.constraint(equalTo: guideHeading.bottomAnchor, constant: 8),
                field.heightAnchor.constraint(equalToConstant: 30),
                saveToken.leadingAnchor.constraint(equalTo: field.leadingAnchor),
                saveToken.topAnchor.constraint(equalTo: field.bottomAnchor, constant: 8),
                saveToken.widthAnchor.constraint(equalToConstant: 240),
                guideText.leadingAnchor.constraint(equalTo: guideTitle.leadingAnchor),
                guideText.trailingAnchor.constraint(equalTo: guideCard.trailingAnchor, constant: -20),
                guideText.topAnchor.constraint(equalTo: saveToken.bottomAnchor, constant: 8),
            ])
        } else {
            guideCard.addSubview(guideText)
        }

        content.addSubview(icon)
        content.addSubview(title)
        content.addSubview(subtitle)
        content.addSubview(statusPill)
        content.addSubview(connectCard)
        content.addSubview(permissionCard)
        content.addSubview(serverCard)
        content.addSubview(guideCard)

        NSLayoutConstraint.activate([
            icon.leadingAnchor.constraint(equalTo: content.leadingAnchor, constant: 34),
            icon.topAnchor.constraint(equalTo: content.topAnchor, constant: 34),
            icon.widthAnchor.constraint(equalToConstant: 86),
            icon.heightAnchor.constraint(equalToConstant: 86),

            title.leadingAnchor.constraint(equalTo: icon.trailingAnchor, constant: 20),
            title.topAnchor.constraint(equalTo: icon.topAnchor, constant: 11),
            title.trailingAnchor.constraint(lessThanOrEqualTo: statusPill.leadingAnchor, constant: -18),

            subtitle.leadingAnchor.constraint(equalTo: title.leadingAnchor),
            subtitle.topAnchor.constraint(equalTo: title.bottomAnchor, constant: 6),
            subtitle.trailingAnchor.constraint(equalTo: content.trailingAnchor, constant: -34),

            statusDot.widthAnchor.constraint(equalToConstant: 10),
            statusDot.heightAnchor.constraint(equalToConstant: 10),
            statusPill.trailingAnchor.constraint(equalTo: content.trailingAnchor, constant: -34),
            statusPill.topAnchor.constraint(equalTo: icon.topAnchor, constant: 10),
            statusPill.heightAnchor.constraint(equalToConstant: 36),
            statusStack.leadingAnchor.constraint(equalTo: statusPill.leadingAnchor, constant: 14),
            statusStack.trailingAnchor.constraint(equalTo: statusPill.trailingAnchor, constant: -14),
            statusStack.centerYAnchor.constraint(equalTo: statusPill.centerYAnchor),

            connectCard.topAnchor.constraint(equalTo: icon.bottomAnchor, constant: 28),
            connectCard.leadingAnchor.constraint(equalTo: content.leadingAnchor, constant: 34),
            connectCard.trailingAnchor.constraint(equalTo: content.trailingAnchor, constant: -34),
            connectCard.heightAnchor.constraint(equalToConstant: 230),

            connectEyebrow.leadingAnchor.constraint(equalTo: connectCard.leadingAnchor, constant: 24),
            connectEyebrow.topAnchor.constraint(equalTo: connectCard.topAnchor, constant: 22),
            connectTitle.leadingAnchor.constraint(equalTo: connectEyebrow.leadingAnchor),
            connectTitle.topAnchor.constraint(equalTo: connectEyebrow.bottomAnchor, constant: 8),
            connectTitle.trailingAnchor.constraint(equalTo: connectCard.trailingAnchor, constant: -24),
            connectHint.leadingAnchor.constraint(equalTo: connectEyebrow.leadingAnchor),
            connectHint.topAnchor.constraint(equalTo: connectTitle.bottomAnchor, constant: 10),
            connectHint.trailingAnchor.constraint(equalTo: connectTitle.trailingAnchor),
            phoneURLField.leadingAnchor.constraint(equalTo: connectEyebrow.leadingAnchor),
            phoneURLField.trailingAnchor.constraint(equalTo: connectTitle.trailingAnchor),
            phoneURLField.topAnchor.constraint(equalTo: connectHint.bottomAnchor, constant: 16),
            phoneURLField.heightAnchor.constraint(equalToConstant: 40),
            connectActions.leadingAnchor.constraint(equalTo: connectEyebrow.leadingAnchor),
            connectActions.trailingAnchor.constraint(equalTo: connectTitle.trailingAnchor),
            connectActions.topAnchor.constraint(equalTo: phoneURLField.bottomAnchor, constant: 14),

            permissionCard.topAnchor.constraint(equalTo: connectCard.bottomAnchor, constant: 16),
            permissionCard.leadingAnchor.constraint(equalTo: connectCard.leadingAnchor),
            permissionCard.trailingAnchor.constraint(equalTo: connectCard.trailingAnchor),
            permissionCard.heightAnchor.constraint(equalToConstant: 120),

            permissionTitle.leadingAnchor.constraint(equalTo: permissionCard.leadingAnchor, constant: 24),
            permissionTitle.topAnchor.constraint(equalTo: permissionCard.topAnchor, constant: 18),
            permissionHeading.leadingAnchor.constraint(equalTo: permissionTitle.leadingAnchor),
            permissionHeading.topAnchor.constraint(equalTo: permissionTitle.bottomAnchor, constant: 8),
            permissionLabel.leadingAnchor.constraint(equalTo: permissionTitle.leadingAnchor),
            permissionLabel.trailingAnchor.constraint(equalTo: permissionButton.leadingAnchor, constant: -18),
            permissionLabel.topAnchor.constraint(equalTo: permissionHeading.bottomAnchor, constant: 10),
            permissionButton.trailingAnchor.constraint(equalTo: permissionCard.trailingAnchor, constant: -24),
            permissionButton.centerYAnchor.constraint(equalTo: permissionCard.centerYAnchor, constant: 12),
            permissionButton.widthAnchor.constraint(equalToConstant: 180),

            serverCard.topAnchor.constraint(equalTo: permissionCard.bottomAnchor, constant: 14),
            serverCard.leadingAnchor.constraint(equalTo: connectCard.leadingAnchor),
            serverCard.trailingAnchor.constraint(equalTo: connectCard.trailingAnchor),
            serverCard.heightAnchor.constraint(equalToConstant: 120),

            serverTitle.leadingAnchor.constraint(equalTo: serverCard.leadingAnchor, constant: 24),
            serverTitle.topAnchor.constraint(equalTo: serverCard.topAnchor, constant: 18),
            serverHeading.leadingAnchor.constraint(equalTo: serverTitle.leadingAnchor),
            serverHeading.topAnchor.constraint(equalTo: serverTitle.bottomAnchor, constant: 8),
            serverHint.leadingAnchor.constraint(equalTo: serverTitle.leadingAnchor),
            serverHint.trailingAnchor.constraint(equalTo: serverActions.leadingAnchor, constant: -18),
            serverHint.topAnchor.constraint(equalTo: serverHeading.bottomAnchor, constant: 10),
            serverActions.trailingAnchor.constraint(equalTo: serverCard.trailingAnchor, constant: -24),
            serverActions.centerYAnchor.constraint(equalTo: serverCard.centerYAnchor, constant: 12),
            serverActions.widthAnchor.constraint(equalToConstant: 220),

            guideCard.topAnchor.constraint(equalTo: serverCard.bottomAnchor, constant: 16),
            guideCard.leadingAnchor.constraint(equalTo: connectCard.leadingAnchor),
            guideCard.trailingAnchor.constraint(equalTo: connectCard.trailingAnchor),
            guideCard.bottomAnchor.constraint(equalTo: content.bottomAnchor, constant: -28),

            guideTitle.leadingAnchor.constraint(equalTo: guideCard.leadingAnchor, constant: 24),
            guideTitle.topAnchor.constraint(equalTo: guideCard.topAnchor, constant: 18),
        ])

        if accountTokenField == nil {
            NSLayoutConstraint.activate([
                guideHeading.leadingAnchor.constraint(equalTo: guideTitle.leadingAnchor),
                guideHeading.topAnchor.constraint(equalTo: guideTitle.bottomAnchor, constant: 8),
                guideText.leadingAnchor.constraint(equalTo: guideTitle.leadingAnchor),
                guideText.trailingAnchor.constraint(equalTo: guideCard.trailingAnchor, constant: -20),
                guideText.topAnchor.constraint(equalTo: guideHeading.bottomAnchor, constant: 10),
            ])
        }
        refreshPermissionStatus(prompt: false)
        forceSquareWindow()
    }

    private func forceSquareWindow() {
        guard let window else { return }
        let screenFrame = NSScreen.main?.visibleFrame ?? window.screen?.visibleFrame ?? NSScreen.screens.first?.visibleFrame ?? .zero
        let origin = NSPoint(x: screenFrame.minX + 100, y: screenFrame.midY - squareWindowSize.height / 2)
        let topLeft = NSPoint(x: screenFrame.minX + 100, y: screenFrame.maxY - 100)
        window.minSize = squareWindowSize
        window.maxSize = squareWindowSize
        window.contentMinSize = squareWindowSize
        window.contentMaxSize = squareWindowSize
        window.setContentSize(squareWindowSize)
        window.contentView?.setFrameSize(squareWindowSize)
        window.setFrame(NSRect(origin: origin, size: squareWindowSize), display: true, animate: false)
        window.setFrameTopLeftPoint(topLeft)
        window.layoutIfNeeded()
    }

    private func panelView() -> NSView {
        let view = NSView()
        view.translatesAutoresizingMaskIntoConstraints = false
        view.wantsLayer = true
        view.layer?.backgroundColor = NSColor(red: 0.075, green: 0.075, blue: 0.075, alpha: 1).cgColor
        view.layer?.cornerRadius = 22
        view.layer?.borderColor = NSColor(white: 0.16, alpha: 1).cgColor
        view.layer?.borderWidth = 1
        return view
    }

    private func sectionTitle(_ text: String) -> NSTextField {
        let label = NSTextField(labelWithString: text.uppercased())
        label.font = NSFont.systemFont(ofSize: 11, weight: .bold)
        label.textColor = NSColor(white: 0.65, alpha: 1)
        label.translatesAutoresizingMaskIntoConstraints = false
        return label
    }

    private func helperText(_ text: String) -> NSTextField {
        let label = NSTextField(wrappingLabelWithString: text)
        label.font = NSFont.systemFont(ofSize: 12, weight: .regular)
        label.textColor = NSColor(white: 0.58, alpha: 1)
        label.translatesAutoresizingMaskIntoConstraints = false
        return label
    }

    private func buttonRow(_ buttons: [NSButton]) -> NSStackView {
        let row = NSStackView(views: buttons)
        row.orientation = .horizontal
        row.spacing = 12
        row.distribution = .fillEqually
        row.translatesAutoresizingMaskIntoConstraints = false
        for button in buttons {
            button.setContentCompressionResistancePriority(.required, for: .horizontal)
            button.heightAnchor.constraint(greaterThanOrEqualToConstant: 36).isActive = true
        }
        return row
    }

    private func gridView(_ buttons: [NSButton]) -> NSGridView {
        let firstRow = Array(buttons.prefix(3))
        let secondRow = Array(buttons.dropFirst(3))
        let grid = NSGridView(views: [firstRow, secondRow])
        grid.translatesAutoresizingMaskIntoConstraints = false
        grid.rowSpacing = 12
        grid.columnSpacing = 12
        for button in buttons {
            button.setContentCompressionResistancePriority(.required, for: .horizontal)
            button.heightAnchor.constraint(equalToConstant: 40).isActive = true
        }
        return grid
    }

    private func primaryButton(_ title: String, _ action: Selector) -> NSButton {
        let button = NSButton(title: title, target: self, action: action)
        button.translatesAutoresizingMaskIntoConstraints = false
        button.bezelStyle = .rounded
        button.controlSize = .large
        button.keyEquivalent = "\r"
        button.font = NSFont.systemFont(ofSize: 13, weight: .semibold)
        return button
    }

    private func secondaryButton(_ title: String, _ action: Selector) -> NSButton {
        let button = NSButton(title: title, target: self, action: action)
        button.translatesAutoresizingMaskIntoConstraints = false
        button.bezelStyle = .rounded
        button.controlSize = .large
        button.font = NSFont.systemFont(ofSize: 13, weight: .semibold)
        return button
    }

    private func dangerButton(_ title: String, _ action: Selector) -> NSButton {
        let button = secondaryButton(title, action)
        button.contentTintColor = NSColor.systemRed
        return button
    }

    private func startServerIfNeeded() {
        refreshPermissionStatus(prompt: false)
        if isPortInUse() {
            setStatus("Ready")
            appendLog("Blind Monkey is already running.\n")
            return
        }

        setStatus("Starting server...")
        appendLog("Starting server from \(repoDir)\n")

        let proc = Process()
        proc.executableURL = URL(fileURLWithPath: "/bin/bash")
        proc.currentDirectoryURL = URL(fileURLWithPath: repoDir)
        proc.arguments = ["-lc", "./run.sh"]
        proc.environment = processEnvironment()

        let pipe = Pipe()
        proc.standardOutput = pipe
        proc.standardError = pipe
        pipe.fileHandleForReading.readabilityHandler = { [weak self] handle in
            let data = handle.availableData
            guard !data.isEmpty, let text = String(data: data, encoding: .utf8) else { return }
            DispatchQueue.main.async {
                self?.appendLog(text)
                if text.contains("Uvicorn running") {
                    self?.setStatus("Ready")
                }
                if text.contains("Accessibility: NOT GRANTED") {
                    self?.setStatus("Needs Accessibility permission")
                    self?.refreshPermissionStatus(prompt: false)
                }
            }
        }

        proc.terminationHandler = { [weak self] _ in
            DispatchQueue.main.async {
                self?.setStatus("Stopped")
                self?.appendLog("\nServer stopped.\n")
            }
        }

        do {
            try proc.run()
            process = proc
        } catch {
            setStatus("Error")
            appendLog("Failed to start server: \(error.localizedDescription)\n")
        }
    }

    private func processEnvironment() -> [String: String] {
        var env = ProcessInfo.processInfo.environment
        for (key, value) in userEnvFileValues() {
            env[key] = value
        }
        if env["BLIND_SUPABASE_ACCESS_TOKEN"] == nil, let t = BMKeychain.get(account: "supabase_access")?.trimmingCharacters(in: .whitespacesAndNewlines), !t.isEmpty {
            env["BLIND_SUPABASE_ACCESS_TOKEN"] = t
        }
        if env["BLIND_PROMPT_ACCESSIBILITY"] == nil {
            env["BLIND_PROMPT_ACCESSIBILITY"] = "1"
        }
        env["PATH"] = "/usr/local/bin:/opt/homebrew/bin:" + (env["PATH"] ?? "")
        return env
    }

    private func appSetting(_ key: String) -> String? {
        if let value = ProcessInfo.processInfo.environment[key]?.trimmingCharacters(in: .whitespacesAndNewlines), !value.isEmpty {
            return value
        }
        if let value = userEnvFileValues()[key]?.trimmingCharacters(in: .whitespacesAndNewlines), !value.isEmpty {
            return value
        }
        return nil
    }

    private func userEnvFileValues() -> [String: String] {
        let envURL = FileManager.default.homeDirectoryForCurrentUser.appendingPathComponent(".hand-control.env")
        guard let raw = try? String(contentsOf: envURL, encoding: .utf8) else {
            return [:]
        }

        var values: [String: String] = [:]
        for line in raw.split(separator: "\n", omittingEmptySubsequences: false) {
            let trimmed = line.trimmingCharacters(in: .whitespacesAndNewlines)
            if trimmed.isEmpty || trimmed.hasPrefix("#") {
                continue
            }
            let cleaned = trimmed.hasPrefix("export ") ? String(trimmed.dropFirst(7)) : trimmed
            guard let equals = cleaned.firstIndex(of: "=") else {
                continue
            }
            let key = String(cleaned[..<equals]).trimmingCharacters(in: .whitespacesAndNewlines)
            var value = String(cleaned[cleaned.index(after: equals)...]).trimmingCharacters(in: .whitespacesAndNewlines)
            if value.count >= 2, let first = value.first, let last = value.last, (first == "\"" && last == "\"") || (first == "'" && last == "'") {
                value = String(value.dropFirst().dropLast())
            }
            if !key.isEmpty {
                values[key] = value
            }
        }
        return values
    }

    private func isPortInUse() -> Bool {
        let proc = Process()
        proc.executableURL = URL(fileURLWithPath: "/usr/sbin/lsof")
        proc.arguments = ["-ti", "tcp:\(port)"]
        proc.standardOutput = Pipe()
        proc.standardError = Pipe()
        do {
            try proc.run()
            proc.waitUntilExit()
            return proc.terminationStatus == 0
        } catch {
            return false
        }
    }

    private func setStatus(_ text: String) {
        let displayText = text
        statusLabel.stringValue = displayText
        phoneURLField?.stringValue = phoneURL()
        let color: NSColor
        if displayText.lowercased().contains("running") || displayText.lowercased().contains("ready") {
            color = .systemGreen
        } else if displayText.lowercased().contains("error") {
            color = .systemRed
        } else if displayText.lowercased().contains("stopped") {
            color = .systemGray
        } else {
            color = .systemOrange
        }
        statusDot?.layer?.backgroundColor = color.cgColor
    }

    private func refreshPermissionStatus(prompt: Bool) {
        // Trust /health: the real work runs in a separate Python process, not
        // this launcher. A trusted companion app is not enough.
        if let health = serverHealth() {
            if health.trusted {
                permissionLabel.stringValue = health.windowsCount > 0
                    ? "Enabled. Found \(health.windowsCount) Cursor window\(health.windowsCount == 1 ? "" : "s")."
                    : "Enabled. Open Cursor to start using your phone."
                permissionLabel.textColor = NSColor.systemGreen
                setStatus("Ready")
                return
            }

            if let py = health.pythonExecutable, !py.isEmpty {
                permissionLabel.stringValue =
                    "The running Python server is not in Accessibility. Enable it (same path the server uses), not only this app — then click Restart. Path: " + py
            } else if let hint = health.accessibilityHint, !hint.isEmpty {
                permissionLabel.stringValue = hint
            } else {
                permissionLabel.stringValue =
                    "The Python server (see \"Python:\" line in the log) must be in Accessibility, then click Restart — not just this app."
            }
            permissionLabel.textColor = NSColor.systemOrange
            setStatus("Needs access")
            if let py = health.pythonExecutable, !py.isEmpty {
                permissionLabel.toolTip = py
            }
            return
        }

        // Server not up yet: fall back to the companion process itself.
        let trusted: Bool
        if prompt {
            let options = [kAXTrustedCheckOptionPrompt.takeUnretainedValue() as String: true] as CFDictionary
            trusted = AXIsProcessTrustedWithOptions(options)
        } else {
            trusted = AXIsProcessTrusted()
        }

        if trusted {
            permissionLabel.stringValue = "Enabled. Your phone can switch Cursor windows and use the trackpad."
            permissionLabel.textColor = NSColor.systemGreen
        } else {
            permissionLabel.stringValue = "Required. Enable Blind Monkey and the Python the server uses (see log \"Python:\") in Accessibility — not just one of them."
            permissionLabel.textColor = NSColor.systemOrange
            setStatus("Needs access")
        }
    }

    private func serverHealth() -> ServerHealth? {
        guard isPortInUse() else { return nil }

        let proc = Process()
        proc.executableURL = URL(fileURLWithPath: "/usr/bin/curl")
        proc.arguments = ["-sk", "--max-time", "2", "https://127.0.0.1:\(port)/health"]
        let pipe = Pipe()
        proc.standardOutput = pipe
        proc.standardError = Pipe()

        do {
            try proc.run()
            proc.waitUntilExit()
            guard proc.terminationStatus == 0 else { return nil }
            let data = pipe.fileHandleForReading.readDataToEndOfFile()
            guard
                let object = try JSONSerialization.jsonObject(with: data) as? [String: Any],
                let accessibility = object["accessibility"] as? [String: Any],
                let trusted = accessibility["trusted"] as? Bool
            else {
                return nil
            }
            let windowsCount = object["windows_count"] as? Int ?? 0
            let process = object["process"] as? [String: Any]
            let python = process?["python"] as? String
            let accHint = object["accessibility_hint"] as? String
            return ServerHealth(
                trusted: trusted,
                windowsCount: windowsCount,
                pythonExecutable: python,
                accessibilityHint: accHint
            )
        } catch {
            return nil
        }
    }

    private func appendLog(_ text: String) {
        if let data = text.data(using: .utf8) {
            if FileManager.default.fileExists(atPath: logFileURL.path) {
                if let handle = try? FileHandle(forWritingTo: logFileURL) {
                    _ = try? handle.seekToEnd()
                    try? handle.write(contentsOf: data)
                    try? handle.close()
                }
            } else {
                try? data.write(to: logFileURL)
            }
        }
        logView?.textStorage?.append(NSAttributedString(string: text))
        logView?.scrollToEndOfDocument(nil)
    }

    private func stopOwnedServer() {
        guard let proc = process, proc.isRunning else { return }
        proc.terminate()
        process = nil
    }

    @objc private func openPhoneURL() {
        if let url = URL(string: phoneURL()) {
            NSWorkspace.shared.open(url)
        }
    }

    @objc private func copyPhoneURL() {
        NSPasteboard.general.clearContents()
        NSPasteboard.general.setString(phoneURL(), forType: .string)
        appendLog("Copied phone URL: \(phoneURL())\n")
    }

    @objc private func showQR() {
        let outputURL = FileManager.default.temporaryDirectory.appendingPathComponent("blind-monkey-phone-qr.png")
        var env = processEnvironment()
        env["BM_PHONE_URL"] = phoneURL()
        env["BM_QR_PATH"] = outputURL.path

        let proc = Process()
        proc.executableURL = URL(fileURLWithPath: "/bin/bash")
        proc.currentDirectoryURL = URL(fileURLWithPath: repoDir)
        proc.arguments = [
            "-lc",
            """
            . .venv/bin/activate 2>/dev/null || true
            python3 - <<'PY'
            import os
            import struct
            import zlib
            import qrcode

            def chunk(kind, data):
                return (
                    struct.pack(">I", len(data))
                    + kind
                    + data
                    + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
                )

            def write_png(path, matrix, scale=10):
                width = len(matrix[0]) * scale
                height = len(matrix) * scale
                rows = []
                for source_row in matrix:
                    expanded = bytearray()
                    for dark in source_row:
                        color = b"\\x00\\x00\\x00" if dark else b"\\xff\\xff\\xff"
                        expanded.extend(color * scale)
                    row = b"\\x00" + bytes(expanded)
                    rows.extend([row] * scale)

                png = (
                    b"\\x89PNG\\r\\n\\x1a\\n"
                    + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
                    + chunk(b"IDAT", zlib.compress(b"".join(rows), 9))
                    + chunk(b"IEND", b"")
                )
                with open(path, "wb") as file:
                    file.write(png)

            qr = qrcode.QRCode(border=3, box_size=12)
            qr.add_data(os.environ["BM_PHONE_URL"])
            qr.make(fit=True)
            write_png(os.environ["BM_QR_PATH"], qr.get_matrix(), scale=10)
            PY
            """,
        ]
        proc.environment = env

        do {
            try proc.run()
            proc.waitUntilExit()
        } catch {
            appendLog("Failed to create QR code: \(error.localizedDescription)\n")
        }

        guard proc.terminationStatus == 0, let image = NSImage(contentsOf: outputURL) else {
            copyPhoneURL()
            showMessage("Phone link copied", "I could not draw the QR code, so I copied the phone link instead.")
            return
        }

        let imageView = NSImageView(frame: NSRect(x: 0, y: 0, width: 280, height: 280))
        imageView.image = image
        imageView.imageScaling = .scaleProportionallyUpOrDown
        imageView.wantsLayer = true
        imageView.layer?.backgroundColor = NSColor.white.cgColor
        imageView.layer?.cornerRadius = 16

        let alert = NSAlert()
        alert.messageText = "Scan with your iPhone"
        alert.informativeText = phoneURL()
        alert.accessoryView = imageView
        alert.addButton(withTitle: "Done")
        alert.addButton(withTitle: "Copy Link")

        if alert.runModal() == .alertSecondButtonReturn {
            copyPhoneURL()
        }
    }

    @objc private func restartServer() {
        stopOwnedServer()
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.6) {
            self.startServerIfNeeded()
        }
    }

    @objc private func stopServer() {
        stopOwnedServer()
        setStatus("Stopped")
    }

    @objc private func openLogs() {
        NSWorkspace.shared.activateFileViewerSelecting([logFileURL])
    }

    private func showMessage(_ title: String, _ message: String) {
        let alert = NSAlert()
        alert.messageText = title
        alert.informativeText = message
        alert.addButton(withTitle: "OK")
        alert.runModal()
    }

    @objc private func openAccessibilitySettings() {
        refreshPermissionStatus(prompt: true)
        if let url = URL(string: "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility") {
            NSWorkspace.shared.open(url)
        }
        appendLog("Opened Accessibility settings. Enable Blind Monkey. If Python appears there, enable it too. Then click Restart.\n")
    }

    @objc private func saveAccountToken() {
        let raw = accountTokenField?.stringValue ?? ""
        let trimmed = raw.trimmingCharacters(in: .whitespacesAndNewlines)
        if trimmed.isEmpty {
            showMessage("Token required", "Paste a Supabase access token, or remove it from Keychain in Keychain Access.")
            return
        }
        BMKeychain.set(trimmed, account: "supabase_access")
        appendLog("Saved Supabase access token to Keychain. Restarting server…\n")
        restartServer()
    }

    private func localHostName() -> String? {
        let proc = Process()
        proc.executableURL = URL(fileURLWithPath: "/usr/sbin/scutil")
        proc.arguments = ["--get", "LocalHostName"]
        let pipe = Pipe()
        proc.standardOutput = pipe
        proc.standardError = Pipe()
        do {
            try proc.run()
            proc.waitUntilExit()
            guard proc.terminationStatus == 0 else { return nil }
            let data = pipe.fileHandleForReading.readDataToEndOfFile()
            let name = String(data: data, encoding: .utf8)?.trimmingCharacters(in: .whitespacesAndNewlines)
            guard let name, !name.isEmpty else { return nil }
            return "\(name).local"
        } catch {
            return nil
        }
    }

    private func phoneURL() -> String {
        let localBase = "https://\(localHostName() ?? "localhost"):\(port)"
        if usesAccountPairing() {
            return appSetting("BLIND_PHONE_APP_URL") ?? localBase
        }

        guard
            let relay = appSetting("BLIND_RELAY_URL"),
            let device = appSetting("BLIND_DEVICE_ID"),
            let token = appSetting("BLIND_RELAY_TOKEN")
        else {
            return localBase
        }

        let base = appSetting("BLIND_PHONE_APP_URL") ?? localBase
        guard var components = URLComponents(string: base) else {
            return localBase
        }
        var queryItems = components.queryItems ?? []
        queryItems.removeAll { item in
            item.name == "relay" || item.name == "device" || item.name == "token"
        }
        queryItems.append(URLQueryItem(name: "relay", value: relay))
        queryItems.append(URLQueryItem(name: "device", value: device))
        queryItems.append(URLQueryItem(name: "token", value: token))
        components.queryItems = queryItems
        return components.string ?? localBase
    }

    private func usesAccountPairing() -> Bool {
        return appSetting("SUPABASE_URL") != nil
            && appSetting("SUPABASE_ANON_KEY") != nil
            && appSetting("BLIND_RELAY_URL") != nil
    }

    private func tailscaleHostName() -> String? {
        let proc = Process()
        proc.executableURL = URL(fileURLWithPath: "/usr/bin/env")
        proc.arguments = ["tailscale", "status", "--json"]
        proc.environment = processEnvironment()
        let pipe = Pipe()
        proc.standardOutput = pipe
        proc.standardError = Pipe()

        do {
            try proc.run()
            proc.waitUntilExit()
            guard proc.terminationStatus == 0 else { return nil }
            let data = pipe.fileHandleForReading.readDataToEndOfFile()
            guard
                let object = try JSONSerialization.jsonObject(with: data) as? [String: Any],
                let selfInfo = object["Self"] as? [String: Any],
                let dnsName = selfInfo["DNSName"] as? String
            else {
                return nil
            }
            let host = dnsName.trimmingCharacters(in: .whitespacesAndNewlines).trimmingCharacters(in: CharacterSet(charactersIn: "."))
            return host.isEmpty ? nil : host
        } catch {
            return nil
        }
    }
}

let app = NSApplication.shared
let delegate = AppDelegate()
app.delegate = delegate
app.setActivationPolicy(.regular)
app.run()
