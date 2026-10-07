// Renders the Convert glyph: a page with two opposing arrows.
//   swift make-icons.swift OUT_DIR
// Writes MenuIconTemplate.png / MenuIconTemplate@2x.png (menu glyph) and AppIcon.iconset/.

import AppKit

let outDir = URL(fileURLWithPath: CommandLine.arguments.count > 1 ? CommandLine.arguments[1] : ".")

/// Strokes the glyph in a 32x32 design space (y down), scaled to fill `rect`.
func drawGlyph(in rect: CGRect, color: NSColor, lineWidth: CGFloat = 2.4) {
    let s = rect.width / 32
    func p(_ x: CGFloat, _ y: CGFloat) -> CGPoint { CGPoint(x: rect.minX + x * s, y: rect.minY + y * s) }

    let page = NSBezierPath()
    page.move(to: p(9, 3))
    page.line(to: p(19, 3))
    page.line(to: p(26, 10))
    page.appendArc(from: p(26, 29), to: p(6, 29), radius: 2.5 * s)
    page.appendArc(from: p(6, 29), to: p(6, 3), radius: 2.5 * s)
    page.appendArc(from: p(6, 3), to: p(19, 3), radius: 2.5 * s)
    page.close()
    page.move(to: p(19, 3))
    page.line(to: p(19, 8))
    page.appendArc(from: p(19, 10), to: p(26, 10), radius: 2 * s)
    page.line(to: p(26, 10))

    let arrows = NSBezierPath()
    arrows.move(to: p(10.5, 16))
    arrows.line(to: p(21.5, 16))
    arrows.move(to: p(18, 12.5))
    arrows.line(to: p(21.5, 16))
    arrows.line(to: p(18, 19.5))
    arrows.move(to: p(21.5, 23.5))
    arrows.line(to: p(10.5, 23.5))
    arrows.move(to: p(14, 20))
    arrows.line(to: p(10.5, 23.5))
    arrows.line(to: p(14, 27))

    color.setStroke()
    for path in [page, arrows] {
        path.lineWidth = lineWidth * s
        path.lineCapStyle = .round
        path.lineJoinStyle = .round
        path.stroke()
    }
}

func render(pixels: Int, to url: URL, draw: (CGRect) -> Void) {
    let rep = NSBitmapImageRep(
        bitmapDataPlanes: nil, pixelsWide: pixels, pixelsHigh: pixels, bitsPerSample: 8,
        samplesPerPixel: 4, hasAlpha: true, isPlanar: false, colorSpaceName: .deviceRGB,
        bytesPerRow: 0, bitsPerPixel: 0)!
    NSGraphicsContext.saveGraphicsState()
    let ctx = NSGraphicsContext(bitmapImageRep: rep)!
    NSGraphicsContext.current = ctx
    // Flip so the design space is y-down.
    ctx.cgContext.translateBy(x: 0, y: CGFloat(pixels))
    ctx.cgContext.scaleBy(x: 1, y: -1)
    draw(CGRect(x: 0, y: 0, width: pixels, height: pixels))
    NSGraphicsContext.restoreGraphicsState()
    try! rep.representation(using: .png, properties: [:])!.write(to: url)
}

func drawAppIcon(in rect: CGRect) {
    let w = rect.width
    let tile = rect.insetBy(dx: w * 0.1, dy: w * 0.1)
    let shape = NSBezierPath(roundedRect: tile, xRadius: tile.width * 0.225, yRadius: tile.width * 0.225)

    NSGraphicsContext.saveGraphicsState()
    let shadow = NSShadow()
    shadow.shadowColor = NSColor.black.withAlphaComponent(0.3)
    shadow.shadowBlurRadius = w * 0.02
    shadow.shadowOffset = NSSize(width: 0, height: w * 0.01)
    shadow.set()
    NSColor.black.setFill()
    shape.fill()
    NSGraphicsContext.restoreGraphicsState()

    let gradient = NSGradient(colors: [
        NSColor(srgbRed: 0.27, green: 0.55, blue: 1.0, alpha: 1),
        NSColor(srgbRed: 0.49, green: 0.30, blue: 0.98, alpha: 1),
    ])!
    gradient.draw(in: shape, angle: -90)

    let glyph = tile.insetBy(dx: tile.width * 0.16, dy: tile.width * 0.16)
    drawGlyph(in: glyph, color: .white, lineWidth: 2.2)
}

try! FileManager.default.createDirectory(at: outDir, withIntermediateDirectories: true)
render(pixels: 16, to: outDir.appendingPathComponent("MenuIconTemplate.png")) { drawGlyph(in: $0, color: .black) }
render(pixels: 32, to: outDir.appendingPathComponent("MenuIconTemplate@2x.png")) { drawGlyph(in: $0, color: .black) }

let iconset = outDir.appendingPathComponent("AppIcon.iconset")
try! FileManager.default.createDirectory(at: iconset, withIntermediateDirectories: true)
for size in [16, 32, 128, 256, 512] {
    render(pixels: size, to: iconset.appendingPathComponent("icon_\(size)x\(size).png"), draw: drawAppIcon)
    render(pixels: size * 2, to: iconset.appendingPathComponent("icon_\(size)x\(size)@2x.png"), draw: drawAppIcon)
}
