//
//  ProfileView.swift
//  ios-app
//
//  Current user and logout (matches web nav user + Logout).
//

import SwiftUI

struct ProfileView: View {
    let user: User?
    let onLogout: () -> Void
    @State private var loadedUser: User?

    var body: some View {
        NavigationStack {
            VStack(alignment: .leading, spacing: 24) {
                Text("ACCOUNT")
                    .overlineLabel()
                if let u = loadedUser ?? user {
                    VStack(alignment: .leading, spacing: 8) {
                        Text(u.display_name)
                            .font(.system(size: 22, weight: .regular, design: .serif))
                            .foregroundStyle(Theme.textPrimary)
                        Text(u.email)
                            .font(.system(size: 14, weight: .light))
                            .foregroundStyle(Theme.textMuted)
                    }
                    .padding(.vertical, 16)
                } else {
                    ProgressView().padding(.vertical, 16)
                }
                Rectangle().fill(Theme.line).frame(height: 1)
                Button(role: .destructive, action: onLogout) {
                    Text("Logout")
                        .font(.system(size: 14, weight: .light))
                        .tracking(0.08)
                        .frame(maxWidth: .infinity)
                        .padding(.vertical, 12)
                }
                .buttonStyle(.plain)
                .foregroundStyle(Theme.danger)
                Spacer()
            }
            .padding(.horizontal, 20)
            .padding(.vertical, 16)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(Theme.background)
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .principal) {
                    Text("NSU Audit")
                        .font(.system(size: 18, weight: .regular, design: .serif))
                        .italic()
                        .foregroundStyle(Theme.textPrimary)
                }
            }
            .onAppear {
                if loadedUser == nil {
                    Task {
                        loadedUser = try? await APIClient.shared.me()
                    }
                }
            }
        }
    }
}

#Preview {
    ProfileView(user: nil, onLogout: {})
}
