import Foundation
import UserNotifications

final class Notifier: NSObject, UNUserNotificationCenterDelegate {
    static let shared = Notifier()

    private let center = UNUserNotificationCenter.current()

    func configure() {
        center.delegate = self
    }

    func requestAuthorization() async -> Bool {
        (try? await center.requestAuthorization(options: [.alert, .sound, .badge])) ?? false
    }

    func authorizationStatus() async -> UNAuthorizationStatus {
        await center.notificationSettings().authorizationStatus
    }

    func post(_ event: MonitorEvent, instance: String, host: String) async {
        let content = UNMutableNotificationContent()
        content.title = event.title
        content.subtitle = host
        content.body = event.message
        content.sound = .default
        content.threadIdentifier = event.kind

        let request = UNNotificationRequest(identifier: "event-\(instance)-\(event.id)", content: content, trigger: nil)
        try? await center.add(request)
    }

    func postTest(host: String) async {
        let content = UNMutableNotificationContent()
        content.title = "Test notification"
        content.subtitle = host
        content.body = "Alerts from BaramMesh will appear like this."
        content.sound = .default

        let request = UNNotificationRequest(identifier: "test-\(UUID().uuidString)", content: content, trigger: nil)
        try? await center.add(request)
    }

    func userNotificationCenter(
        _ center: UNUserNotificationCenter,
        willPresent notification: UNNotification
    ) async -> UNNotificationPresentationOptions {
        [.banner, .list, .sound]
    }
}
