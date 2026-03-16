//
//  Theme.swift
//  ios-app
//
//  Design system matching the web app (dark, editorial style).
//

import SwiftUI

enum Theme {
    // Background
    static let background = Color(hex: "0a0a0a")
    static let surface = Color(hex: "111111")
    static let surface2 = Color(hex: "181818")

    // Text
    static let textPrimary = Color(hex: "f0ede8")
    static let textMuted = Color(white: 1, opacity: 0.45)
    static let line = Color(white: 1, opacity: 0.14)

    // Semantic
    static let success = Color(red: 134/255, green: 190/255, blue: 130/255).opacity(0.85)
    static let warning = Color(red: 220/255, green: 180/255, blue: 100/255).opacity(0.85)
    static let danger = Color(red: 210/255, green: 100/255, blue: 90/255).opacity(0.85)
}

extension Color {
    init(hex: String) {
        let hex = hex.trimmingCharacters(in: CharacterSet.alphanumerics.inverted)
        var int: UInt64 = 0
        Scanner(string: hex).scanHexInt64(&int)
        let a, r, g, b: UInt64
        switch hex.count {
        case 3:
            (a, r, g, b) = (255, (int >> 8) * 17, (int >> 4 & 0xF) * 17, (int & 0xF) * 17)
        case 6:
            (a, r, g, b) = (255, int >> 16, int >> 8 & 0xFF, int & 0xFF)
        case 8:
            (a, r, g, b) = (int >> 24, int >> 16 & 0xFF, int >> 8 & 0xFF, int & 0xFF)
        default:
            (a, r, g, b) = (255, 0, 0, 0)
        }
        self.init(
            .sRGB,
            red: Double(r) / 255,
            green: Double(g) / 255,
            blue: Double(b) / 255,
            opacity: Double(a) / 255
        )
    }
}

// Typography: match web (serif for headings, sans for body)
struct SerifTitle: ViewModifier {
    func body(content: Content) -> some View {
        content.font(.system(size: 28, weight: .regular, design: .serif))
    }
}

struct OverlineLabel: ViewModifier {
    func body(content: Content) -> some View {
        content
            .font(.system(size: 11, weight: .light))
            .tracking(1.2)
            .textCase(.uppercase)
            .foregroundStyle(Theme.textMuted)
    }
}

extension View {
    func serifTitle() -> some View { modifier(SerifTitle()) }
    func overlineLabel() -> some View { modifier(OverlineLabel()) }
}
