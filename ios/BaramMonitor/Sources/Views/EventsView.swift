import SwiftUI

struct EventsView: View {
    @EnvironmentObject private var store: MonitorStore

    private func icon(_ severity: String) -> String {
        switch severity {
        case "critical": return "exclamationmark.octagon.fill"
        case "warning": return "exclamationmark.triangle.fill"
        default: return "info.circle.fill"
        }
    }

    var body: some View {
        List {
            if store.events.isEmpty {
                Text("No events yet. Alerts and phase changes from BaramMesh appear here.")
                    .foregroundStyle(.secondary)
            }

            ForEach(store.events) { event in
                HStack(alignment: .top, spacing: 12) {
                    Image(systemName: icon(event.severity))
                        .foregroundColor(Palette.severity(event.severity))
                        .frame(width: 24)

                    VStack(alignment: .leading, spacing: 2) {
                        Text(event.title).font(.headline)
                        Text(event.message).font(.subheadline).foregroundStyle(.secondary)
                        Text(event.date, style: .relative)
                            .font(.caption)
                            .foregroundStyle(.tertiary)
                    }
                }
                .padding(.vertical, 2)
            }
        }
        .navigationTitle("Events")
    }
}
