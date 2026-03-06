import { Navigate, Outlet } from "react-router-dom";
import { CircularProgress, Box } from "@mui/material";
import { useAuthStore } from "../store/authStore";

/** Redirect to /login if the user is not authenticated. */
export default function ProtectedRoute() {
  const { user, loading, checked } = useAuthStore();

  if (!checked || loading) {
    return (
      <Box sx={{ display: "flex", justifyContent: "center", mt: 10 }}>
        <CircularProgress />
      </Box>
    );
  }

  return user ? <Outlet /> : <Navigate to="/login" replace />;
}
