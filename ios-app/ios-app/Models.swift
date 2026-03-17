//
//  Models.swift
//  ios-app
//
//  API response models matching the backend and web frontend.
//

import Foundation

// MARK: - Auth & User

struct User: Codable {
    let user_id: String
    let email: String
    let display_name: String
    let is_admin: Bool
}

// MARK: - History

struct HistoryRun: Codable {
    let run_id: String
    let program: String
    let status: String
    let transcript_filename: String?
    let created_at: String
    let completed_at: String?
    let source: String?
    let cgpa: Double?
    let credit_completed: Double?
    let required_credits: Double?
}

struct HistoryListResponse: Codable {
    let runs: [HistoryRun]
    let limit: Int
    let offset: Int
}

// MARK: - Admin

struct AdminRecentRun: Codable {
    let run_id: String
    let program: String
    let status: String
    let transcript_filename: String?
    let created_at: String
    let cgpa: Double?
    let credit_completed: Double?
    let required_credits: Double?
    let user_email: String
    let user_name: String
}

struct AdminStats: Codable {
    let total_runs: Int
    let total_users: Int
    let runs_by_program: [String: Int]
    let avg_cgpa: Double?
    let avg_credits: Double?
    let recent_runs: [AdminRecentRun]
}

// MARK: - Audit choices

// MARK: - Audit choices (pick and yes_no from API)
struct AuditChoice: Codable {
    let key: String
    let type: String  // "pick" | "yes_no"
    let group: String?
    let label: String?
    let prompt: String
    let options: [String]?
    let display: [String]?
    /// For type "pick": selected option string. For type "yes_no": not used (use selectedBool).
    let selected: String?
    /// For type "yes_no": the default/selected boolean.
    let selectedBool: Bool?

    enum CodingKeys: String, CodingKey {
        case key, type, group, label, prompt, options, display, selected
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        key = try c.decode(String.self, forKey: .key)
        type = try c.decode(String.self, forKey: .type)
        group = try c.decodeIfPresent(String.self, forKey: .group)
        label = try c.decodeIfPresent(String.self, forKey: .label)
        prompt = try c.decode(String.self, forKey: .prompt)
        options = try c.decodeIfPresent([String].self, forKey: .options)
        display = try c.decodeIfPresent([String].self, forKey: .display)
        if let b = try? c.decode(Bool.self, forKey: .selected) {
            selected = nil
            selectedBool = b
        } else {
            selected = try c.decodeIfPresent(String.self, forKey: .selected)
            selectedBool = nil
        }
    }

    func encode(to encoder: Encoder) throws {
        var c = encoder.container(keyedBy: CodingKeys.self)
        try c.encode(key, forKey: .key)
        try c.encode(type, forKey: .type)
        try c.encodeIfPresent(group, forKey: .group)
        try c.encodeIfPresent(label, forKey: .label)
        try c.encode(prompt, forKey: .prompt)
        try c.encodeIfPresent(options, forKey: .options)
        try c.encodeIfPresent(display, forKey: .display)
        if let b = selectedBool {
            try c.encode(b, forKey: .selected)
        } else {
            try c.encodeIfPresent(selected, forKey: .selected)
        }
    }
}

// MARK: - Audit result & deficiency

struct CourseDetail: Codable {
    let course: String
    let credits: Double?
    let grade: String
    let counted: Bool
    let label: String?
    let reason: String?
}

struct MissingCategory: Codable {
    let category: String
    let courses: [String]
}

struct DeficiencyFailure: Codable {
    let course: String
    let reason: String
}

struct Deficiency: Codable {
    let eligible: Bool
    let credit_shortfall: Double
    let probation: Bool
    let missing_mandatory: [MissingCategory]
    let prereq_failures_list: [DeficiencyFailure]
    let retake_note: String
}

struct MinorProgram: Codable {
    let name: String
    let total_credits: Double
    let complete: Bool
    let progress: String
    let core_courses: [String]?
    let declared_courses: [String]
    let choice_slot: ChoiceSlot?
    let open_elective_course: String?
}

struct ChoiceSlot: Codable {
    let options: [String]
    let selected: String?
}

struct AuditResult: Codable {
    let program: String
    let total_valid_credits: Double?
    let required_credits: Double
    let credit_completed: Double
    let cgpa: Double
    let waived_courses: [String]?
    let waiver_notes: [String]?
    let major_electives: [String]?
    let free_electives: [String]?
    let open_elective: String?
    let prereq_failures: [String: String]?
    let per_course_credits: [String: Double]?
    let console_log: String?
    let credit_passed: Double?
    let credit_counted: Double?
    let total_grade_points: Double?
    let academic_standing: String?
    let per_course_detail: [CourseDetail]?
    let deficiency: Deficiency?
    let minor_programs: [MinorProgram]?
}

struct AuditRunResponse: Codable {
    let run_id: String?
    let result: AuditResult
    let choices: [AuditChoice]
}

struct HistoryDetailResponse: Codable {
    let run_id: String
    let program: String
    let status: String
    let transcript_filename: String?
    let created_at: String
    let completed_at: String?
    let source: String?
    let result: AuditResult
    let answers: [String: AnyCodable]?
}

struct AnyCodable: Codable {
    let value: Any
    init(_ value: Any) { self.value = value }
    init(from decoder: Decoder) throws {
        let c = try decoder.singleValueContainer()
        if let b = try? c.decode(Bool.self) { value = b }
        else if let s = try? c.decode(String.self) { value = s }
        else if let d = try? c.decode(Double.self) { value = d }
        else if let a = try? c.decode([AnyCodable].self) { value = a.map(\.value) }
        else if let dict = try? c.decode([String: AnyCodable].self) { value = dict.mapValues(\.value) }
        else { value = NSNull() }
    }
    func encode(to encoder: Encoder) throws {
        var c = encoder.singleValueContainer()
        switch value {
        case let b as Bool: try c.encode(b)
        case let s as String: try c.encode(s)
        case let d as Double: try c.encode(d)
        case let a as [Any]: try c.encode(a.map { AnyCodable($0) })
        case let dict as [String: Any]: try c.encode(dict.mapValues { AnyCodable($0) })
        default: try c.encodeNil()
        }
    }
}

// MARK: - Device flow

struct DeviceStartResponse: Codable {
    let user_code: String
    let verification_url: String
    let device_code: String
    let expires_in: Int?
    let interval: Int?
    let client_id: String
    let client_secret: String?
}

struct DeviceExchangeResponse: Codable {
    let access_token: String
    let token_type: String?
}
