//
//  APIClient.swift
//  ios-app
//
//  HTTP client for NSU Audit API. Uses Bearer token; on 401 clears session.
//

import Foundation

enum APIError: LocalizedError {
    case notAuthenticated
    case invalidResponse
    case serverError(Int, String?)

    var errorDescription: String? {
        switch self {
        case .notAuthenticated: return "Not authenticated. Please sign in again."
        case .invalidResponse: return "Invalid response from server."
        case .serverError(let code, let msg): return msg ?? "Server error (\(code))."
        }
    }
}

final class APIClient {
    static let shared = APIClient()
    private let base: URL
    private let session: URLSession
    var onUnauthorized: (() -> Void)?

    private init() {
        self.base = AppConfig.apiBaseURL
        let config = URLSessionConfiguration.default
        config.timeoutIntervalForRequest = 60
        config.timeoutIntervalForResource = AppConfig.auditTimeout
        self.session = URLSession(configuration: config)
    }

    func token() -> String? { AuthService.shared.currentToken() }

    private func request(
        path: String,
        method: String = "GET",
        body: Data? = nil,
        contentType: String? = "application/json",
        formBoundary: String? = nil
    ) async throws -> (Data, HTTPURLResponse) {
        let url = base.appendingPathComponent(path)
        var req = URLRequest(url: url)
        req.httpMethod = method
        if let t = token() {
            req.setValue("Bearer \(t)", forHTTPHeaderField: "Authorization")
        }
        if let ct = formBoundary {
            req.setValue("multipart/form-data; boundary=\(ct)", forHTTPHeaderField: "Content-Type")
        } else if let ct = contentType {
            req.setValue(ct, forHTTPHeaderField: "Content-Type")
        }
        req.httpBody = body

        let (data, resp) = try await session.data(for: req)
        guard let http = resp as? HTTPURLResponse else { throw APIError.invalidResponse }
        if http.statusCode == 401 {
            AuthService.shared.logout()
            onUnauthorized?()
            throw APIError.notAuthenticated
        }
        if http.statusCode >= 400 {
            let msg = String(data: data, encoding: .utf8)
            throw APIError.serverError(http.statusCode, msg)
        }
        return (data, http)
    }

    func me() async throws -> User {
        let (data, _) = try await request(path: "api/auth/me")
        return try JSONDecoder().decode(User.self, from: data)
    }

    func historyList(limit: Int = 20, offset: Int = 0) async throws -> HistoryListResponse {
        var comp = URLComponents(url: base.appendingPathComponent("api/history/"), resolvingAgainstBaseURL: false)!
        comp.queryItems = [URLQueryItem(name: "limit", value: "\(limit)"), URLQueryItem(name: "offset", value: "\(offset)")]
        let (data, _) = try await request(path: "api/history/?limit=\(limit)&offset=\(offset)")
        return try JSONDecoder().decode(HistoryListResponse.self, from: data)
    }

    func historyDetail(runId: String) async throws -> HistoryDetailResponse {
        let (data, _) = try await request(path: "api/history/\(runId)")
        return try JSONDecoder().decode(HistoryDetailResponse.self, from: data)
    }

    func auditRun(
        fileURL: URL,
        program: String,
        answers: [String: Any],
        save: Bool,
        source: String = "ios"
    ) async throws -> AuditRunResponse {
        let boundary = UUID().uuidString
        var body = Data()
        func append(_ s: String) { body.append(Data(s.utf8)) }
        func appendPart(name: String, value: String) {
            append("--\(boundary)\r\nContent-Disposition: form-data; name=\"\(name)\"\r\n\r\n\(value)\r\n")
        }
        func appendFile(name: String, filename: String, data: Data, mime: String) {
            append("--\(boundary)\r\nContent-Disposition: form-data; name=\"\(name)\"; filename=\"\(filename)\"\r\nContent-Type: \(mime)\r\n\r\n")
            body.append(data)
            append("\r\n")
        }

        appendPart(name: "program", value: program)
        appendPart(name: "answers", value: (try? JSONSerialization.data(withJSONObject: answers)).flatMap { String(data: $0, encoding: .utf8) } ?? "{}")
        appendPart(name: "save", value: save ? "true" : "false")
        appendPart(name: "source", value: source)

        let fileData = try Data(contentsOf: fileURL)
        let ext = fileURL.pathExtension.lowercased()
        let mime = ext == "csv" ? "text/csv" : (ext == "pdf" ? "application/pdf" : "image/\(ext == "jpg" || ext == "jpeg" ? "jpeg" : ext)")
        appendFile(name: "transcript", filename: fileURL.lastPathComponent, data: fileData, mime: mime)
        append("--\(boundary)--\r\n")

        let (data, _) = try await request(path: "api/audit/run", method: "POST", body: body, contentType: nil, formBoundary: boundary)
        return try JSONDecoder().decode(AuditRunResponse.self, from: data)
    }

    func getAudit(runId: String) async throws -> AuditResult {
        let (data, _) = try await request(path: "api/audit/\(runId)")
        let json = try JSONSerialization.jsonObject(with: data) as? [String: Any]
        guard let result = json?["result"], let resultData = try? JSONSerialization.data(withJSONObject: result) else {
            throw APIError.invalidResponse
        }
        return try JSONDecoder().decode(AuditResult.self, from: resultData)
    }
}
