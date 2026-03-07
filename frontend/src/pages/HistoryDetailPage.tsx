import { useEffect, useState } from "react";
import { Alert, Box, Button, Fade, Skeleton } from "@mui/material";
import ArrowBackIcon from "@mui/icons-material/ArrowBack";
import DownloadIcon from "@mui/icons-material/Download";
import PrintIcon from "@mui/icons-material/Print";
import { useNavigate, useParams } from "react-router-dom";
import { auditApi, AuditResult } from "../api/client";
import AuditReport from "../components/AuditReport";

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
      <Box sx={{ maxWidth: 760 }}>
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

        <AuditReport result={result} />
      </Box>
    </Fade>
  );
}
