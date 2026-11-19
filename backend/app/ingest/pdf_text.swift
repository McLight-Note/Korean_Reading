// macOS-only helper: dump the embedded text layer of each PDF page as JSON.
// usage: swift pdf_text.swift in.pdf out.json
import PDFKit
import Foundation
let a = CommandLine.arguments
guard a.count >= 3, let doc = PDFDocument(url: URL(fileURLWithPath: a[1])) else { fputs("usage: pdf_text.swift in.pdf out.json\n", stderr); exit(1) }
var pages: [[String: Any]] = []
for i in 0..<doc.pageCount {
  pages.append(["pdf_page": i + 1, "text": doc.page(at: i)?.string ?? ""])
}
let data = try JSONSerialization.data(withJSONObject: pages, options: [])
try data.write(to: URL(fileURLWithPath: a[2]))
print("wrote \(pages.count) pages")
