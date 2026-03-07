import React, { useState, useMemo, useRef, useCallback } from "react";
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  Chip,
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
import GavelIcon from "@mui/icons-material/Gavel";
import SchoolIcon from "@mui/icons-material/School";
import AltRouteIcon from "@mui/icons-material/AltRoute";
import MenuBookIcon from "@mui/icons-material/MenuBook";
import { useNavigate } from "react-router-dom";
import {
  auditApi,
  AuditResult,
  AuditChoice,
  AuditChoicePick,
} from "../api/client";
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
  const [rediscovering, setRediscovering] = useState(false);
  const rediscoverAbort = useRef<AbortController | null>(null);

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

  // ── Re-discover choices when a trail selection changes ──────────────────────
  const handleTrailChange = useCallback(
    async (key: string, value: string) => {
      // Update local answer immediately for responsive UI
      const nextAnswers = { ...answers, [key]: value };
      setAnswers(nextAnswers);

      if (!file) return;

      // Cancel any in-flight re-discovery
      rediscoverAbort.current?.abort();
      const ctrl = new AbortController();
      rediscoverAbort.current = ctrl;

      setRediscovering(true);
      try {
        // Only send trail answers so the engine re-derives trail courses
        const trailAnswers: Record<string, unknown> = {};
        for (const c of choices) {
          if (c.type === "pick" && c.group === "trail") {
            trailAnswers[c.key] = c.key === key ? value : (nextAnswers[c.key] ?? c.selected);
          }
        }
        const { data } = await auditApi.rediscover(file, program, trailAnswers);
        if (ctrl.signal.aborted) return;

        setChoices(data.choices);
        // Merge: keep existing non-trail-course answers, reset trail_course to new defaults
        const merged: Answers = {};
        for (const c of data.choices) {
          if (c.type === "pick" && (c.group === "trail_course" || c.group === "open_elective")) {
            merged[c.key] = c.selected; // reset to new defaults
          } else {
            merged[c.key] = nextAnswers[c.key] ?? c.selected;
          }
        }
        setAnswers(merged);
      } catch {
        // Silently ignore aborted requests
      } finally {
        if (!ctrl.signal.aborted) setRediscovering(false);
      }
    },
    [answers, choices, file, program],
  );

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

  // ── Organize choices into grouped sections ──────────────────────────────────
  const ynChoices = choices.filter((c) => c.type === "yes_no");

  const picksByGroup = useMemo(() => {
    const groups: Record<string, AuditChoicePick[]> = {};
    for (const c of choices) {
      if (c.type !== "pick") continue;
      const g = c.group || "other";
      (groups[g] ??= []).push(c);
    }
    return groups;
  }, [choices]);

  // Group metadata for display
  const GROUP_META: Record<
    string,
    { title: string; subtitle: string; icon: React.ReactNode }
  > = {
    ged_core: {
      title: "GED / University Core Slots",
      subtitle:
        "You passed multiple courses that fill the same GED slot. Choose which one to count.",
      icon: <SchoolIcon />,
    },
    mic_core: {
      title: "MIC Core Choice Slots",
      subtitle:
        "Choose which course fills each core slot (language, humanities, social sciences, science pair).",
      icon: <SchoolIcon />,
    },
    trail: {
      title: "Trail Selection",
      subtitle:
        "Select your primary and secondary specialization trails. Course options below will update accordingly.",
      icon: <AltRouteIcon />,
    },
    trail_course: {
      title: "Trail Courses",
      subtitle:
        "Pick the specific courses to count from your selected trails.",
      icon: <MenuBookIcon />,
    },
    open_elective: {
      title: "Open Elective",
      subtitle:
        "Choose one open elective from remaining trail courses or outside-curriculum NSU courses.",
      icon: <MenuBookIcon />,
    },
    major_elective: {
      title: "Major Electives",
      subtitle: "Select your major elective courses.",
      icon: <MenuBookIcon />,
    },
    free_elective: {
      title: "Free Electives",
      subtitle: "Select your free elective courses.",
      icon: <MenuBookIcon />,
    },
    other: {
      title: "Other Selections",
      subtitle: "Additional course selections.",
      icon: <MenuBookIcon />,
    },
  };

  // ── Trail sections: pair each "trail" pick with its subsequent "trail_course" picks
  const trailSections = useMemo(() => {
    const sections: { trailPick: AuditChoicePick; coursePicks: AuditChoicePick[] }[] = [];
    const allPicks = choices.filter(
      (c): c is AuditChoicePick => c.type === "pick",
    );
    let current: (typeof sections)[number] | null = null;
    for (const p of allPicks) {
      if (p.group === "trail") {
        current = { trailPick: p, coursePicks: [] };
        sections.push(current);
      } else if (p.group === "trail_course" && current) {
        current.coursePicks.push(p);
      }
    }
    return sections;
  }, [choices]);

  // ── Courses selected in trail_course dropdowns (exclude from open elective)
  const trailCourseSelected = useMemo(() => {
    const set = new Set<string>();
    for (const sec of trailSections) {
      for (const cp of sec.coursePicks) {
        const val = (answers[cp.key] as string) ?? cp.selected;
        if (val) set.add(val);
      }
    }
    return set;
  }, [trailSections, answers]);

  // ── Render a simple group card (GED, open elective, etc.) ─────────────────
  function renderGroupCard(g: string) {
    const picks = picksByGroup[g];
    if (!picks?.length) return null;
    const meta = GROUP_META[g] ?? GROUP_META.other;
    return (
      <Card key={g} variant="outlined">
        <CardContent sx={{ p: 2.5, "&:last-child": { pb: 2.5 } }}>
          <Box
            sx={{ display: "flex", alignItems: "center", gap: 1, mb: 0.5 }}
          >
            <Box sx={{ color: "primary.main", display: "flex" }}>
              {meta.icon}
            </Box>
            <Typography variant="subtitle1" fontWeight={600}>
              {meta.title}
            </Typography>
            <Chip
              label={`${picks.length}`}
              size="small"
              variant="outlined"
              sx={{ ml: "auto" }}
            />
          </Box>
          <Typography
            variant="body2"
            color="text.secondary"
            sx={{ mb: 2 }}
          >
            {meta.subtitle}
          </Typography>
          {picks.map(renderPickDropdown)}
        </CardContent>
      </Card>
    );
  }

  // ── Render a pick dropdown (generic, no sibling filtering) ────────────────
  function renderPickDropdown(c: AuditChoicePick) {
    const selVal = (answers[c.key] as string) ?? c.selected;
    return (
      <FormControl key={c.key} fullWidth size="small" sx={{ mb: 2 }}>
        <InputLabel id={`lbl-${c.key}`}>{c.label}</InputLabel>
        <Select
          labelId={`lbl-${c.key}`}
          value={selVal}
          label={c.label}
          onChange={(e) =>
            setAnswers((a) => ({ ...a, [c.key]: e.target.value }))
          }
        >
          {c.options.map((opt: string, i: number) => (
            <MenuItem key={opt} value={opt}>
              {c.display[i]}
            </MenuItem>
          ))}
        </Select>
        {c.options.length > 1 && (
          <Typography
            variant="caption"
            color="text.secondary"
            sx={{ mt: 0.25, ml: 0.5 }}
          >
            {c.options.length} options available
          </Typography>
        )}
      </FormControl>
    );
  }

  // ── Render a trail-course dropdown that filters out sibling selections ────
  function renderTrailCourseDropdown(
    c: AuditChoicePick,
    siblingKeys: string[],
  ) {
    const selVal = (answers[c.key] as string) ?? c.selected;
    const siblingSelected = new Set(
      siblingKeys
        .filter((k) => k !== c.key)
        .map((k) => answers[k] as string)
        .filter(Boolean),
    );
    const availableOpts = c.options.filter(
      (opt) => opt === selVal || !siblingSelected.has(opt),
    );
    return (
      <FormControl key={c.key} fullWidth size="small" sx={{ mb: 2 }}>
        <InputLabel id={`lbl-${c.key}`}>{c.label}</InputLabel>
        <Select
          labelId={`lbl-${c.key}`}
          value={selVal}
          label={c.label}
          onChange={(e) =>
            setAnswers((a) => ({ ...a, [c.key]: e.target.value }))
          }
        >
          {availableOpts.map((opt) => (
            <MenuItem key={opt} value={opt}>
              {c.display[c.options.indexOf(opt)]}
            </MenuItem>
          ))}
        </Select>
        {availableOpts.length > 1 && (
          <Typography
            variant="caption"
            color="text.secondary"
            sx={{ mt: 0.25, ml: 0.5 }}
          >
            {availableOpts.length} options available
          </Typography>
        )}
      </FormControl>
    );
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
        <Box
          sx={{
            display: step === 1 ? "flex" : "none",
            flexDirection: "column",
            gap: 2,
            maxWidth: 680,
          }}
        >
          {/* Header */}
          <Typography variant="h6" fontWeight={600}>
            Configure Audit Choices
          </Typography>
          <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
            Review and adjust the choices detected from your transcript before
            running the final audit.
          </Typography>

          {/* ── Waivers card ──────────────────────────────────────────────── */}
          {ynChoices.length > 0 && (
            <Card variant="outlined">
              <CardContent sx={{ p: 2.5, "&:last-child": { pb: 2.5 } }}>
                <Box sx={{ display: "flex", alignItems: "center", gap: 1, mb: 1 }}>
                  <GavelIcon fontSize="small" color="primary" />
                  <Typography variant="subtitle1" fontWeight={600}>
                    Waivers
                  </Typography>
                </Box>
                <Typography
                  variant="body2"
                  color="text.secondary"
                  sx={{ mb: 1.5 }}
                >
                  Waived courses count toward Credit Completed but not toward
                  CGPA.
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
                    label={
                      <Typography variant="body2">{c.prompt}</Typography>
                    }
                    sx={{ display: "flex", mb: 0.5, ml: 0 }}
                  />
                ))}
              </CardContent>
            </Card>
          )}

          {/* ── GED / MIC core cards ────────────────────────────────────── */}
          {renderGroupCard("ged_core")}
          {renderGroupCard("mic_core")}

          {/* ── Trail sections (trail selection → course cards) ────────────── */}
          {trailSections.map((section) => {
            const isPrimary = section.trailPick.label
              .toLowerCase()
              .includes("primary");
            const trailName =
              (answers[section.trailPick.key] as string) ??
              section.trailPick.selected;
            const sectionLabel = isPrimary
              ? "Primary Trail"
              : "Secondary Trail";

            return (
              <React.Fragment key={section.trailPick.key}>
                {/* ── Trail name selection card ──────────────────────────── */}
                <Card variant="outlined">
                  <CardContent
                    sx={{ p: 2.5, "&:last-child": { pb: 2.5 } }}
                  >
                    <Box
                      sx={{
                        display: "flex",
                        alignItems: "center",
                        gap: 1,
                        mb: 0.5,
                      }}
                    >
                      <Box
                        sx={{ color: "primary.main", display: "flex" }}
                      >
                        <AltRouteIcon />
                      </Box>
                      <Typography variant="subtitle1" fontWeight={600}>
                        {sectionLabel}
                      </Typography>
                    </Box>
                    <Typography
                      variant="body2"
                      color="text.secondary"
                      sx={{ mb: 2 }}
                    >
                      {isPrimary
                        ? "Select your primary specialization trail. Course options will appear after selection."
                        : "Select your secondary specialization trail."}
                    </Typography>
                    <FormControl fullWidth size="small">
                      <InputLabel id={`lbl-${section.trailPick.key}`}>
                        {section.trailPick.label}
                      </InputLabel>
                      <Select
                        labelId={`lbl-${section.trailPick.key}`}
                        value={trailName}
                        label={section.trailPick.label}
                        onChange={(e) =>
                          handleTrailChange(
                            section.trailPick.key,
                            e.target.value as string,
                          )
                        }
                      >
                        {section.trailPick.options.map((opt: string) => (
                          <MenuItem key={opt} value={opt}>
                            {opt}
                          </MenuItem>
                        ))}
                      </Select>
                    </FormControl>
                    {trailName && (
                      <Chip
                        label={trailName}
                        color="primary"
                        size="small"
                        sx={{ mt: 1 }}
                      />
                    )}
                  </CardContent>
                </Card>

                {/* ── Trail courses card (appears after trail selection) ─── */}
                {trailName && section.coursePicks.length > 0 && (
                  <Card variant="outlined">
                    <CardContent
                      sx={{ p: 2.5, "&:last-child": { pb: 2.5 } }}
                    >
                      <Box
                        sx={{
                          display: "flex",
                          alignItems: "center",
                          gap: 1,
                          mb: 0.5,
                        }}
                      >
                        <Box
                          sx={{ color: "primary.main", display: "flex" }}
                        >
                          <MenuBookIcon />
                        </Box>
                        <Typography variant="subtitle1" fontWeight={600}>
                          {sectionLabel} Courses — {trailName}
                        </Typography>
                        <Chip
                          label={`${section.coursePicks.length}`}
                          size="small"
                          variant="outlined"
                          sx={{ ml: "auto" }}
                        />
                      </Box>
                      <Typography
                        variant="body2"
                        color="text.secondary"
                        sx={{ mb: 2 }}
                      >
                        Pick courses from your{" "}
                        {isPrimary ? "primary" : "secondary"} trail.
                        Already-selected courses are removed from subsequent
                        dropdowns.
                      </Typography>
                      {rediscovering && <LinearProgress sx={{ mb: 2 }} />}
                      {section.coursePicks.map((c) =>
                        renderTrailCourseDropdown(
                          c,
                          section.coursePicks.map((s) => s.key),
                        ),
                      )}
                    </CardContent>
                  </Card>
                )}
              </React.Fragment>
            );
          })}

          {/* ── Open elective card (filters out trail-course selections) ──── */}
          {(() => {
            const oePicks = picksByGroup["open_elective"];
            if (!oePicks?.length) return null;
            const meta = GROUP_META["open_elective"];
            return (
              <Card variant="outlined">
                <CardContent sx={{ p: 2.5, "&:last-child": { pb: 2.5 } }}>
                  <Box
                    sx={{
                      display: "flex",
                      alignItems: "center",
                      gap: 1,
                      mb: 0.5,
                    }}
                  >
                    <Box sx={{ color: "primary.main", display: "flex" }}>
                      {meta.icon}
                    </Box>
                    <Typography variant="subtitle1" fontWeight={600}>
                      {meta.title}
                    </Typography>
                  </Box>
                  <Typography
                    variant="body2"
                    color="text.secondary"
                    sx={{ mb: 2 }}
                  >
                    {meta.subtitle}
                  </Typography>
                  {rediscovering && <LinearProgress sx={{ mb: 2 }} />}
                  {oePicks.map((c) => {
                    const selVal =
                      (answers[c.key] as string) ?? c.selected;
                    const filteredOpts = c.options.filter(
                      (opt) =>
                        opt === selVal || !trailCourseSelected.has(opt),
                    );
                    return (
                      <FormControl
                        key={c.key}
                        fullWidth
                        size="small"
                        sx={{ mb: 2 }}
                      >
                        <InputLabel id={`lbl-${c.key}`}>
                          {c.label}
                        </InputLabel>
                        <Select
                          labelId={`lbl-${c.key}`}
                          value={selVal}
                          label={c.label}
                          onChange={(e) =>
                            setAnswers((a) => ({
                              ...a,
                              [c.key]: e.target.value,
                            }))
                          }
                        >
                          {filteredOpts.map((opt) => (
                            <MenuItem key={opt} value={opt}>
                              {c.display[c.options.indexOf(opt)]}
                            </MenuItem>
                          ))}
                        </Select>
                        {filteredOpts.length > 1 && (
                          <Typography
                            variant="caption"
                            color="text.secondary"
                            sx={{ mt: 0.25, ml: 0.5 }}
                          >
                            {filteredOpts.length} options available
                          </Typography>
                        )}
                      </FormControl>
                    );
                  })}
                </CardContent>
              </Card>
            );
          })()}

          {/* ── Major / Free elective cards (with sibling filtering) ──────── */}
          {(() => {
            const groups = ["major_elective", "free_elective"] as const;
            return groups.map((g) => {
              const picks = picksByGroup[g];
              if (!picks?.length) return null;
              const meta = GROUP_META[g] ?? GROUP_META.other;
              const siblingKeys = picks.map((p) => p.key);
              return (
                <Card key={g} variant="outlined">
                  <CardContent sx={{ p: 2.5, "&:last-child": { pb: 2.5 } }}>
                    <Box
                      sx={{
                        display: "flex",
                        alignItems: "center",
                        gap: 1,
                        mb: 0.5,
                      }}
                    >
                      <Box sx={{ color: "primary.main", display: "flex" }}>
                        {meta.icon}
                      </Box>
                      <Typography variant="subtitle1" fontWeight={600}>
                        {meta.title}
                      </Typography>
                      <Chip
                        label={`${picks.length}`}
                        size="small"
                        variant="outlined"
                        sx={{ ml: "auto" }}
                      />
                    </Box>
                    <Typography
                      variant="body2"
                      color="text.secondary"
                      sx={{ mb: 2 }}
                    >
                      {meta.subtitle} Already-selected courses are removed
                      from subsequent dropdowns.
                    </Typography>
                    {picks.map((c) => {
                      const selVal =
                        (answers[c.key] as string) ?? c.selected;
                      const siblingSelected = new Set(
                        siblingKeys
                          .filter((k) => k !== c.key)
                          .map((k) => answers[k] as string)
                          .filter(Boolean),
                      );
                      const filteredOpts = c.options.filter(
                        (opt) =>
                          opt === selVal || !siblingSelected.has(opt),
                      );
                      return (
                        <FormControl
                          key={c.key}
                          fullWidth
                          size="small"
                          sx={{ mb: 2 }}
                        >
                          <InputLabel id={`lbl-${c.key}`}>
                            {c.label}
                          </InputLabel>
                          <Select
                            labelId={`lbl-${c.key}`}
                            value={selVal}
                            label={c.label}
                            onChange={(e) =>
                              setAnswers((a) => ({
                                ...a,
                                [c.key]: e.target.value,
                              }))
                            }
                          >
                            {filteredOpts.map((opt) => (
                              <MenuItem key={opt} value={opt}>
                                {c.display[c.options.indexOf(opt)]}
                              </MenuItem>
                            ))}
                          </Select>
                          {filteredOpts.length > 1 && (
                            <Typography
                              variant="caption"
                              color="text.secondary"
                              sx={{ mt: 0.25, ml: 0.5 }}
                            >
                              {filteredOpts.length} options available
                            </Typography>
                          )}
                        </FormControl>
                      );
                    })}
                  </CardContent>
                </Card>
              );
            });
          })()}
          {renderGroupCard("other")}

          {/* No choices at all */}
          {choices.length === 0 && (
            <Card variant="outlined">
              <CardContent>
                <Typography variant="body2" color="text.secondary">
                  No interactive choices needed for this transcript. Click "Run
                  Audit" to proceed.
                </Typography>
              </CardContent>
            </Card>
          )}

          {error && (
            <Alert severity="error" sx={{ mb: 1 }}>
              {error}
            </Alert>
          )}
          {busy && <LinearProgress sx={{ mb: 1 }} />}

          <Box
            sx={{ display: "flex", justifyContent: "space-between", mt: 1 }}
          >
            <Button onClick={() => setStep(0)} disabled={busy || rediscovering}>
              Back
            </Button>
            <Button variant="contained" onClick={handleRun} disabled={busy || rediscovering}>
              {busy ? "Running…" : rediscovering ? "Updating…" : "Run Audit"}
            </Button>
          </Box>
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
