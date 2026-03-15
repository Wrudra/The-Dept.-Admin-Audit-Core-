import { useSearchParams } from "react-router-dom";
import { Box, Button, Typography } from "@mui/material";
import GoogleIcon from "@mui/icons-material/Google";
import { SERIF, SANS } from "../theme";

const ERROR_MESSAGES: Record<string, string> = {
  domain:
    "Only @northsouth.edu accounts are allowed. Please sign in with your NSU email.",
  auth: "Authentication failed. Please try again.",
  state: "Security check failed. Please try again.",
  session: "Session expired during login. Please try again.",
};

/** Public login page — clicking the button redirects the browser to the
 *  backend's /api/auth/login endpoint, which triggers the Google PKCE flow. */
export default function LoginPage() {
  const [params] = useSearchParams();
  const errorKey = params.get("error") ?? "";
  const errorMsg = ERROR_MESSAGES[errorKey] ?? "";

  return (
    <Box
      sx={{
        minHeight: "100vh",
        bgcolor: "background.default",
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        px: 3,
      }}
    >
      <Box sx={{ textAlign: "center", maxWidth: 400, width: "100%" }}>
        {/* Section label */}
        <Typography variant="overline" color="text.secondary">
          Student Portal
        </Typography>

        {/* Headline */}
        <Typography
          sx={{
            fontFamily: SERIF,
            fontSize: "clamp(40px, 8vw, 64px)",
            lineHeight: 1.1,
            color: "text.primary",
            mt: 1,
            mb: 5,
          }}
        >
          Sign in to
          <br />
          <em>your audit.</em>
        </Typography>

        {/* Google button */}
        <Button
          fullWidth
          component="a"
          href="/api/auth/login"
          startIcon={<GoogleIcon />}
          sx={{
            bgcolor: "text.primary",
            color: "background.default",
            border: "1px solid",
            borderColor: "text.primary",
            borderRadius: "6px",
            textTransform: "uppercase",
            letterSpacing: "0.12em",
            fontSize: "0.8125rem",
            fontWeight: 300,
            fontFamily: SANS,
            py: 1.5,
            "& .MuiButton-startIcon": { color: "inherit" },
            "&:hover": {
              bgcolor: "#e8e5e0",
              color: "background.default",
              borderColor: "#e8e5e0",
            },
          }}
        >
          Continue with Google
        </Button>

        {/* Error message */}
        {errorMsg && (
          <Typography
            variant="caption"
            sx={{ display: "block", mt: 2, color: "error.main" }}
          >
            {errorMsg}
          </Typography>
        )}

        {/* Footer */}
        <Typography
          variant="caption"
          color="text.secondary"
          sx={{ display: "block", mt: 4 }}
        >
          North South University · Degree Audit System
        </Typography>
      </Box>
    </Box>
  );
}
