import SwiftUI

struct Sparkline: View {
    let lines: [SparkLine]
    let guides: [Marker]
    let range: ClosedRange<Double>
    var window: Double = 300

    var body: some View {
        Canvas { context, size in
            let span = max(range.upperBound - range.lowerBound, 0.000001)

            func point(_ age: Double, _ value: Double) -> CGPoint {
                let x = (1 - min(max(age / window, 0), 1)) * size.width
                let y = (1 - min(max((value - range.lowerBound) / span, 0), 1)) * size.height
                return CGPoint(x: x, y: y)
            }

            for guide in guides {
                var path = Path()
                let y = point(0, guide.value).y
                path.move(to: CGPoint(x: 0, y: y))
                path.addLine(to: CGPoint(x: size.width, y: y))
                context.stroke(path, with: .color(guide.color.opacity(0.8)), style: StrokeStyle(lineWidth: 1, dash: [3, 3]))
            }

            for line in lines where line.values.count > 1 {
                let points = line.values.sorted { $0.age > $1.age }.map { point($0.age, $0.value) }
                var stroke = Path()
                stroke.move(to: points[0])
                for p in points.dropFirst() { stroke.addLine(to: p) }

                if line.filled {
                    var fill = stroke
                    fill.addLine(to: CGPoint(x: points[points.count - 1].x, y: size.height))
                    fill.addLine(to: CGPoint(x: points[0].x, y: size.height))
                    fill.closeSubpath()
                    context.fill(fill, with: .color(line.color.opacity(0.22)))
                }

                context.stroke(stroke, with: .color(line.color), style: StrokeStyle(lineWidth: 1.6, lineJoin: .round))
            }
        }
        .background(Color.primary.opacity(0.05), in: RoundedRectangle(cornerRadius: 6))
        .frame(height: 44)
    }
}
