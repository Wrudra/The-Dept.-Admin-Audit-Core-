//
//  AuditResultView.swift
//  ios-app
//
//  Full audit report for a run: stats, deficiency, course tables (matches web AuditReport).
//

import SwiftUI

struct AuditResultView: View {
    let runId: String
    @State private var result: AuditResult?
    @State private var loading = true
    @State private var error: String?
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        Group {
            if loading {
                ProgressView().frame(maxWidth: .infinity, maxHeight: .infinity)
            } else if let err = error {
                VStack(alignment: .leading, spacing: 16) {
                    Button { dismiss() } label: {
                        Label("Back to History", systemImage: "arrow.left")
                            .font(.system(size: 14, weight: .light))
                            .foregroundStyle(Theme.textPrimary)
                    }
                    Text(err)
                        .font(.system(size: 14))
                        .foregroundStyle(Theme.danger)
                }
                .padding(20)
            } else if let r = result {
                ScrollView {
                    VStack(alignment: .leading, spacing: 20) {
                        Button { dismiss() } label: {
                            Label("Back to History", systemImage: "arrow.left")
                                .font(.system(size: 14, weight: .light))
                                .foregroundStyle(Theme.textPrimary)
                        }
                        AuditReportView(result: r)
                    }
                    .padding(20)
                }
            }
        }
        .background(Theme.background)
        .navigationBarTitleDisplayMode(.inline)
        .onAppear { load() }
    }

    private func load() {
        Task {
            do {
                let detail = try await APIClient.shared.historyDetail(runId: runId)
                result = detail.result
            } catch {
                self.error = error.localizedDescription
            }
            loading = false
        }
    }
}

struct AuditReportView: View {
    let result: AuditResult

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            // Summary stats
            HStack(alignment: .top, spacing: 24) {
                StatBlock(label: "CGPA", value: String(format: "%.2f", result.cgpa))
                StatBlock(label: "Credits", value: "\(Int(result.credit_completed))/\(Int(result.required_credits))")
                StatBlock(label: "Standing", value: result.academic_standing ?? "—")
            }
            .padding(.vertical, 12)

            if let def = result.deficiency {
                DeficiencyCard(deficiency: def)
            }

            if let detail = result.per_course_detail, !detail.isEmpty {
                Text("COURSES")
                    .overlineLabel()
                CourseTable(rows: detail)
            }
        }
    }
}

private struct StatBlock: View {
    let label: String
    let value: String
    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(label)
                .overlineLabel()
            Text(value)
                .font(.system(size: 18, weight: .regular, design: .serif))
                .foregroundStyle(Theme.textPrimary)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }
}

private struct DeficiencyCard: View {
    let deficiency: Deficiency
    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("DEFICIENCY")
                .overlineLabel()
            Rectangle().fill(Theme.line).frame(height: 1)
            HStack {
                Text(deficiency.eligible ? "Eligible" : "Not eligible")
                    .font(.system(size: 14, weight: .light))
                    .foregroundStyle(deficiency.eligible ? Theme.success : Theme.danger)
                if deficiency.credit_shortfall > 0 {
                    Text("Shortfall: \(String(format: "%.1f", deficiency.credit_shortfall)) cr")
                        .font(.system(size: 12, weight: .light))
                        .foregroundStyle(Theme.textMuted)
                }
                if deficiency.probation {
                    Text("Probation")
                        .font(.system(size: 12, weight: .light))
                        .foregroundStyle(Theme.warning)
                }
            }
            if !deficiency.missing_mandatory.isEmpty {
                ForEach(Array(deficiency.missing_mandatory.enumerated()), id: \.offset) { _, m in
                    Text("\(m.category): \(m.courses.joined(separator: ", "))")
                        .font(.system(size: 12, weight: .light))
                        .foregroundStyle(Theme.textMuted)
                }
            }
        }
        .padding(16)
        .background(Theme.surface)
        .overlay(Rectangle().stroke(Theme.line, lineWidth: 1))
    }
}

private struct CourseTable: View {
    let rows: [CourseDetail]
    var body: some View {
        VStack(spacing: 0) {
            HStack {
                Text("Course").frame(maxWidth: .infinity, alignment: .leading)
                Text("Credits").frame(width: 50)
                Text("Grade").frame(width: 44)
                Text("Status").frame(maxWidth: .infinity, alignment: .leading)
            }
            .font(.system(size: 11, weight: .light))
            .tracking(0.12)
            .textCase(.uppercase)
            .foregroundStyle(Theme.textMuted)
            .padding(.vertical, 10)
            .padding(.horizontal, 12)
            .background(Theme.background)
            Rectangle().fill(Theme.line).frame(height: 1)
            ForEach(Array(rows.enumerated()), id: \.offset) { _, row in
                HStack(alignment: .center) {
                    Text(row.course).frame(maxWidth: .infinity, alignment: .leading)
                    Text(row.credits.map { String(format: "%.1f", $0) } ?? "—").frame(width: 50)
                    Text(row.grade).frame(width: 44)
                    Text(row.counted ? (row.label ?? "—") : (row.reason ?? "—"))
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .font(.system(size: 12))
                        .foregroundStyle(row.counted ? Theme.textPrimary : Theme.textMuted)
                }
                .font(.system(size: 14, weight: .light))
                .foregroundStyle(Theme.textMuted)
                .padding(.vertical, 10)
                .padding(.horizontal, 12)
                Rectangle().fill(Theme.line).frame(height: 1)
            }
        }
        .background(Theme.surface)
        .overlay(Rectangle().stroke(Theme.line, lineWidth: 1))
    }
}

#Preview {
    NavigationStack {
        AuditResultView(runId: "00000000-0000-0000-0000-000000000000")
    }
}
