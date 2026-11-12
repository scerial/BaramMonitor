import SwiftUI

struct RingGauge: View {
    let maximum: Double
    let segments: [Segment]
    let markers: [Marker]
    let center: String
    var lineWidth: CGFloat = 12

    private var arcs: [(start: Double, end: Double, color: Color)] {
        var used = 0.0
        var result: [(start: Double, end: Double, color: Color)] = []
        let limit = max(maximum, 0.000001)
        for segment in segments {
            let value = min(max(segment.value, 0), limit - used)
            guard value > 0 else { continue }
            result.append((start: used / limit, end: (used + value) / limit, color: segment.color))
            used += value
        }

        return result
    }

    var body: some View {
        GeometryReader { proxy in
            let side = min(proxy.size.width, proxy.size.height)
            let radius = (side - lineWidth) / 2
            let mid = CGPoint(x: side / 2, y: side / 2)

            ZStack {
                Circle()
                    .stroke(Color.primary.opacity(0.12), lineWidth: lineWidth)
                    .padding(lineWidth / 2)

                ForEach(Array(arcs.enumerated()), id: \.offset) { _, arc in
                    Circle()
                        .trim(from: arc.start, to: arc.end)
                        .stroke(arc.color, style: StrokeStyle(lineWidth: lineWidth, lineCap: .butt))
                        .rotationEffect(.degrees(-90))
                        .padding(lineWidth / 2)
                }

                ForEach(Array(markers.enumerated()), id: \.offset) { _, marker in
                    let fraction = min(max(marker.value / max(maximum, 0.000001), 0), 1)
                    let angle = (-90 + 360 * fraction) * Double.pi / 180
                    Path { path in
                        let inner = radius - lineWidth / 2 - 2
                        let outer = radius + lineWidth / 2 + 2
                        path.move(to: CGPoint(x: mid.x + inner * cos(angle), y: mid.y + inner * sin(angle)))
                        path.addLine(to: CGPoint(x: mid.x + outer * cos(angle), y: mid.y + outer * sin(angle)))
                    }
                    .stroke(marker.color, lineWidth: 2)
                }

                Text(center)
                    .font(.system(.title3, design: .rounded).weight(.bold))
                    .minimumScaleFactor(0.5)
                    .lineLimit(1)
                    .padding(.horizontal, lineWidth + 4)
            }
            .frame(width: side, height: side)
            .position(x: proxy.size.width / 2, y: proxy.size.height / 2)
        }
        .aspectRatio(1, contentMode: .fit)
    }
}
