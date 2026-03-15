import {
  Box,
  Card,
  CardContent,
  Chip,
  Divider,
  Grow,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Typography,
} from "@mui/material";
import CheckCircleIcon from "@mui/icons-material/CheckCircle";
import WarningAmberIcon from "@mui/icons-material/WarningAmber";
import { AuditResult, CourseDetail, MinorProgram } from "../api/client";
import { SERIF } from "../theme";

interface Props {
  result: AuditResult;
}

// ── Helpers ──────────────────────────────────────────────────────────────────

function Stat({
  label,
  value,
  sub,
}: {
  label: string;
  value: string;
  sub?: string;
}) {
  return (
    <Box sx={{ minWidth: 100 }}>
      <Typography variant="overline" color="text.secondary" sx={{ display: "block" }}>
        {label}
      </Typography>
      <Typography
        variant="h6"
        sx={{ lineHeight: 1.2, fontFamily: SERIF, mt: 0.25 }}
      >
        {value}
      </Typography>
      {sub && (
        <Typography variant="caption" color="text.secondary">
          {sub}
        </Typography>
      )}
    </Box>
  );
}

function SectionCard({
  title,
  timeout,
  children,
}: {
  title: string;
  timeout: number;
  children: React.ReactNode;
}) {
  return (
    <Grow in timeout={timeout}>
      <Card sx={{ mb: 2 }}>
        <CardContent>
          <Typography variant="overline" color="text.secondary" gutterBottom>
            {title}
          </Typography>
          <Divider sx={{ mb: 1.5 }} />
          {children}
        </CardContent>
      </Card>
    </Grow>
  );
}

// ── Course tables ─────────────────────────────────────────────────────────────

function CourseTable({
  rows,
  columns,
}: {
  rows: CourseDetail[];
  columns: Array<{
    key: keyof CourseDetail | "label_or_reason";
    label: string;
  }>;
}) {
  return (
    <TableContainer sx={{ maxHeight: 360, overflowY: "auto" }}>
      <Table size="small" stickyHeader>
        <TableHead>
          <TableRow>
            {columns.map((c) => (
              <TableCell key={c.key}>{c.label}</TableCell>
            ))}
          </TableRow>
        </TableHead>
        <TableBody>
          {rows.map((row, i) => (
            <TableRow key={`${row.course}-${i}`} hover>
              {columns.map((c) => {
                if (c.key === "label_or_reason") {
                  const val = row.counted
                    ? (row.label ?? "—")
                    : (row.reason ?? "—");
                  return (
                    <TableCell key={c.key}>
                      {row.counted && row.label ? (
                        <Chip label={val} size="small" color="primary" />
                      ) : (
                        <Typography
                          variant="body2"
                          color={
                            row.counted ? "text.primary" : "text.secondary"
                          }
                        >
                          {val}
                        </Typography>
                      )}
                    </TableCell>
                  );
                }
                const val = row[c.key];
                return (
                  <TableCell key={c.key}>
                    <Typography variant="body2">
                      {val === null || val === undefined ? "—" : String(val)}
                    </Typography>
                  </TableCell>
                );
              })}
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </TableContainer>
  );
}

// ── Main component ────────────────────────────────────────────────────────────

export default function AuditReport({ result }: Props) {
  const {
    program,
    cgpa,
    credit_completed,
    required_credits,
    credit_passed,
    credit_counted,
    total_grade_points,
    academic_standing,
    waived_courses,
    waiver_notes,
    major_electives,
    open_elective,
    free_electives,
    prereq_failures,
    deficiency,
    per_course_detail,
    minor_programs,
  } = result;

  const eligible = deficiency?.eligible ?? credit_completed >= required_credits;
  const probation = deficiency?.probation ?? false;

  const countedRows = per_course_detail.filter((r) => r.counted);
  const notCountedRows = per_course_detail.filter((r) => !r.counted);

  const statusColor = eligible
    ? "success.main"
    : probation
      ? "error.main"
      : "warning.main";

  const statusText = eligible ? "Eligible" : "Not Eligible";
  const statusSub = eligible
    ? "for graduation"
    : deficiency?.credit_shortfall
      ? `${deficiency.credit_shortfall.toFixed(1)} credit(s) below required ${required_credits}`
      : "requirements not met";

  return (
    <Box>
      {/* 1. Typographic eligibility band */}
      <Box
        sx={{
          borderTop: "1px solid",
          borderBottom: "1px solid",
          borderColor: "divider",
          py: 4,
          mb: 3,
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          gap: 3,
          flexWrap: "wrap",
        }}
      >
        <Box>
          <Typography
            sx={{
              fontFamily: SERIF,
              fontStyle: "italic",
              fontSize: "clamp(32px, 6vw, 52px)",
              color: statusColor,
              lineHeight: 1,
            }}
          >
            {statusText}
          </Typography>
          <Typography
            variant="body2"
            color="text.secondary"
            sx={{ mt: 0.75 }}
          >
            {statusSub}
          </Typography>
        </Box>
        <Box sx={{ textAlign: { xs: "left", sm: "right" } }}>
          <Typography variant="overline" color="text.secondary">
            CGPA
          </Typography>
          <Typography
            variant="h4"
            sx={{ fontFamily: SERIF, lineHeight: 1.1 }}
          >
            {cgpa.toFixed(2)}
          </Typography>
          <Typography variant="caption" color="text.secondary">
            {credit_completed} / {required_credits} credits
          </Typography>
        </Box>
      </Box>

      {/* 2. Summary */}
      <Grow in timeout={300}>
        <Card sx={{ mb: 2 }}>
          <CardContent>
            <Typography variant="overline" color="text.secondary" gutterBottom>
              Summary
            </Typography>
            <Divider sx={{ mb: 2 }} />
            <Box sx={{ display: "flex", flexWrap: "wrap", gap: 3, mb: 2 }}>
              <Stat label="Program" value={program} />
              <Stat
                label="CGPA"
                value={cgpa.toFixed(2)}
                sub={academic_standing ?? undefined}
              />
              <Stat
                label="Credits Completed"
                value={`${credit_completed} / ${required_credits}`}
              />
              {total_grade_points != null && (
                <Stat
                  label="Grade Points"
                  value={total_grade_points.toFixed(2)}
                  sub={
                    credit_counted != null
                      ? `÷ ${credit_counted} counted`
                      : undefined
                  }
                />
              )}
            </Box>
            {(credit_passed != null || credit_counted != null) && (
              <>
                <Divider sx={{ mb: 1.5 }} />
                <Box sx={{ display: "flex", flexWrap: "wrap", gap: 3 }}>
                  {credit_passed != null && (
                    <Stat
                      label="Credit Passed"
                      value={String(credit_passed)}
                      sub="A–D passing grades"
                    />
                  )}
                  {credit_counted != null && (
                    <Stat
                      label="Credit Counted"
                      value={String(credit_counted)}
                      sub="CGPA denominator"
                    />
                  )}
                </Box>
              </>
            )}
          </CardContent>
        </Card>
      </Grow>

      {/* 3. Deficiency — missing courses by category */}
      {deficiency &&
        (deficiency.missing_mandatory.length > 0 || deficiency.probation) && (
          <Grow in timeout={380}>
            <Card
              sx={{
                mb: 2,
                border: "1px solid",
                borderColor: "warning.main",
                bgcolor: "rgba(220,180,100,0.04)",
              }}
            >
              <CardContent>
                <Typography
                  variant="overline"
                  color="warning.main"
                  gutterBottom
                >
                  Outstanding Requirements
                </Typography>
                <Divider sx={{ mb: 1.5 }} />

                {deficiency.probation && (
                  <Box
                    sx={{
                      mb: 1.5,
                      p: 1.5,
                      border: "1px solid",
                      borderColor: "error.main",
                      borderRadius: "2px",
                      color: "error.main",
                    }}
                  >
                    <Typography variant="body2">
                      CGPA Probation — CGPA is below the 2.0 minimum required
                      for graduation.
                    </Typography>
                  </Box>
                )}

                {deficiency.credit_shortfall > 0 && (
                  <Typography variant="body2" sx={{ mb: 1 }}>
                    <strong>Credit shortfall:</strong>{" "}
                    {deficiency.credit_shortfall.toFixed(1)} credit(s) below
                    required total.
                  </Typography>
                )}

                {deficiency.missing_mandatory.map(({ category, courses }) => (
                  <Box key={category} sx={{ mb: 1 }}>
                    <Typography
                      variant="body2"
                      color="text.secondary"
                      fontWeight={400}
                      gutterBottom
                    >
                      {category}
                    </Typography>
                    <Box sx={{ display: "flex", flexWrap: "wrap", gap: 0.75 }}>
                      {courses.map((c) => (
                        <Chip key={c} label={c} size="small" color="warning" />
                      ))}
                    </Box>
                  </Box>
                ))}
              </CardContent>
            </Card>
          </Grow>
        )}

      {/* 4. Waivers */}
      {waived_courses.length > 0 && (
        <Grow in timeout={450}>
          <Card sx={{ mb: 2 }}>
            <CardContent>
              <Typography variant="overline" color="text.secondary" gutterBottom>
                Waivers
              </Typography>
              {waiver_notes.length > 0 && (
                <Typography
                  variant="caption"
                  color="text.secondary"
                  sx={{ display: "block", mb: 1 }}
                >
                  {waiver_notes.join(" · ")}
                </Typography>
              )}
              <Box sx={{ display: "flex", gap: 1, flexWrap: "wrap" }}>
                {waived_courses.map((c) => (
                  <Chip key={c} label={c} size="small" color="info" />
                ))}
              </Box>
            </CardContent>
          </Card>
        </Grow>
      )}

      {/* 5. Selected electives */}
      {(major_electives.length > 0 ||
        open_elective ||
        free_electives.length > 0) && (
        <Grow in timeout={520}>
          <Card sx={{ mb: 2 }}>
            <CardContent>
              <Typography variant="overline" color="text.secondary" gutterBottom>
                Selected Electives
              </Typography>
              <Box sx={{ display: "flex", gap: 1, flexWrap: "wrap", mt: 0.5 }}>
                {major_electives.map((c) => (
                  <Chip key={c} label={c} size="small" color="primary" />
                ))}
                {open_elective && (
                  <Chip
                    label={`${open_elective} (open)`}
                    size="small"
                    color="secondary"
                  />
                )}
                {free_electives.map((c) => (
                  <Chip key={c} label={`${c} (free)`} size="small" />
                ))}
              </Box>
            </CardContent>
          </Card>
        </Grow>
      )}

      {/* 5b. Minor Programs */}
      {minor_programs && minor_programs.length > 0 && (
        <Grow in timeout={560}>
          <Card variant="outlined" sx={{ mb: 2 }}>
            <CardContent>
              <Typography variant="overline" color="text.secondary" gutterBottom>
                Minor Program(s) Detected
              </Typography>
              {minor_programs.map((mp: MinorProgram) => (
                <Box key={mp.name} sx={{ mb: 2 }}>
                  <Box
                    sx={{
                      display: "flex",
                      alignItems: "center",
                      gap: 1,
                      mb: 0.5,
                    }}
                  >
                    {mp.complete ? (
                      <CheckCircleIcon color="success" fontSize="small" />
                    ) : (
                      <WarningAmberIcon color="warning" fontSize="small" />
                    )}
                    <Typography variant="subtitle1">
                      {mp.name}
                    </Typography>
                    <Typography variant="body2" color="text.secondary">
                      — {mp.total_credits} credits
                      {mp.complete ? " ✓ COMPLETE" : ` (${mp.progress})`}
                    </Typography>
                  </Box>
                  {mp.core_courses && mp.core_courses.length > 0 && (
                    <Box sx={{ ml: 4, mb: 0.5 }}>
                      <Typography variant="caption" color="text.secondary">
                        Core:
                      </Typography>{" "}
                      {mp.core_courses.map((c) => (
                        <Chip key={c} label={c} size="small" sx={{ mr: 0.5 }} />
                      ))}
                    </Box>
                  )}
                  {mp.declared_courses.length > 0 && (
                    <Box sx={{ ml: 4, mb: 0.5 }}>
                      <Typography variant="caption" color="text.secondary">
                        Declared:
                      </Typography>{" "}
                      {mp.declared_courses.map((c) => (
                        <Chip
                          key={c}
                          label={c}
                          size="small"
                          color="primary"
                          sx={{ mr: 0.5 }}
                        />
                      ))}
                    </Box>
                  )}
                  {mp.choice_slot && (
                    <Box sx={{ ml: 4, mb: 0.5 }}>
                      <Typography variant="caption" color="text.secondary">
                        Choice ({mp.choice_slot.options.join(" / ")}):
                      </Typography>{" "}
                      {mp.choice_slot.selected ? (
                        <Chip
                          label={mp.choice_slot.selected}
                          size="small"
                          color="info"
                        />
                      ) : (
                        <Typography variant="caption" color="text.secondary">
                          not yet selected
                        </Typography>
                      )}
                    </Box>
                  )}
                  {mp.open_elective_course && (
                    <Box sx={{ ml: 4 }}>
                      <Typography variant="caption" color="text.secondary">
                        Open elective: {mp.open_elective_course}
                      </Typography>
                    </Box>
                  )}
                </Box>
              ))}
            </CardContent>
          </Card>
        </Grow>
      )}

      {/* 6. Courses counted table */}
      {countedRows.length > 0 && (
        <SectionCard
          title={`Courses Counted — ${countedRows.length}`}
          timeout={590}
        >
          <CourseTable
            rows={countedRows}
            columns={[
              { key: "course", label: "Course" },
              { key: "credits", label: "Credits" },
              { key: "grade", label: "Grade" },
              { key: "label_or_reason", label: "Type" },
            ]}
          />
        </SectionCard>
      )}

      {/* 7. Courses not counted table */}
      {notCountedRows.length > 0 && (
        <SectionCard
          title={`Courses Not Counted — ${notCountedRows.length}`}
          timeout={660}
        >
          <CourseTable
            rows={notCountedRows}
            columns={[
              { key: "course", label: "Course" },
              { key: "grade", label: "Grade" },
              { key: "label_or_reason", label: "Reason" },
            ]}
          />
        </SectionCard>
      )}

      {/* 8. Prerequisite failures fallback (legacy results without per_course_detail) */}
      {notCountedRows.length === 0 &&
        Object.keys(prereq_failures).length > 0 && (
          <Grow in timeout={660}>
            <Card
              sx={{
                mb: 2,
                border: "1px solid",
                borderColor: "error.main",
              }}
            >
              <CardContent>
                <Typography
                  variant="overline"
                  color="error.main"
                  gutterBottom
                >
                  Prerequisite Failures
                </Typography>
                <Box>
                  {Object.entries(prereq_failures).map(([course, reason]) => (
                    <Typography key={course} variant="body2" sx={{ mb: 0.5 }}>
                      <strong>{course}:</strong> {reason}
                    </Typography>
                  ))}
                </Box>
              </CardContent>
            </Card>
          </Grow>
        )}
    </Box>
  );
}
