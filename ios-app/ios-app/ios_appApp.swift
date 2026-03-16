//
//  ios_appApp.swift
//  ios-app
//

import SwiftUI

@main
struct ios_appApp: App {
    @StateObject private var auth = AuthService.shared

    init() {
        APIClient.shared.onUnauthorized = {
            Task { @MainActor in
                AuthService.shared.logout()
            }
        }
    }

    var body: some Scene {
        WindowGroup {
            Group {
                if auth.token != nil {
                    MainView()
                } else {
                    LoginView()
                }
            }
            .onAppear {
                auth.refreshFromKeychain()
            }
        }
    }
}
