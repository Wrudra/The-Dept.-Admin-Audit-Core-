//
//  HistoryListView.swift
//  ios-app
//
//  Audit History: list past runs, load more, tap to detail (matches web HistoryPage).
//

import SwiftUI

struct HistoryListView: View {
    @State private var runs: [HistoryRun] = []
    @State private var loading = true
    @State private var loadingMore = false
    @State private var offset = 0
    @State private var hasMore = false
    @State private var loadError: String?
    private let limit = 20

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 0) {
                    Text("AUDIT HISTORY")
                        .overlineLabel()
                    VStack(alignment: .leading, spacing: 0) {
                        Text("Your past")
                            .font(.system(size: 22, weight: .regular, design: .serif))
                            .foregroundStyle(Theme.textPrimary)
                        Text("runs.")
                            .font(.system(size: 22, weight: .regular, design: .serif))
                            .italic()
                            .foregroundStyle(Theme.textPrimary)
                    }
                    .padding(.bottom, 20)

                    Rectangle().fill(Theme.line).frame(height: 1)

                    if loading {
                        ProgressView().frame(maxWidth: .infinity).padding(.vertical, 32)
                    } else if let err = loadError {
                        VStack(alignment: .leading, spacing: 10) {
                            Text("Couldn’t load history.")
                                .font(.system(size: 14, weight: .light))
                                .foregroundStyle(Theme.textPrimary)
                            Text(err)
                                .font(.system(size: 12, weight: .light))
                                .foregroundStyle(Theme.textMuted)
                                .lineLimit(3)
                            Button {
                                loadFirst()
                            } label: {
                                Text("Try again")
                                    .font(.system(size: 14, weight: .light))
                                    .foregroundStyle(Theme.textPrimary)
                            }
                            .buttonStyle(.plain)
                        }
                        .padding(.vertical, 24)
                    } else if runs.isEmpty {
                        VStack(alignment: .leading, spacing: 10) {
                            Text("No past audits yet.")
                                .font(.system(size: 14, weight: .light))
                                .foregroundStyle(Theme.textPrimary)
                            Text("Run your first audit from the New Audit tab.")
                                .font(.system(size: 12, weight: .light))
                                .foregroundStyle(Theme.textMuted)
                        }
                        .padding(.vertical, 24)
                    } else {
                        LazyVStack(spacing: 12) {
                            ForEach(runs, id: \.run_id) { r in
                                NavigationLink {
                                    AuditResultView(runId: r.run_id)
                                } label: {
                                    HistoryListRow(run: r)
                                }
                                .buttonStyle(.plain)
                            }
                        }
                        .padding(.top, 14)
                        if hasMore {
                            Button {
                                loadMore()
                            } label: {
                                Text(loadingMore ? "Loading…" : "Load more")
                                    .font(.system(size: 14, weight: .light))
                                    .foregroundStyle(Theme.textPrimary)
                            }
                            .disabled(loadingMore)
                            .frame(maxWidth: .infinity)
                            .padding(.vertical, 20)
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
            .onAppear { loadFirst() }
            .refreshable { loadFirst() }
        }
    }

    private func loadFirst() {
        loading = true
        loadError = nil
        Task {
            do {
                let resp = try await APIClient.shared.historyList(limit: limit + 1, offset: 0)
                if resp.runs.count > limit {
                    runs = Array(resp.runs.prefix(limit))
                    hasMore = true
                    offset = limit
                } else {
                    runs = resp.runs
                    hasMore = false
                }
            } catch {
                runs = []
                loadError = error.localizedDescription
            }
            loading = false
        }
    }

    private func loadMore() {
        loadingMore = true
        Task {
            do {
                let resp = try await APIClient.shared.historyList(limit: limit + 1, offset: offset)
                if resp.runs.count > limit {
                    runs += Array(resp.runs.prefix(limit))
                    offset += limit
                    hasMore = true
                } else {
                    runs += resp.runs
                    hasMore = false
                }
            } catch { }
            loadingMore = false
        }
    }
}

private struct HistoryListRow: View {
    let run: HistoryRun
    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack(alignment: .firstTextBaseline, spacing: 8) {
                Chip(text: run.program, primary: true)
                Chip(text: (run.source ?? "ios").uppercased(), primary: false)
                Spacer()
                Chip(text: statusLabel(run.status), primary: run.status == "complete")
                Image(systemName: "chevron.right")
                    .font(.system(size: 12, weight: .light))
                    .foregroundStyle(Theme.textMuted)
            }

            Text(run.transcript_filename ?? "uploaded transcript")
                .font(.system(size: 14, weight: .light))
                .foregroundStyle(Theme.textPrimary)
                .lineLimit(1)
                .truncationMode(.tail)

            HStack(spacing: 10) {
                Text(formatDateTime(run.created_at))
                    .font(.system(size: 11, weight: .light))
                    .foregroundStyle(Theme.textMuted)
                if let cgpa = run.cgpa {
                    Text(String(format: "CGPA %.2f", cgpa))
                        .font(.system(size: 11, weight: .light))
                        .foregroundStyle(Theme.textMuted)
                }
                Spacer()
            }
        }
        .padding(14)
        .background(Theme.surface)
        .overlay(
            RoundedRectangle(cornerRadius: 14, style: .continuous)
                .stroke(Theme.line, lineWidth: 1)
        )
    }

    private func formatDateTime(_ iso: String) -> String {
        // ISO8601 from backend; display yyyy-mm-dd hh:mm:ss when possible.
        let s = iso.replacingOccurrences(of: "T", with: " ")
        if s.count >= 19 { return String(s.prefix(19)) }
        if s.count >= 10 { return String(s.prefix(10)) }
        return iso
    }

    private func statusLabel(_ status: String) -> String {
        let s = status.lowercased()
        if s == "complete" { return "DONE" }
        if s == "running" { return "RUNNING" }
        if s == "failed" { return "FAILED" }
        return s.uppercased()
    }
}

#Preview {
    HistoryListView()
}
