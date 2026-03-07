import React, { useState } from "react";
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  Divider,
  Fade,
  FormControl,
  FormControlLabel,
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
import TuneIcon from "@mui/icons-material/Tune";
import { useNavigate } from "react-router-dom";
import { auditApi, AuditResult, AuditChoice } from "../api/client";
import AuditReport from "../components/AuditReport";

type Answers = Record<string, boolean | string>;

const STEPS = ["Upload Transcript", "Configure Choices", "Audit Report"];

export default function AuditPage() {
  const navigate = useNavigate();
  const [step, setStep] = useState(0);
  const [file, setFile] = useState<File | null>(null);
  const [program, setProgram] = useState<"CSE" | "MIC">("CSE");
  const [choices, setChoices] = useState<AuditChoice[]>([]);
  const [answers, setAnswers] = useState<Answers>({});
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

  // ── Discovery: analyze transcript and detect choices ────────────────────────
  async function handleAnalyze() {
    if (!file) return;
    setBusy(true);
    setError("");
    try {
      const { data } = await auditApi.discover(file, program);
      setChoices(data.choices);
      const defaults: Answers = {};
      for (const c of data.choices) {
        defaults[c.key] = c.selected;
      }
      setAnswers(defaults);
      setResult(data.result);
      setStep(1);
    } catch (err: unknown) {
      const msg =
        (err as { response?: { data?: { detail?: string } } })?.response?.data
          ?.detail ?? "Analysis failed. Please try again.";
      setError(msg);
      showSnack(msg, "error");
    } finally {
      setBusy(false);
    }
  }

  // ── Final audit run with user's choices ─────────────────────────────────────
  async function handleRun() {
    if (!file) return;
    setBusy(true);
    setError("");
    try {
      const { data } = await auditApi.run(file, program, answers);
      setResult(data.result);
      setChoices(data.choices);
      // Sync answers with the (possibly updated) choices
      const updated: Answers = {};
      for (const c of data.choices) {
        updated[c.key] = c.selected;
      }
      setAnswers(updated);
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

  // ── Render choice form elements ─────────────────────────────────────────────
  const ynChoices = choices.filter((c) => c.type === "yes_no");
  const pickChoices = choices.filter((c) => c.type === "pick");

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

              {error && (
                <Alert severity="error" sx={{ mt: 2 }}>
                  {error}
                </Alert>
              )}
              {busy && <LinearProgress sx={{ mt: 2 }} />}

              <Box sx={{ mt: 3, display: "flex", justifyContent: "flex-end" }}>
                <Button
                  variant="contained"
                  disabled={!file || busy}
                  onClick={handleAnalyze}
                  startIcon={<TuneIcon />}
                >
                  {busy ? "Analyzing…" : "Analyze Transcript"}
                </Button>
              </Box>
            </CardContent>
          </Card>
        </Box>
      </Fade>

      {/* ── Step 1: Configure Choices ──────────────────────────────────────── */}
      <Fade in={step === 1} unmountOnExit>
        <Box sx={{ display: step === 1 ? "block" : "none" }}>
          <Card sx={{ maxWidth: 640 }}>
            <CardContent sx={{ p: 3 }}>
              <Typography variant="subtitle1" gutterBottom fontWeight={600}>
                Audit Choices
              </Typography>
              <Typography variant="body2" color="text.secondary" sx={{ mb: 3 }}>
                The following choices were detected from your transcript. Review
                and modify them before running the final audit.
              </Typography>

              {/* ── Yes / No choices (waivers etc.) ─────────────────────────── */}
              {ynChoices.length > 0 && (
                <Box sx={{ mb: 2 }}>
                  <Typography
                    variant="overline"
                    color="text.secondary"
                    sx={{ mb: 1, display: "block" }}
                  >
                    Waivers
                  </Typography>
                  {ynChoices.map((c) => (
                    <FormControlLabel
                      key={c.key}
                      control={
                        <Switch
                          checked={!!answers[c.key]}
                          onChange={() =>
                            setAnswers((a) => ({
                              ...a,
                              [c.key]: !a[c.key],
                            }))
                          }
                        />
                      }
                      label={c.prompt}
                      sx={{ display: "flex", mb: 0.5 }}
                    />
                  ))}
                </Box>
              )}

              {/* ── Pick choices (trails, electives, GED, etc.) ────────────── */}
              {pickChoices.length > 0 && (
                <Box>
                  {ynChoices.length > 0 && <Divider sx={{ my: 2 }} />}
                  <Typography
                    variant="overline"
                    color="text.secondary"
                    sx={{ mb: 1, display: "block" }}
                  >
                    Course Selections
                  </Typography>
                  {pickChoices.map((c) => {
                    if (c.type !== "pick") return null;
                    const label = c.prompt || `Selection ${c.key}`;
                    return (
                      <FormControl
                        key={c.key}
                        fullWidth
                        size="small"
                        sx={{ mb: 2 }}
                      >
                        <InputLabel id={`lbl-${c.key}`}>{label}</InputLabel>
                        <Select
                          labelId={`lbl-${c.key}`}
                          value={(answers[c.key] as string) ?? c.selected}
                          label={label}
                          onChange={(e) =>
                            setAnswers((a) => ({
                              ...a,
                              [c.key]: e.target.value,
                            }))
                          }
                        >
                          {c.options.map((opt: string, i: number) => (
                            <MenuItem key={opt} value={opt}>
                              {c.display[i]}
                            </MenuItem>
                          ))}
                        </Select>
                      </FormControl>
                    );
                  })}
                </Box>
              )}

              {choices.length === 0 && (
                <Typography
                  variant="body2"
                  color="text.secondary"
                  sx={{ mb: 2 }}
                >
                  No interactive choices needed for this transcript. Click "Run
                  Audit" to proceed.
                </Typography>
              )}

              {error && (
                <Alert severity="error" sx={{ mb: 2 }}>
                  {error}
                </Alert>
              )}
              {busy && <LinearProgress sx={{ mb: 2 }} />}

              <Box
                sx={{
                  display: "flex",
                  justifyContent: "space-between",
                  mt: 3,
                }}
              >
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
            maxWidth: 760,
          }}
        >
          {result && (
            <>
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
                <Button
                  variant="outlined"
                  size="small"
                  startIcon={<TuneIcon />}
                  onClick={() => setStep(1)}
                >
                  Modify Choices
                </Button>
              </Box>

              <AuditReport result={result} />

              <Box sx={{ mt: 2, display: "flex", gap: 2 }}>
                <Button
                  variant="outlined"
                  onClick={() => {
                    setStep(0);
                    setResult(null);
                    setFile(null);
                    setChoices([]);
                    setAnswers({});
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
