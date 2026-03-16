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
                                HistoryRowView(run: r)
                            }
                            .buttonStyle(.plain)
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
        }
    }

    private func loadRuns() {
        Task {
            do {
                let resp = try await APIClient.shared.historyList(limit: 5, offset: 0)
                runs = resp.runs
            } catch {
                runs = []
            }
            loading = false
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

private struct HistoryRowView: View {
    let run: HistoryRun
    var body: some View {
        HStack(alignment: .center) {
            HStack(spacing: 6) {
                Chip(text: run.program, primary: true)
                Chip(text: run.source ?? "ios", primary: false)
            }
            Text(run.transcript_filename ?? "uploaded transcript")
                .font(.system(size: 14, weight: .light))
                .foregroundStyle(Theme.textMuted)
                .lineLimit(1)
                .truncationMode(.tail)
            Spacer()
            if let cgpa = run.cgpa {
                Text(String(format: "CGPA %.2f", cgpa))
                    .font(.system(size: 11, weight: .light))
                    .foregroundStyle(Theme.textMuted)
            }
            Text(formatDate(run.created_at))
                .font(.system(size: 11, weight: .light))
                .foregroundStyle(Theme.textMuted)
            Image(systemName: "arrow.right")
                .font(.system(size: 12))
                .foregroundStyle(Theme.textMuted)
        }
        .padding(.vertical, 14)
        Rectangle().fill(Theme.line).frame(height: 1)
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
