import React, { useState } from "react";
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  Divider,
  Fade,
  FormControl,
  FormControlLabel,
  FormHelperText,
  Grow,
  InputLabel,
  LinearProgress,
  MenuItem,
  Select,
  Snackbar,
  Step,
  StepLabel,
  Stepper,
  Switch,
  Typography,
} from "@mui/material";
import CloudUploadIcon from "@mui/icons-material/CloudUpload";
import DownloadIcon from "@mui/icons-material/Download";
import PrintIcon from "@mui/icons-material/Print";
import { useNavigate } from "react-router-dom";
import { auditApi, AuditResult } from "../api/client";

type Answers = Record<string, boolean | string | string[]>;

const STEPS = ["Upload Transcript", "Configure Answers", "Audit Report"];

export default function AuditPage() {
  const navigate = useNavigate();
  const [step, setStep] = useState(0);
  const [file, setFile] = useState<File | null>(null);
  const [program, setProgram] = useState<"CSE" | "MIC">("CSE");
  const [answers, setAnswers] = useState<Answers>({
    waiver_eng102: false,
    waiver_mat112: false,
  });
  const [result, setResult] = useState<AuditResult | null>(null);
  const [error, setError] = useState<string>("");
  const [busy, setBusy] = useState(false);
  const [snackOpen, setSnackOpen] = useState(false);
  const [snackMsg, setSnackMsg] = useState("");
  const [snackSeverity, setSnackSeverity] = useState<"success" | "error">(
    "success",
  );

  function showSnack(msg: string, severity: "success" | "error" = "success") {
    setSnackMsg(msg);
    setSnackSeverity(severity);
    setSnackOpen(true);
  }

  // ── Step 0 handlers ─────────────────────────────────────────────────────────
  function handleFile(e: React.ChangeEvent<HTMLInputElement>) {
    const f = e.target.files?.[0];
    if (f) setFile(f);
  }

  function handleDropFile(e: React.DragEvent) {
    e.preventDefault();
    const f = e.dataTransfer.files?.[0];
    if (f) setFile(f);
  }

  // ── Step 1 handlers ─────────────────────────────────────────────────────────
  function toggleBool(key: string) {
    setAnswers((a) => ({ ...a, [key]: !a[key] }));
  }

  // ── Export CSV ────────────────────────────────────────────────────────────
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
    a.download = `audit_report_${result.program}_${Date.now()}.csv`;
    a.click();
    URL.revokeObjectURL(url);
    showSnack("CSV exported successfully.");
  }

  // ── Submit ────────────────────────────────────────────────────────────────
  async function handleRun() {
    if (!file) return;
    setBusy(true);
    setError("");
    try {
      const { data } = await auditApi.run(file, program, answers);
      setResult(data.result);
      setStep(2);
      showSnack("Audit completed successfully!");
    } catch (err: unknown) {
      const msg =
        (err as { response?: { data?: { detail?: string } } })?.response?.data
          ?.detail ?? "Audit failed. Please try again.";
      setError(msg);
      showSnack(msg, "error");
    } finally {
      setBusy(false);
    }
  }

  return (
    <Box>
      <Typography variant="h5" gutterBottom fontWeight={700}>
        New Audit
      </Typography>

      <Stepper activeStep={step} sx={{ mb: 4 }}>
        {STEPS.map((label) => (
          <Step key={label}>
            <StepLabel>{label}</StepLabel>
          </Step>
        ))}
      </Stepper>

      {/* ── Step 0: Upload ─────────────────────────────────────────────────── */}
      <Fade in={step === 0} unmountOnExit>
        <Box sx={{ display: step === 0 ? "block" : "none" }}>
          <Card sx={{ maxWidth: 560 }}>
            <CardContent sx={{ p: 3 }}>
              <FormControl fullWidth sx={{ mb: 3 }}>
                <InputLabel id="prog-label">Program</InputLabel>
                <Select
                  labelId="prog-label"
                  value={program}
                  label="Program"
                  onChange={(e) => setProgram(e.target.value as "CSE" | "MIC")}
                >
                  <MenuItem value="CSE">
                    CSE — Computer Science &amp; Engineering
                  </MenuItem>
                  <MenuItem value="MIC">MIC — Microbiology</MenuItem>
                </Select>
              </FormControl>

              {/* Drop zone */}
              <Box
                onDragOver={(e) => e.preventDefault()}
                onDrop={handleDropFile}
                sx={{
                  border: "2px dashed",
                  borderColor: file ? "primary.main" : "action.disabled",
                  borderRadius: 2,
                  p: 4,
                  textAlign: "center",
                  cursor: "pointer",
                  transition: "border-color 0.2s, background-color 0.2s",
                  "&:hover": {
                    borderColor: "primary.light",
                    bgcolor: "action.hover",
                  },
                }}
              >
                <CloudUploadIcon
                  sx={{
                    fontSize: 48,
                    color: file ? "primary.main" : "text.secondary",
                    mb: 1,
                    transition: "color 0.2s",
                  }}
                />
                <Typography variant="body1" gutterBottom>
                  {file ? file.name : "Drag & drop your transcript here"}
                </Typography>
                <Typography variant="caption" color="text.secondary">
                  or
                </Typography>
                <Box sx={{ mt: 1 }}>
                  <Button variant="outlined" size="small" component="label">
                    Browse
                    <input
                      hidden
                      type="file"
                      accept=".csv,.pdf,.jpg,.jpeg,.png,.tif,.tiff,.bmp"
                      onChange={handleFile}
                    />
                  </Button>
                </Box>
                <Typography
                  variant="caption"
                  color="text.secondary"
                  sx={{ display: "block", mt: 1 }}
                >
                  .csv, .pdf, .jpg, .png · max {10} MB
                </Typography>
              </Box>

              <Box sx={{ mt: 3, display: "flex", justifyContent: "flex-end" }}>
                <Button
                  variant="contained"
                  disabled={!file}
                  onClick={() => setStep(1)}
                >
                  Next
                </Button>
              </Box>
            </CardContent>
          </Card>
        </Box>
      </Fade>

      {/* ── Step 1: Answers ────────────────────────────────────────────────── */}
      <Fade in={step === 1} unmountOnExit>
        <Box sx={{ display: step === 1 ? "block" : "none" }}>
          <Card sx={{ maxWidth: 560 }}>
            <CardContent sx={{ p: 3 }}>
              <Typography variant="subtitle1" gutterBottom fontWeight={600}>
                Waiver Status
              </Typography>
              <FormHelperText sx={{ mb: 2 }}>
                Waived courses receive 3 credit hours toward graduation (not
                counted in CGPA).
              </FormHelperText>

              <FormControlLabel
                control={
                  <Switch
                    checked={!!answers.waiver_eng102}
                    onChange={() => toggleBool("waiver_eng102")}
                  />
                }
                label="ENG102 — English waiver"
                sx={{ display: "flex", mb: 1 }}
              />
              <FormControlLabel
                control={
                  <Switch
                    checked={!!answers.waiver_mat112}
                    onChange={() => toggleBool("waiver_mat112")}
                  />
                }
                label="MAT112 — Mathematics waiver"
                sx={{ display: "flex", mb: 3 }}
              />

              <Typography variant="body2" color="text.secondary" sx={{ mb: 3 }}>
                All other choices (trails, electives, GED slots) will be
                auto-selected based on best grade. You can review them in the
                report.
              </Typography>

              {error && (
                <Alert severity="error" sx={{ mb: 2 }}>
                  {error}
                </Alert>
              )}
              {busy && <LinearProgress sx={{ mb: 2 }} />}

              <Box sx={{ display: "flex", justifyContent: "space-between" }}>
                <Button onClick={() => setStep(0)} disabled={busy}>
                  Back
                </Button>
                <Button variant="contained" onClick={handleRun} disabled={busy}>
                  {busy ? "Running…" : "Run Audit"}
                </Button>
              </Box>
            </CardContent>
          </Card>
        </Box>
      </Fade>

      {/* ── Step 2: Report ─────────────────────────────────────────────────── */}
      <Fade in={step === 2 && !!result} unmountOnExit>
        <Box
          sx={{
            display: step === 2 && result ? "block" : "none",
            maxWidth: 720,
          }}
        >
          {result && (
            <>
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

              {/* Export actions */}
              <Box sx={{ display: "flex", gap: 1, mb: 2 }}>
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

              <Grow in timeout={300}>
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
                        label="Valid credits"
                        value={String(result.total_valid_credits)}
                      />
                    </Box>
                  </CardContent>
                </Card>
              </Grow>

              {result.waived_courses.length > 0 && (
                <Grow in timeout={400}>
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
                      <Box
                        sx={{
                          mt: 1,
                          display: "flex",
                          gap: 1,
                          flexWrap: "wrap",
                        }}
                      >
                        {result.waived_courses.map((c) => (
                          <Chip key={c} label={c} size="small" color="info" />
                        ))}
                      </Box>
                    </CardContent>
                  </Card>
                </Grow>
              )}

              {result.major_electives.length > 0 && (
                <Grow in timeout={500}>
                  <Card sx={{ mb: 2 }}>
                    <CardContent>
                      <Typography variant="subtitle1" fontWeight={600}>
                        Selected Electives
                      </Typography>
                      <Box
                        sx={{
                          mt: 1,
                          display: "flex",
                          gap: 1,
                          flexWrap: "wrap",
                        }}
                      >
                        {result.major_electives.map((c) => (
                          <Chip
                            key={c}
                            label={c}
                            size="small"
                            color="primary"
                          />
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
                <Grow in timeout={600}>
                  <Card
                    sx={{
                      mb: 2,
                      border: "1px solid",
                      borderColor: "error.dark",
                    }}
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
                            <Typography
                              key={course}
                              variant="body2"
                              sx={{ mb: 0.5 }}
                            >
                              <strong>{course}:</strong> {reason}
                            </Typography>
                          ),
                        )}
                      </Box>
                    </CardContent>
                  </Card>
                </Grow>
              )}

              <Box sx={{ mt: 2, display: "flex", gap: 2 }}>
                <Button
                  variant="outlined"
                  onClick={() => {
                    setStep(0);
                    setResult(null);
                    setFile(null);
                  }}
                >
                  Run Another
                </Button>
                <Button variant="text" onClick={() => navigate("/history")}>
                  View History
                </Button>
              </Box>
            </>
          )}
        </Box>
      </Fade>

      {/* ── Snackbar ──────────────────────────────────────────────────────────── */}
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
