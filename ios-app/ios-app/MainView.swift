//
//  MainView.swift
//  ios-app
//
//  Main shell after login: tab bar (Dashboard, New Audit, History, Profile).
//

import SwiftUI

struct MainView: View {
    @StateObject private var auth = AuthService.shared
    @State private var user: User?
    @State private var selectedTab = 0
    @State private var lastTabCount = 4

    var body: some View {
        TabView(selection: $selectedTab) {
            DashboardView(user: user)
                .tabItem { Label("Dashboard", systemImage: "house") }
                .tag(0)

            RunAuditView(onComplete: { selectedTab = 2 })
                .tabItem { Label("New Audit", systemImage: "doc.badge.plus") }
                .tag(1)

            HistoryListView()
                .tabItem { Label("History", systemImage: "clock.arrow.circlepath") }
                .tag(2)

            if user?.is_admin == true {
                AdminView()
                    .tabItem { Label("Admin", systemImage: "shield.lefthalf.filled") }
                    .tag(3)

                ProfileView(user: user, onLogout: { auth.logout() })
                    .tabItem { Label("Profile", systemImage: "person.circle") }
                    .tag(4)
            } else {
                ProfileView(user: user, onLogout: { auth.logout() })
                    .tabItem { Label("Profile", systemImage: "person.circle") }
                    .tag(3)
            }
        }
        .tint(Theme.textPrimary)
        .task(id: auth.token) { loadUser() }
        .onChange(of: user?.is_admin == true ? 5 : 4) { _, newCount in
            // If tab count shrinks (admin toggled off), clamp selected tab.
            if newCount < lastTabCount, selectedTab >= newCount { selectedTab = 0 }
            lastTabCount = newCount
        }
    }

    private func loadUser() {
        Task {
            do {
                user = try await APIClient.shared.me()
            } catch {
                user = nil
            }
        }
    }
}

#Preview {
    MainView()
}
