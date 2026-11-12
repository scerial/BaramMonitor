import SwiftUI

@main
struct BaramMonitorApp: App {
    @Environment(\.scenePhase) private var scenePhase
    @StateObject private var store = MonitorStore.shared

    init() {
        BackgroundRefresh.register()
        Notifier.shared.configure()
    }

    var body: some Scene {
        WindowGroup {
            NavigationStack {
                DashboardView()
            }
            .environmentObject(store)
            .onOpenURL { url in
                if store.pair(with: url) {
                    Task { await store.requestNotifications() }
                }
            }
        }
        .onChange(of: scenePhase) { phase in
            switch phase {
            case .active:
                store.activate()
            case .background:
                store.deactivate()
                BackgroundRefresh.schedule()
            default:
                break
            }
        }
    }
}
