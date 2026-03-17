//
//  LoginView.swift
//  ios-app
//
//  Sign in with North South account (native Google OAuth PKCE).
//

import SwiftUI

struct LoginView: View {
    @StateObject private var auth = AuthService.shared
    @State private var isSigningIn = false
    @State private var errorMessage: String?
    @State private var showError = false

    var body: some View {
        ZStack {
            Theme.background.ignoresSafeArea()
            VStack(spacing: 0) {
                Spacer()
                VStack(spacing: 24) {
                    Image("Logo")
                        .resizable()
                        .aspectRatio(contentMode: .fit)
                        .frame(width: 120, height: 120)
                        .clipShape(RoundedRectangle(cornerRadius: 20, style: .continuous))
                        .overlay(
                            RoundedRectangle(cornerRadius: 20, style: .continuous)
                                .stroke(Theme.line, lineWidth: 1)
                        )
                    VStack(alignment: .center, spacing: 16) {
                        Text("WELCOME TO NSU AUDIT")
                            .overlineLabel()
                        Text("Sign in to")
                            .font(.system(size: 34, weight: .regular, design: .serif))
                            .foregroundStyle(Theme.textPrimary)
                        Text("your audit.")
                            .font(.system(size: 34, weight: .regular, design: .serif))
                            .italic()
                            .foregroundStyle(Theme.textPrimary)
                    }
                    .multilineTextAlignment(.center)
                    .frame(maxWidth: .infinity)
                }
                .padding(.horizontal, 24)
                .padding(.bottom, 32)

                if isSigningIn {
                    VStack(spacing: 12) {
                        ProgressView()
                            .progressViewStyle(CircularProgressViewStyle(tint: Theme.textMuted))
                            .scaleEffect(1.2)
                        Text("Signing you in…")
                            .font(.system(size: 14, weight: .light))
                            .foregroundStyle(Theme.textMuted)
                    }
                    .padding(.vertical, 24)
                } else {
                    Button {
                        startSignIn()
                    } label: {
                        HStack(spacing: 8) {
                            Image(systemName: "person.crop.circle")
                            Text("Sign in with North South account")
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
                isSigningIn = false
            }
        } message: {
            if let msg = errorMessage { Text(msg) }
        }
    }

    private func startSignIn() {
        errorMessage = nil
        isSigningIn = true
        Task {
            do {
                try await auth.signInWithNorthSouthAccount()
                isSigningIn = false
            } catch {
                DispatchQueue.main.async {
                    isSigningIn = false
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
