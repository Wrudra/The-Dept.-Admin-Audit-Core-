import { useEffect, useMemo, useState } from "react";
import {
  Alert,
  Box,
  Chip,
  Divider,
  Skeleton,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Typography,
} from "@mui/material";
import { adminApi, AdminRecentRun, AdminStats } from "../api/client";
import { useAuthStore } from "../store/authStore";
import { SERIF } from "../theme";

// ── Utilities ─────────────────────────────────────────────────────────────────

function timeAgo(dateStr: string): string {
  const diff = Date.now() - new Date(dateStr).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  if (days < 7) return `${days}d ago`;
  return dateStr.slice(0, 10);
}

function cgpaColor(cgpa: number | null): string {
  if (cgpa == null) return "text.disabled";
  if (cgpa < 2.0) return "error.main";
  if (cgpa < 2.5) return "warning.main";
  if (cgpa < 3.0) return "text.secondary";
  return "success.main";
}

function sourceLabel(src: string | null) {
  if (src === "mcp") return "MCP";
  if (src === "cli") return "CLI";
  if (src === "ios") return "iOS";
  return "Web";
}

// ── Sub-components ────────────────────────────────────────────────────────────

function StatCell({
  label,
  value,
  sub,
  border = true,
}: {
  label: string;
  value: string;
  sub?: string;
  border?: boolean;
}) {
  return (
    <Box
      sx={{
        flex: "1 1 120px",
        p: { xs: 2.5, md: 3 },
        borderRight: border ? "1px solid" : "none",
        borderColor: "divider",
      }}
    >
      <Typography variant="overline" color="text.secondary" sx={{ display: "block" }}>
        {label}
      </Typography>
      <Typography
        sx={{
          fontFamily: SERIF,
          fontSize: "clamp(28px, 4vw, 40px)",
          lineHeight: 1.1,
          mt: 0.25,
        }}
      >
        {value}
      </Typography>
      {sub && (
        <Typography variant="caption" color="text.secondary" sx={{ mt: 0.25, display: "block" }}>
          {sub}
        </Typography>
      )}
    </Box>
  );
}

function HorizBar({
  label,
  count,
  total,
  color = "text.secondary",
}: {
  label: string;
  count: number;
  total: number;
  color?: string;
}) {
  const pct = total > 0 ? (count / total) * 100 : 0;
  return (
    <Box sx={{ display: "flex", alignItems: "center", gap: 2, mb: 1.75 }}>
      <Typography
        variant="caption"
        color="text.secondary"
        sx={{ width: 64, flexShrink: 0 }}
      >
        {label}
      </Typography>
      <Box
        sx={{
          flex: 1,
          height: 3,
          bgcolor: "divider",
          borderRadius: "999px",
          overflow: "hidden",
        }}
      >
        <Box
          sx={{
            height: "100%",
            width: `${pct}%`,
            bgcolor: color,
            borderRadius: "999px",
            transition: "width 0.6s cubic-bezier(0.16,1,0.3,1)",
          }}
        />
      </Box>
      <Typography
        variant="caption"
        color="text.secondary"
        sx={{ width: 28, textAlign: "right", flexShrink: 0 }}
      >
        {count}
      </Typography>
    </Box>
  );
}

// ── Main page ─────────────────────────────────────────────────────────────────

export default function AdminPage() {
  const { user } = useAuthStore();
  const [stats, setStats] = useState<AdminStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    adminApi
      .stats()
      .then(({ data }) => setStats(data))
      .catch(() => setError("Failed to load admin stats."))
      .finally(() => setLoading(false));
  }, []);

  // ── Derived analytics from recent_runs ──────────────────────────────────────
  const derived = useMemo(() => {
    if (!stats) return null;
    const runs = stats.recent_runs;

    // Source breakdown
    const sourceCounts: Record<string, number> = {};
    for (const r of runs) {
      const src = sourceLabel(r.source);
      sourceCounts[src] = (sourceCounts[src] ?? 0) + 1;
    }

    // CGPA buckets
    const cgpaBuckets: Record<string, number> = {
      "< 2.0": 0,
      "2.0 – 2.5": 0,
      "2.5 – 3.0": 0,
      "3.0 – 3.5": 0,
      "3.5 – 4.0": 0,
    };
    let cgpaCount = 0;
    for (const r of runs) {
      if (r.cgpa == null) continue;
      cgpaCount++;
      if (r.cgpa < 2.0) cgpaBuckets["< 2.0"]++;
      else if (r.cgpa < 2.5) cgpaBuckets["2.0 – 2.5"]++;
      else if (r.cgpa < 3.0) cgpaBuckets["2.5 – 3.0"]++;
      else if (r.cgpa < 3.5) cgpaBuckets["3.0 – 3.5"]++;
      else cgpaBuckets["3.5 – 4.0"]++;
    }

    // Top active users
    const userMap: Record<string, { name: string; count: number; programs: Set<string> }> = {};
    for (const r of runs) {
      if (!userMap[r.user_email]) {
        userMap[r.user_email] = { name: r.user_name, count: 0, programs: new Set() };
      }
      userMap[r.user_email].count++;
      userMap[r.user_email].programs.add(r.program);
    }
    const topUsers = Object.entries(userMap)
      .sort((a, b) => b[1].count - a[1].count)
      .slice(0, 5);

    // Runs per user
    const runsPerUser =
      stats.total_users > 0
        ? (stats.total_runs / stats.total_users).toFixed(1)
        : "—";

    return { sourceCounts, cgpaBuckets, cgpaCount, topUsers, runsPerUser };
  }, [stats]);

  if (!user?.is_admin) {
    return (
      <Box sx={{ py: 8, textAlign: "center" }}>
        <Typography variant="overline" color="text.secondary">
          Access Denied
        </Typography>
        <Typography variant="h6" sx={{ mt: 1 }}>
          You don't have permission to view this page.
        </Typography>
      </Box>
    );
  }

  return (
    <Box>
      {/* ── Page header ──────────────────────────────────────────────────────── */}
      <Typography variant="overline" color="text.secondary">
        Administration
      </Typography>
      <Typography variant="h5" sx={{ mt: 0.5, mb: 4, lineHeight: 1.2 }}>
        Platform
        <br />
        <em>overview.</em>
      </Typography>

      {error && (
        <Alert severity="error" sx={{ mb: 3 }}>
          {error}
        </Alert>
      )}

      {loading ? (
        <Box sx={{ display: "flex", flexDirection: "column", gap: 2 }}>
          <Skeleton height={120} sx={{ borderRadius: "2px" }} />
          <Box sx={{ display: "flex", gap: 2 }}>
            <Skeleton height={160} sx={{ flex: 1, borderRadius: "2px" }} />
            <Skeleton height={160} sx={{ flex: 1, borderRadius: "2px" }} />
          </Box>
          <Skeleton height={200} sx={{ borderRadius: "2px" }} />
          <Skeleton height={300} sx={{ borderRadius: "2px" }} />
        </Box>
      ) : stats && derived ? (
        <>
          {/* ── Key metrics strip ────────────────────────────────────────────── */}
          <Box
            sx={{
              display: "flex",
              flexWrap: "wrap",
              border: "1px solid",
              borderColor: "divider",
              borderRadius: "2px",
              mb: 3,
              "& > *:last-child": { borderRight: "none" },
              "& > *": {
                borderBottom: { xs: "1px solid", md: "none" },
                borderColor: "divider",
              },
            }}
          >
            <StatCell
              label="Total Audits"
              value={String(stats.total_runs)}
              sub="all time"
            />
            <StatCell
              label="Total Users"
              value={String(stats.total_users)}
              sub="registered"
            />
            <StatCell
              label="Runs / User"
              value={derived.runsPerUser}
              sub="average"
            />
            <StatCell
              label="Avg CGPA"
              value={stats.avg_cgpa != null ? stats.avg_cgpa.toFixed(2) : "—"}
              sub="across all runs"
            />
            <StatCell
              label="Avg Credits"
              value={
                stats.avg_credits != null
                  ? stats.avg_credits.toFixed(1)
                  : "—"
              }
              sub="completed"
              border={false}
            />
          </Box>

          {/* ── Charts row ───────────────────────────────────────────────────── */}
          <Box
            sx={{
              display: "grid",
              gridTemplateColumns: { xs: "1fr", md: "1fr 1fr" },
              gap: 2,
              mb: 3,
            }}
          >
            {/* Runs by program */}
            <Box
              sx={{
                border: "1px solid",
                borderColor: "divider",
                borderRadius: "2px",
                p: 3,
              }}
            >
              <Typography variant="overline" color="text.secondary">
                Runs by Program
              </Typography>
              <Divider sx={{ my: 1.5 }} />
              {Object.entries(stats.runs_by_program).map(([prog, count]) => (
                <HorizBar
                  key={prog}
                  label={prog}
                  count={count}
                  total={stats.total_runs}
                  color="text.secondary"
                />
              ))}
              {Object.keys(stats.runs_by_program).length === 0 && (
                <Typography variant="caption" color="text.secondary">
                  No data yet.
                </Typography>
              )}
            </Box>

            {/* Source breakdown */}
            <Box
              sx={{
                border: "1px solid",
                borderColor: "divider",
                borderRadius: "2px",
                p: 3,
              }}
            >
              <Typography variant="overline" color="text.secondary">
                Source Breakdown
              </Typography>
              <Typography variant="caption" color="text.secondary" sx={{ display: "block", mb: 1 }}>
                from last {stats.recent_runs.length} runs
              </Typography>
              <Divider sx={{ mb: 1.5 }} />
              {(["Web", "CLI", "MCP"] as const).map((src) => (
                <HorizBar
                  key={src}
                  label={src}
                  count={derived.sourceCounts[src] ?? 0}
                  total={stats.recent_runs.length}
                  color="text.secondary"
                />
              ))}
            </Box>
          </Box>

          {/* ── CGPA distribution + Top users ────────────────────────────────── */}
          <Box
            sx={{
              display: "grid",
              gridTemplateColumns: { xs: "1fr", md: "1fr 1fr" },
              gap: 2,
              mb: 3,
            }}
          >
            {/* CGPA distribution */}
            <Box
              sx={{
                border: "1px solid",
                borderColor: "divider",
                borderRadius: "2px",
                p: 3,
              }}
            >
              <Typography variant="overline" color="text.secondary">
                CGPA Distribution
              </Typography>
              <Typography variant="caption" color="text.secondary" sx={{ display: "block", mb: 1 }}>
                {derived.cgpaCount} runs with CGPA data
              </Typography>
              <Divider sx={{ mb: 1.5 }} />
              {[
                { label: "< 2.0", color: "error.main" },
                { label: "2.0 – 2.5", color: "warning.main" },
                { label: "2.5 – 3.0", color: "text.secondary" },
                { label: "3.0 – 3.5", color: "success.main" },
                { label: "3.5 – 4.0", color: "success.main" },
              ].map(({ label, color }) => (
                <HorizBar
                  key={label}
                  label={label}
                  count={derived.cgpaBuckets[label] ?? 0}
                  total={derived.cgpaCount || 1}
                  color={color}
                />
              ))}
            </Box>

            {/* Top active users */}
            <Box
              sx={{
                border: "1px solid",
                borderColor: "divider",
                borderRadius: "2px",
                p: 3,
              }}
            >
              <Typography variant="overline" color="text.secondary">
                Top Active Users
              </Typography>
              <Typography variant="caption" color="text.secondary" sx={{ display: "block", mb: 1 }}>
                by run count in recent data
              </Typography>
              <Divider sx={{ mb: 1.5 }} />
              {derived.topUsers.length === 0 ? (
                <Typography variant="caption" color="text.secondary">
                  No data yet.
                </Typography>
              ) : (
                derived.topUsers.map(([email, { name, count, programs }]) => (
                  <Box
                    key={email}
                    sx={{
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "space-between",
                      py: 1,
                      borderBottom: "1px solid",
                      borderColor: "divider",
                      "&:last-child": { borderBottom: "none" },
                    }}
                  >
                    <Box sx={{ minWidth: 0 }}>
                      <Typography variant="body2" noWrap>
                        {name}
                      </Typography>
                      <Typography variant="caption" color="text.secondary" noWrap>
                        {email}
                      </Typography>
                    </Box>
                    <Box
                      sx={{
                        display: "flex",
                        alignItems: "center",
                        gap: 1,
                        flexShrink: 0,
                        ml: 2,
                      }}
                    >
                      {Array.from(programs).map((p) => (
                        <Chip key={p} label={p} size="small" color="primary" />
                      ))}
                      <Typography
                        sx={{
                          fontFamily: SERIF,
                          fontSize: "1.25rem",
                          lineHeight: 1,
                          color: "text.secondary",
                          ml: 0.5,
                        }}
                      >
                        {count}
                      </Typography>
                    </Box>
                  </Box>
                ))
              )}
            </Box>
          </Box>

          {/* ── Recent runs table ────────────────────────────────────────────── */}
          <Box
            sx={{
              border: "1px solid",
              borderColor: "divider",
              borderRadius: "2px",
            }}
          >
            <Box sx={{ px: 3, pt: 2.5, pb: 1.5 }}>
              <Typography variant="overline" color="text.secondary">
                Recent Runs
              </Typography>
              <Typography variant="caption" color="text.secondary" sx={{ ml: 1.5 }}>
                last {stats.recent_runs.length} across all users
              </Typography>
            </Box>
            <Divider />
            <TableContainer>
              <Table size="small">
                <TableHead>
                  <TableRow>
                    <TableCell>User</TableCell>
                    <TableCell>Program</TableCell>
                    <TableCell>Source</TableCell>
                    <TableCell>File</TableCell>
                    <TableCell>CGPA</TableCell>
                    <TableCell>Credits</TableCell>
                    <TableCell>Status</TableCell>
                    <TableCell>When</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {stats.recent_runs.map((r: AdminRecentRun) => (
                    <TableRow key={r.run_id} hover>
                      {/* User */}
                      <TableCell sx={{ maxWidth: 200 }}>
                        <Typography variant="body2" noWrap color="text.primary">
                          {r.user_name}
                        </Typography>
                        <Typography variant="caption" color="text.secondary" noWrap sx={{ display: "block" }}>
                          {r.user_email}
                        </Typography>
                      </TableCell>

                      {/* Program */}
                      <TableCell>
                        <Chip label={r.program} size="small" color="primary" />
                      </TableCell>

                      {/* Source */}
                      <TableCell>
                        <Chip label={sourceLabel(r.source)} size="small" />
                      </TableCell>

                      {/* File */}
                      <TableCell sx={{ maxWidth: 140 }}>
                        <Typography variant="body2" noWrap color="text.secondary">
                          {r.transcript_filename ?? "—"}
                        </Typography>
                      </TableCell>

                      {/* CGPA — colored */}
                      <TableCell>
                        <Typography
                          variant="body2"
                          sx={{
                            fontFamily: SERIF,
                            color: cgpaColor(r.cgpa),
                            fontSize: "0.9375rem",
                          }}
                        >
                          {r.cgpa != null ? r.cgpa.toFixed(2) : "—"}
                        </Typography>
                      </TableCell>

                      {/* Credits */}
                      <TableCell>
                        <Typography variant="body2" color="text.secondary">
                          {r.credit_completed != null
                            ? `${r.credit_completed} / ${r.required_credits}`
                            : "—"}
                        </Typography>
                      </TableCell>

                      {/* Status */}
                      <TableCell>
                        <Chip
                          label={r.status}
                          size="small"
                          color={r.status === "complete" ? "success" : undefined}
                        />
                      </TableCell>

                      {/* Time */}
                      <TableCell>
                        <Typography variant="caption" color="text.secondary">
                          {timeAgo(r.created_at)}
                        </Typography>
                        <Typography variant="caption" color="text.secondary" sx={{ display: "block" }}>
                          {r.created_at.slice(0, 10)}
                        </Typography>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </TableContainer>
          </Box>
        </>
      ) : null}
    </Box>
  );
}
