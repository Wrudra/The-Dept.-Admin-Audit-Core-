# NSU Audit iOS App

Native iOS app for the NSU Transcript Audit system. Uses the same backend and API as the web and CLI.

## Requirements

- Xcode 26+
- iOS 17+
- Backend running (e.g. `http://localhost:8000`)

## Run in Xcode

1. Open `ios-app.xcodeproj` in Xcode.
2. Select a simulator or device and run (⌘R).

## Connecting to the backend

- **Simulator / local dev**: The app defaults to `http://localhost:8000` if no config is set. You must add an **App Transport Security** exception in Xcode or the app cannot reach the backend:
  - Select the **ios-app** target → **Info** tab → **App Transport Security** → add **Exception Domains** → **localhost** with **Allows Insecure HTTP Loads** = YES.
- **Production**: Set the backend URL via UserDefaults (key `NSUAuditAPIBaseURL`) or add it to the target’s Info. Use an HTTPS URL.

## Sign-in

The app uses the **device flow**: tap “Continue with Google”, then enter the code in the browser and sign in with your @northsouth.edu account. After that, the JWT is stored in the Keychain.

## Features

- **Dashboard**: Welcome, quick actions, recent runs.
- **New Audit**: Upload transcript (CSV/PDF/image), choose program (CSE/MIC), configure choices, run audit, view report.
- **History**: List past runs, load more, tap for full report.
- **Profile**: View account, logout.

Audit runs from the app are stored with `source=ios` in the backend.
