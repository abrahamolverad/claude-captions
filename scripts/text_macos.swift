// CoreText renderer used by overlay.py on macOS: shapes any script correctly (Devanagari, Arabic, CJK), colour emoji and SF Symbols.
// usage: swift text_macos.swift SPEC.json
// SPEC = [{"kind": "text", "text": "…", "font": "HiraginoSans-W6", "size": 40, "maxw": 940, "out": "x.png", "shadow": true},
//         {"kind": "symbol", "text": "person.3.fill", "size": 120, "out": "icon.png"}]
// Each PNG is transparent, white text with a soft black shadow (emoji keep their colours). Prints "out width height" per item.
import AppKit
import CoreText
import Foundation
import ImageIO
import UniformTypeIdentifiers

struct Spec: Decodable {
    let kind: String?; let text: String; let font: String?; let size: CGFloat; let out: String
    let maxw: CGFloat?; let shadow: Bool?; let align: String?
}

func write(_ ctx: CGContext, _ out: String) {
    let dest = CGImageDestinationCreateWithURL(URL(fileURLWithPath: out) as CFURL, UTType.png.identifier as CFString, 1, nil)!
    CGImageDestinationAddImage(dest, ctx.makeImage()!, nil)
    CGImageDestinationFinalize(dest)
}

func context(_ w: Int, _ h: Int) -> CGContext {
    return CGContext(data: nil, width: w, height: h, bitsPerComponent: 8, bytesPerRow: 0, space: CGColorSpaceCreateDeviceRGB(),
                     bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue)!
}

let specs = try! JSONDecoder().decode([Spec].self, from: Data(contentsOf: URL(fileURLWithPath: CommandLine.arguments[1])))
for s in specs {
    let pad: CGFloat = 40
    if s.kind == "symbol" {
        let cfg = NSImage.SymbolConfiguration(pointSize: s.size, weight: .bold)
        guard let img = NSImage(systemSymbolName: s.text, accessibilityDescription: nil)?.withSymbolConfiguration(cfg) else {
            print("missing-symbol", s.text); continue
        }
        let W = Int(img.size.width + pad * 2), H = Int(img.size.height + pad * 2)
        let ctx = context(W, H)
        NSGraphicsContext.saveGraphicsState(); NSGraphicsContext.current = NSGraphicsContext(cgContext: ctx, flipped: false)
        if s.shadow ?? true {
            let sh = NSShadow(); sh.shadowColor = NSColor.black.withAlphaComponent(0.7); sh.shadowBlurRadius = 14
            sh.shadowOffset = NSSize(width: 0, height: -4); sh.set()
        }
        let white = NSImage(size: img.size, flipped: false) { r in img.draw(in: r); NSColor.white.set(); r.fill(using: .sourceAtop); return true }
        white.draw(in: NSRect(x: pad, y: pad, width: img.size.width, height: img.size.height))
        NSGraphicsContext.restoreGraphicsState()
        write(ctx, s.out); print(s.out, W, H)
        continue
    }
    let f = NSFont(name: s.font ?? "HelveticaNeue-Bold", size: s.size) ?? NSFont.boldSystemFont(ofSize: s.size)
    let para = NSMutableParagraphStyle(); para.alignment = (s.align == "left") ? .left : .center; para.lineSpacing = s.size * 0.18
    let str = NSAttributedString(string: s.text, attributes: [.font: f, .foregroundColor: NSColor.white, .paragraphStyle: para])
    let maxw = s.maxw ?? 1000
    let bounds = str.boundingRect(with: NSSize(width: maxw, height: 4000), options: [.usesLineFragmentOrigin, .usesFontLeading])
    let W = Int(ceil(maxw) + pad * 2), H = Int(ceil(bounds.height) + pad * 2)
    let ctx = context(W, H)
    NSGraphicsContext.saveGraphicsState(); NSGraphicsContext.current = NSGraphicsContext(cgContext: ctx, flipped: false)
    if s.shadow ?? true {
        let sh = NSShadow(); sh.shadowColor = NSColor.black.withAlphaComponent(0.75); sh.shadowBlurRadius = 14
        sh.shadowOffset = NSSize(width: 0, height: -4); sh.set()
    }
    str.draw(with: NSRect(x: pad, y: pad, width: maxw, height: bounds.height), options: [.usesLineFragmentOrigin, .usesFontLeading])
    NSGraphicsContext.restoreGraphicsState()
    write(ctx, s.out); print(s.out, W, H)
}
