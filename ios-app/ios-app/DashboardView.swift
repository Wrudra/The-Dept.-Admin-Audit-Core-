//
//  DashboardView.swift
//  ios-app
//
//  Overview: welcome, quick actions, recent runs (matches web DashboardPage).
//

import SwiftUI

struct DashboardView: View {
    let user: User?
    @State private var runs: [HistoryRun] = []
    @State private var loading = true
    @State private var loadError: String?

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 0) {
                    Text("OVERVIEW")
                        .overlineLabel()
                    VStack(alignment: .leading, spacing: 0) {
                        Text("Welcome back,")
                            .font(.system(size: 22, weight: .regular, design: .serif))
                            .foregroundStyle(Theme.textPrimary)
                        Text("\(user?.display_name ?? "—").")
                            .font(.system(size: 22, weight: .regular, design: .serif))
                            .italic()
                            .foregroundStyle(Theme.textPrimary)
                    }
                    .padding(.bottom, 20)

                    Rectangle().fill(Theme.line).frame(height: 1)

                    QuickActionRow(title: "New Audit", subtitle: "Upload a transcript and run your audit", destination: .audit)
                    QuickActionRow(title: "History", subtitle: "Browse past audit runs", destination: .history)

                    Text("RECENT RUNS")
                        .overlineLabel()
                        .padding(.top, 28)
                    Rectangle().fill(Theme.line).frame(height: 1).padding(.top, 4)

                    if loading {
                        ProgressView().padding(.vertical, 24)
                    } else if let err = loadError {
                        VStack(alignment: .leading, spacing: 10) {
                            Text("Couldn’t load recent runs.")
                                .font(.system(size: 14, weight: .light))
                                .foregroundStyle(Theme.textPrimary)
                            Text(err)
                                .font(.system(size: 12, weight: .light))
                                .foregroundStyle(Theme.textMuted)
                                .lineLimit(3)
                            Button {
                                loadRuns()
                            } label: {
                                Text("Try again")
                                    .font(.system(size: 14, weight: .light))
                                    .foregroundStyle(Theme.textPrimary)
                            }
                            .buttonStyle(.plain)
                        }
                        .padding(.vertical, 20)
                    } else if runs.isEmpty {
                        VStack(alignment: .leading, spacing: 8) {
                            Text("No audit runs yet.")
                                .font(.system(size: 14, weight: .light))
                                .foregroundStyle(Theme.textMuted)
                            NavigationLink("Upload your first transcript →") {
                                RunAuditView(onComplete: {})
                            }
                            .font(.system(size: 13))
                            .foregroundStyle(Theme.textMuted)
                        }
                        .padding(.vertical, 20)
                    } else {
                        ForEach(runs, id: \.run_id) { r in
                            NavigationLink {
                                AuditResultView(runId: r.run_id)
                            } label: {
                                RecentRunRow(run: r)
                            }
                            .buttonStyle(.plain)
                            Rectangle().fill(Theme.line).frame(height: 1)
                        }
                    }
                }
                .padding(.horizontal, 20)
                .padding(.vertical, 16)
            }
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
            .onAppear { loadRuns() }
            .refreshable { loadRuns() }
        }
    }

    private func loadRuns() {
        Task {
            await MainActor.run {
                loading = true
                loadError = nil
            }
            do {
                let resp = try await APIClient.shared.historyList(limit: 5, offset: 0)
                await MainActor.run {
                    runs = resp.runs
                }
            } catch {
                await MainActor.run {
                    runs = []
                    loadError = error.localizedDescription
                }
            }
            await MainActor.run { loading = false }
        }
    }
}

private enum QuickActionDest {
    case audit, history
}

private struct QuickActionRow: View {
    let title: String
    let subtitle: String
    let destination: QuickActionDest
    var body: some View {
        NavigationLink {
            Group {
                switch destination {
                case .audit: RunAuditView(onComplete: {})
                case .history: HistoryListView()
                }
            }
        } label: {
            HStack {
                VStack(alignment: .leading, spacing: 2) {
                    Text(title)
                        .font(.system(size: 16, weight: .light))
                        .foregroundStyle(Theme.textPrimary)
                    Text(subtitle)
                        .font(.system(size: 12, weight: .light))
                        .foregroundStyle(Theme.textMuted)
                }
                Spacer()
                Image(systemName: "arrow.right")
                    .font(.system(size: 14))
                    .foregroundStyle(Theme.textMuted)
            }
            .padding(.vertical, 16)
        }
        .buttonStyle(.plain)
        Rectangle().fill(Theme.line).frame(height: 1)
    }
}

/// Recent run row — same visual rhythm as QuickActionRow (title, subtitle, trailing arrow).
private struct RecentRunRow: View {
    let run: HistoryRun

    private var title: String {
        if let f = run.transcript_filename, !f.isEmpty { return f }
        let id = run.run_id
        if id.count > 12 { return "Audit \(id.prefix(8))…" }
        return "Audit run"
    }

    private var subtitle: String {
        var parts: [String] = [
            run.program,
            (run.source ?? "ios").uppercased(),
        ]
        if let c = run.cgpa {
            parts.append(String(format: "CGPA %.2f", c))
        }
        parts.append(formatDate(run.created_at))
        if run.status.lowercased() != "completed" {
            parts.append(run.status.uppercased())
        }
        return parts.joined(separator: " · ")
    }

    var body: some View {
        HStack(alignment: .center, spacing: 16) {
            VStack(alignment: .leading, spacing: 4) {
                Text(title)
                    .font(.system(size: 16, weight: .light))
                    .foregroundStyle(Theme.textPrimary)
                    .lineLimit(2)
                    .multilineTextAlignment(.leading)
                Text(subtitle)
                    .font(.system(size: 12, weight: .light))
                    .foregroundStyle(Theme.textMuted)
                    .lineLimit(2)
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            Image(systemName: "arrow.right")
                .font(.system(size: 14))
                .foregroundStyle(Theme.textMuted)
        }
        .padding(.vertical, 16)
        .frame(maxWidth: .infinity, alignment: .leading)
        .contentShape(Rectangle())
    }

    private func formatDate(_ iso: String) -> String {
        if iso.count >= 10 { return String(iso.prefix(10)) }
        return iso
    }
}

struct Chip: View {
    let text: String
    var primary = false
    var body: some View {
        Text(text)
            .font(.system(size: 11, weight: .light))
            .tracking(0.08)
            .lineLimit(1)
            .fixedSize(horizontal: true, vertical: false)
            .allowsTightening(true)
            .minimumScaleFactor(0.85)
            .padding(.horizontal, 10)
            .padding(.vertical, 4)
            .background(Theme.surface)
            .overlay(Rectangle().stroke(primary ? Theme.textMuted : Theme.line, lineWidth: 1))
            .foregroundStyle(primary ? Theme.textPrimary : Theme.textMuted)
    }
}

#Preview {
    DashboardView(user: nil)
}
