import { AuthProvider, useAuth } from "./auth";
import Login from "./components/Login";
import Shell from "./components/Shell";

function Gate() {
  const auth = useAuth();
  if (auth.status === "loading") return <div className="login"><p className="muted" role="status">Loading…</p></div>;
  if (auth.status === "anon") return <Login />;
  return <Shell />;
}

export default function App() {
  return (
    <AuthProvider>
      <Gate />
    </AuthProvider>
  );
}
