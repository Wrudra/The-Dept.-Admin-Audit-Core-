import { useEffect, useState } from "react";
import { Box, Chip, Divider, Skeleton, Typography } from "@mui/material";
import { useNavigate } from "react-router-dom";
import { historyApi, HistoryRun } from "../api/client";
import { useAuthStore } from "../store/authStore";
import { SERIF } from "../theme";

// Shared work-list row hover style — applied via sx on each clickable row
const rowHoverSx = {
  display: "flex",
  alignItems: "center",
  py: 2,
  pl: 0,
  pr: 1,
  borderBottom: "1px solid",
  borderColor: "divider",
  cursor: "pointer",
  "@media (prefers-reduced-motion: no-preference)": {
    transition: "padding-left 0.35s cubic-bezier(0.16,1,0.3,1)",
    "&:hover": { pl: "20px" },
    "&:hover .row-arrow": { opacity: 1, transform: "scale(1)" },
  },
} as const;

const RowArrow = () => (
  <Box
    className="row-arrow"
    aria-hidden
    sx={{
      opacity: 0,
      transform: "scale(0.8)",
      "@media (prefers-reduced-motion: no-preference)": {
        transition: "opacity 0.3s, transform 0.3s",
      },
      color: "text.secondary",
      flexShrink: 0,
      fontSize: "1rem",
      ml: 1,
    }}
  >
    →
  </Box>
);

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

  const displayName = user?.display_name ?? "";

  const QUICK_ACTIONS = [
    {
      label: "New Audit",
      sub: "Upload a transcript and run your audit",
      path: "/audit",
    },
    {
      label: "History",
      sub: "Browse past audit runs",
      path: "/history",
    },
    ...(user?.is_admin
      ? [
          {
            label: "Admin",
            sub: "Platform statistics and overview",
            path: "/admin",
          },
        ]
      : []),
  ];

  return (
    <Box>
      {/* Page header */}
      <Typography variant="overline" color="text.secondary">
        Overview
      </Typography>
      <Typography
        variant="h5"
        sx={{ mt: 0.5, mb: 3, lineHeight: 1.2 }}
      >
        Welcome back,
        <br />
          <em style={{ fontFamily: SERIF }}>{displayName}.</em>
      </Typography>

      <Divider sx={{ mb: 0 }} />

      {/* Quick actions — work-list rows */}
      {QUICK_ACTIONS.map(({ label, sub, path }) => (
        <Box key={path} onClick={() => navigate(path)} sx={rowHoverSx}>
          <Box sx={{ flexGrow: 1 }}>
            <Typography variant="body1" color="text.primary">
              {label}
            </Typography>
            <Typography variant="caption" color="text.disabled">
              {sub}
            </Typography>
          </Box>
          <RowArrow />
        </Box>
      ))}

      {/* Recent runs */}
      <Typography
        variant="overline"
        color="text.secondary"
        sx={{ display: "block", mt: 4, mb: 0 }}
      >
        Recent Runs
      </Typography>

      <Divider sx={{ mb: 0 }} />

      {loading ? (
        [0, 1, 2].map((i) => (
          <Skeleton key={i} height={60} sx={{ mb: 0, borderRadius: 0 }} />
        ))
      ) : runs.length === 0 ? (
        <Box
          sx={{
            py: 3,
            borderBottom: "1px solid",
            borderColor: "divider",
          }}
        >
          <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
            No audit runs yet.
          </Typography>
          <Box
            component="span"
            onClick={() => navigate("/audit")}
            sx={{
              fontSize: "0.8125rem",
              color: "text.secondary",
              cursor: "pointer",
              textDecoration: "underline",
              textDecorationColor: "divider",
              transition: "color 0.2s",
              "&:hover": { color: "text.primary" },
            }}
          >
            Upload your first transcript →
          </Box>
        </Box>
      ) : (
        runs.map((r) => (
          <Box
            key={r.run_id}
            onClick={() => navigate(`/history/${r.run_id}`)}
            sx={{
              ...rowHoverSx,
              flexWrap: "wrap",
              gap: 1.5,
            }}
          >
            {/* Left: chips + filename */}
            <Box
              sx={{
                display: "flex",
                alignItems: "center",
                gap: 1.5,
                flexGrow: 1,
                minWidth: 0,
              }}
            >
              <Chip label={r.program} size="small" color="primary" />
              <Chip
                label={
                  r.source === "mcp"
                    ? "MCP"
                    : r.source === "cli"
                      ? "CLI"
                      : "Web"
                }
                size="small"
              />
              <Typography variant="body2" noWrap sx={{ flexGrow: 1 }}>
                {r.transcript_filename ?? "uploaded transcript"}
              </Typography>
            </Box>

            {/* Right: CGPA + date + arrow */}
            <Box
              sx={{
                display: "flex",
                alignItems: "center",
                gap: 2,
                flexShrink: 0,
              }}
            >
              {r.cgpa != null && (
                <Typography variant="caption" color="text.secondary">
                  CGPA {r.cgpa}
                </Typography>
              )}
              <Typography variant="caption" color="text.disabled">
                {r.created_at.slice(0, 10)}
              </Typography>
              <RowArrow />
            </Box>
          </Box>
        ))
      )}
    </Box>
  );
}
