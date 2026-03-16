//
//  AppConfig.swift
//  ios-app
//
//  NSU Audit API base URL and app configuration.
//

import Foundation

enum AppConfig {
    private static let baseURLKey = "NSUAuditAPIBaseURL"

    /// Backend API base URL (e.g. https://your-backend.com or http://localhost:8000 for dev).
    /// Set via Info.plist key NSUAuditAPIBaseURL or UserDefaults for debugging.
    static var apiBaseURL: URL {
        if let override = UserDefaults.standard.string(forKey: baseURLKey), !override.isEmpty,
           let url = URL(string: override) {
            return url
        }
        if let plist = Bundle.main.object(forInfoDictionaryKey: baseURLKey) as? String,
           let url = URL(string: plist) {
            return url
        }
        // Default for simulator / local dev
        return URL(string: "http://localhost:8000")!
    }

    /// Timeout for audit run requests (matches web: 2 min).
    static let auditTimeout: TimeInterval = 120
}
