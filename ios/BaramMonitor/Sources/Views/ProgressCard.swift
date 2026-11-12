import SwiftUI

struct ProgressCard: View {
    let progress: MeshProgress

    private static func duration(_ seconds: Double) -> String {
        let total = Int(seconds)
        let h = total / 3600
        let m = (total % 3600) / 60
        let s = total % 60
        return h > 0 ? String(format: "%d:%02d:%02d", h, m, s) : String(format: "%d:%02d", m, s)
    }

    private func number(_ value: Int?) -> String {
        guard let value else { return "–" }
        return value.formatted(.number.grouping(.automatic))
    }

    private var tiles: [(String, String)] {
        switch progress.mode {
        case "layers":
            return [
                ("Extruded", progress.extrusionPercent.map { String(format: "%.1f%%", $0) } ?? "–"),
                ("Layer iteration", number(progress.layerIteration)),
                ("Illegal faces", number(progress.lastIllegal))
            ]
        case "snap":
            return [
                ("Morph iteration", progress.morphIteration.map { "\($0) / \(progress.morphTotal ?? 0)" } ?? "–")
            ]
        default:
            return [
                ("Cells selected", number(progress.selected)),
                ("Total cells", number(progress.totalCells)),
                ("Refinement steps", String(progress.refinementSteps))
            ]
        }
    }

    private var line: SparkLine? {
        switch progress.mode {
        case "layers":
            let values = progress.series.extruded
            return SparkLine(values: values.enumerated().map { (age: Double(values.count - $0.offset), value: $0.element) },
                             color: Palette.done, filled: true)
        case "refinement":
            let values = progress.series.selected
            return SparkLine(values: values.enumerated().map { (age: Double(values.count - $0.offset), value: $0.element) },
                             color: Palette.meshing, filled: true)
        default:
            return nil
        }
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack {
                Text("Meshing").font(.subheadline).foregroundStyle(.secondary)
                Spacer()
                ChipView(chip: Chip(text: progress.health.text, color: Palette.health(progress.health.key)))
            }

            HStack(alignment: .firstTextBaseline) {
                Text(progress.step).font(.title3.weight(.semibold))
                if !progress.phase.isEmpty {
                    Text(progress.phase.capitalized).foregroundStyle(.secondary)
                }
                Spacer()
                if let elapsed = progress.elapsed {
                    Text(Self.duration(elapsed)).monospacedDigit().foregroundStyle(.secondary)
                }
            }

            if progress.mode == "layers", let percent = progress.extrusionPercent {
                ProgressView(value: min(max(percent, 0), 100), total: 100)
                    .tint(Palette.done)
            }

            HStack(spacing: 18) {
                ForEach(Array(tiles.enumerated()), id: \.offset) { _, tile in
                    VStack(alignment: .leading, spacing: 2) {
                        Text(tile.0).font(.caption).foregroundStyle(.secondary)
                        Text(tile.1).font(.headline).monospacedDigit()
                    }
                }
                Spacer(minLength: 0)
            }

            if let line, line.values.count > 1 {
                let upper = progress.mode == "layers" ? 100.0 : (line.values.map { $0.value }.max() ?? 1)
                Sparkline(lines: [line], guides: [], range: 0...max(upper, 1), window: Double(line.values.count))
            }
        }
        .padding(12)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Color(.secondarySystemBackground), in: RoundedRectangle(cornerRadius: 14))
    }
}
