//
//  AuthService.swift
//  ios-app
//
//  Independent iOS Google OAuth (PKCE) → exchange id_token for NSU Audit JWT.
//

import Foundation
import Combine
import AuthenticationServices
import CryptoKit
import UIKit

enum AuthError: LocalizedError {
    case notConfigured(String)
    case cancelled
    case oauthFailed(String)
    case invalidCallback(String)
    case tokenExchangeFailed(String)

    var errorDescription: String? {
        switch self {
        case .notConfigured(let m): return m
        case .cancelled: return "Sign-in was cancelled."
        case .oauthFailed(let m): return m
        case .invalidCallback(let m): return m
        case .tokenExchangeFailed(let m): return m
        }
    }
}

private final class AuthSessionContext: NSObject, ASWebAuthenticationPresentationContextProviding {
    func presentationAnchor(for session: ASWebAuthenticationSession) -> ASPresentationAnchor {
        let windows = UIApplication.shared.connectedScenes
            .compactMap { $0 as? UIWindowScene }
            .flatMap { $0.windows }
        if let key = windows.first(where: { $0.isKeyWindow }) { return key }
        if let first = windows.first { return first }
        if let scene = UIApplication.shared.connectedScenes.compactMap({ $0 as? UIWindowScene }).first {
            return UIWindow(windowScene: scene)
        }
        // This should be unreachable in practice, but satisfy the return type without using deprecated UIWindow().
        return UIWindow(frame: .zero)
    }
}

/// Ensures the async continuation is resumed at most once.
private final class OneShotContinuation<T> {
    private let continuation: CheckedContinuation<T, Error>
    private var resumed = false
    private let lock = NSLock()

    init(_ continuation: CheckedContinuation<T, Error>) {
        self.continuation = continuation
    }

    func resume(returning value: T) {
        lock.lock()
        defer { lock.unlock() }
        guard !resumed else { return }
        resumed = true
        continuation.resume(returning: value)
    }

    func resume(throwing error: Error) {
        lock.lock()
        defer { lock.unlock() }
        guard !resumed else { return }
        resumed = true
        continuation.resume(throwing: error)
    }
}

@MainActor
final class AuthService: ObservableObject {
    static let shared = AuthService()

    @Published private(set) var token: String?

    // Retain these until the callback runs.
    private var webAuthPresentationContext: AuthSessionContext?
    private var activeWebAuthSession: ASWebAuthenticationSession?

    private init() {
        token = KeychainHelper.load()
    }

    var isLoggedIn: Bool { token != nil }

    func currentToken() -> String? {
        token ?? KeychainHelper.load()
    }

    /// Native Google OAuth (PKCE) using the iOS client ID, then exchange id_token for API JWT.
    func signInWithNorthSouthAccount() async throws {
        let clientID = AppConfig.googleIOSClientID
        if clientID.isEmpty {
            throw AuthError.notConfigured("Missing NSUAuditGoogleIOSClientID (Google iOS OAuth client id).")
        }

        let redirectURI = AppConfig.oauthRedirectURI
        let callbackScheme = AppConfig.oauthCallbackScheme

        let verifier = Self.randomBase64URL(length: 64)
        let challenge = Self.codeChallengeS256(verifier: verifier)
        let state = Self.randomBase64URL(length: 32)

        let authURL = try Self.buildGoogleAuthorizeURL(
            clientID: clientID,
            redirectURI: redirectURI,
            codeChallenge: challenge,
            state: state
        )

        let code = try await startWebAuth(authURL: authURL, callbackScheme: callbackScheme, expectedState: state)
        let idToken = try await exchangeCodeForIdToken(
            code: code,
            clientID: clientID,
            redirectURI: redirectURI,
            verifier: verifier
        )
        let jwt = try await exchangeIdTokenForAPIToken(idToken: idToken)

        try KeychainHelper.save(token: jwt)
        token = jwt
    }

    private func startWebAuth(authURL: URL, callbackScheme: String, expectedState: String) async throws -> String {
        try await withCheckedThrowingContinuation { (continuation: CheckedContinuation<String, Error>) in
            let oneShot = OneShotContinuation<String>(continuation)

            let session = ASWebAuthenticationSession(url: authURL, callbackURLScheme: callbackScheme) { [weak self] callbackURL, error in
                defer {
                    self?.webAuthPresentationContext = nil
                    self?.activeWebAuthSession = nil
                }

                if let error = error as? NSError,
                   error.domain == ASWebAuthenticationSessionErrorDomain,
                   error.code == ASWebAuthenticationSessionError.canceledLogin.rawValue {
                    oneShot.resume(throwing: AuthError.cancelled)
                    return
                }
                if let error = error {
                    oneShot.resume(throwing: AuthError.oauthFailed(error.localizedDescription))
                    return
                }
                guard let url = callbackURL else {
                    oneShot.resume(throwing: AuthError.invalidCallback("No callback URL"))
                    return
                }

                guard let comps = URLComponents(url: url, resolvingAgainstBaseURL: false) else {
                    oneShot.resume(throwing: AuthError.invalidCallback("Bad callback URL"))
                    return
                }

                let items = comps.queryItems ?? []
                let returnedState = items.first(where: { $0.name == "state" })?.value ?? ""
                if returnedState != expectedState {
                    oneShot.resume(throwing: AuthError.invalidCallback("State mismatch"))
                    return
                }

                if let errorCode = items.first(where: { $0.name == "error" })?.value {
                    oneShot.resume(throwing: AuthError.oauthFailed("Google sign-in error: \(errorCode)"))
                    return
                }
                guard let code = items.first(where: { $0.name == "code" })?.value, !code.isEmpty else {
                    oneShot.resume(throwing: AuthError.invalidCallback("Missing authorization code"))
                    return
                }
                oneShot.resume(returning: code)
            }

            let context = AuthSessionContext()
            self.webAuthPresentationContext = context
            self.activeWebAuthSession = session
            session.presentationContextProvider = context
            session.prefersEphemeralWebBrowserSession = false
            if !session.start() {
                self.webAuthPresentationContext = nil
                self.activeWebAuthSession = nil
                oneShot.resume(throwing: AuthError.oauthFailed("Could not start sign-in"))
            }
        }
    }

    private func exchangeCodeForIdToken(code: String, clientID: String, redirectURI: String, verifier: String) async throws -> String {
        let url = URL(string: "https://oauth2.googleapis.com/token")!
        var req = URLRequest(url: url)
        req.httpMethod = "POST"
        req.setValue("application/x-www-form-urlencoded", forHTTPHeaderField: "Content-Type")
        let body: [String: String] = [
            "grant_type": "authorization_code",
            "code": code,
            "client_id": clientID,
            "redirect_uri": redirectURI,
            "code_verifier": verifier
        ]
        req.httpBody = Self.formURLEncoded(body).data(using: .utf8)

        let (data, resp) = try await URLSession.shared.data(for: req)
        guard (resp as? HTTPURLResponse)?.statusCode == 200 else {
            throw AuthError.oauthFailed(String(data: data, encoding: .utf8) ?? "Google token exchange failed")
        }
        let json = (try JSONSerialization.jsonObject(with: data) as? [String: Any]) ?? [:]
        guard let idToken = json["id_token"] as? String, !idToken.isEmpty else {
            throw AuthError.oauthFailed("id_token missing from Google response")
        }
        return idToken
    }

    private func exchangeIdTokenForAPIToken(idToken: String) async throws -> String {
        let base = AppConfig.apiBaseURL
        let url = base.appendingPathComponent("api/auth/mobile/exchange")
        var req = URLRequest(url: url)
        req.httpMethod = "POST"
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        req.httpBody = try JSONEncoder().encode(["id_token": idToken])

        let (data, resp) = try await URLSession.shared.data(for: req)
        guard (resp as? HTTPURLResponse)?.statusCode == 200 else {
            throw AuthError.tokenExchangeFailed(String(data: data, encoding: .utf8) ?? "Backend token exchange failed")
        }
        let exchange = try JSONDecoder().decode(DeviceExchangeResponse.self, from: data)
        return exchange.access_token
    }

    func logout() {
        try? KeychainHelper.delete()
        token = nil
    }

    func refreshFromKeychain() {
        token = KeychainHelper.load()
    }

    // MARK: - Google OAuth URL + PKCE helpers

    private static func buildGoogleAuthorizeURL(
        clientID: String,
        redirectURI: String,
        codeChallenge: String,
        state: String
    ) throws -> URL {
        var comps = URLComponents(string: "https://accounts.google.com/o/oauth2/v2/auth")!
        comps.queryItems = [
            URLQueryItem(name: "client_id", value: clientID),
            URLQueryItem(name: "redirect_uri", value: redirectURI),
            URLQueryItem(name: "response_type", value: "code"),
            URLQueryItem(name: "scope", value: "openid email profile"),
            URLQueryItem(name: "state", value: state),
            URLQueryItem(name: "code_challenge", value: codeChallenge),
            URLQueryItem(name: "code_challenge_method", value: "S256"),
            URLQueryItem(name: "prompt", value: "select_account"),
            URLQueryItem(name: "hd", value: "northsouth.edu")
        ]
        guard let url = comps.url else { throw AuthError.oauthFailed("Could not build authorization URL") }
        return url
    }

    private static func codeChallengeS256(verifier: String) -> String {
        let data = Data(verifier.utf8)
        let digest = SHA256.hash(data: data)
        return base64url(Data(digest))
    }

    private static func randomBase64URL(length: Int) -> String {
        var bytes = [UInt8](repeating: 0, count: length)
        _ = SecRandomCopyBytes(kSecRandomDefault, bytes.count, &bytes)
        return base64url(Data(bytes))
    }

    private static func base64url(_ data: Data) -> String {
        data.base64EncodedString()
            .replacingOccurrences(of: "+", with: "-")
            .replacingOccurrences(of: "/", with: "_")
            .replacingOccurrences(of: "=", with: "")
    }

    private static func formURLEncoded(_ params: [String: String]) -> String {
        params.map { key, value in
            let v = value.addingPercentEncoding(withAllowedCharacters: .urlQueryAllowed) ?? value
            return "\(key)=\(v)"
        }.sorted().joined(separator: "&")
    }
}

