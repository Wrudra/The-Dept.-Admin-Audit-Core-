import { useState } from "react";
import { Outlet, NavLink } from "react-router-dom";
import { Box, useMediaQuery, useTheme } from "@mui/material";
import { useAuthStore } from "../store/authStore";
import { SERIF, SANS } from "../theme";

const NAV = [
  { label: "Dashboard", path: "/dashboard" },
  { label: "New Audit", path: "/audit" },
  { label: "History", path: "/history" },
];

const NAV_LINK_BASE = {
  fontSize: "0.6875rem",
  letterSpacing: "0.12em",
  textTransform: "uppercase" as const,
  textDecoration: "none",
  fontFamily: SANS,
  fontWeight: 300,
  transition: "color 0.2s",
} as const;

export default function Layout() {
  const { user, logout } = useAuthStore();
  const [menuOpen, setMenuOpen] = useState(false);
  const theme = useTheme();
  const isMobile = useMediaQuery(theme.breakpoints.down("md"));

  const allNavItems = [
    ...NAV,
    ...(user?.is_admin ? [{ label: "Admin", path: "/admin" }] : []),
  ];

  return (
    <Box sx={{ minHeight: "100vh", bgcolor: "background.default" }}>
      {/* ── Fixed top navbar ─────────────────────────────────────────────────── */}
      <Box
        component="nav"
        sx={{
          position: "fixed",
          top: 0,
          left: 0,
          right: 0,
          zIndex: 100,
          height: 56,
          borderBottom: "1px solid",
          borderColor: "divider",
          bgcolor: "background.default",
          display: "flex",
          alignItems: "center",
          px: { xs: 2, md: 6 },
          justifyContent: "space-between",
        }}
      >
        {/* Logo */}
        <Box
          component={NavLink as React.ElementType}
          to="/dashboard"
          sx={{
            fontFamily: SERIF,
            fontStyle: "italic",
            fontSize: "1.125rem",
            color: "text.primary",
            textDecoration: "none",
            letterSpacing: "-0.01em",
          }}
        >
          NSU Audit
        </Box>

        {/* Desktop nav links */}
        {!isMobile && (
          <Box sx={{ display: "flex", alignItems: "center", gap: 4 }}>
            {allNavItems.map(({ label, path }) => (
              <Box
                key={path}
                component={NavLink as React.ElementType}
                to={path}
                sx={{
                  ...NAV_LINK_BASE,
                  color: "text.disabled",
                  "&:hover": { color: "text.primary" },
                  "&.active": {
                    color: "text.primary",
                    borderBottom: "1px solid",
                    borderColor: "text.primary",
                    paddingBottom: "2px",
                  },
                }}
              >
                {label}
              </Box>
            ))}

            <Box
              component="button"
              onClick={logout}
              sx={{
                ...NAV_LINK_BASE,
                background: "none",
                border: "none",
                cursor: "pointer",
                color: "text.disabled",
                padding: 0,
                "&:hover": { color: "error.main" },
              }}
            >
              Logout
            </Box>
          </Box>
        )}

        {/* Mobile hamburger */}
        {isMobile && (
          <Box
            component="button"
            aria-label="Open navigation menu"
            onClick={() => setMenuOpen(true)}
            sx={{
              background: "none",
              border: "none",
              cursor: "pointer",
              display: "flex",
              flexDirection: "column",
              gap: "5px",
              p: 1,
            }}
          >
            <Box sx={{ width: 22, height: "1px", bgcolor: "text.secondary" }} />
            <Box sx={{ width: 22, height: "1px", bgcolor: "text.secondary" }} />
            <Box sx={{ width: 22, height: "1px", bgcolor: "text.secondary" }} />
          </Box>
        )}
      </Box>

      {/* ── Mobile full-screen overlay nav ──────────────────────────────────── */}
      {menuOpen && (
        <Box
          sx={{
            position: "fixed",
            inset: 0,
            zIndex: 200,
            bgcolor: "background.default",
            display: "flex",
            flexDirection: "column",
            px: 4,
            py: 4,
            overflowY: "auto",
          }}
        >
          {/* Overlay header */}
          <Box
            sx={{
              display: "flex",
              justifyContent: "space-between",
              alignItems: "center",
              mb: 6,
            }}
          >
            <Box
              sx={{
                fontFamily: SERIF,
                fontStyle: "italic",
                fontSize: "1.125rem",
                color: "text.primary",
              }}
            >
              NSU Audit
            </Box>
            <Box
              component="button"
              aria-label="Close navigation menu"
              onClick={() => setMenuOpen(false)}
              sx={{
                background: "none",
                border: "none",
                cursor: "pointer",
                color: "text.secondary",
                fontSize: "1.5rem",
                lineHeight: 1,
                p: 0.5,
                "&:hover": { color: "text.primary" },
              }}
            >
              ×
            </Box>
          </Box>

          {/* Large serif nav links */}
          <Box sx={{ display: "flex", flexDirection: "column", gap: 2.5 }}>
            {allNavItems.map(({ label, path }) => (
              <Box
                key={path}
                component={NavLink as React.ElementType}
                to={path}
                onClick={() => setMenuOpen(false)}
                sx={{
                  fontFamily: SERIF,
                  fontSize: "clamp(28px, 8vw, 48px)",
                  textDecoration: "none",
                  color: "text.disabled",
                  lineHeight: 1.15,
                  transition: "color 0.2s",
                  "&:hover, &.active": { color: "text.primary" },
                }}
              >
                {label}
              </Box>
            ))}
          </Box>

          {/* User info + logout at bottom */}
          <Box sx={{ mt: "auto", pt: 4, borderTop: "1px solid", borderColor: "divider" }}>
            <Box
              sx={{
                fontSize: "0.6875rem",
                color: "text.disabled",
                fontFamily: SANS,
                mb: 1.5,
              }}
            >
              {user?.email}
            </Box>
            <Box
              component="button"
              onClick={logout}
              sx={{
                background: "none",
                border: "none",
                cursor: "pointer",
                ...NAV_LINK_BASE,
                color: "error.main",
                padding: 0,
                "&:hover": { color: "error.light" },
              }}
            >
              Logout
            </Box>
          </Box>
        </Box>
      )}

      {/* ── Main content ──────────────────────────────────────────────────────── */}
      <Box
        component="main"
        sx={{
          pt: "56px",
          minHeight: "100vh",
          bgcolor: "background.default",
        }}
      >
        <Box
          sx={{
            maxWidth: 1200,
            margin: "0 auto",
            px: { xs: 2, sm: 3, md: 6 },
            py: { xs: 4, md: 6 },
          }}
        >
          <Outlet />
        </Box>
      </Box>
    </Box>
  );
}
