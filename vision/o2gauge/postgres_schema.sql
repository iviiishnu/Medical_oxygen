CREATE TABLE IF NOT EXISTS staff (
  uid TEXT PRIMARY KEY,
  email TEXT NOT NULL,
  display_name TEXT NOT NULL DEFAULT '',
  role TEXT NOT NULL DEFAULT 'staff',
  password_hash TEXT,
  is_active BOOLEAN NOT NULL DEFAULT TRUE,
  on_duty BOOLEAN NOT NULL DEFAULT TRUE,
  escalation_order INTEGER NOT NULL DEFAULT 1,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS devices (
  id TEXT PRIMARY KEY,
  name TEXT NOT NULL,
  created_by TEXT REFERENCES staff(uid),
  status TEXT NOT NULL DEFAULT 'UNKNOWN',
  alarm TEXT NOT NULL DEFAULT 'OK',
  online BOOLEAN NOT NULL DEFAULT FALSE,
  trend_falling BOOLEAN NOT NULL DEFAULT FALSE,
  battery DOUBLE PRECISION,
  last_heartbeat TIMESTAMPTZ,
  last_reading JSONB,
  low_threshold DOUBLE PRECISION NOT NULL DEFAULT 3.5,
  critical_threshold DOUBLE PRECISION NOT NULL DEFAULT 3.0,
  registration_image TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS device_gauges (
  device_id TEXT NOT NULL REFERENCES devices(id) ON DELETE CASCADE,
  number INTEGER NOT NULL,
  name TEXT NOT NULL,
  unit TEXT NOT NULL,
  kind TEXT NOT NULL,
  scale DOUBLE PRECISION NOT NULL DEFAULT 0,
  reading DOUBLE PRECISION,
  confidence_pct INTEGER NOT NULL DEFAULT 0,
  low_threshold DOUBLE PRECISION,
  critical_threshold DOUBLE PRECISION,
  ignored BOOLEAN NOT NULL DEFAULT FALSE,
  PRIMARY KEY (device_id, number)
);

CREATE TABLE IF NOT EXISTS readings (
  id BIGSERIAL PRIMARY KEY,
  device_id TEXT NOT NULL REFERENCES devices(id) ON DELETE CASCADE,
  gauge_number INTEGER NOT NULL,
  captured_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  value DOUBLE PRECISION,
  unit TEXT NOT NULL,
  status TEXT NOT NULL,
  confidence_pct INTEGER,
  payload JSONB NOT NULL
);
CREATE INDEX IF NOT EXISTS readings_device_time_idx ON readings(device_id, captured_at DESC);

CREATE TABLE IF NOT EXISTS alerts (
  id TEXT PRIMARY KEY,
  device_id TEXT NOT NULL REFERENCES devices(id) ON DELETE CASCADE,
  type TEXT NOT NULL,
  state TEXT NOT NULL DEFAULT 'OPEN',
  value DOUBLE PRECISION,
  unit TEXT NOT NULL DEFAULT 'kg/cm2',
  reason TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  acked_by TEXT REFERENCES staff(uid),
  acked_by_name TEXT,
  acked_at TIMESTAMPTZ,
  ack_reason TEXT,
  ack_resolution TEXT,
  ack_notes TEXT,
  resolved_at TIMESTAMPTZ,
  escalation_level INTEGER NOT NULL DEFAULT 0,
  last_notified_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  evidence_image TEXT
);
CREATE INDEX IF NOT EXISTS alerts_created_idx ON alerts(created_at DESC);
CREATE INDEX IF NOT EXISTS alerts_state_idx ON alerts(state, created_at DESC);
ALTER TABLE alerts ADD COLUMN IF NOT EXISTS last_notified_at TIMESTAMPTZ NOT NULL DEFAULT NOW();
ALTER TABLE staff ADD COLUMN IF NOT EXISTS display_name TEXT NOT NULL DEFAULT '';
ALTER TABLE staff ADD COLUMN IF NOT EXISTS password_hash TEXT;
ALTER TABLE staff ADD COLUMN IF NOT EXISTS is_active BOOLEAN NOT NULL DEFAULT TRUE;
ALTER TABLE staff DROP COLUMN IF EXISTS fcm_tokens;
