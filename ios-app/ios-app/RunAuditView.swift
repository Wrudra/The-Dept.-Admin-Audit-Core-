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
    @State private var selectedTempURL: URL?
    @State private var program: String = "CSE"
    @State private var choices: [AuditChoice] = []
    @State private var answers: [String: Any] = [:]
    @State private var result: AuditResult?
    @State private var runId: String?
    @State private var busy = false
    @State private var rediscovering = false
    @State private var errorMessage: String?
    @State private var showFileImporter = false
    @State private var showError = false
    @State private var currentTask: Task<Void, Never>?
    @State private var rediscoverTask: Task<Void, Never>?

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
                        selectedFileURL = url
                        selectedTempURL = nil
                        stageImportedFile(url)
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
            .disabled(busy)
            Picker("Program", selection: $program) {
                Text("CSE").tag("CSE")
                Text("MIC").tag("MIC")
            }
            .pickerStyle(.segmented)
            if selectedTempURL != nil {
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
        ScrollView {
            VStack(alignment: .leading, spacing: 12) {
                Text("Answer each question (waivers, electives, etc.)")
                    .font(.system(size: 14, weight: .light))
                    .foregroundStyle(Theme.textMuted)
                if rediscovering {
                    HStack(spacing: 10) {
                        ProgressView().scaleEffect(0.9)
                        Text("Updating trail course options…")
                            .font(.system(size: 12, weight: .light))
                            .foregroundStyle(Theme.textMuted)
                    }
                    .padding(.top, 6)
                }

                // 1) Yes/No choices
                let yn = choices.filter { $0.type == "yes_no" }
                if !yn.isEmpty {
                    GroupCard(title: "Required confirmations", subtitle: "Waivers and shared-slot confirmations.") {
                        VStack(alignment: .leading, spacing: 14) {
                            ForEach(yn, id: \.key) { c in
                                Toggle(isOn: bindingYesNo(c.key, default: c.selectedBool ?? false)) {
                                    Text(c.prompt.isEmpty ? (c.label ?? c.key) : c.prompt)
                                        .font(.system(size: 14, weight: .light))
                                        .foregroundStyle(Theme.textPrimary)
                                        .fixedSize(horizontal: false, vertical: true)
                                }
                                .tint(Theme.textMuted)
                            }
                        }
                    }
                }

                // 2) Pick choices grouped (matches web grouping intent)
                let picks = choices.filter { $0.type == "pick" }
                let grouped = Dictionary(grouping: picks, by: { ($0.group ?? "other") })
                let groupOrder = ["ged_core", "mic_core", "trail", "trail_course", "open_elective", "major_elective", "free_elective", "bio_internship", "other"]
                ForEach(groupOrder, id: \.self) { g in
                    if let items = grouped[g], !items.isEmpty {
                        let meta = GroupMeta.forGroup(g)
                        GroupCard(title: meta.title, subtitle: meta.subtitle) {
                            VStack(alignment: .leading, spacing: 14) {
                                if g == "trail_course" {
                                    // Filter sibling selections like web: don't allow duplicates within this group.
                                    let keys = items.map(\.key)
                                    ForEach(items, id: \.key) { c in
                                        PickField(
                                            choice: c,
                                            selected: (answers[c.key] as? String) ?? c.selected ?? "",
                                            availableOptions: filteredOptionsForTrailCourse(choice: c, siblingKeys: keys),
                                            onSelect: { setPick(choice: c, value: $0, triggerRediscoverIfTrail: false) }
                                        )
                                    }
                                } else if g == "trail" {
                                    ForEach(items, id: \.key) { c in
                                        PickField(
                                            choice: c,
                                            selected: (answers[c.key] as? String) ?? c.selected ?? "",
                                            availableOptions: c.options ?? [],
                                            onSelect: { setPick(choice: c, value: $0, triggerRediscoverIfTrail: true) }
                                        )
                                    }
                                } else {
                                    ForEach(items, id: \.key) { c in
                                        PickField(
                                            choice: c,
                                            selected: (answers[c.key] as? String) ?? c.selected ?? "",
                                            availableOptions: c.options ?? [],
                                            onSelect: { setPick(choice: c, value: $0, triggerRediscoverIfTrail: false) }
                                        )
                                    }
                                }
                            }
                        }
                    } else {
                        EmptyView()
                    }
                }

                // Keep content above the fixed bottom CTA.
                Spacer().frame(height: 80)
            }
            .frame(maxWidth: .infinity, alignment: .leading)
        }
        .safeAreaInset(edge: .bottom) {
            VStack(spacing: 10) {
                Button {
                    runAudit()
                } label: {
                    Text(busy ? "Running…" : "Run audit")
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
            .padding(.horizontal, 20)
            .padding(.top, 10)
            .padding(.bottom, 12)
            .background(Theme.background)
            .overlay(Rectangle().fill(Theme.line).frame(height: 1), alignment: .top)
        }
    }

    private var stepReport: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                if let r = result {
                    AuditReportView(result: r)
                }
                Button {
                    reset()
                    onComplete()
                } label: {
                    Text("Start another audit")
                        .font(.system(size: 14, weight: .light))
                        .foregroundStyle(Theme.textPrimary)
                }
                .buttonStyle(.plain)
                .padding(.bottom, 24)
            }
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
        guard let temp = selectedTempURL else { return }
        busy = true
        errorMessage = nil
        currentTask?.cancel()
        currentTask = Task {
            do {
                let resp = try await APIClient.shared.auditRun(fileURL: temp, program: program, answers: [:], save: false, source: "ios")
                await MainActor.run {
                    choices = resp.choices
                    syncAnswersFromChoices(resp.choices, preferExisting: [:])
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
        guard let temp = selectedTempURL else { return }
        busy = true
        errorMessage = nil
        currentTask?.cancel()
        currentTask = Task {
            do {
                let resp = try await APIClient.shared.auditRun(fileURL: temp, program: program, answers: answers, save: true, source: "ios")
                await MainActor.run {
                    result = resp.result
                    runId = resp.run_id
                    choices = resp.choices
                    syncAnswersFromChoices(resp.choices, preferExisting: answers)
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

    private func stageImportedFile(_ url: URL) {
        busy = true
        errorMessage = nil
        currentTask?.cancel()
        currentTask = Task {
            let didStart = url.startAccessingSecurityScopedResource()
            defer {
                if didStart { url.stopAccessingSecurityScopedResource() }
            }
            do {
                let temp = try copyToTempUnique(url)
                await MainActor.run {
                    selectedTempURL = temp
                    busy = false
                }
            } catch {
                await MainActor.run {
                    selectedTempURL = nil
                    busy = false
                    errorMessage = error.localizedDescription
                    showError = true
                }
            }
        }
    }

    private func copyToTempUnique(_ url: URL) throws -> URL {
        let ext = url.pathExtension.isEmpty ? "" : ".\(url.pathExtension)"
        let temp = FileManager.default.temporaryDirectory.appendingPathComponent("nsu-audit-\(UUID().uuidString)\(ext)")
        try FileManager.default.copyItem(at: url, to: temp)
        return temp
    }

    private func reset() {
        currentTask?.cancel()
        currentTask = nil
        rediscoverTask?.cancel()
        rediscoverTask = nil
        rediscovering = false
        step = 0
        selectedFileURL = nil
        selectedTempURL = nil
        choices = []
        answers = [:]
        result = nil
        runId = nil
    }

    private func syncAnswersFromChoices(_ newChoices: [AuditChoice], preferExisting existing: [String: Any]) {
        var next: [String: Any] = [:]
        for c in newChoices {
            if let keep = existing[c.key] {
                next[c.key] = keep
                continue
            }
            if c.type == "yes_no" {
                next[c.key] = c.selectedBool ?? false
            } else {
                next[c.key] = c.selected ?? (c.options?.first ?? "")
            }
        }
        answers = next
    }

    private func setPick(choice: AuditChoice, value: String, triggerRediscoverIfTrail: Bool) {
        answers[choice.key] = value
        if triggerRediscoverIfTrail, choice.group == "trail" {
            rediscoverTrailOptions(changedKey: choice.key, changedValue: value)
        }
    }

    private func rediscoverTrailOptions(changedKey: String, changedValue: String) {
        guard let temp = selectedTempURL else { return }
        // Cancel any in-flight rediscover (matches web behavior)
        rediscoverTask?.cancel()
        rediscovering = true
        let currentChoices = choices
        let currentAnswers = answers

        rediscoverTask = Task {
            // Only send trail answers so the engine re-derives trail courses
            var trailAnswers: [String: Any] = [:]
            for c in currentChoices where c.type == "pick" && c.group == "trail" {
                if c.key == changedKey {
                    trailAnswers[c.key] = changedValue
                } else {
                    trailAnswers[c.key] = currentAnswers[c.key] ?? c.selected ?? ""
                }
            }
            do {
                let resp = try await APIClient.shared.auditRun(fileURL: temp, program: program, answers: trailAnswers, save: false, source: "ios")
                await MainActor.run {
                    choices = resp.choices
                    // Merge like web: reset trail_course/open_elective picks to new defaults; keep others.
                    var merged: [String: Any] = [:]
                    for c in resp.choices {
                        if c.type == "pick", (c.group == "trail_course" || c.group == "open_elective") {
                            merged[c.key] = c.selected ?? (c.options?.first ?? "")
                        } else {
                            merged[c.key] = answers[c.key] ?? (c.type == "yes_no" ? (c.selectedBool ?? false) : (c.selected ?? (c.options?.first ?? "")))
                        }
                    }
                    answers = merged
                }
            } catch {
                // Ignore cancellation; surface real errors.
                if Task.isCancelled { }
                else {
                    await MainActor.run {
                        errorMessage = error.localizedDescription
                        showError = true
                    }
                }
            }
            await MainActor.run { rediscovering = false }
        }
    }

    private func filteredOptionsForTrailCourse(choice: AuditChoice, siblingKeys: [String]) -> [String] {
        let selected = (answers[choice.key] as? String) ?? choice.selected ?? ""
        let siblingSelected = Set(
            siblingKeys
                .filter { $0 != choice.key }
                .compactMap { answers[$0] as? String }
                .filter { !$0.isEmpty }
        )
        let opts = choice.options ?? []
        return opts.filter { $0 == selected || !siblingSelected.contains($0) }
    }
}

private struct GroupMeta {
    let title: String
    let subtitle: String

    static func forGroup(_ g: String) -> GroupMeta {
        switch g {
        case "ged_core":
            return .init(title: "GED / University Core Slots", subtitle: "Choose which course fills each GED slot.")
        case "mic_core":
            return .init(title: "MIC Core Choice Slots", subtitle: "Choose which course fills each MIC core slot.")
        case "trail":
            return .init(title: "Trail Selection", subtitle: "Select your primary and secondary trails. Courses update accordingly.")
        case "trail_course":
            return .init(title: "Trail Courses", subtitle: "Pick the specific courses to count from your trails.")
        case "open_elective":
            return .init(title: "Open Elective", subtitle: "Choose one open elective from available options.")
        case "major_elective":
            return .init(title: "Major Electives", subtitle: "Select your major elective courses.")
        case "free_elective":
            return .init(title: "Free Electives", subtitle: "Select your free elective courses.")
        case "bio_internship":
            return .init(title: "Internship / Research or BIO103L", subtitle: "Choose which option fills the shared slot.")
        default:
            return .init(title: "Other Selections", subtitle: "Additional course selections.")
        }
    }
}

private struct GroupCard<Content: View>: View {
    let title: String
    let subtitle: String
    let content: Content

    init(title: String, subtitle: String, @ViewBuilder content: () -> Content) {
        self.title = title
        self.subtitle = subtitle
        self.content = content()
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text(title)
                .font(.system(size: 16, weight: .light))
                .foregroundStyle(Theme.textPrimary)
            Text(subtitle)
                .font(.system(size: 12, weight: .light))
                .foregroundStyle(Theme.textMuted)
                .fixedSize(horizontal: false, vertical: true)
            content
        }
        .padding(16)
        .background(Theme.surface)
        .overlay(Rectangle().stroke(Theme.line, lineWidth: 1))
    }
}

private struct PickField: View {
    let choice: AuditChoice
    let selected: String
    let availableOptions: [String]
    let onSelect: (String) -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(choice.label ?? (choice.prompt.isEmpty ? choice.key : choice.prompt))
                .font(.system(size: 13, weight: .light))
                .foregroundStyle(Theme.textMuted)
                .fixedSize(horizontal: false, vertical: true)
            Menu {
                ForEach(availableOptions, id: \.self) { opt in
                    Button(optionDisplay(for: opt)) { onSelect(opt) }
                }
            } label: {
                HStack {
                    Text(optionDisplay(for: selected.isEmpty ? (availableOptions.first ?? "Select…") : selected))
                        .font(.system(size: 16, weight: .light))
                        .foregroundStyle(Theme.textPrimary)
                        .lineLimit(1)
                    Spacer()
                    Image(systemName: "chevron.down")
                        .font(.system(size: 12, weight: .light))
                        .foregroundStyle(Theme.textMuted)
                }
                .padding(.vertical, 14)
                .padding(.horizontal, 12)
                .background(Theme.surface)
                .overlay(Rectangle().stroke(Theme.line, lineWidth: 1))
            }
        }
    }

    private func optionDisplay(for opt: String) -> String {
        if let idx = choice.options?.firstIndex(of: opt), let disp = choice.display, idx < disp.count {
            return disp[idx]
        }
        return opt
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
