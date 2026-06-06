import { useState } from "react";

import { clearToken, getToken } from "./api/client";
import DashboardPage from "./pages/DashboardPage";
import LoginPage from "./pages/LoginPage";

export default function App() {
  const [authed, setAuthed] = useState<boolean>(() => !!getToken());

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
