import { createTheme } from "@mui/material/styles";

const BG = "#0a0a0a";
const SURFACE = "#111111";
const SURFACE_2 = "#181818";
const FG = "#f0ede8";
const FG_MUTED = "rgba(240,237,232,0.45)";
const LINE = "rgba(240,237,232,0.14)";
const SUCCESS = "rgba(134,190,130,0.85)";
const WARN = "rgba(220,180,100,0.85)";
const DANGER = "rgba(210,100,90,0.85)";

export const SERIF = '"DM Serif Display", serif';
export const SANS = '"DM Sans", system-ui, sans-serif';

const theme = createTheme({
  palette: {
    mode: "dark",
    background: {
      default: BG,
      paper: SURFACE,
    },
    primary: {
      main: "#ffffff",
      contrastText: BG,
    },
    secondary: {
      main: FG_MUTED,
      contrastText: BG,
    },
    error: { main: DANGER },
    success: { main: SUCCESS },
    warning: { main: WARN },
    info: { main: FG_MUTED },
    text: {
      primary: FG,
      secondary: FG,
      disabled: FG_MUTED,
    },
    divider: LINE,
    action: {
      hover: SURFACE_2,
      selected: SURFACE_2,
      disabled: FG_MUTED,
      disabledBackground: "transparent",
      active: FG_MUTED,
    },
  },
  shape: { borderRadius: 2 },
  typography: {
    fontFamily: SANS,
    fontWeightLight: 200,
    fontWeightRegular: 300,
    fontWeightMedium: 400,
    fontWeightBold: 400,
    h1: { fontFamily: SERIF, fontWeight: 400, letterSpacing: "-0.02em" },
    h2: { fontFamily: SERIF, fontWeight: 400, letterSpacing: "-0.02em" },
    h3: { fontFamily: SERIF, fontWeight: 400, letterSpacing: "-0.01em" },
    h4: { fontFamily: SERIF, fontWeight: 400 },
    h5: { fontFamily: SERIF, fontWeight: 400 },
    h6: { fontFamily: SERIF, fontWeight: 400 },
    subtitle1: {
      fontFamily: SANS,
      fontWeight: 400,
      letterSpacing: "0.02em",
      fontSize: "1rem",
    },
    subtitle2: { fontFamily: SANS, fontWeight: 400, fontSize: "0.9375rem" },
    body1: {
      fontFamily: SANS,
      fontWeight: 300,
      fontSize: "1rem",
      lineHeight: 1.65,
    },
    body2: {
      fontFamily: SANS,
      fontWeight: 300,
      fontSize: "0.9375rem",
      lineHeight: 1.55,
    },
    caption: {
      fontFamily: SANS,
      fontWeight: 300,
      fontSize: "0.75rem",
      letterSpacing: "0.04em",
    },
    overline: {
      fontFamily: SANS,
      fontWeight: 300,
      fontSize: "0.6875rem",
      letterSpacing: "0.12em",
      textTransform: "uppercase" as const,
    },
    button: {
      fontFamily: SANS,
      fontWeight: 300,
      letterSpacing: "0.08em",
      textTransform: "none" as const,
      fontSize: "0.875rem",
    },
  },
  components: {
    MuiCssBaseline: {
      styleOverrides: {
        "*, *::before, *::after": { boxSizing: "border-box" },
        html: { scrollBehavior: "smooth" },
        body: {
          background: BG,
          color: FG,
          fontFamily: SANS,
          fontWeight: 300,
          overscrollBehavior: "none",
        },
        "::selection": { background: SURFACE_2, color: FG },
      },
    },

    MuiCard: {
      styleOverrides: {
        root: {
          background: SURFACE,
          backgroundImage: "none",
          border: `1px solid ${LINE}`,
          borderRadius: "2px",
          boxShadow: "none",
        },
      },
    },
    MuiCardActionArea: {
      styleOverrides: {
        root: {
          "&:hover .MuiCardActionArea-focusHighlight": { opacity: 0 },
          "&:hover": { background: SURFACE_2 },
        },
      },
    },
    MuiPaper: {
      styleOverrides: {
        root: { backgroundImage: "none", background: SURFACE },
        outlined: { border: `1px solid ${LINE}` },
      },
    },
    MuiAppBar: {
      styleOverrides: {
        root: {
          backgroundImage: "none",
          background: BG,
          borderBottom: `1px solid ${LINE}`,
          boxShadow: "none",
        },
      },
    },

    MuiButton: {
      defaultProps: { disableElevation: true },
      styleOverrides: {
        root: {
          textTransform: "none",
          borderRadius: "2px",
          fontFamily: SANS,
          fontWeight: 300,
          letterSpacing: "0.08em",
          fontSize: "0.875rem",
          "&.Mui-disabled": { opacity: 0.4 },
        },
        outlined: {
          borderColor: LINE,
          color: FG_MUTED,
          "&:hover": {
            borderColor: FG_MUTED,
            color: FG,
            background: "transparent",
          },
        },
        contained: {
          background: "transparent",
          border: `1px solid ${FG_MUTED}`,
          color: FG,
          boxShadow: "none",
          "&:hover": { background: SURFACE_2, boxShadow: "none" },
          "&.Mui-disabled": {
            background: "transparent",
            border: `1px solid ${LINE}`,
          },
        },
        text: {
          color: FG_MUTED,
          "&:hover": { color: FG, background: "transparent" },
        },
      },
    },
    MuiIconButton: {
      styleOverrides: {
        root: {
          color: FG_MUTED,
          borderRadius: "2px",
          "&:hover": { color: FG, background: SURFACE_2 },
        },
      },
    },

    MuiChip: {
      styleOverrides: {
        root: {
          borderRadius: "999px",
          fontSize: "0.6875rem",
          letterSpacing: "0.08em",
          fontFamily: SANS,
          fontWeight: 300,
          height: "auto",
          border: `1px solid ${LINE}`,
          color: FG_MUTED,
          "& .MuiChip-label": { padding: "3px 10px" },
          "&.MuiChip-colorPrimary": { borderColor: FG_MUTED, color: FG },
          "&.MuiChip-colorSuccess": { borderColor: SUCCESS, color: SUCCESS },
          "&.MuiChip-colorError": { borderColor: DANGER, color: DANGER },
          "&.MuiChip-colorWarning": { borderColor: WARN, color: WARN },
          "&.MuiChip-colorInfo": { borderColor: LINE, color: FG_MUTED },
          "&.MuiChip-colorSecondary": {
            borderColor: FG_MUTED,
            color: FG_MUTED,
          },
        },
        filled: {
          background: "transparent !important",
        },
        outlined: {
          background: "transparent",
        },
      },
    },

    MuiDivider: {
      styleOverrides: { root: { borderColor: LINE } },
    },

    MuiTableCell: {
      styleOverrides: {
        head: {
          fontFamily: SANS,
          fontSize: "0.6875rem",
          letterSpacing: "0.12em",
          textTransform: "uppercase",
          color: FG_MUTED,
          background: BG,
          borderBottom: `1px solid ${LINE}`,
          fontWeight: 300,
          padding: "10px 12px",
        },
        body: {
          fontFamily: SANS,
          fontSize: "0.875rem",
          borderBottom: `1px solid ${LINE}`,
          color: FG_MUTED,
          fontWeight: 300,
          padding: "11px 12px",
        },
        stickyHeader: { background: BG },
      },
    },
    MuiTableRow: {
      styleOverrides: {
        root: {
          "&.MuiTableRow-hover:hover": { background: SURFACE_2 },
        },
      },
    },
    MuiTableContainer: {
      styleOverrides: {
        root: {
          background: "transparent",
          "@media (max-width: 600px)": {
            overflowX: "auto",
            WebkitOverflowScrolling: "touch",
          },
        },
      },
    },

    MuiSelect: {
      styleOverrides: {
        select: {
          fontFamily: SANS,
          fontWeight: 300,
          fontSize: "0.875rem",
          color: FG,
        },
        icon: { color: FG_MUTED },
      },
    },
    MuiInputLabel: {
      styleOverrides: {
        root: {
          fontFamily: SANS,
          fontSize: "0.6875rem",
          letterSpacing: "0.10em",
          textTransform: "uppercase",
          color: FG_MUTED,
          "&.Mui-focused": { color: FG_MUTED },
        },
      },
    },
    MuiOutlinedInput: {
      styleOverrides: {
        root: {
          borderRadius: "2px",
          fontFamily: SANS,
          fontWeight: 300,
          "& .MuiOutlinedInput-notchedOutline": { borderColor: LINE },
          "&:hover .MuiOutlinedInput-notchedOutline": {
            borderColor: FG_MUTED,
          },
          "&.Mui-focused .MuiOutlinedInput-notchedOutline": {
            borderColor: FG_MUTED,
            borderWidth: "1px",
          },
        },
      },
    },
    MuiMenuItem: {
      styleOverrides: {
        root: {
          fontFamily: SANS,
          fontWeight: 300,
          fontSize: "0.875rem",
          color: FG_MUTED,
          "&:hover": { background: SURFACE_2, color: FG },
          "&.Mui-selected": { background: SURFACE_2, color: FG },
          "&.Mui-selected:hover": { background: SURFACE_2 },
        },
      },
    },
    MuiFormControlLabel: {
      styleOverrides: {
        label: {
          fontFamily: SANS,
          fontWeight: 300,
          fontSize: "0.875rem",
          color: FG_MUTED,
        },
      },
    },
    MuiSwitch: {
      styleOverrides: {
        track: { background: LINE, opacity: "1 !important" },
        thumb: { background: FG_MUTED },
        switchBase: {
          "&.Mui-checked .MuiSwitch-thumb": { background: FG },
          "&.Mui-checked + .MuiSwitch-track": {
            background: "rgba(240,237,232,0.25) !important",
            opacity: "1 !important",
          },
        },
      },
    },

    MuiSkeleton: {
      styleOverrides: {
        root: { background: SURFACE_2, borderRadius: "2px" },
      },
    },
    MuiLinearProgress: {
      styleOverrides: {
        root: { background: SURFACE_2, borderRadius: 0 },
        bar: { background: FG_MUTED },
      },
    },
    MuiCircularProgress: {
      styleOverrides: { root: { color: FG_MUTED } },
    },

    MuiAlert: {
      styleOverrides: {
        root: {
          borderRadius: "2px",
          border: `1px solid ${LINE}`,
          fontFamily: SANS,
          fontWeight: 300,
          fontSize: "0.875rem",
        },
        standardError: {
          border: `1px solid ${DANGER}`,
          color: DANGER,
          background: "rgba(210,100,90,0.06)",
          "& .MuiAlert-icon": { color: DANGER },
        },
        standardSuccess: {
          border: `1px solid ${SUCCESS}`,
          color: SUCCESS,
          background: "rgba(134,190,130,0.06)",
          "& .MuiAlert-icon": { color: SUCCESS },
        },
        standardWarning: {
          border: `1px solid ${WARN}`,
          color: WARN,
          background: "rgba(220,180,100,0.06)",
          "& .MuiAlert-icon": { color: WARN },
        },
        standardInfo: {
          border: `1px solid ${LINE}`,
          color: FG_MUTED,
          background: SURFACE,
          "& .MuiAlert-icon": { color: FG_MUTED },
        },
        filledError: {
          background: "rgba(210,100,90,0.12)",
          border: `1px solid ${DANGER}`,
          color: DANGER,
        },
        filledSuccess: {
          background: "rgba(134,190,130,0.12)",
          border: `1px solid ${SUCCESS}`,
          color: SUCCESS,
        },
      },
    },
    MuiSnackbar: {
      defaultProps: {
        anchorOrigin: { vertical: "bottom", horizontal: "center" },
      },
    },

    MuiTooltip: {
      styleOverrides: {
        tooltip: {
          background: SURFACE_2,
          border: `1px solid ${LINE}`,
          color: FG_MUTED,
          fontSize: "0.6875rem",
          borderRadius: "2px",
          fontFamily: SANS,
        },
        arrow: { color: LINE },
      },
    },

    MuiStepLabel: {
      styleOverrides: {
        label: {
          fontFamily: SANS,
          fontSize: "0.6875rem",
          letterSpacing: "0.12em",
          textTransform: "uppercase",
          color: FG_MUTED,
          "&.Mui-active": { color: `${FG} !important`, fontWeight: "300 !important" },
          "&.Mui-completed": {
            color: `${FG_MUTED} !important`,
            fontWeight: "300 !important",
          },
        },
      },
    },
    MuiStepIcon: {
      styleOverrides: {
        root: {
          color: SURFACE_2,
          "& .MuiStepIcon-text": {
            fill: FG_MUTED,
            fontFamily: SANS,
            fontSize: "0.6rem",
          },
          "&.Mui-active": {
            color: SURFACE_2,
            "& .MuiStepIcon-text": { fill: FG },
          },
          "&.Mui-completed": { color: FG_MUTED },
        },
      },
    },
    MuiStepConnector: {
      styleOverrides: { line: { borderColor: LINE } },
    },

    MuiDialog: {
      styleOverrides: {
        paper: {
          background: SURFACE,
          border: `1px solid ${LINE}`,
          borderRadius: "2px",
          boxShadow: "none",
        },
      },
    },
    MuiPopover: {
      styleOverrides: {
        paper: {
          background: SURFACE,
          border: `1px solid ${LINE}`,
          borderRadius: "2px",
          boxShadow: "none",
        },
      },
    },
    MuiMenu: {
      styleOverrides: {
        paper: {
          background: SURFACE,
          border: `1px solid ${LINE}`,
          borderRadius: "2px",
          boxShadow: "none",
        },
      },
    },
  },
});

export default theme;
