import BackgroundTasks
import Foundation

enum BackgroundRefresh {
    static let identifier = "com.baramonitor.app.refresh"
    private static let interval: TimeInterval = 15 * 60

    static func register() {
        BGTaskScheduler.shared.register(forTaskWithIdentifier: identifier, using: nil) { task in
            guard let task = task as? BGAppRefreshTask else {
                task.setTaskCompleted(success: false)
                return
            }

            handle(task)
        }
    }

    static func schedule() {
        let request = BGAppRefreshTaskRequest(identifier: identifier)
        request.earliestBeginDate = Date(timeIntervalSinceNow: interval)
        try? BGTaskScheduler.shared.submit(request)
    }

    private static func handle(_ task: BGAppRefreshTask) {
        schedule()

        let work = Task { @MainActor in
            await MonitorStore.shared.backgroundSync()
            task.setTaskCompleted(success: !Task.isCancelled)
        }

        task.expirationHandler = {
            work.cancel()
        }
    }
}
