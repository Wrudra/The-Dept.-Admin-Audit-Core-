import { useEffect, useState } from "react";
import {
  Box,
  Button,
  Chip,
  Divider,
  Skeleton,
  Typography,
} from "@mui/material";
import { useNavigate } from "react-router-dom";
import { historyApi, HistoryRun } from "../api/client";

const LIMIT = 20;

export default function HistoryPage() {
  const navigate = useNavigate();
  const [runs, setRuns] = useState<HistoryRun[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [offset, setOffset] = useState(0);
  const [hasMore, setHasMore] = useState(false);

  useEffect(() => {
    setLoading(true);
    historyApi
      .list({ limit: LIMIT + 1, offset: 0 })
      .then(({ data }) => {
        if (data.runs.length > LIMIT) {
          setRuns(data.runs.slice(0, LIMIT));
          setHasMore(true);
        } else {
          setRuns(data.runs);
          setHasMore(false);
        }
        setOffset(LIMIT);
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  function loadMore() {
    setLoadingMore(true);
    historyApi
      .list({ limit: LIMIT + 1, offset })
      .then(({ data }) => {
        if (data.runs.length > LIMIT) {
          setRuns((prev) => [...prev, ...data.runs.slice(0, LIMIT)]);
          setHasMore(true);
        } else {
          setRuns((prev) => [...prev, ...data.runs]);
          setHasMore(false);
        }
        setOffset((prev) => prev + LIMIT);
      })
      .catch(() => {})
      .finally(() => setLoadingMore(false));
  }

  return (
    <Box>
      {/* Page header */}
      <Typography variant="overline" color="text.secondary">
        Audit History
      </Typography>
      <Typography variant="h5" sx={{ mt: 0.5, mb: 3, lineHeight: 1.2 }}>
        Your past
        <br />
        <em>runs.</em>
      </Typography>

      <Divider sx={{ mb: 0 }} />

      {loading ? (
        [0, 1, 2, 3, 4].map((i) => (
          <Skeleton key={i} height={64} sx={{ borderRadius: 0 }} />
        ))
      ) : runs.length === 0 ? (
        <Box sx={{ py: 4, borderBottom: "1px solid", borderColor: "divider" }}>
          <Typography variant="body2" color="text.secondary">
            No past audits.
          </Typography>
        </Box>
      ) : (
        runs.map((r) => (
          <Box
            key={r.run_id}
            onClick={() => navigate(`/history/${r.run_id}`)}
            sx={{
              position: "relative",
              display: "flex",
              alignItems: "center",
              gap: { xs: 1, sm: 2 },
              py: 1.75,
              pl: 0,
              pr: 1,
              borderBottom: "1px solid",
              borderColor: "divider",
              cursor: "pointer",
              flexWrap: { xs: "wrap", sm: "nowrap" },
              "@media (prefers-reduced-motion: no-preference)": {
                transition: "padding-left 0.35s cubic-bezier(0.16,1,0.3,1)",
                "&:hover": { pl: "20px" },
                "&:hover .row-arrow": { opacity: 1, transform: "scale(1)" },
              },
            }}
          >
            {/* Program + source chips */}
            <Box sx={{ display: "flex", gap: 1, flexShrink: 0 }}>
              <Chip label={r.program} size="small" color="primary" />
              <Chip
                label={
                  r.source === "mcp"
                    ? "MCP"
                    : r.source === "cli"
                      ? "CLI"
                      : r.source === "ios"
                        ? "iOS"
                      : "Web"
                }
                size="small"
              />
            </Box>

            {/* Filename + date */}
            <Box sx={{ flexGrow: 1, minWidth: 0 }}>
              <Typography variant="body2" noWrap>
                {r.transcript_filename ?? "uploaded transcript"}
              </Typography>
              <Typography variant="caption" color="text.secondary">
                {r.created_at.slice(0, 19).replace("T", " ")}
              </Typography>
            </Box>

            {/* CGPA + credits + status */}
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
              {r.credit_completed != null && (
                <Typography
                  variant="caption"
                  color="text.secondary"
                  sx={{ display: { xs: "none", sm: "block" } }}
                >
                  {r.credit_completed}/{r.required_credits} cr
                </Typography>
              )}
              <Chip
                label={r.status}
                size="small"
                color={r.status === "complete" ? "success" : undefined}
              />
            </Box>

            {/* Arrow */}
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
              }}
            >
              →
            </Box>
          </Box>
        ))
      )}

      {/* Load more */}
      {hasMore && (
        <Box sx={{ py: 3, textAlign: "center" }}>
          <Button
            variant="text"
            onClick={loadMore}
            disabled={loadingMore}
            sx={{ letterSpacing: "0.08em" }}
          >
            {loadingMore ? "Loading…" : "Load more"}
          </Button>
        </Box>
      )}
    </Box>
  );
}
