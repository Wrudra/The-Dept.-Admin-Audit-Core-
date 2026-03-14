import axios from "axios";

/** All API calls go through /api/* (proxied to http://localhost:8000 in dev,
 *  served from the same origin in production via Nginx). */
const client = axios.create({
  baseURL: "/api",
  withCredentials: true, // send/receive the HttpOnly JWT cookie
  timeout: 120_000, // 2 min — audit runs can be slow
});

client.interceptors.response.use(
  (res) => res,
  (err) => {
    if (err.response?.status === 401 && window.location.pathname !== "/login") {
      window.location.href = "/login";
    }
    return Promise.reject(err);
  },
);

export default client;

// ── Typed helpers ─────────────────────────────────────────────────────────────

export interface User {
  user_id: string;
  email: string;
  display_name: string;
  is_admin: boolean;
}

export interface CourseDetail {
  course: string;
  credits: number | null;
  grade: string;
  counted: boolean;
  label: string | null; // "Major Elective" | "Open Elective" | "Free Elective" | null
  reason: string | null; // reason for not counting
}

export interface MissingCategory {
  category: string;
  courses: string[];
}

export interface DeficiencyFailure {
  course: string;
  reason: string;
}

export interface Deficiency {
  eligible: boolean;
  credit_shortfall: number;
  probation: boolean;
  missing_mandatory: MissingCategory[];
  prereq_failures_list: DeficiencyFailure[];
  retake_note: string;
}

export interface AuditChoicePick {
  key: string;
  type: "pick";
  group: string;
  label: string;
  prompt: string;
  options: string[];
  display: string[];
  selected: string;
}

export interface AuditChoiceYesNo {
  key: string;
  type: "yes_no";
  prompt: string;
  selected: boolean;
}

export type AuditChoice = AuditChoicePick | AuditChoiceYesNo;

export interface MinorProgram {
  name: string;
  total_credits: number;
  complete: boolean;
  progress: string;
  core_courses?: string[];
  declared_courses: string[];
  choice_slot?: { options: string[]; selected: string | null };
  open_elective_course: string | null;
}

export interface AuditResult {
  program: string;
  total_valid_credits: number;
  required_credits: number;
  credit_completed: number;
  cgpa: number;
  waived_courses: string[];
  waiver_notes: string[];
  major_electives: string[];
  free_electives: string[];
  open_elective: string | null;
  prereq_failures: Record<string, string>;
  per_course_credits: Record<string, number>;
  console_log: string;
  // Level-3 extended fields (null for legacy stored results)
  credit_passed: number | null;
  credit_counted: number | null;
  total_grade_points: number | null;
  academic_standing: string | null;
  per_course_detail: CourseDetail[];
  deficiency: Deficiency | null;
  minor_programs: MinorProgram[] | null;
}

export interface HistoryRun {
  run_id: string;
  program: string;
  status: string;
  transcript_filename: string | null;
  created_at: string;
  completed_at: string | null;
  source: string | null;
  cgpa: number | null;
  credit_completed: number | null;
  required_credits: number | null;
}

export interface AdminRecentRun extends HistoryRun {
  user_email: string;
  user_name: string;
}

export interface AdminStats {
  total_runs: number;
  total_users: number;
  runs_by_program: Record<string, number>;
  avg_cgpa: number | null;
  avg_credits: number | null;
  recent_runs: AdminRecentRun[];
}

export const authApi = {
  me: () => client.get<User>("/auth/me"),
  logout: () => client.post("/auth/logout"),
};

export const auditApi = {
  /** Discover choices (no DB save) — used for the configure step. */
  discover: (transcript: File, program: string) => {
    const fd = new FormData();
    fd.append("transcript", transcript);
    fd.append("program", program);
    fd.append("answers", "{}");
    fd.append("save", "false");
    return client.post<{ result: AuditResult; choices: AuditChoice[] }>(
      "/audit/run",
      fd,
      { headers: { "Content-Type": "multipart/form-data" } },
    );
  },
  /** Re-discover choices with partial answers (e.g. after trail change). */
  rediscover: (
    transcript: File,
    program: string,
    answers: Record<string, unknown>,
  ) => {
    const fd = new FormData();
    fd.append("transcript", transcript);
    fd.append("program", program);
    fd.append("answers", JSON.stringify(answers));
    fd.append("save", "false");
    return client.post<{ result: AuditResult; choices: AuditChoice[] }>(
      "/audit/run",
      fd,
      { headers: { "Content-Type": "multipart/form-data" } },
    );
  },
  /** Run audit with user-selected answers and persist to DB. */
  run: (
    transcript: File,
    program: string,
    answers: Record<string, unknown>,
  ) => {
    const fd = new FormData();
    fd.append("transcript", transcript);
    fd.append("program", program);
    fd.append("answers", JSON.stringify(answers));
    fd.append("save", "true");
    return client.post<{
      run_id: string;
      result: AuditResult;
      choices: AuditChoice[];
    }>("/audit/run", fd, {
      headers: { "Content-Type": "multipart/form-data" },
    });
  },
  get: (runId: string) =>
    client.get<{ result: AuditResult }>(`/audit/${runId}`),
};

export const historyApi = {
  list: (params?: { limit?: number; offset?: number }) =>
    client.get<{ runs: HistoryRun[] }>("/history/", { params }),
  get: (runId: string) => client.get(`/history/${runId}`),
  delete: (runId: string) => client.delete(`/history/${runId}`),
};

export const adminApi = {
  stats: () => client.get<AdminStats>("/admin/stats"),
};
