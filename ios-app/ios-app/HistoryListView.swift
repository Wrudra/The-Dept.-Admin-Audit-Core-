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
                    } else if runs.isEmpty {
                        Text("No past audits.")
                            .font(.system(size: 14, weight: .light))
                            .foregroundStyle(Theme.textMuted)
                            .padding(.vertical, 24)
                    } else {
                        ForEach(runs, id: \.run_id) { r in
                            NavigationLink {
                                AuditResultView(runId: r.run_id)
                            } label: {
                                HistoryListRow(run: r)
                            }
                            .buttonStyle(.plain)
                        }
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
        }
    }

    private func loadFirst() {
        loading = true
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
        HStack(alignment: .center) {
            HStack(spacing: 6) {
                Chip(text: run.program, primary: true)
                Chip(text: run.source ?? "ios", primary: false)
            }
            VStack(alignment: .leading, spacing: 2) {
                Text(run.transcript_filename ?? "uploaded transcript")
                    .font(.system(size: 14, weight: .light))
                    .foregroundStyle(Theme.textPrimary)
                    .lineLimit(1)
                Text(run.created_at.replacingOccurrences(of: "T", with: " ").prefix(19).description)
                    .font(.system(size: 11, weight: .light))
                    .foregroundStyle(Theme.textMuted)
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            if let cgpa = run.cgpa {
                Text(String(format: "%.2f", cgpa))
                    .font(.system(size: 11, weight: .light))
                    .foregroundStyle(Theme.textMuted)
            }
            Chip(text: run.status, primary: run.status == "complete")
            Image(systemName: "arrow.right")
                .font(.system(size: 12))
                .foregroundStyle(Theme.textMuted)
        }
        .padding(.vertical, 14)
        Rectangle().fill(Theme.line).frame(height: 1)
    }
}

#Preview {
    HistoryListView()
}
