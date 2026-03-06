import { useEffect, useState } from "react";
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  Divider,
  Fade,
  Grow,
  Skeleton,
  Typography,
} from "@mui/material";
import ArrowBackIcon from "@mui/icons-material/ArrowBack";
import DownloadIcon from "@mui/icons-material/Download";
import PrintIcon from "@mui/icons-material/Print";
import { useNavigate, useParams } from "react-router-dom";
import { auditApi, AuditResult } from "../api/client";

export default function HistoryDetailPage() {
  const { runId } = useParams<{ runId: string }>();
  const navigate = useNavigate();
  const [result, setResult] = useState<AuditResult | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!runId) return;
    auditApi
      .get(runId)
      .then(({ data }) => setResult(data.result))
      .catch(() => setError("Could not load this audit run."))
      .finally(() => setLoading(false));
  }, [runId]);

  function handleExportCSV() {
    if (!result) return;
    const rows = [
      ["Course", "Credits"],
      ...Object.entries(result.per_course_credits).map(([c, cr]) => [
        c,
        String(cr),
      ]),
    ];
    const csv = rows.map((r) => r.join(",")).join("\n");
    const blob = new Blob([csv], { type: "text/csv" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `audit_report_${runId?.slice(0, 8)}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  }

  if (loading) {
    return (
      <Box>
        <Skeleton width={120} height={36} sx={{ mb: 2 }} />
        <Skeleton height={80} sx={{ mb: 1 }} />
        <Skeleton height={160} sx={{ mb: 1 }} />
        <Skeleton height={120} />
      </Box>
    );
  }

  if (error) {
    return (
      <Box>
        <Button
          startIcon={<ArrowBackIcon />}
          onClick={() => navigate("/history")}
          sx={{ mb: 2 }}
        >
          Back to History
        </Button>
        <Alert severity="error">{error}</Alert>
      </Box>
    );
  }

  if (!result) return null;

  return (
    <Fade in timeout={400}>
      <Box>
        <Box
          sx={{
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            mb: 3,
          }}
        >
          <Button
            startIcon={<ArrowBackIcon />}
            onClick={() => navigate("/history")}
          >
            Back to History
          </Button>
          <Box sx={{ display: "flex", gap: 1 }}>
            <Button
              variant="outlined"
              size="small"
              startIcon={<DownloadIcon />}
              onClick={handleExportCSV}
            >
              Export CSV
            </Button>
            <Button
              variant="outlined"
              size="small"
              startIcon={<PrintIcon />}
              onClick={() => window.print()}
            >
              Print / PDF
            </Button>
          </Box>
        </Box>

        <Alert
          severity={
            result.credit_completed >= result.required_credits
              ? "success"
              : "warning"
          }
          sx={{ mb: 3 }}
        >
          {result.credit_completed >= result.required_credits
            ? `Completed ${result.credit_completed}/${result.required_credits} credits — eligible to graduate!`
            : `Completed ${result.credit_completed}/${result.required_credits} credits — ${result.required_credits - result.credit_completed} remaining.`}
        </Alert>

        <Grow in timeout={400}>
          <Card sx={{ mb: 2 }}>
            <CardContent>
              <Typography variant="h6" gutterBottom>
                Summary
              </Typography>
              <Divider sx={{ mb: 2 }} />
              <Box sx={{ display: "flex", flexWrap: "wrap", gap: 2 }}>
                <Stat label="Program" value={result.program} />
                <Stat label="CGPA" value={result.cgpa.toFixed(2)} />
                <Stat
                  label="Credits"
                  value={`${result.credit_completed} / ${result.required_credits}`}
                />
                <Stat
                  label="Valid Credits"
                  value={String(result.total_valid_credits)}
                />
              </Box>
            </CardContent>
          </Card>
        </Grow>

        {result.waived_courses.length > 0 && (
          <Grow in timeout={500}>
            <Card sx={{ mb: 2 }}>
              <CardContent>
                <Typography variant="subtitle1" fontWeight={600}>
                  Waivers
                </Typography>
                {result.waiver_notes.length > 0 && (
                  <Typography
                    variant="caption"
                    color="text.secondary"
                    sx={{ display: "block", mb: 1 }}
                  >
                    {result.waiver_notes.join(" · ")}
                  </Typography>
                )}
                <Box sx={{ mt: 1, display: "flex", gap: 1, flexWrap: "wrap" }}>
                  {result.waived_courses.map((c) => (
                    <Chip key={c} label={c} size="small" color="info" />
                  ))}
                </Box>
              </CardContent>
            </Card>
          </Grow>
        )}

        {result.major_electives.length > 0 && (
          <Grow in timeout={580}>
            <Card sx={{ mb: 2 }}>
              <CardContent>
                <Typography variant="subtitle1" fontWeight={600}>
                  Selected Electives
                </Typography>
                <Box sx={{ mt: 1, display: "flex", gap: 1, flexWrap: "wrap" }}>
                  {result.major_electives.map((c) => (
                    <Chip key={c} label={c} size="small" color="primary" />
                  ))}
                  {result.open_elective && (
                    <Chip
                      label={`${result.open_elective} (open)`}
                      size="small"
                      color="secondary"
                    />
                  )}
                  {result.free_electives.map((c) => (
                    <Chip key={c} label={`${c} (free)`} size="small" />
                  ))}
                </Box>
              </CardContent>
            </Card>
          </Grow>
        )}

        {Object.keys(result.prereq_failures).length > 0 && (
          <Grow in timeout={660}>
            <Card
              sx={{ mb: 2, border: "1px solid", borderColor: "error.dark" }}
            >
              <CardContent>
                <Typography
                  variant="subtitle1"
                  fontWeight={600}
                  color="error.main"
                >
                  Prerequisite Failures
                </Typography>
                <Box sx={{ mt: 1 }}>
                  {Object.entries(result.prereq_failures).map(
                    ([course, reason]) => (
                      <Typography key={course} variant="body2" sx={{ mb: 0.5 }}>
                        <strong>{course}:</strong> {reason}
                      </Typography>
                    ),
                  )}
                </Box>
              </CardContent>
            </Card>
          </Grow>
        )}
      </Box>
    </Fade>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <Box sx={{ minWidth: 120 }}>
      <Typography variant="caption" color="text.secondary">
        {label}
      </Typography>
      <Typography variant="h6">{value}</Typography>
    </Box>
  );
}
