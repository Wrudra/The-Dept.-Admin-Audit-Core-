import { useEffect, useState } from "react";
import {
  Box,
  Card,
  CardActionArea,
  CardContent,
  Chip,
  Fade,
  Grow,
  Skeleton,
  Typography,
} from "@mui/material";
import { useNavigate } from "react-router-dom";
import { historyApi, HistoryRun } from "../api/client";

export default function HistoryPage() {
  const navigate = useNavigate();
  const [runs, setRuns] = useState<HistoryRun[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    historyApi
      .list({ limit: 50 })
      .then(({ data }) => setRuns(data.runs))
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

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
                <CardActionArea onClick={() => navigate(`/history/${r.run_id}`)}>
                  <CardContent
                    sx={{
                      display: "flex",
                      alignItems: "center",
                      gap: 2,
                      py: "12px !important",
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
                      color={
                        r.source === "mcp"
                          ? "secondary"
                          : r.source === "cli"
                            ? "warning"
                            : "info"
                      }
                      variant="outlined"
                    />

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
              </Card>
            </Grow>
          ))
        )}
      </Box>
    </Fade>
  );
}
