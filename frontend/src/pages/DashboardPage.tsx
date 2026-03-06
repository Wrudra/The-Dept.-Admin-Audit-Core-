import { useEffect, useState } from "react";
import {
  Box,
  Card,
  CardActionArea,
  CardContent,
  Chip,
  Fade,
  Grid,
  Grow,
  Skeleton,
  Typography,
} from "@mui/material";
import AddCircleOutlineIcon from "@mui/icons-material/AddCircleOutline";
import HistoryIcon from "@mui/icons-material/History";
import AdminPanelSettingsIcon from "@mui/icons-material/AdminPanelSettings";
import { useNavigate } from "react-router-dom";
import { historyApi, HistoryRun } from "../api/client";
import { useAuthStore } from "../store/authStore";

export default function DashboardPage() {
  const { user } = useAuthStore();
  const navigate = useNavigate();
  const [runs, setRuns] = useState<HistoryRun[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    historyApi
      .list({ limit: 5 })
      .then(({ data }) => setRuns(data.runs))
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  return (
    <Fade in timeout={400}>
      <Box>
        <Typography variant="h5" gutterBottom fontWeight={700}>
          Welcome, {user?.display_name}
        </Typography>
        <Typography variant="body2" color="text.secondary" gutterBottom>
          {user?.email}
        </Typography>

        <Grid container spacing={2} sx={{ mt: 2 }}>
          {/* ── Quick actions ──────────────────────────────────────────────── */}
          <Grid item xs={12} sm={6} md={4}>
            <Grow in timeout={400}>
              <Card
                sx={{
                  transition: "transform 0.2s, box-shadow 0.2s",
                  "&:hover": { transform: "translateY(-4px)", boxShadow: 6 },
                }}
              >
                <CardActionArea
                  onClick={() => navigate("/audit")}
                  sx={{ p: 2 }}
                >
                  <CardContent sx={{ textAlign: "center" }}>
                    <AddCircleOutlineIcon
                      sx={{ fontSize: 48, color: "primary.main", mb: 1 }}
                    />
                    <Typography variant="h6">New Audit</Typography>
                    <Typography variant="body2" color="text.secondary">
                      Upload a transcript and get your audit report
                    </Typography>
                  </CardContent>
                </CardActionArea>
              </Card>
            </Grow>
          </Grid>

          <Grid item xs={12} sm={6} md={4}>
            <Grow in timeout={520}>
              <Card
                sx={{
                  transition: "transform 0.2s, box-shadow 0.2s",
                  "&:hover": { transform: "translateY(-4px)", boxShadow: 6 },
                }}
              >
                <CardActionArea
                  onClick={() => navigate("/history")}
                  sx={{ p: 2 }}
                >
                  <CardContent sx={{ textAlign: "center" }}>
                    <HistoryIcon
                      sx={{ fontSize: 48, color: "secondary.main", mb: 1 }}
                    />
                    <Typography variant="h6">History</Typography>
                    <Typography variant="body2" color="text.secondary">
                      View past audit reports
                    </Typography>
                  </CardContent>
                </CardActionArea>
              </Card>
            </Grow>
          </Grid>

          {user?.is_admin && (
            <Grid item xs={12} sm={6} md={4}>
              <Grow in timeout={640}>
                <Card
                  sx={{
                    transition: "transform 0.2s, box-shadow 0.2s",
                    "&:hover": { transform: "translateY(-4px)", boxShadow: 6 },
                  }}
                >
                  <CardActionArea
                    onClick={() => navigate("/admin")}
                    sx={{ p: 2 }}
                  >
                    <CardContent sx={{ textAlign: "center" }}>
                      <AdminPanelSettingsIcon
                        sx={{ fontSize: 48, color: "warning.main", mb: 1 }}
                      />
                      <Typography variant="h6">Admin</Typography>
                      <Typography variant="body2" color="text.secondary">
                        Platform statistics &amp; recent runs
                      </Typography>
                    </CardContent>
                  </CardActionArea>
                </Card>
              </Grow>
            </Grid>
          )}

          {/* ── Recent runs ────────────────────────────────────────────────── */}
          <Grid item xs={12}>
            <Typography variant="h6" sx={{ mt: 2, mb: 1 }}>
              Recent runs
            </Typography>

            {loading ? (
              [0, 1, 2].map((i) => (
                <Skeleton key={i} height={56} sx={{ mb: 1 }} />
              ))
            ) : runs.length === 0 ? (
              <Typography color="text.secondary">No audits yet.</Typography>
            ) : (
              runs.map((r, i) => (
                <Grow key={r.run_id} in timeout={300 + i * 60}>
                  <Card
                    sx={{
                      mb: 1,
                      transition: "box-shadow 0.2s",
                      "&:hover": { boxShadow: 3 },
                    }}
                  >
                    <CardActionArea
                      onClick={() => navigate(`/history/${r.run_id}`)}
                    >
                      <CardContent
                        sx={{
                          display: "flex",
                          alignItems: "center",
                          gap: 2,
                          py: "12px !important",
                        }}
                      >
                        <Chip label={r.program} size="small" color="primary" />
                        <Typography variant="body2" sx={{ flexGrow: 1 }}>
                          {r.transcript_filename ?? "uploaded transcript"}
                        </Typography>
                        {r.cgpa != null && (
                          <Typography variant="body2" color="text.secondary">
                            CGPA {r.cgpa}
                          </Typography>
                        )}
                        <Typography variant="caption" color="text.secondary">
                          {r.created_at.slice(0, 10)}
                        </Typography>
                      </CardContent>
                    </CardActionArea>
                  </Card>
                </Grow>
              ))
            )}
          </Grid>
        </Grid>
      </Box>
    </Fade>
  );
}
