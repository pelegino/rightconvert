import AppKit

/// Background helper: receives rightconvert://convert?token=T&to=FORMAT&f=PATH&f=PATH from the Finder
/// extension and runs the bundled rightconvert script, which the sandboxed extension can't do itself.
final class AppDelegate: NSObject, NSApplicationDelegate {
    private let script = Bundle.main.url(forResource: "rightconvert", withExtension: nil)!
    private let supportDir = FileManager.default.homeDirectoryForCurrentUser
        .appendingPathComponent("Library/Application Support/rightconvert")
    private var receivedURL = false
    private var running = 0

    /// Any app or web page can open a rightconvert:// URL, so only requests carrying this secret,
    /// which only the Finder extension can read, are acted on.
    private lazy var token: String = {
        let url = supportDir.appendingPathComponent("token")
        if let existing = try? String(contentsOf: url, encoding: .utf8).trimmingCharacters(in: .whitespacesAndNewlines),
           !existing.isEmpty {
            return existing
        }
        var bytes = [UInt8](repeating: 0, count: 32)
        _ = SecRandomCopyBytes(kSecRandomDefault, bytes.count, &bytes)
        let fresh = bytes.map { String(format: "%02x", $0) }.joined()
        try? FileManager.default.createDirectory(at: supportDir, withIntermediateDirectories: true)
        FileManager.default.createFile(
            atPath: url.path, contents: Data(fresh.utf8), attributes: [.posixPermissions: 0o600])
        return fresh
    }()

    func applicationDidFinishLaunching(_ notification: Notification) {
        _ = token
        refreshMatrix()
        DispatchQueue.main.asyncAfter(deadline: .now() + 1) { [self] in
            if !receivedURL { showWelcome() }
        }
    }

    func application(_ application: NSApplication, open urls: [URL]) {
        receivedURL = true
        for url in urls where url.scheme == "rightconvert" { handle(url) }
        quitWhenIdle()
    }

    private func handle(_ url: URL) {
        let items = URLComponents(url: url, resolvingAgainstBaseURL: false)?.queryItems ?? []
        guard items.first(where: { $0.name == "token" })?.value == token else {
            NSLog("RightConvert: ignoring request without a valid token")
            return
        }
        let files = items.filter { $0.name == "f" }.compactMap(\.value)
        guard !files.isEmpty else { return }
        var args = ["--gui"]
        if let format = items.first(where: { $0.name == "to" })?.value { args += ["--to", format] }
        run(args + ["--"] + files) {}
    }

    /// Rewrites the table the Finder extension reads, so newly installed engines show up in the menu.
    private func refreshMatrix() {
        let dir = supportDir
        try? FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        let output = Pipe()
        run(["--matrix"], stdout: output) {
            let data = output.fileHandleForReading.readDataToEndOfFile()
            if !data.isEmpty { try? data.write(to: dir.appendingPathComponent("matrix.txt"), options: .atomic) }
        }
    }

    private func run(_ args: [String], stdout: Pipe? = nil, completion: @escaping () -> Void) {
        let process = Process()
        process.executableURL = URL(fileURLWithPath: "/bin/zsh")
        process.arguments = [script.path] + args
        if let stdout { process.standardOutput = stdout } else { process.standardOutput = FileHandle.nullDevice }
        running += 1
        let finish = { [self] in
            running -= 1
            completion()
            quitWhenIdle()
        }
        process.terminationHandler = { _ in DispatchQueue.main.async(execute: finish) }
        do { try process.run() } catch { finish() }
    }

    private func quitWhenIdle() {
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.5) { [self] in
            if running == 0 && receivedURL { NSApp.terminate(nil) }
        }
    }

    private func showWelcome() {
        NSApp.activate(ignoringOtherApps: true)
        let alert = NSAlert()
        alert.messageText = "RightConvert is installed"
        alert.informativeText = """
            Right-click any file in Finder and hover Convert to pick a format.

            If Convert doesn't appear in the menu, open System Settings > General > \
            Login Items & Extensions, click the info button next to Finder, and turn on RightConvert.
            """
        alert.addButton(withTitle: "OK")
        alert.addButton(withTitle: "Open System Settings")
        if alert.runModal() == .alertSecondButtonReturn {
            NSWorkspace.shared.open(URL(string: "x-apple.systempreferences:com.apple.ExtensionsPreferences")!)
        }
        NSApp.terminate(nil)
    }
}

let app = NSApplication.shared
let delegate = AppDelegate()
app.delegate = delegate
app.setActivationPolicy(.accessory)
app.run()
