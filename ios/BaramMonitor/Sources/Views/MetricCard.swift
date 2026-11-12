import SwiftUI

struct ChipView: View {
    let chip: Chip

    var body: some View {
        Text(chip.text)
            .font(.caption.weight(.semibold))
            .foregroundColor(chip.color == Palette.warn ? Color.black.opacity(0.85) : .white)
            .padding(.horizontal, 8)
            .padding(.vertical, 2)
            .background(chip.color, in: Capsule())
    }
}

struct MetricCard: View {
    let model: MetricCardModel

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(alignment: .top, spacing: 14) {
                RingGauge(maximum: model.maximum, segments: model.segments, markers: model.markers, center: model.center)
                    .frame(width: 104, height: 104)

                VStack(alignment: .leading, spacing: 4) {
                    HStack {
                        Text(model.title).font(.subheadline).foregroundStyle(.secondary)
                        Spacer(minLength: 4)
                        if let chip = model.chip {
                            ChipView(chip: chip)
                        }
                    }

                    Text(model.value)
                        .font(.headline)
                        .fixedSize(horizontal: false, vertical: true)

                    Text(model.detail)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                        .fixedSize(horizontal: false, vertical: true)
                }
            }

            if model.available {
                Sparkline(lines: model.lines, guides: model.guides, range: model.range)
            }
        }
        .padding(12)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Color(.secondarySystemBackground), in: RoundedRectangle(cornerRadius: 14))
    }
}
