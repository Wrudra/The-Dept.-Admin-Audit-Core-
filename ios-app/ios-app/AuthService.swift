//
//  AuthService.swift
//  ios-app
//
//  Device Authorization Grant: start → open URL → poll Google → exchange for JWT.
//

import Foundation
import Combine
import AuthenticationServices

enum AuthError: LocalizedError {
    case noToken
    case deviceStartFailed(String)
    case pollFailed(String)
    case exchangeFailed(String)

    var errorDescription: String? {
        switch self {
        case .noToken: return "Not authenticated."
        case .deviceStartFailed(let m): return m
        case .pollFailed(let m): return m
        case .exchangeFailed(let m): return m
        }
    }
}

@MainActor
final class AuthService: ObservableObject {
    static let shared = AuthService()

    @Published private(set) var token: String?

    private init() {
        token = KeychainHelper.load()
    }

    var isLoggedIn: Bool { token != nil }

    func currentToken() -> String? {
        token ?? KeychainHelper.load()
    }

    func runDeviceFlow(verificationURL: (String, URL) -> Void) async throws {
        let base = AppConfig.apiBaseURL
        let startURL = base.appendingPathComponent("api/auth/device/start")
        var req = URLRequest(url: startURL)
        req.httpMethod = "POST"
        req.setValue("application/json", forHTTPHeaderField: "Accept")

        let (data, _) = try await URLSession.shared.data(for: req)
        let startResp = try JSONDecoder().decode(DeviceStartResponse.self, from: data)
        let userCode = startResp.user_code
        let verificationURLParsed = URL(string: startResp.verification_url) ?? base

        verificationURL(userCode, verificationURLParsed)

        // Poll Google token endpoint
        let idToken = try await pollGoogle(
            deviceCode: startResp.device_code,
            clientId: startResp.client_id,
            clientSecret: startResp.client_secret ?? "",
            interval: TimeInterval(startResp.interval ?? 5),
            expiresIn: TimeInterval(startResp.expires_in ?? 1800)
        )

        // Exchange id_token for API JWT
        let exchangeURL = base.appendingPathComponent("api/auth/device/exchange")
        var exchangeReq = URLRequest(url: exchangeURL)
        exchangeReq.httpMethod = "POST"
        exchangeReq.setValue("application/json", forHTTPHeaderField: "Content-Type")
        exchangeReq.httpBody = try JSONEncoder().encode(["id_token": idToken])

        let (exchangeData, exchangeResp) = try await URLSession.shared.data(for: exchangeReq)
        guard (exchangeResp as? HTTPURLResponse)?.statusCode == 200 else {
            throw AuthError.exchangeFailed(String(data: exchangeData, encoding: .utf8) ?? "Exchange failed")
        }
        let exchange = try JSONDecoder().decode(DeviceExchangeResponse.self, from: exchangeData)
        try KeychainHelper.save(token: exchange.access_token)
        token = exchange.access_token
    }

    private func pollGoogle(
        deviceCode: String,
        clientId: String,
        clientSecret: String,
        interval: TimeInterval,
        expiresIn: TimeInterval
    ) async throws -> String {
        let url = URL(string: "https://oauth2.googleapis.com/token")!
        let deadline = Date().addingTimeInterval(expiresIn)
        var lastInterval = interval

        while Date() < deadline {
            var req = URLRequest(url: url)
            req.httpMethod = "POST"
            req.setValue("application/x-www-form-urlencoded", forHTTPHeaderField: "Content-Type")
            let body = [
                "grant_type", "urn:ietf:params:oauth:grant-type:device_code",
                "device_code", deviceCode,
                "client_id", clientId,
                "client_secret", clientSecret,
            ]
            req.httpBody = body.chunked(into: 2).map { "\($0[0])=\($0[1].addingPercentEncoding(withAllowedCharacters: .urlQueryAllowed) ?? $0[1])" }.joined(separator: "&").data(using: .utf8)

            let (data, _) = try await URLSession.shared.data(for: req)
            let json = try JSONSerialization.jsonObject(with: data) as? [String: Any]
            if let idToken = json?["id_token"] as? String {
                return idToken
            }
            if let err = json?["error"] as? String {
                if err == "authorization_pending" || err == "slow_down" {
                    if err == "slow_down" { lastInterval = min(lastInterval + 5, 60) }
                    try await Task.sleep(nanoseconds: UInt64(lastInterval * 1_000_000_000))
                    continue
                }
                throw AuthError.pollFailed(err + ": \(json?["error_description"] as? String ?? "")")
            }
            try await Task.sleep(nanoseconds: UInt64(lastInterval * 1_000_000_000))
        }
        throw AuthError.pollFailed("Authorization timed out. Please try again.")
    }

    func logout() {
        try? KeychainHelper.delete()
        token = nil
    }

    func refreshFromKeychain() {
        token = KeychainHelper.load()
    }
}

extension Array {
    fileprivate func chunked(into size: Int) -> [[Element]] {
        stride(from: 0, to: count, by: size).map { Array(self[$0..<Swift.min($0 + size, count)]) }
    }
}
