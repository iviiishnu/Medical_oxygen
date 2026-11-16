module.exports = ({ config }) => {
  return {
    ...config,
    extra: {
      ...config.extra,
      o2VisionPort: Number(process.env.O2_VISION_PORT) || 8765,
      // Public API address only. DATABASE_URL and AUTH_SECRET stay on the server.
      o2BackendUrl: process.env.O2_BACKEND_URL || config.extra?.o2BackendUrl || '',
    },
  };
};
