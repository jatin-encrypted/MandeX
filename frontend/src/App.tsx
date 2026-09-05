import React from "react";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { Toaster } from "react-hot-toast";
import { AuthProvider, useAuth } from "./lib/AuthContext";
import MerchantOnboarding from "./pages/MerchantOnboarding";
import MerchantDashboard from "./pages/MerchantDashboard";
import DemoBuyerConsole from "./pages/DemoBuyerConsole";
import "./styles/tokens.css";

function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const { user, loading } = useAuth();
  if (loading) return <div className="min-h-screen bg-ink flex items-center justify-center"><p className="text-text-ink/50 text-sm">Loading…</p></div>;
  if (!user) return <Navigate to="/" replace />;
  return <>{children}</>;
}

function AppRoutes() {
  return (
    <Routes>
      <Route path="/" element={<MerchantOnboarding />} />
      <Route
        path="/dashboard"
        element={<ProtectedRoute><MerchantDashboard /></ProtectedRoute>}
      />
      {/* Primary route — used in nav links and runbook */}
      <Route path="/buyer-demo" element={<DemoBuyerConsole />} />
      {/* Legacy alias kept so any existing bookmarks still work */}
      <Route path="/demo" element={<DemoBuyerConsole />} />
    </Routes>
  );
}

export default function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Toaster
          position="top-right"
          toastOptions={{
            style: { background: "#1D2125", color: "#F4F2EA", border: "1px solid #C9A46A", borderRadius: 0 },
          }}
        />
        <AppRoutes />
      </BrowserRouter>
    </AuthProvider>
  );
}
