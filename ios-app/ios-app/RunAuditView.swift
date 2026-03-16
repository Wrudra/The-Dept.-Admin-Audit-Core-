//
//  RunAuditView.swift
//  ios-app
//
//  New audit: Upload → Configure choices → Report (matches web AuditPage stepper).
//

import SwiftUI
import UniformTypeIdentifiers

struct RunAuditView: View {
    var onComplete: () -> Void
    @State private var step = 0
    @State private var selectedFileURL: URL?
    @State private var program: String = "CSE"
    @State private var choices: [AuditChoice] = []
    @State private var answers: [String: Any] = [:]
    @State private var result: AuditResult?
    @State private var runId: String?
    @State private var busy = false
    @State private var errorMessage: String?
    @State private var showFileImporter = false
    @State private var showError = false

    private let allowedTypes: [UTType] = [.commaSeparatedText, .pdf, .jpeg, .png, .tiff, .bmp]

    var body: some View {
        NavigationStack {
            VStack(alignment: .leading, spacing: 20) {
                StepperView(step: step, titles: ["Upload Transcript", "Configure Choices", "Audit Report"])
                if step == 0 {
                    stepUpload
                } else if step == 1 {
                    stepConfigure
                } else {
                    stepReport
                }
            }
            .padding(20)
            .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
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
            .fileImporter(isPresented: $showFileImporter, allowedContentTypes: allowedTypes, allowsMultipleSelection: false) { result in
                switch result {
                case .success(let urls):
                    if let url = urls.first {
                        _ = url.startAccessingSecurityScopedResource()
                        selectedFileURL = url
                    }
                case .failure: break
                }
            }
            .alert("Error", isPresented: $showError) {
                Button("OK") { errorMessage = nil }
            } message: {
                if let m = errorMessage { Text(m) }
            }
        }
    }

    private var stepUpload: some View {
        VStack(alignment: .leading, spacing: 16) {
            Text("Select transcript (CSV, PDF, or image)")
                .font(.system(size: 14, weight: .light))
                .foregroundStyle(Theme.textMuted)
            Button {
                showFileImporter = true
            } label: {
                HStack {
                    Image(systemName: "doc.badge.plus")
                    Text(selectedFileURL?.lastPathComponent ?? "Choose file…")
                        .lineLimit(1)
                }
                .font(.system(size: 14, weight: .light))
                .foregroundStyle(Theme.textPrimary)
                .frame(maxWidth: .infinity)
                .padding(.vertical, 16)
                .background(Theme.surface)
                .overlay(Rectangle().stroke(Theme.line, lineWidth: 1))
            }
            .buttonStyle(.plain)
            Picker("Program", selection: $program) {
                Text("CSE").tag("CSE")
                Text("MIC").tag("MIC")
            }
            .pickerStyle(.segmented)
            if selectedFileURL != nil {
                Button {
                    analyze()
                } label: {
                    Text("Analyze")
                        .font(.system(size: 14, weight: .light))
                        .tracking(0.08)
                        .frame(maxWidth: .infinity)
                        .padding(.vertical, 12)
                        .background(Theme.textPrimary)
                        .foregroundStyle(Theme.background)
                }
                .buttonStyle(.plain)
                .disabled(busy)
            }
            if busy { ProgressView().frame(maxWidth: .infinity) }
        }
    }

    private var stepConfigure: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Answer each question (waivers, electives, etc.)")
                .font(.system(size: 14, weight: .light))
                .foregroundStyle(Theme.textMuted)
            ScrollView {
                VStack(alignment: .leading, spacing: 16) {
                    ForEach(Array(choices.enumerated()), id: \.element.key) { _, c in
                        if c.type == "yes_no" {
                            Toggle(isOn: bindingYesNo(c.key, default: c.selectedBool ?? false)) {
                                Text(c.prompt)
                                    .font(.system(size: 14, weight: .light))
                                    .foregroundStyle(Theme.textMuted)
                            }
                            .tint(Theme.textMuted)
                        } else {
                            Picker(selection: bindingPick(c.key, options: c.options ?? [], default: c.selected ?? (c.options?.first ?? ""))) {
                                ForEach(c.options ?? [], id: \.self) { opt in
                                    Text(opt).tag(opt)
                                }
                            } label: {
                                Text(c.prompt)
                                    .font(.system(size: 14, weight: .light))
                                    .foregroundStyle(Theme.textMuted)
                            }
                            .pickerStyle(.menu)
                        }
                    }
                }
            }
            Button {
                runAudit()
            } label: {
                Text("Run audit")
                    .font(.system(size: 14, weight: .light))
                    .tracking(0.08)
                    .frame(maxWidth: .infinity)
                    .padding(.vertical, 12)
                    .background(Theme.textPrimary)
                    .foregroundStyle(Theme.background)
            }
            .buttonStyle(.plain)
            .disabled(busy)
            if busy { ProgressView().frame(maxWidth: .infinity) }
        }
    }

    private var stepReport: some View {
        VStack(alignment: .leading, spacing: 16) {
            if let r = result {
                AuditReportView(result: r)
            }
            Button {
                step = 0
                selectedFileURL = nil
                choices = []
                answers = [:]
                result = nil
                runId = nil
                onComplete()
            } label: {
                Text("Start another audit")
                    .font(.system(size: 14, weight: .light))
                    .foregroundStyle(Theme.textPrimary)
            }
            .buttonStyle(.plain)
        }
    }

    private func bindingYesNo(_ key: String, default def: Bool) -> Binding<Bool> {
        Binding(
            get: { (answers[key] as? Bool) ?? def },
            set: { answers[key] = $0 }
        )
    }

    private func bindingPick(_ key: String, options: [String], default def: String) -> Binding<String> {
        Binding(
            get: { (answers[key] as? String) ?? def },
            set: { answers[key] = $0 }
        )
    }

    private func analyze() {
        guard let url = selectedFileURL else { return }
        busy = true
        errorMessage = nil
        Task {
            do {
                let copyURL = try copyToTemp(url)
                let resp = try await APIClient.shared.auditRun(fileURL: copyURL, program: program, answers: [:], save: false, source: "ios")
                await MainActor.run {
                    choices = resp.choices
                    for c in resp.choices {
                        if c.type == "yes_no" {
                            answers[c.key] = c.selectedBool ?? false
                        } else {
                            answers[c.key] = c.selected ?? (c.options?.first ?? "")
                        }
                    }
                    step = 1
                }
            } catch {
                await MainActor.run {
                    errorMessage = error.localizedDescription
                    showError = true
                }
            }
            await MainActor.run { busy = false }
        }
    }

    private func runAudit() {
        guard let url = selectedFileURL else { return }
        busy = true
        errorMessage = nil
        Task {
            do {
                let copyURL = try copyToTemp(url)
                let resp = try await APIClient.shared.auditRun(fileURL: copyURL, program: program, answers: answers, save: true, source: "ios")
                await MainActor.run {
                    result = resp.result
                    runId = resp.run_id
                    step = 2
                }
            } catch {
                await MainActor.run {
                    errorMessage = error.localizedDescription
                    showError = true
                }
            }
            await MainActor.run { busy = false }
        }
    }

    private func copyToTemp(_ url: URL) throws -> URL {
        let temp = FileManager.default.temporaryDirectory.appendingPathComponent(url.lastPathComponent)
        if FileManager.default.fileExists(atPath: temp.path) { try FileManager.default.removeItem(at: temp) }
        try FileManager.default.copyItem(at: url, to: temp)
        return temp
    }
}

private struct StepperView: View {
    let step: Int
    let titles: [String]
    var body: some View {
        HStack(spacing: 8) {
            ForEach(Array(titles.enumerated()), id: \.offset) { i, t in
                if i > 0 {
                    Rectangle().fill(Theme.line).frame(height: 1).frame(maxWidth: .infinity)
                }
                VStack(spacing: 4) {
                    Text("\(i + 1)")
                        .font(.system(size: 12, weight: .light))
                        .foregroundStyle(step >= i ? Theme.textPrimary : Theme.textMuted)
                        .frame(width: 24, height: 24)
                        .background(step >= i ? Theme.surface2 : Theme.surface)
                    Text(t)
                        .font(.system(size: 11, weight: .light))
                        .tracking(0.12)
                        .textCase(.uppercase)
                        .foregroundStyle(step >= i ? Theme.textPrimary : Theme.textMuted)
                        .lineLimit(1)
                        .minimumScaleFactor(0.8)
                }
                .frame(maxWidth: .infinity)
                if i < titles.count - 1 {
                    Rectangle().fill(Theme.line).frame(height: 1).frame(maxWidth: .infinity)
                }
            }
        }
    }
}

#Preview {
    RunAuditView(onComplete: {})
}
