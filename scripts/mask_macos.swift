// Person segmentation masks for a video (Apple Vision, on-device). 2026-10-24.
// usage: swift mask_macos.swift <video> <out.raw> [W H]   (called by mask.py on macOS)
// Writes one 8-bit mask per frame (W x H, default 540x960), concatenated, in decode order (person = 255).
import AVFoundation
import CoreImage
import Foundation
import Vision

let args = CommandLine.arguments
let url = URL(fileURLWithPath: args[1])
let out = URL(fileURLWithPath: args[2])
let W = args.count > 3 ? Int(args[3])! : 540
let H = args.count > 4 ? Int(args[4])! : 960

let asset = AVURLAsset(url: url)
let sem = DispatchSemaphore(value: 0)
var track: AVAssetTrack?
Task { track = try? await asset.loadTracks(withMediaType: .video).first; sem.signal() }
sem.wait()
guard let vtrack = track else { fatalError("no video track") }
let reader = try AVAssetReader(asset: asset)
let output = AVAssetReaderTrackOutput(track: vtrack, outputSettings: [kCVPixelBufferPixelFormatTypeKey as String: kCVPixelFormatType_32BGRA])
reader.add(output)
reader.startReading()

FileManager.default.createFile(atPath: out.path, contents: nil)
let fh = try FileHandle(forWritingTo: out)
let ctx = CIContext()
let request = VNGeneratePersonSegmentationRequest()
request.qualityLevel = .accurate
request.outputPixelFormat = kCVPixelFormatType_OneComponent8
var n = 0
while let sample = output.copyNextSampleBuffer() {
    guard let pb = CMSampleBufferGetImageBuffer(sample) else { continue }
    let handler = VNImageRequestHandler(cvPixelBuffer: pb, options: [:])
    try handler.perform([request])
    var bytes = [UInt8](repeating: 0, count: W * H)
    if let mask = request.results?.first?.pixelBuffer {
        let ci = CIImage(cvPixelBuffer: mask)
        let sx = CGFloat(W) / ci.extent.width, sy = CGFloat(H) / ci.extent.height
        let scaled = ci.transformed(by: CGAffineTransform(scaleX: sx, y: sy))
        ctx.render(scaled, toBitmap: &bytes, rowBytes: W, bounds: CGRect(x: 0, y: 0, width: W, height: H), format: .L8, colorSpace: nil)
    }
    fh.write(Data(bytes))
    n += 1
}
try fh.close()
print("frames \(n) mask \(W)x\(H)")
