//
//  AppConfig.swift
//  ios-app
//
//  NSU Audit API base URL and app configuration.
//

import Foundation

enum AppConfig {
    private static let baseURLKey = "NSUAuditAPIBaseURL"
    private static let googleIOSClientIDKey = "NSUAuditGoogleIOSClientID"
    private static let oauthCallbackSchemeKey = "NSUAuditOAuthCallbackScheme"

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

    /// Google OAuth Client ID for the iOS app.
    /// Set via Info.plist key NSUAuditGoogleIOSClientID or UserDefaults for debugging.
    static var googleIOSClientID: String {
        if let override = UserDefaults.standard.string(forKey: googleIOSClientIDKey), !override.isEmpty {
            return override
        }
        if let plist = Bundle.main.object(forInfoDictionaryKey: googleIOSClientIDKey) as? String, !plist.isEmpty {
            return plist
        }
        return ""
    }

    /// URL scheme used by the app for OAuth callbacks (default: nsuaudit).
    static var oauthCallbackScheme: String {
        if let override = UserDefaults.standard.string(forKey: oauthCallbackSchemeKey), !override.isEmpty {
            return override
        }
        if let plist = Bundle.main.object(forInfoDictionaryKey: oauthCallbackSchemeKey) as? String, !plist.isEmpty {
            return plist
        }
        // For Google iOS OAuth clients, the default scheme is the reversed client id:
        //   com.googleusercontent.apps.<client_id_prefix>
        // and redirect URI:
        //   com.googleusercontent.apps.<client_id_prefix>:/oauthredirect
        let clientId = googleIOSClientID
        if let prefix = clientId.split(separator: ".").first, !prefix.isEmpty {
            return "com.googleusercontent.apps.\(prefix)"
        }
        return "nsuaudit"
    }

    /// Redirect URI for Google native OAuth (must match the scheme registered in the app).
    static var oauthRedirectURI: String {
        "\(oauthCallbackScheme):/oauthredirect"
    }

    /// Timeout for audit run requests (matches web: 2 min).
    static let auditTimeout: TimeInterval = 120
}
