import Foundation

struct Thresholds: Codable, Equatable {
    var tdpWatts: Double
    var pptWatts: Double
    var tempWarn: Double
    var tempCritical: Double
    var psuWatts: Double
    var baselineWatts: Double
}

struct Resources: Codable, Equatable {
    var memTotal: Double
    var memUsed: Double
    var memMeshing: Double
    var meshingRanks: Int
    var cpuPercent: Double
    var cpuMeshingPercent: Double
    var logicalCores: Int
    var cpuName: String?
    var cpuTemp: Double?
    var cpuPower: Double?
    var cpuPowerEstimated: Bool
    var gpuPower: Double?
    var gpuNames: [String]
    var pcPower: Double?
    var pcPowerMeasured: Bool
    var sensorSource: String?
    var sensorDetail: String?
    var sensorError: String?
    var libraryError: String?
    var ageSeconds: Double
    var thresholds: Thresholds
}

struct Health: Codable, Equatable {
    var key: String
    var text: String
}

struct ProgressSeries: Codable, Equatable {
    var selected: [Double]
    var extruded: [Double]
}

struct MeshProgress: Codable, Equatable {
    var runId: Double
    var program: String
    var phase: String
    var mode: String
    var step: String
    var health: Health
    var elapsed: Double?
    var iteration: Int?
    var selected: Int?
    var totalCells: Int?
    var morphIteration: Int?
    var morphTotal: Int?
    var layerIteration: Int?
    var extrusionPercent: Double?
    var lastIllegal: Int?
    var finished: Bool
    var finishedIllegal: Int
    var refinementSteps: Int
    var series: ProgressSeries
}

struct MonitorState: Codable, Equatable {
    var apiVersion: Int
    var instance: String
    var host: String
    var serverTime: Double
    var uptime: Double
    var resources: Resources?
    var progress: MeshProgress?
    var lastEventId: Int
}

struct MonitorEvent: Codable, Equatable, Identifiable {
    var id: Int
    var time: Double
    var kind: String
    var severity: String
    var title: String
    var message: String
    var notify: Bool

    var date: Date { Date(timeIntervalSince1970: time) }
}

struct EventsResponse: Codable {
    var instance: String
    var lastEventId: Int
    var events: [MonitorEvent]
}

struct PingResponse: Codable {
    var ok: Bool
    var apiVersion: Int
    var host: String
}

struct HistoryPoint: Codable, Equatable {
    var t: Double
    var memUsed: Double
    var memMeshing: Double
    var cpu: Double
    var cpuMeshing: Double
    var temp: Double?
    var cpuPower: Double?
    var pcPower: Double?
}

struct HistoryResponse: Codable {
    var seconds: Double
    var points: [HistoryPoint]
}

struct SamplePoint: Equatable {
    var date: Date
    var memUsed: Double
    var memMeshing: Double
    var cpu: Double
    var cpuMeshing: Double
    var temp: Double?
    var cpuPower: Double?
    var pcPower: Double?
}
