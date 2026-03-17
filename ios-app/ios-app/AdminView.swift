//
//  AdminView.swift
//  ios-app
//
//  Admin-only overview (mirrors web AdminPage essentials).
//

import SwiftUI

struct AdminView: View {
    @State private var stats: AdminStats?
    @State private var loading = true
    @State private var error: String?

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 16) {
                    Text("ADMIN")
                        .overlineLabel()

                    if loading {
                        ProgressView().frame(maxWidth: .infinity).padding(.vertical, 24)
                    } else if let err = error {
                        VStack(alignment: .leading, spacing: 10) {
                            Text("Couldn’t load admin stats.")
                                .font(.system(size: 14, weight: .light))
                                .foregroundStyle(Theme.textPrimary)
                            Text(err)
                                .font(.system(size: 12, weight: .light))
                                .foregroundStyle(Theme.textMuted)
                                .lineLimit(4)
                            Button("Try again") { load() }
                                .font(.system(size: 14, weight: .light))
                                .foregroundStyle(Theme.textPrimary)
                                .buttonStyle(.plain)
                        }
                        .padding(.vertical, 16)
                    } else if let s = stats {
                        StatGrid(stats: s)
                        Text("RECENT RUNS")
                            .overlineLabel()
                            .padding(.top, 10)
                        Rectangle().fill(Theme.line).frame(height: 1).padding(.top, 4)

                        ForEach(s.recent_runs, id: \.run_id) { r in
                            VStack(alignment: .leading, spacing: 6) {
                                HStack {
                                    Chip(text: r.program, primary: true)
                                    Spacer()
                                    Text(r.created_at.replacingOccurrences(of: "T", with: " ").prefix(19))
                                        .font(.system(size: 11, weight: .light))
                                        .foregroundStyle(Theme.textMuted)
                                }
                                Text(r.transcript_filename ?? "uploaded transcript")
                                    .font(.system(size: 14, weight: .light))
                                    .foregroundStyle(Theme.textPrimary)
                                    .lineLimit(1)
                                Text("\(r.user_name) · \(r.user_email)")
                                    .font(.system(size: 12, weight: .light))
                                    .foregroundStyle(Theme.textMuted)
                                    .lineLimit(1)
                            }
                            .padding(.vertical, 12)
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
            .onAppear { load() }
            .refreshable { load() }
        }
    }

    private func load() {
        loading = true
        error = nil
        Task {
            do {
                stats = try await APIClient.shared.adminStats()
            } catch {
                stats = nil
                self.error = error.localizedDescription
            }
            loading = false
        }
    }
}

private struct StatGrid: View {
    let stats: AdminStats
    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack(spacing: 16) {
                StatTile(label: "Total runs", value: "\(stats.total_runs)")
                StatTile(label: "Total users", value: "\(stats.total_users)")
            }
            HStack(spacing: 16) {
                StatTile(label: "Avg CGPA", value: stats.avg_cgpa.map { String(format: "%.2f", $0) } ?? "—")
                StatTile(label: "Avg credits", value: stats.avg_credits.map { String(format: "%.1f", $0) } ?? "—")
            }
            HStack(spacing: 8) {
                ForEach(stats.runs_by_program.keys.sorted(), id: \.self) { k in
                    let v = stats.runs_by_program[k] ?? 0
                    Chip(text: "\(k) \(v)", primary: true)
                }
            }
        }
    }
}

private struct StatTile: View {
    let label: String
    let value: String
    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(label.uppercased())
                .font(.system(size: 11, weight: .light))
                .tracking(0.12)
                .foregroundStyle(Theme.textMuted)
            Text(value)
                .font(.system(size: 22, weight: .regular, design: .serif))
                .foregroundStyle(Theme.textPrimary)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(14)
        .background(Theme.surface)
        .overlay(Rectangle().stroke(Theme.line, lineWidth: 1))
    }
}

#Preview {
    AdminView()
}

