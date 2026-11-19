/**
 * App.jsx
 * =======
 * Root router. Wraps everything in AuthProvider + BrowserRouter.
 *
 * Routes:
 *   /login  → Login page (public)
 *   /*      → PortalApp (any authenticated user)
 *   *       → redirect to /login
 */
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { AuthProvider } from './context/AuthContext';
import { useAuth }      from './hooks/useAuth';
import { ProtectedRoute } from './components/routing/ProtectedRoute';
import Login      from './pages/Login';
import PortalApp  from './PortalApp';

function AppRoutes() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />

      <Route path="/*" element={
        <ProtectedRoute>
          <PortalApp />
        </ProtectedRoute>
      } />

      <Route path="*" element={<Navigate to="/login" replace />} />
    </Routes>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <AppRoutes />
      </AuthProvider>
    </BrowserRouter>
  );
}
