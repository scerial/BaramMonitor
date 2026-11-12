import SwiftUI

struct DashboardView: View {
    @EnvironmentObject private var store: MonitorStore

    private var statusLine: (text: String, color: Color) {
        switch store.status {
        case .notConfigured: return ("Not paired", Palette.idle)
        case .connecting: return ("Connecting…", Palette.idle)
        case .connected: return ("Connected to \(store.state?.host ?? store.connection.displayName)", Palette.done)
        case .unauthorized: return ("Access token rejected. Pair again.", Palette.critical)
        case .offline(let reason): return ("Offline: \(reason)", Palette.caution)
        }
    }

    private var columns: [GridItem] {
        [GridItem(.adaptive(minimum: 320), spacing: 12, alignment: .top)]
    }

    var body: some View {
        ScrollView {
            VStack(spacing: 12) {
                HStack(spacing: 8) {
                    Circle().fill(statusLine.color).frame(width: 10, height: 10)
                    Text(statusLine.text).font(.footnote).foregroundStyle(.secondary)
                    Spacer()
                    if let updated = store.lastUpdate {
                        Text(updated, style: .time).font(.footnote).foregroundStyle(.tertiary)
                    }
                }

                if store.status == .notConfigured {
                    VStack(alignment: .leading, spacing: 8) {
                        Text("Pair with your PC").font(.headline)
                        Text("In BaramMesh open the Resources tab, choose Settings, switch on sharing and tap Pair a phone. Scan the code with the Camera app, or enter the details under Settings here.")
                            .font(.subheadline)
                            .foregroundStyle(.secondary)
                    }
                    .padding(14)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .background(Color(.secondarySystemBackground), in: RoundedRectangle(cornerRadius: 14))
                }

                if let progress = store.state?.progress {
                    ProgressCard(progress: progress)
                }

                if let resources = store.state?.resources {
                    LazyVGrid(columns: columns, spacing: 12) {
                        ForEach(MetricPresentation.cards(resources: resources, history: store.history)) { model in
                            MetricCard(model: model)
                        }
                    }

                    if let note = resources.sensorError ?? resources.libraryError {
                        Text(note).font(.footnote).foregroundStyle(.secondary).frame(maxWidth: .infinity, alignment: .leading)
                    }
                }
            }
            .padding(16)
        }
        .navigationTitle(store.state?.host ?? "BaramMonitor")
        .navigationBarTitleDisplayMode(.inline)
        .toolbar {
            ToolbarItem(placement: .navigationBarLeading) {
                NavigationLink {
                    EventsView()
                } label: {
                    Image(systemName: "bell")
                }
            }

            ToolbarItem(placement: .navigationBarTrailing) {
                NavigationLink {
                    SettingsView()
                } label: {
                    Image(systemName: "gearshape")
                }
            }
        }
    }
}
