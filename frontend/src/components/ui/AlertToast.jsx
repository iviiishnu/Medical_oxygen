/**
 * AlertToast.jsx
 * ==============
 * Toast item with an optional "View" action button.
 * Used for new alert notifications from usePortalData.
 */
import { X, AlertTriangle } from 'lucide-react';

export default function AlertToastItem({ toast, onDismiss, onAction }) {
  return (
    <div
      role="alert"
      aria-live="polite"
      className="toast-in flex items-start gap-3 px-4 py-3 rounded-xl border shadow-hover max-w-sm w-full bg-red-50 border-red-200"
    >
      <AlertTriangle size={18} className="mt-0.5 shrink-0 text-red-500" />
      <p className="flex-1 text-sm font-medium leading-snug text-red-800">{toast.message}</p>

      {onAction && (
        <button
          onClick={onAction}
          className="shrink-0 text-xs font-bold px-2.5 py-1 rounded-lg bg-red-100 text-red-700 hover:bg-red-200 transition-colors"
        >
          View
        </button>
      )}

      <button
        onClick={() => onDismiss(toast.id)}
        aria-label="Dismiss"
        className="shrink-0 opacity-50 hover:opacity-100 transition-opacity text-red-500"
      >
        <X size={15} />
      </button>
    </div>
  );
}
