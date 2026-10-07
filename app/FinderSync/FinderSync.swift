import Cocoa
import FinderSync

/// One row of the table written by `rightconvert --matrix`.
private struct Entry {
    let normalized: String
    let category: String
    let targets: [String]
}

// homeDirectoryForCurrentUser is the sandbox container here, so resolve the real home.
private let supportDir = URL(fileURLWithPath: String(cString: getpwuid(getuid())!.pointee.pw_dir))
    .appendingPathComponent("Library/Application Support/rightconvert")

private struct Matrix {
    static let url = supportDir.appendingPathComponent("matrix.txt")

    let entries: [String: Entry]

    static func load() -> Matrix? {
        guard let text = try? String(contentsOf: url, encoding: .utf8) else { return nil }
        var entries: [String: Entry] = [:]
        for line in text.split(separator: "\n") {
            let fields = line.split(separator: " ").map(String.init)
            guard fields.count >= 3 else { continue }
            entries[fields[0]] = Entry(normalized: fields[1], category: fields[2], targets: Array(fields[3...]))
        }
        return Matrix(entries: entries)
    }

    /// Formats every supported file in the selection can be converted to, mirroring rightconvert's rules:
    /// unsupported files are ignored, and a format all files already have is dropped.
    func targets(for urls: [URL]) -> (category: String, formats: [String]) {
        let selected = urls.compactMap { entries[$0.pathExtension.lowercased()] }
        guard let first = selected.first else { return ("", []) }
        var common = first.targets + [first.normalized]
        for entry in selected.dropFirst() {
            let allowed = Set(entry.targets + [entry.normalized])
            common = common.filter(allowed.contains)
        }
        let owns = Set(selected.map(\.normalized))
        if owns.count == 1 { common.removeAll { owns.contains($0) } }
        let categories = Set(selected.map(\.category))
        return (categories.count == 1 ? first.category : "mixed", common)
    }
}

@objc(ConvertFinderSync)
final class ConvertFinderSync: FIFinderSync {
    private static let glyph = Bundle(for: ConvertFinderSync.self).image(forResource: "MenuIconTemplate")

    /// Finder draws extension menu images as-is and ignores isTemplate, so tint for the current appearance.
    private static func icon() -> NSImage? {
        guard let glyph else { return nil }
        let dark = UserDefaults.standard.string(forKey: "AppleInterfaceStyle") == "Dark"
        let color: NSColor = dark ? .white : .black
        let size = glyph.size
        guard let rep = NSBitmapImageRep(
            bitmapDataPlanes: nil, pixelsWide: Int(size.width * 2), pixelsHigh: Int(size.height * 2),
            bitsPerSample: 8, samplesPerPixel: 4, hasAlpha: true, isPlanar: false,
            colorSpaceName: .deviceRGB, bytesPerRow: 0, bitsPerPixel: 0)
        else { return nil }
        rep.size = size
        NSGraphicsContext.saveGraphicsState()
        NSGraphicsContext.current = NSGraphicsContext(bitmapImageRep: rep)
        let rect = NSRect(origin: .zero, size: size)
        glyph.draw(in: rect)
        color.set()
        rect.fill(using: .sourceAtop)
        NSGraphicsContext.restoreGraphicsState()
        let image = NSImage(size: size)
        image.addRepresentation(rep)
        return image
    }

    override init() {
        super.init()
        FIFinderSyncController.default().directoryURLs = [URL(fileURLWithPath: "/")]
    }

    override func menu(for menuKind: FIMenuKind) -> NSMenu? {
        guard menuKind == .contextualMenuForItems,
              let urls = FIFinderSyncController.default().selectedItemURLs(), !urls.isEmpty
        else { return nil }

        let menu = NSMenu(title: "")
        let item = NSMenuItem(title: "Convert", action: nil, keyEquivalent: "")
        item.image = Self.icon()

        // Folder contents aren't readable from the sandbox, so folders go through the format picker.
        if urls.contains(where: \.hasDirectoryPath) {
            item.title = "Convert..."
            item.action = #selector(pickFormat(_:))
            item.target = self
        } else if let matrix = Matrix.load() {
            let (category, formats) = matrix.targets(for: urls)
            guard !formats.isEmpty else { return nil }
            let submenu = NSMenu(title: "Convert")
            for format in formats {
                let formatItem = NSMenuItem(
                    title: label(category: category, format: format),
                    action: #selector(convert(_:)), keyEquivalent: "")
                formatItem.target = self
                submenu.addItem(formatItem)
            }
            item.submenu = submenu
        } else {
            item.title = "Convert..."
            item.action = #selector(pickFormat(_:))
            item.target = self
        }

        menu.addItem(item)
        return menu
    }

    @objc private func convert(_ sender: NSMenuItem) {
        // Finder hands back a copy of the item without representedObject, so decode the title.
        guard var format = sender.title.split(separator: " ").first?.lowercased() else { return }
        if sender.title.hasSuffix(Self.smallerSuffix) { format += "-small" }
        open(format: format)
    }

    @objc private func pickFormat(_ sender: NSMenuItem) {
        open(format: nil)
    }

    private func open(format: String?) {
        guard let urls = FIFinderSyncController.default().selectedItemURLs(), !urls.isEmpty,
              let token = try? String(contentsOf: supportDir.appendingPathComponent("token"), encoding: .utf8)
        else { return }
        var components = URLComponents()
        components.scheme = "rightconvert"
        components.host = "convert"
        var query = [URLQueryItem(name: "token", value: token.trimmingCharacters(in: .whitespacesAndNewlines))]
        if let format { query.append(URLQueryItem(name: "to", value: format)) }
        query += urls.map { URLQueryItem(name: "f", value: $0.path) }
        components.queryItems = query
        if let url = components.url { NSWorkspace.shared.open(url) }
    }

    private static let smallerSuffix = " (smaller file)"

    /// Mirrors label_for in bin/rightconvert.
    private func label(category: String, format: String) -> String {
        if format.hasSuffix("-small") {
            return format.dropLast("-small".count).uppercased() + Self.smallerSuffix
        }
        let name = format.uppercased()
        switch (category, format) {
        case ("video", "mp3"), ("video", "m4a"), ("video", "wav"): return "\(name) (audio only)"
        case ("video", "gif"): return "\(name) (animated)"
        case ("pdf", "png"), ("pdf", "jpg"): return "\(name) (one image per page)"
        default: return name
        }
    }
}
