//
//  LoginView.swift
//  ios-app
//
//  Sign in with Google (device flow): show user code, open verification URL.
//

import SwiftUI
import AuthenticationServices

struct LoginView: View {
    @StateObject private var auth = AuthService.shared
    @State private var userCode = ""
    @State private var verificationURL: URL?
    @State private var isWaiting = false
    @State private var errorMessage: String?
    @State private var showError = false

    var body: some View {
        ZStack {
            Theme.background.ignoresSafeArea()
            VStack(spacing: 0) {
                Spacer()
                VStack(alignment: .leading, spacing: 16) {
                    Text("STUDENT PORTAL")
                        .overlineLabel()
                    Text("Sign in to")
                        .font(.system(size: 34, weight: .regular, design: .serif))
                        .foregroundStyle(Theme.textPrimary)
                    Text("your audit.")
                        .font(.system(size: 34, weight: .regular, design: .serif))
                        .italic()
                        .foregroundStyle(Theme.textPrimary)
                }
                .frame(maxWidth: .infinity)
                .padding(.bottom, 32)

                if isWaiting {
                    VStack(spacing: 12) {
                        ProgressView()
                            .progressViewStyle(CircularProgressViewStyle(tint: Theme.textMuted))
                            .scaleEffect(1.2)
                        Text("Waiting for you to sign in…")
                            .font(.system(size: 14, weight: .light))
                            .foregroundStyle(Theme.textMuted)
                    }
                    .padding(.vertical, 24)
                } else if userCode.isEmpty {
                    Button {
                        startDeviceFlow()
                    } label: {
                        HStack(spacing: 8) {
                            Image(systemName: "globe")
                            Text("Continue with Google")
                                .tracking(0.12)
                        }
                        .font(.system(size: 13, weight: .light))
                        .frame(maxWidth: .infinity)
                        .padding(.vertical, 14)
                        .background(Theme.textPrimary)
                        .foregroundStyle(Theme.background)
                    }
                    .buttonStyle(.plain)
                    .padding(.horizontal, 24)
                } else {
                    VStack(alignment: .leading, spacing: 12) {
                        Text("Enter this code in your browser:")
                            .font(.system(size: 14, weight: .light))
                            .foregroundStyle(Theme.textMuted)
                        Text(userCode)
                            .font(.system(size: 24, weight: .medium, design: .monospaced))
                            .foregroundStyle(Theme.textPrimary)
                            .padding(.vertical, 8)
                            .padding(.horizontal, 16)
                            .background(Theme.surface)
                            .overlay(Rectangle().stroke(Theme.line, lineWidth: 1))
                        if let url = verificationURL {
                            Button {
                                UIApplication.shared.open(url)
                            } label: {
                                Text("Open browser to sign in")
                                    .font(.system(size: 14, weight: .light))
                                    .foregroundStyle(Theme.textPrimary)
                            }
                            .buttonStyle(.plain)
                        }
                    }
                    .padding(20)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .background(Theme.surface)
                    .overlay(Rectangle().stroke(Theme.line, lineWidth: 1))
                    .padding(.horizontal, 24)
                }

                Spacer()
                Text("North South University · Degree Audit System")
                    .font(.system(size: 11, weight: .light))
                    .foregroundStyle(Theme.textMuted)
                    .padding(.bottom, 32)
            }
        }
        .alert("Sign-in failed", isPresented: $showError) {
            Button("OK") {
                errorMessage = nil
                userCode = ""
                verificationURL = nil
                isWaiting = false
            }
        } message: {
            if let msg = errorMessage { Text(msg) }
        }
    }

    private func startDeviceFlow() {
        errorMessage = nil
        userCode = ""
        verificationURL = nil
        isWaiting = true
        Task {
            do {
                try await auth.runDeviceFlow { code, url in
                    DispatchQueue.main.async {
                        userCode = code
                        verificationURL = url
                        UIApplication.shared.open(url)
                    }
                }
                isWaiting = false
                userCode = ""
                verificationURL = nil
            } catch {
                DispatchQueue.main.async {
                    isWaiting = false
                    errorMessage = error.localizedDescription
                    showError = true
                }
            }
        }
    }
}

#Preview {
    LoginView()
}
