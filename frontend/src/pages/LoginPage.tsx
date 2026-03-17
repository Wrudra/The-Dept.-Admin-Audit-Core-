import { useSearchParams } from "react-router-dom";
import { Box, Button, Typography } from "@mui/material";
import GoogleIcon from "@mui/icons-material/Google";
import { SERIF, SANS } from "../theme";
import logoUrl from "../assets/logo.png";

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
        <Box sx={{ display: "flex", justifyContent: "center", mb: 2 }}>
          <Box
            component="img"
            src={logoUrl}
            alt="NSU Audit"
            sx={{
              width: 120,
              height: 120,
              borderRadius: "18px",
              objectFit: "contain",
              bgcolor: "background.paper",
              border: "1px solid",
              borderColor: "divider",
            }}
          />
        </Box>

        {/* Welcoming label */}
        <Typography
          variant="overline"
          sx={{
            color: "text.secondary",
            letterSpacing: "0.12em",
            textTransform: "uppercase",
            display: "block",
          }}
        >
          Welcome to NSU Audit
        </Typography>

        {/* Headline (match iOS split) */}
        <Box sx={{ mt: 1, mb: 5 }}>
          <Typography
            sx={{
              fontFamily: SERIF,
              fontSize: "clamp(40px, 8vw, 64px)",
              lineHeight: 1.1,
              color: "text.primary",
            }}
          >
            Sign in to
          </Typography>
          <Typography
            sx={{
              fontFamily: SERIF,
              fontSize: "clamp(40px, 8vw, 64px)",
              lineHeight: 1.1,
              color: "text.primary",
              fontStyle: "italic",
            }}
          >
            your audit.
          </Typography>
        </Box>

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
          Sign in with North South account
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
