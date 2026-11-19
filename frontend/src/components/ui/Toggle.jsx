/**
 * components/ui/Toggle.jsx
 * ========================
 * Reusable toggle switch.
 * Track: 44×24px (w-11 h-6), rounded-full, overflow hidden.
 * Knob: 20×20px, white, slides right when on.
 * Blue when on, grey when off. Knob never escapes the track.
 */
export function Toggle({ checked, onChange, disabled }) {
  return (
    <button
      type="button"
      onClick={() => !disabled && onChange(!checked)}
      disabled={disabled}
      className="relative w-11 h-6 rounded-full overflow-hidden transition-colors shrink-0 disabled:opacity-40 disabled:cursor-not-allowed"
      style={{ background: checked ? '#2F80ED' : '#CBD5E1' }}
      aria-checked={checked}
      role="switch"
    >
      <span
        className="absolute rounded-full bg-white transition-transform"
        style={{
          top: '2px',
          left: '2px',
          width: '20px',
          height: '20px',
          transform: checked ? 'translateX(20px)' : 'translateX(0)',
          boxShadow: '0 1px 3px rgba(0,0,0,0.2)',
        }}
      />
    </button>
  );
}
