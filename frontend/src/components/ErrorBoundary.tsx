import React from "react";
import { Box, Button, Typography } from "@mui/material";
import { SANS } from "../theme";

interface State {
  hasError: boolean;
  error: Error | null;
}

export class ErrorBoundary extends React.Component<
  { children: React.ReactNode },
  State
> {
  state: State = { hasError: false, error: null };

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  render() {
    if (this.state.hasError) {
      return (
        <Box sx={{ py: 4, borderTop: "1px solid", borderColor: "divider" }}>
          <Typography variant="overline" color="text.secondary">
            Render Error
          </Typography>
          <Typography variant="h6" sx={{ mt: 0.5, mb: 1 }}>
            Something went wrong displaying this report.
          </Typography>
          <Typography
            variant="body2"
            color="text.secondary"
            sx={{
              mb: 2.5,
              fontFamily: '"Menlo", "Consolas", monospace',
              fontSize: "0.75rem",
            }}
          >
            {this.state.error?.message}
          </Typography>
          <Button
            variant="outlined"
            size="small"
            onClick={() => this.setState({ hasError: false, error: null })}
            sx={{ fontFamily: SANS }}
          >
            Try again
          </Button>
        </Box>
      );
    }
    return this.props.children;
  }
}
