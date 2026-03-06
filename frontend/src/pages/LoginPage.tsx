import { useSearchParams } from "react-router-dom";
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  Collapse,
  Grow,
  Typography,
} from "@mui/material";
import ErrorOutlineIcon from "@mui/icons-material/ErrorOutline";
import GoogleIcon from "@mui/icons-material/Google";
import SchoolIcon from "@mui/icons-material/School";

const ERROR_MESSAGES: Record<string, string> = {
  domain:
    "Only @northsouth.edu accounts are allowed. Please sign in with your NSU email.",
  auth: "Authentication failed. Please try again.",
  state: "Security check failed. Please try again.",
  session: "Session expired during login. Please try again.",
};

/** Public login page — clicking "Sign in" redirects the browser to the
 *  backend's /api/auth/login endpoint, which triggers the Google PKCE flow. */
export default function LoginPage() {
  const [params] = useSearchParams();
  const errorKey = params.get("error") ?? "";
  const errorMsg = ERROR_MESSAGES[errorKey] ?? "";

  return (
    <Box
      sx={{
        minHeight: "100vh",
        background:
          "linear-gradient(135deg, #0d1117 0%, #161b22 50%, #0d1117 100%)",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
      }}
    >
      <Grow in timeout={500}>
        <Card sx={{ maxWidth: 420, width: "100%", mx: 2, boxShadow: 8 }}>
          <CardContent sx={{ p: 4, textAlign: "center" }}>
            <SchoolIcon sx={{ fontSize: 48, color: "primary.main", mb: 1 }} />
            <Typography variant="h5" gutterBottom fontWeight={700}>
              NSU Audit
            </Typography>
            <Typography variant="body2" color="text.secondary" sx={{ mb: 3 }}>
              Sign in with your North South University email to continue.
            </Typography>

            <Collapse in={!!errorMsg} unmountOnExit>
              <Alert
                severity="error"
                icon={<ErrorOutlineIcon />}
                sx={{
                  mb: 3,
                  textAlign: "left",
                  borderRadius: 2,
                  "& .MuiAlert-message": { fontWeight: 500 },
                }}
              >
                {errorMsg}
              </Alert>
            </Collapse>

            <Button
              variant="contained"
              size="large"
              fullWidth
              startIcon={<GoogleIcon />}
              href="/api/auth/login"
              sx={{
                py: 1.5,
                textTransform: "none",
                fontSize: "1rem",
                transition: "transform 0.15s",
                "&:hover": { transform: "translateY(-2px)" },
              }}
            >
              Sign in with Google
            </Button>

            <Typography
              variant="caption"
              color="text.secondary"
              sx={{ display: "block", mt: 3 }}
            >
              Only <strong>@northsouth.edu</strong> accounts are permitted.
            </Typography>
          </CardContent>
        </Card>
      </Grow>
    </Box>
  );
}
