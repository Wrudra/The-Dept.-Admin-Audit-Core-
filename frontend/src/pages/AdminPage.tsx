import { useEffect, useState } from "react";
import {
  Alert,
  Box,
  Card,
  CardContent,
  Chip,
  Divider,
  Fade,
  Grow,
  Skeleton,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Typography,
} from "@mui/material";
import AdminPanelSettingsIcon from "@mui/icons-material/AdminPanelSettings";
import PeopleIcon from "@mui/icons-material/People";
import AssessmentIcon from "@mui/icons-material/Assessment";
import { adminApi, AdminStats } from "../api/client";
import { useAuthStore } from "../store/authStore";

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

  if (!user?.is_admin) {
    return (
      <Box sx={{ mt: 8, textAlign: "center" }}>
        <Typography color="error">Access denied.</Typography>
      </Box>
    );
  }

  return (
    <Fade in timeout={400}>
      <Box>
        <Box sx={{ display: "flex", alignItems: "center", gap: 1, mb: 3 }}>
          <AdminPanelSettingsIcon color="warning" sx={{ fontSize: 32 }} />
          <Typography variant="h5" fontWeight={700}>
            Admin Dashboard
          </Typography>
        </Box>

        {error && (
          <Alert severity="error" sx={{ mb: 3 }}>
            {error}
          </Alert>
        )}

        {loading ? (
          <Box sx={{ display: "flex", gap: 2, flexWrap: "wrap", mb: 3 }}>
            {[0, 1, 2, 3].map((i) => (
              <Skeleton
                key={i}
                variant="rectangular"
                width={180}
                height={100}
                sx={{ borderRadius: 2 }}
              />
            ))}
          </Box>
        ) : stats ? (
          <>
            {/* ── Stat cards ──────────────────────────────────────────────── */}
            <Box sx={{ display: "flex", gap: 2, flexWrap: "wrap", mb: 3 }}>
              {[
                {
                  label: "Total Audits",
                  value: stats.total_runs,
                  icon: (
                    <AssessmentIcon
                      sx={{ fontSize: 36, color: "primary.main" }}
                    />
                  ),
                  delay: 0,
                },
                {
                  label: "Total Users",
                  value: stats.total_users,
                  icon: (
                    <PeopleIcon
                      sx={{ fontSize: 36, color: "secondary.main" }}
                    />
                  ),
                  delay: 80,
                },
                {
                  label: "Avg CGPA",
                  value:
                    stats.avg_cgpa != null ? stats.avg_cgpa.toFixed(2) : "—",
                  icon: null,
                  delay: 160,
                },
                {
                  label: "Avg Credits",
                  value:
                    stats.avg_credits != null
                      ? stats.avg_credits.toFixed(1)
                      : "—",
                  icon: null,
                  delay: 240,
                },
              ].map(({ label, value, icon, delay }) => (
                <Grow key={label} in timeout={500 + delay}>
                  <Card sx={{ minWidth: 160, flex: "1 1 160px" }}>
                    <CardContent sx={{ textAlign: "center", py: 2 }}>
                      {icon}
                      <Typography
                        variant="h4"
                        fontWeight={700}
                        sx={{ mt: icon ? 0.5 : 0 }}
                      >
                        {value}
                      </Typography>
                      <Typography variant="caption" color="text.secondary">
                        {label}
                      </Typography>
                    </CardContent>
                  </Card>
                </Grow>
              ))}
            </Box>

            {/* ── Runs by program ─────────────────────────────────────────── */}
            {Object.keys(stats.runs_by_program).length > 0 && (
              <Fade in timeout={700}>
                <Card sx={{ mb: 3 }}>
                  <CardContent>
                    <Typography
                      variant="subtitle1"
                      fontWeight={600}
                      gutterBottom
                    >
                      Runs by Program
                    </Typography>
                    <Box
                      sx={{ display: "flex", gap: 2, flexWrap: "wrap", mt: 1 }}
                    >
                      {Object.entries(stats.runs_by_program).map(
                        ([prog, count]) => (
                          <Box key={prog} sx={{ textAlign: "center" }}>
                            <Chip
                              label={prog}
                              color="primary"
                              sx={{ mb: 0.5 }}
                            />
                            <Typography variant="h6" fontWeight={700}>
                              {count}
                            </Typography>
                            <Typography
                              variant="caption"
                              color="text.secondary"
                            >
                              runs
                            </Typography>
                          </Box>
                        ),
                      )}
                    </Box>
                  </CardContent>
                </Card>
              </Fade>
            )}

            {/* ── Recent 20 runs ──────────────────────────────────────────── */}
            <Fade in timeout={900}>
              <Card>
                <CardContent>
                  <Typography variant="subtitle1" fontWeight={600} gutterBottom>
                    Recent Runs (all users)
                  </Typography>
                  <Divider sx={{ mb: 1 }} />
                  <TableContainer>
                    <Table size="small">
                      <TableHead>
                        <TableRow>
                          <TableCell>User</TableCell>
                          <TableCell>Program</TableCell>
                          <TableCell>File</TableCell>
                          <TableCell>CGPA</TableCell>
                          <TableCell>Credits</TableCell>
                          <TableCell>Status</TableCell>
                          <TableCell>Date</TableCell>
                        </TableRow>
                      </TableHead>
                      <TableBody>
                        {stats.recent_runs.map((r) => (
                          <TableRow key={r.run_id} hover>
                            <TableCell>
                              <Typography
                                variant="body2"
                                noWrap
                                sx={{ maxWidth: 180 }}
                              >
                                {r.user_email}
                              </Typography>
                            </TableCell>
                            <TableCell>
                              <Chip
                                label={r.program}
                                size="small"
                                color="primary"
                              />
                            </TableCell>
                            <TableCell>
                              <Typography
                                variant="body2"
                                noWrap
                                sx={{ maxWidth: 140 }}
                              >
                                {r.transcript_filename ?? "—"}
                              </Typography>
                            </TableCell>
                            <TableCell>{r.cgpa ?? "—"}</TableCell>
                            <TableCell>
                              {r.credit_completed != null
                                ? `${r.credit_completed}/${r.required_credits}`
                                : "—"}
                            </TableCell>
                            <TableCell>
                              <Chip
                                label={r.status}
                                size="small"
                                color={
                                  r.status === "complete"
                                    ? "success"
                                    : "default"
                                }
                                variant="outlined"
                              />
                            </TableCell>
                            <TableCell>
                              <Typography
                                variant="caption"
                                color="text.secondary"
                              >
                                {r.created_at.slice(0, 10)}
                              </Typography>
                            </TableCell>
                          </TableRow>
                        ))}
                      </TableBody>
                    </Table>
                  </TableContainer>
                </CardContent>
              </Card>
            </Fade>
          </>
        ) : null}
      </Box>
    </Fade>
  );
}
