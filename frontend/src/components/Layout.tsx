import { Outlet, NavLink } from "react-router-dom";
import {
  Box,
  Drawer,
  Fade,
  List,
  ListItemButton,
  ListItemIcon,
  ListItemText,
  Toolbar,
  Typography,
} from "@mui/material";
import DashboardIcon from "@mui/icons-material/Dashboard";
import AssignmentIcon from "@mui/icons-material/Assignment";
import HistoryIcon from "@mui/icons-material/History";
import AdminPanelSettingsIcon from "@mui/icons-material/AdminPanelSettings";
import LogoutIcon from "@mui/icons-material/Logout";
import AccountCircleIcon from "@mui/icons-material/AccountCircle";
import { useAuthStore } from "../store/authStore";

const DRAWER_W = 220;

const NAV = [
  { label: "Dashboard", path: "/dashboard", icon: <DashboardIcon /> },
  { label: "New Audit", path: "/audit", icon: <AssignmentIcon /> },
  { label: "History", path: "/history", icon: <HistoryIcon /> },
];

export default function Layout() {
  const { user, logout } = useAuthStore();

  return (
    <Box sx={{ display: "flex", minHeight: "100vh" }}>
      {/* ── Side nav ──────────────────────────────────────────────────────── */}
      <Drawer
        variant="permanent"
        sx={{
          width: DRAWER_W,
          flexShrink: 0,
          "& .MuiDrawer-paper": {
            width: DRAWER_W,
            boxSizing: "border-box",
            bgcolor: "background.paper",
            borderRight: "1px solid rgba(255,255,255,0.08)",
          },
        }}
      >
        <Toolbar sx={{ justifyContent: "center" }}>
          <Typography
            variant="h6"
            color="primary"
            sx={{ fontWeight: 700, letterSpacing: 1 }}
          >
            NSU Audit
          </Typography>
        </Toolbar>

        <List sx={{ flexGrow: 1, pt: 0 }}>
          {NAV.map(({ label, path, icon }, i) => (
            <Fade key={path} in timeout={300 + i * 80}>
              <ListItemButton
                component={NavLink}
                to={path}
                sx={{
                  "&.active": { bgcolor: "action.selected" },
                  "&:hover": { bgcolor: "action.hover" },
                  borderRadius: 1,
                  mx: 1,
                  mb: 0.5,
                  transition: "background-color 0.2s",
                }}
              >
                <ListItemIcon sx={{ minWidth: 36, color: "primary.main" }}>
                  {icon}
                </ListItemIcon>
                <ListItemText primary={label} />
              </ListItemButton>
            </Fade>
          ))}

          {user?.is_admin && (
            <Fade in timeout={620}>
              <ListItemButton
                component={NavLink}
                to="/admin"
                sx={{
                  "&.active": { bgcolor: "action.selected" },
                  "&:hover": { bgcolor: "action.hover" },
                  borderRadius: 1,
                  mx: 1,
                  mb: 0.5,
                  transition: "background-color 0.2s",
                }}
              >
                <ListItemIcon sx={{ minWidth: 36, color: "warning.main" }}>
                  <AdminPanelSettingsIcon />
                </ListItemIcon>
                <ListItemText primary="Admin" />
              </ListItemButton>
            </Fade>
          )}
        </List>

        {/* User info + logout */}
        <Box sx={{ p: 2, borderTop: "1px solid rgba(255,255,255,0.08)" }}>
          <Box sx={{ display: "flex", alignItems: "center", gap: 1, mb: 1 }}>
            <AccountCircleIcon fontSize="small" color="disabled" />
            <Typography variant="caption" color="text.secondary" noWrap>
              {user?.email}
            </Typography>
          </Box>
          <ListItemButton
            onClick={logout}
            sx={{ borderRadius: 1, color: "error.main", p: "4px 8px" }}
          >
            <ListItemIcon sx={{ minWidth: 32, color: "error.main" }}>
              <LogoutIcon fontSize="small" />
            </ListItemIcon>
            <ListItemText
              primary="Logout"
              primaryTypographyProps={{ variant: "body2" }}
            />
          </ListItemButton>
        </Box>
      </Drawer>

      {/* ── Main content ──────────────────────────────────────────────────── */}
      <Box
        component="main"
        sx={{
          flexGrow: 1,
          p: 3,
          bgcolor: "background.default",
          overflowY: "auto",
        }}
      >
        <Outlet />
      </Box>
    </Box>
  );
}
