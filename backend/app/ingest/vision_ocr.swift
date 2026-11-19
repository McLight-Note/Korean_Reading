// macOS-only: OCR scanned PDF pages locally with Apple Vision (ko-KR + en-US). No network.
// usage: swift vision_ocr.swift in.pdf out_dir [first_page last_page]   (1-based, inclusive)
// writes out_dir/page_NNN.jpg and out_dir/page_NNN.json  ({"pdf_page":N,"lines":[{"text","x","y","w","h","conf"}]})
// Resumable: pages whose JSON already exists are skipped.
import PDFKit
import Vision
import AppKit
import Foundation

let a = CommandLine.arguments
guard a.count >= 3, let doc = PDFDocument(url: URL(fileURLWithPath: a[1])) else { fputs("usage\n", stderr); exit(1) }
let out = URL(fileURLWithPath: a[2])
try FileManager.default.createDirectory(at: out, withIntermediateDirectories: true)
let first = a.count > 3 ? Int(a[3])! : 1
let last = a.count > 4 ? min(Int(a[4])!, doc.pageCount) : doc.pageCount

for p in first...last {
  let name = String(format: "page_%03d", p)
  let jsonURL = out.appendingPathComponent(name + ".json")
  if FileManager.default.fileExists(atPath: jsonURL.path) { continue }
  autoreleasepool {
    guard let page = doc.page(at: p - 1) else { return }
    let r = page.bounds(for: .mediaBox)
    let scale = 2200.0 / max(r.width, r.height)
    let img = page.thumbnail(of: NSSize(width: r.width * scale, height: r.height * scale), for: .mediaBox)
    guard let tiff = img.tiffRepresentation, let rep = NSBitmapImageRep(data: tiff), let cg = rep.cgImage else { return }
    if let jpg = rep.representation(using: .jpeg, properties: [.compressionFactor: 0.8]) {
      try? jpg.write(to: out.appendingPathComponent(name + ".jpg"))
    }
    let req = VNRecognizeTextRequest()
    req.recognitionLevel = .accurate
    req.recognitionLanguages = ["ko-KR", "en-US"]
    req.usesLanguageCorrection = false
    try? VNImageRequestHandler(cgImage: cg).perform([req])
    var lines: [[String: Any]] = []
    for o in (req.results ?? []) {
      guard let c = o.topCandidates(1).first else { continue }
      let b = o.boundingBox   // normalised, origin bottom-left
      lines.append(["text": c.string, "x": Double(b.minX), "y": Double(1 - b.maxY), "w": Double(b.width), "h": Double(b.height), "conf": Double(c.confidence)])
    }
    lines.sort { ($0["y"] as! Double) < ($1["y"] as! Double) }
    let data = try! JSONSerialization.data(withJSONObject: ["pdf_page": p, "lines": lines], options: [])
    try! data.write(to: jsonURL)
    print("page \(p): \(lines.count) lines")
  }
}
