/**
 * ProtectedRoute.jsx
 * ==================
 * Wraps a route with auth guard.
 * Any authenticated user is allowed in; role-based access control
 * is handled per-page when needed.
 *
 * Behaviour:
 *   loading → show skeleton
 *   not authenticated → redirect to /login
 *   authenticated → render children
 */
import { Navigate } from 'react-router-dom';
import { useAuth } from '../../hooks/useAuth';
import { PageSkeleton } from '../ui/Skeleton';

export function ProtectedRoute({ children }) {
  const { isAuthenticated, loading } = useAuth();

  if (loading) return <PageSkeleton />;
  if (!isAuthenticated) return <Navigate to="/login" replace />;

  return children;
}
