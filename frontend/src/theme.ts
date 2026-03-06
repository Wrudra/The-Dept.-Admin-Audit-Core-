import { createTheme } from "@mui/material/styles";

/** Material Design 2 dark theme.
 *  Reference: https://m2.material.io/design/color/dark-theme.html
 */
const theme = createTheme({
  palette: {
    mode: "dark",
    background: {
      default: "#121212",
      paper: "#1e1e1e",
    },
    primary: {
      main: "#90CAF9", // Blue 200 — readable on dark surfaces
      contrastText: "#000000",
    },
    secondary: {
      main: "#CE93D8", // Purple 200
      contrastText: "#000000",
    },
    error: { main: "#CF6679" },
    success: { main: "#81C784" },
    warning: { main: "#FFD54F" },
  },
  shape: { borderRadius: 8 },
  typography: {
    fontFamily: '"Roboto", "Helvetica", "Arial", sans-serif',
    h5: { fontWeight: 600 },
    h6: { fontWeight: 600 },
  },
  components: {
    MuiCard: {
      styleOverrides: {
        root: { backgroundImage: "none" },
      },
    },
    MuiAppBar: {
      styleOverrides: {
        root: {
          backgroundImage: "none",
          backgroundColor: "#1e1e1e",
        },
      },
    },
    MuiButton: {
      defaultProps: { disableElevation: true },
    },
  },
});

export default theme;
