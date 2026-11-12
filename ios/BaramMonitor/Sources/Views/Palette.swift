import SwiftUI

extension Color {
    init(hex: UInt32) {
        self.init(
            red: Double((hex >> 16) & 0xFF) / 255,
            green: Double((hex >> 8) & 0xFF) / 255,
            blue: Double(hex & 0xFF) / 255)
    }
}

enum Palette {
    static let normal = Color(hex: 0x0072B2)
    static let meshing = Color(hex: 0xE69F00)
    static let warn = Color(hex: 0xF2C200)
    static let critical = Color(hex: 0xE03131)
    static let done = Color(hex: 0x009E73)
    static let caution = Color(hex: 0xD55E00)
    static let idle = Color(hex: 0x6B7280)
    static let muted = Color.secondary
    static let other = Color.secondary.opacity(0.55)

    static func health(_ key: String) -> Color {
        switch key {
        case "done": return done
        case "warn": return caution
        case "running": return normal
        default: return idle
        }
    }

    static func severity(_ severity: String) -> Color {
        switch severity {
        case "critical": return critical
        case "warning": return warn
        default: return normal
        }
    }
}
