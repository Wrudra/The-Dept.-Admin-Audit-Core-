import { useEffect, useState } from "react";
import {
  Alert,
  Box,
  Button,
  Card,
  CardActionArea,
  CardContent,
  Chip,
  Dialog,
  DialogActions,
  DialogContent,
  DialogContentText,
  DialogTitle,
  Fade,
  Grow,
  IconButton,
  Skeleton,
  Snackbar,
  Tooltip,
  Typography,
} from "@mui/material";
import DeleteOutlineIcon from "@mui/icons-material/DeleteOutline";
import { useNavigate } from "react-router-dom";
import { historyApi, HistoryRun } from "../api/client";

export default function HistoryPage() {
  const navigate = useNavigate();
  const [runs, setRuns] = useState<HistoryRun[]>([]);
  const [loading, setLoading] = useState(true);
  const [deletingId, setDeletingId] = useState<string | null>(null);
  const [confirmId, setConfirmId] = useState<string | null>(null);
  const [snackOpen, setSnackOpen] = useState(false);
  const [snackMsg, setSnackMsg] = useState("");
  const [snackSeverity, setSnackSeverity] = useState<"success" | "error">(
    "success",
  );

  useEffect(() => {
    load();
  }, []);

  function load() {
    setLoading(true);
    historyApi
      .list({ limit: 50 })
      .then(({ data }) => setRuns(data.runs))
      .catch(() => {})
      .finally(() => setLoading(false));
  }

  function showSnack(msg: string, severity: "success" | "error" = "success") {
    setSnackMsg(msg);
    setSnackSeverity(severity);
    setSnackOpen(true);
  }

  async function confirmDelete() {
    if (!confirmId) return;
    const id = confirmId;
    setConfirmId(null);
    setDeletingId(id);
    try {
      await historyApi.delete(id);
      setRuns((prev) => prev.filter((r) => r.run_id !== id));
      showSnack("Audit run deleted.");
    } catch {
      showSnack("Failed to delete. Please try again.", "error");
    } finally {
      setDeletingId(null);
    }
  }

  return (
    <Fade in timeout={400}>
      <Box>
        <Typography variant="h5" gutterBottom fontWeight={700}>
          Audit History
        </Typography>

        {loading ? (
          [0, 1, 2, 3, 4].map((i) => (
            <Skeleton key={i} height={64} sx={{ mb: 1 }} />
          ))
        ) : runs.length === 0 ? (
          <Typography color="text.secondary">No past audits.</Typography>
        ) : (
          runs.map((r, i) => (
            <Grow key={r.run_id} in timeout={300 + i * 40}>
              <Card
                sx={{
                  mb: 1,
                  transition: "box-shadow 0.2s",
                  "&:hover": { boxShadow: 4 },
                }}
              >
                <Box sx={{ display: "flex", alignItems: "center" }}>
                  <CardActionArea
                    onClick={() => navigate(`/history/${r.run_id}`)}
                    sx={{ flexGrow: 1 }}
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

                      <Box sx={{ flexGrow: 1 }}>
                        <Typography variant="body2">
                          {r.transcript_filename ?? "uploaded transcript"}
                        </Typography>
                        <Typography variant="caption" color="text.secondary">
                          {r.created_at.slice(0, 19).replace("T", " ")}
                        </Typography>
                      </Box>

                      {r.cgpa != null && (
                        <Typography variant="body2" color="text.secondary">
                          CGPA {r.cgpa}
                        </Typography>
                      )}
                      {r.credit_completed != null && (
                        <Typography variant="body2" color="text.secondary">
                          {r.credit_completed} / {r.required_credits} cr
                        </Typography>
                      )}

                      <Chip
                        label={r.status}
                        size="small"
                        color={r.status === "complete" ? "success" : "default"}
                        variant="outlined"
                      />
                    </CardContent>
                  </CardActionArea>

                  <Tooltip title="Delete run">
                    <IconButton
                      size="small"
                      sx={{ mr: 1, color: "error.main" }}
                      disabled={deletingId === r.run_id}
                      onClick={() => setConfirmId(r.run_id)}
                    >
                      <DeleteOutlineIcon fontSize="small" />
                    </IconButton>
                  </Tooltip>
                </Box>
              </Card>
            </Grow>
          ))
        )}

        {/* ── Delete confirmation dialog ──────────────────────────────────── */}
        <Dialog open={!!confirmId} onClose={() => setConfirmId(null)}>
          <DialogTitle>Delete audit run?</DialogTitle>
          <DialogContent>
            <DialogContentText>
              This will permanently remove the audit run and its results. This
              action cannot be undone.
            </DialogContentText>
          </DialogContent>
          <DialogActions>
            <Button onClick={() => setConfirmId(null)}>Cancel</Button>
            <Button color="error" variant="contained" onClick={confirmDelete}>
              Delete
            </Button>
          </DialogActions>
        </Dialog>

        {/* ── Snackbar ──────────────────────────────────────────────────────── */}
        <Snackbar
          open={snackOpen}
          autoHideDuration={4000}
          onClose={() => setSnackOpen(false)}
          anchorOrigin={{ vertical: "bottom", horizontal: "center" }}
        >
          <Alert
            onClose={() => setSnackOpen(false)}
            severity={snackSeverity}
            sx={{ width: "100%" }}
            variant="filled"
          >
            {snackMsg}
          </Alert>
        </Snackbar>
      </Box>
    </Fade>
  );
}
