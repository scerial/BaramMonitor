import SwiftUI

struct Segment {
    var value: Double
    var color: Color
}

struct Marker {
    var value: Double
    var color: Color
}

struct Chip {
    var text: String
    var color: Color
}

struct SparkLine {
    var values: [(age: Double, value: Double)]
    var color: Color
    var filled: Bool
}

struct MetricCardModel: Identifiable {
    var id: String
    var title: String
    var center: String
    var value: String
    var detail: String
    var maximum: Double
    var segments: [Segment]
    var markers: [Marker]
    var chip: Chip?
    var lines: [SparkLine]
    var guides: [Marker]
    var range: ClosedRange<Double>
    var available: Bool
}

enum MetricPresentation {
    private static let gib = 1_073_741_824.0
    private static let memoryWarn = 0.85
    private static let memoryCritical = 0.95
    private static let psuWarn = 0.8
    private static let window = 300.0

    static func cards(resources r: Resources, history: [SamplePoint]) -> [MetricCardModel] {
        let now = Date()
        func series(_ pick: (SamplePoint) -> Double?) -> [(age: Double, value: Double)] {
            history.compactMap { point in
                pick(point).map { (age: now.timeIntervalSince(point.date), value: $0) }
            }.filter { $0.age <= window }
        }

        return [
            memory(r, used: series { $0.memUsed / gib }, meshing: series { min($0.memMeshing, $0.memUsed) / gib }),
            cpu(r, total: series { $0.cpu }, meshing: series { min($0.cpuMeshing, $0.cpu) }),
            temperature(r, line: series { $0.temp }),
            cpuPower(r, line: series { $0.cpuPower }),
            pcPower(r, line: series { $0.pcPower })
        ]
    }

    private static func gb(_ bytes: Double) -> String {
        String(format: "%.1f", bytes / gib)
    }

    private static func percent(_ ratio: Double) -> String {
        String(format: "%.0f%%", ratio * 100)
    }

    private static func unavailable(_ id: String, _ title: String, _ reason: String) -> MetricCardModel {
        MetricCardModel(
            id: id, title: title, center: "–", value: "–", detail: reason, maximum: 1, segments: [], markers: [],
            chip: nil, lines: [], guides: [], range: 0...1, available: false)
    }

    private static func memory(
        _ r: Resources, used: [(age: Double, value: Double)], meshing: [(age: Double, value: Double)]
    ) -> MetricCardModel {
        let ratio = r.memTotal > 0 ? r.memUsed / r.memTotal : 0
        let meshingBytes = min(r.memMeshing, r.memUsed)
        let other = r.memUsed - meshingBytes
        let who = r.meshingRanks > 0
            ? "Meshing \(gb(meshingBytes)) GB in \(r.meshingRanks) process\(r.meshingRanks == 1 ? "" : "es")"
            : "No meshing running"

        var chip: Chip?
        if ratio >= memoryCritical {
            chip = Chip(text: "Nearly full", color: Palette.critical)
        } else if ratio >= memoryWarn {
            chip = Chip(text: "High", color: Palette.warn)
        }

        return MetricCardModel(
            id: "memory", title: "Memory", center: percent(ratio),
            value: "\(gb(r.memUsed)) / \(gb(r.memTotal)) GB",
            detail: "\(who) · other \(gb(other)) GB · free \(gb(r.memTotal - r.memUsed)) GB",
            maximum: r.memTotal,
            segments: [Segment(value: meshingBytes, color: Palette.meshing), Segment(value: other, color: Palette.other)],
            markers: [], chip: chip,
            lines: [
                SparkLine(values: used, color: Palette.other, filled: false),
                SparkLine(values: meshing, color: Palette.meshing, filled: true)
            ],
            guides: [], range: 0...max(r.memTotal / gib, 1), available: true)
    }

    private static func cpu(
        _ r: Resources, total: [(age: Double, value: Double)], meshing: [(age: Double, value: Double)]
    ) -> MetricCardModel {
        let meshingShare = min(r.cpuMeshingPercent, r.cpuPercent)
        return MetricCardModel(
            id: "cpu", title: "CPU usage", center: String(format: "%.0f%%", r.cpuPercent),
            value: String(format: "%.0f%%", r.cpuPercent),
            detail: String(format: "Meshing %.0f%% · %d logical cores", meshingShare, r.logicalCores),
            maximum: 100,
            segments: [
                Segment(value: meshingShare, color: Palette.meshing),
                Segment(value: r.cpuPercent - meshingShare, color: Palette.normal)
            ],
            markers: [], chip: nil,
            lines: [
                SparkLine(values: total, color: Palette.normal, filled: true),
                SparkLine(values: meshing, color: Palette.meshing, filled: false)
            ],
            guides: [], range: 0...100, available: true)
    }

    private static func temperature(_ r: Resources, line: [(age: Double, value: Double)]) -> MetricCardModel {
        guard let temp = r.cpuTemp else {
            return unavailable("temperature", "CPU temperature", "Unavailable: the PC has no temperature source running.")
        }

        let t = r.thresholds
        var color = Palette.normal
        var chip: Chip?
        if temp >= t.tempCritical {
            color = Palette.critical
            chip = Chip(text: "At limit", color: Palette.critical)
        } else if temp >= t.tempWarn {
            color = Palette.warn
            chip = Chip(text: "Near limit", color: Palette.warn)
        }

        let maximum = max(100, t.tempCritical + 5)
        return MetricCardModel(
            id: "temperature", title: "CPU temperature", center: String(format: "%.0f°", temp),
            value: String(format: "%.1f °C", temp),
            detail: String(format: "Yellow from %.0f °C · red at %.0f °C", t.tempWarn, t.tempCritical),
            maximum: maximum, segments: [Segment(value: temp, color: color)],
            markers: [Marker(value: t.tempWarn, color: Palette.warn), Marker(value: t.tempCritical, color: Palette.critical)],
            chip: chip, lines: [SparkLine(values: line, color: Palette.normal, filled: false)],
            guides: [Marker(value: t.tempWarn, color: Palette.warn), Marker(value: t.tempCritical, color: Palette.critical)],
            range: 30...maximum, available: true)
    }

    private static func cpuPower(_ r: Resources, line: [(age: Double, value: Double)]) -> MetricCardModel {
        guard let power = r.cpuPower else {
            return unavailable("cpuPower", "CPU power", "Unavailable: the PC has no power source running.")
        }

        let t = r.thresholds
        let scale = max(t.pptWatts, t.tdpWatts) * 1.05
        var color = Palette.normal
        var chip: Chip?
        if power >= t.pptWatts * 0.98 {
            color = Palette.critical
            chip = Chip(text: "At PPT limit", color: Palette.critical)
        } else if power > t.tdpWatts {
            color = Palette.warn
            chip = Chip(text: "Above TDP", color: Palette.warn)
        }

        let approx = r.cpuPowerEstimated ? "~" : ""
        let ratio = t.tdpWatts > 0 ? power / t.tdpWatts : 0
        let detail = r.cpuPowerEstimated
            ? "Estimated from CPU usage"
            : String(format: "TDP %.0f W · package power limit (PPT) %.0f W", t.tdpWatts, t.pptWatts)

        return MetricCardModel(
            id: "cpuPower", title: "CPU power", center: approx + percent(ratio),
            value: String(format: "%@%.0f W / %.0f W TDP (%@)", approx, power, t.tdpWatts, percent(ratio)),
            detail: detail, maximum: scale, segments: [Segment(value: power, color: color)],
            markers: [Marker(value: t.tdpWatts, color: Palette.muted), Marker(value: t.pptWatts, color: Palette.critical)],
            chip: chip, lines: [SparkLine(values: line, color: Palette.normal, filled: true)],
            guides: [Marker(value: t.tdpWatts, color: Palette.muted), Marker(value: t.pptWatts, color: Palette.critical)],
            range: 0...scale, available: true)
    }

    private static func pcPower(_ r: Resources, line: [(age: Double, value: Double)]) -> MetricCardModel {
        guard let power = r.pcPower else {
            return unavailable("pcPower", "PC power", "Unavailable: needs the CPU power reading from the PC.")
        }

        let t = r.thresholds
        let source: String
        if r.pcPowerMeasured {
            source = "Measured by the PSU sensor"
        } else {
            let gpu = r.gpuPower.map { String(format: "%.0f W", $0) } ?? "n/a"
            source = String(
                format: "Estimate: CPU %.0f W + GPU %@ + rest of system %.0f W", r.cpuPower ?? 0, gpu, t.baselineWatts)
        }

        guard t.psuWatts > 0 else {
            return MetricCardModel(
                id: "pcPower", title: "PC power", center: String(format: "%.0f W", power),
                value: String(format: "%.0f W", power),
                detail: source + " · set the PSU capacity on the PC to see the ratio",
                maximum: max(power * 2, 1), segments: [Segment(value: power, color: Palette.normal)],
                markers: [], chip: nil, lines: [SparkLine(values: line, color: Palette.normal, filled: true)],
                guides: [], range: 0...max(power * 2, 1), available: true)
        }

        let ratio = power / t.psuWatts
        var color = Palette.normal
        var chip: Chip?
        if ratio >= 1 {
            color = Palette.critical
            chip = Chip(text: "Over PSU capacity", color: Palette.critical)
        } else if ratio >= psuWarn {
            color = Palette.warn
            chip = Chip(text: "High load", color: Palette.warn)
        }

        let maximum = t.psuWatts * 1.05
        return MetricCardModel(
            id: "pcPower", title: "PC power", center: percent(ratio),
            value: String(format: "%.0f W / %.0f W PSU (%@)", power, t.psuWatts, percent(ratio)),
            detail: source + " · yellow from 80% of PSU capacity",
            maximum: maximum, segments: [Segment(value: power, color: color)],
            markers: [Marker(value: t.psuWatts * psuWarn, color: Palette.warn), Marker(value: t.psuWatts, color: Palette.critical)],
            chip: chip, lines: [SparkLine(values: line, color: Palette.normal, filled: true)],
            guides: [Marker(value: t.psuWatts * psuWarn, color: Palette.warn), Marker(value: t.psuWatts, color: Palette.critical)],
            range: 0...maximum, available: true)
    }
}
