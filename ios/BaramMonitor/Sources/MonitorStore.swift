import Foundation
import SwiftUI
import UIKit
import UserNotifications

@MainActor
final class MonitorStore: ObservableObject {
    static let shared = MonitorStore()

    enum Status: Equatable {
        case notConfigured
        case connecting
        case connected
        case unauthorized
        case offline(String)
    }

    private enum Keys {
        static let instance = "events.instance"
        static let cursor = "events.cursor"
        static let notifications = "settings.notifications"
        static let keepScreenOn = "settings.keepScreenOn"
    }

    @Published private(set) var status: Status = .notConfigured
    @Published private(set) var state: MonitorState?
    @Published private(set) var events: [MonitorEvent] = []
    @Published private(set) var history: [SamplePoint] = []
    @Published private(set) var lastUpdate: Date?
    @Published private(set) var connection: Connection
    @Published private(set) var notificationStatus: UNAuthorizationStatus = .notDetermined

    @Published var notificationsEnabled: Bool {
        didSet { defaults.set(notificationsEnabled, forKey: Keys.notifications) }
    }

    @Published var keepScreenOn: Bool {
        didSet {
            defaults.set(keepScreenOn, forKey: Keys.keepScreenOn)
            applyIdleTimer()
        }
    }

    private let defaults = UserDefaults.standard
    private let maxNotificationAge: TimeInterval = 12 * 3600
    private let historyWindow: TimeInterval = 300
    private let eventCapacity = 200
    private var active = false
    private var pollTask: Task<Void, Never>?
    private var eventTask: Task<Void, Never>?

    private init() {
        connection = ConnectionStorage.load()
        notificationsEnabled = UserDefaults.standard.object(forKey: Keys.notifications) as? Bool ?? true
        keepScreenOn = UserDefaults.standard.bool(forKey: Keys.keepScreenOn)
        status = connection.isComplete ? .connecting : .notConfigured
    }

    private var savedInstance: String? {
        get { defaults.string(forKey: Keys.instance) }
        set { defaults.set(newValue, forKey: Keys.instance) }
    }

    private var cursor: Int {
        get { defaults.integer(forKey: Keys.cursor) }
        set { defaults.set(newValue, forKey: Keys.cursor) }
    }

    func activate() {
        active = true
        applyIdleTimer()
        Task { await refreshNotificationStatus() }
        start()
    }

    func deactivate() {
        active = false
        applyIdleTimer()
        stop()
    }

    func save(_ new: Connection) {
        let changed = new.host != connection.host || new.port != connection.port || new.token != connection.token
        connection = new
        ConnectionStorage.save(new)
        if changed {
            resetEvents()
            state = nil
            history = []
        }

        if active {
            start()
        } else {
            status = new.isComplete ? .connecting : .notConfigured
        }
    }

    func pair(with url: URL) -> Bool {
        guard let paired = Connection(pairing: url) else { return false }
        save(paired)
        return true
    }

    func forget() {
        stop()
        connection = Connection()
        ConnectionStorage.save(connection)
        state = nil
        history = []
        resetEvents()
        status = .notConfigured
    }

    func requestNotifications() async {
        _ = await Notifier.shared.requestAuthorization()
        await refreshNotificationStatus()
    }

    func refreshNotificationStatus() async {
        notificationStatus = await Notifier.shared.authorizationStatus()
    }

    func sendTestNotification() async {
        await Notifier.shared.postTest(host: connection.displayName)
    }

    func backgroundSync() async {
        guard connection.isComplete else { return }

        let client = MonitorClient(connection: connection)
        await refresh(client)
        await pullEvents(client, wait: 0)
    }

    private func start() {
        stop()
        guard connection.isComplete else {
            status = .notConfigured
            return
        }

        status = .connecting
        let client = MonitorClient(connection: connection)

        pollTask = Task { [weak self] in
            await self?.backfillHistory(client)
            while !Task.isCancelled {
                await self?.refresh(client)
                try? await Task.sleep(nanoseconds: 2_000_000_000)
            }
        }

        eventTask = Task { [weak self] in
            while !Task.isCancelled {
                let healthy = await self?.pullEvents(client, wait: 25) ?? false
                if !healthy {
                    try? await Task.sleep(nanoseconds: 5_000_000_000)
                }
            }
        }
    }

    private func stop() {
        pollTask?.cancel()
        eventTask?.cancel()
        pollTask = nil
        eventTask = nil
    }

    private func applyIdleTimer() {
        UIApplication.shared.isIdleTimerDisabled = active && keepScreenOn
    }

    private func refresh(_ client: MonitorClient) async {
        do {
            let newState = try await client.state()
            state = newState
            lastUpdate = Date()
            status = .connected
            if let resources = newState.resources {
                appendHistory(resources)
            }
        } catch is CancellationError {
            return
        } catch MonitorError.unauthorized {
            status = .unauthorized
        } catch {
            status = .offline(error.localizedDescription)
        }
    }

    private func backfillHistory(_ client: MonitorClient) async {
        guard let response = try? await client.history(seconds: Int(historyWindow)) else { return }

        let now = Date()
        history = response.points.sorted { $0.t > $1.t }.map {
            SamplePoint(
                date: now.addingTimeInterval(-$0.t), memUsed: $0.memUsed, memMeshing: $0.memMeshing,
                cpu: $0.cpu, cpuMeshing: $0.cpuMeshing, temp: $0.temp, cpuPower: $0.cpuPower, pcPower: $0.pcPower)
        }
    }

    private func appendHistory(_ resources: Resources) {
        let now = Date()
        history.append(SamplePoint(
            date: now, memUsed: resources.memUsed, memMeshing: resources.memMeshing, cpu: resources.cpuPercent,
            cpuMeshing: resources.cpuMeshingPercent, temp: resources.cpuTemp, cpuPower: resources.cpuPower,
            pcPower: resources.pcPower))
        history.removeAll { now.timeIntervalSince($0.date) > historyWindow }
    }

    private func resetEvents() {
        events = []
        savedInstance = nil
        cursor = 0
    }

    @discardableResult
    private func pullEvents(_ client: MonitorClient, wait: Int) async -> Bool {
        do {
            let response = try await client.events(since: cursor, wait: wait)
            handle(response)
            return true
        } catch is CancellationError {
            return true
        } catch {
            return false
        }
    }

    private func handle(_ response: EventsResponse) {
        if response.instance != savedInstance {
            let firstContact = savedInstance == nil
            savedInstance = response.instance
            if firstContact {
                events = response.events.sorted { $0.id > $1.id }
                cursor = response.lastEventId
            } else {
                events = []
                cursor = 0
            }

            return
        }

        let fresh = response.events.filter { $0.id > cursor }
        cursor = max(cursor, response.lastEventId)
        guard !fresh.isEmpty else { return }

        events = Array((fresh.sorted { $0.id > $1.id } + events).prefix(eventCapacity))
        guard notificationsEnabled else { return }

        let now = Date()
        let host = connection.displayName
        for event in fresh where event.notify && now.timeIntervalSince(event.date) < maxNotificationAge {
            Task { await Notifier.shared.post(event, instance: response.instance, host: host) }
        }
    }
}
