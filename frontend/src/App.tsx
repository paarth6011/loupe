import { useState } from "react";

import { clearToken, getToken } from "./api/client";
import DashboardPage from "./pages/DashboardPage";
import LoginPage from "./pages/LoginPage";
import StatusPage from "./pages/StatusPage";

export default function App() {
  const [authed, setAuthed] = useState<boolean>(() => !!getToken());

  // The public status page is reachable without logging in. A tiny path check
  // keeps us from pulling in a router for a single extra route.
  if (window.location.pathname.replace(/\/$/, "") === "/status") {
    return <StatusPage />;
  }

  if (!authed) {
    return <LoginPage onLogin={() => setAuthed(true)} />;
  }
  return (
    <DashboardPage
      onLogout={() => {
        clearToken();
        setAuthed(false);
      }}
    />
  );
}
