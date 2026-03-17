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
        let eligible = result.deficiency?.eligible ?? (result.credit_completed >= result.required_credits)
        let probation = result.deficiency?.probation ?? false

        let statusText = eligible ? "Eligible" : "Not Eligible"
        let statusSub: String = {
            if eligible { return "for graduation" }
            if let s = result.deficiency?.credit_shortfall, s > 0 {
                return "\(String(format: "%.1f", s)) credit(s) below required \(String(format: "%.0f", result.required_credits))"
            }
            return "requirements not met"
        }()

        let counted = (result.per_course_detail ?? []).filter { $0.counted }
        let notCounted = (result.per_course_detail ?? []).filter { !$0.counted }

        return VStack(alignment: .leading, spacing: 16) {
            // 1) Eligibility band (web-like)
            VStack(alignment: .leading, spacing: 8) {
                Rectangle().fill(Theme.line).frame(height: 1)
                HStack(alignment: .top) {
                    VStack(alignment: .leading, spacing: 6) {
                        Text(statusText)
                            .font(.system(size: 44, weight: .regular, design: .serif))
                            .italic()
                            .foregroundStyle(eligible ? Theme.success : (probation ? Theme.danger : Theme.warning))
                            .lineLimit(1)
                            .minimumScaleFactor(0.7)
                        Text(statusSub)
                            .font(.system(size: 12, weight: .light))
                            .foregroundStyle(Theme.textMuted)
                    }
                    Spacer()
                    VStack(alignment: .trailing, spacing: 6) {
                        Text("CGPA")
                            .overlineLabel()
                        Text(String(format: "%.2f", result.cgpa))
                            .font(.system(size: 30, weight: .regular, design: .serif))
                            .foregroundStyle(Theme.textPrimary)
                        Text("\(Int(result.credit_completed)) / \(Int(result.required_credits)) credits")
                            .font(.system(size: 11, weight: .light))
                            .foregroundStyle(Theme.textMuted)
                    }
                }
                Rectangle().fill(Theme.line).frame(height: 1)
            }
            .padding(.vertical, 8)

            // 2) Summary card (web-like)
            SectionCard(title: "Summary") {
                HStack(alignment: .top, spacing: 24) {
                    StatBlock(label: "Program", value: result.program)
                    StatBlock(label: "CGPA", value: String(format: "%.2f", result.cgpa), sub: result.academic_standing)
                    StatBlock(label: "Credits Completed", value: "\(Int(result.credit_completed)) / \(Int(result.required_credits))")
                }
            }

            if let def = result.deficiency {
                SectionCard(title: "Deficiency") {
                    DeficiencyBody(deficiency: def)
                }
            }

            if let waived = result.waived_courses, !waived.isEmpty {
                SectionCard(title: "Waived courses") {
                    Text(waived.sorted().joined(separator: ", "))
                        .font(.system(size: 12, weight: .light))
                        .foregroundStyle(Theme.textMuted)
                        .fixedSize(horizontal: false, vertical: true)
                }
            }

            if let notes = result.waiver_notes, !notes.isEmpty {
                SectionCard(title: "Waiver notes") {
                    VStack(alignment: .leading, spacing: 8) {
                        ForEach(Array(notes.enumerated()), id: \.offset) { _, n in
                            Text("• \(n)")
                                .font(.system(size: 12, weight: .light))
                                .foregroundStyle(Theme.textMuted)
                                .fixedSize(horizontal: false, vertical: true)
                        }
                    }
                }
            }

            if let majors = result.major_electives, !majors.isEmpty {
                SectionCard(title: "Major electives") {
                    Text(majors.sorted().joined(separator: ", "))
                        .font(.system(size: 12, weight: .light))
                        .foregroundStyle(Theme.textMuted)
                        .fixedSize(horizontal: false, vertical: true)
                }
            }

            if let open = result.open_elective, !open.isEmpty {
                SectionCard(title: "Open elective") {
                    Text(open)
                        .font(.system(size: 12, weight: .light))
                        .foregroundStyle(Theme.textMuted)
                }
            }

            if let free = result.free_electives, !free.isEmpty {
                SectionCard(title: "Free electives") {
                    Text(free.sorted().joined(separator: ", "))
                        .font(.system(size: 12, weight: .light))
                        .foregroundStyle(Theme.textMuted)
                        .fixedSize(horizontal: false, vertical: true)
                }
            }

            if let prereq = result.prereq_failures, !prereq.isEmpty {
                SectionCard(title: "Prerequisite failures") {
                    VStack(alignment: .leading, spacing: 8) {
                        ForEach(prereq.keys.sorted(), id: \.self) { k in
                            Text("\(k): \(prereq[k] ?? "")")
                                .font(.system(size: 12, weight: .light))
                                .foregroundStyle(Theme.textMuted)
                                .fixedSize(horizontal: false, vertical: true)
                        }
                    }
                }
            }

            if let minors = result.minor_programs, !minors.isEmpty {
                SectionCard(title: "Minor programs") {
                    VStack(alignment: .leading, spacing: 10) {
                        ForEach(minors, id: \.name) { m in
                            HStack {
                                Text(m.name)
                                    .font(.system(size: 14, weight: .light))
                                    .foregroundStyle(Theme.textPrimary)
                                Spacer()
                                Chip(text: m.complete ? "COMPLETE" : "IN PROGRESS", primary: m.complete)
                            }
                            Text(m.progress)
                                .font(.system(size: 12, weight: .light))
                                .foregroundStyle(Theme.textMuted)
                        }
                    }
                }
            }

            if !counted.isEmpty {
                SectionCard(title: "Counted courses") {
                    CourseTable(rows: counted)
                        .frame(maxHeight: 380)
                }
            }

            if !notCounted.isEmpty {
                SectionCard(title: "Not counted courses") {
                    CourseTable(rows: notCounted)
                        .frame(maxHeight: 380)
                }
            }
        }
    }
}

private struct StatBlock: View {
    let label: String
    let value: String
    var sub: String? = nil
    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(label)
                .overlineLabel()
            Text(value)
                .font(.system(size: 18, weight: .regular, design: .serif))
                .foregroundStyle(Theme.textPrimary)
            if let sub, !sub.isEmpty {
                Text(sub)
                    .font(.system(size: 11, weight: .light))
                    .foregroundStyle(Theme.textMuted)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }
}

private struct SectionCard<Content: View>: View {
    let title: String
    let content: Content
    init(title: String, @ViewBuilder content: () -> Content) {
        self.title = title
        self.content = content()
    }
    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(title.uppercased())
                .overlineLabel()
            Rectangle().fill(Theme.line).frame(height: 1)
            content
        }
        .padding(16)
        .background(Theme.surface)
        .overlay(Rectangle().stroke(Theme.line, lineWidth: 1))
    }
}

private struct DeficiencyBody: View {
    let deficiency: Deficiency
    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
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
                        .fixedSize(horizontal: false, vertical: true)
                }
            }
        }
    }
}

private struct CourseTable: View {
    let rows: [CourseDetail]
    var body: some View {
        ScrollView(.vertical) {
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
