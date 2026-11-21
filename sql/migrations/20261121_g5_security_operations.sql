BEGIN;

CREATE TABLE IF NOT EXISTS security_events (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    category varchar(40) NOT NULL
        CHECK (category IN (
            'sms_ip_threshold',
            'captcha_failure_burst',
            'registration_enumeration',
            'blocked_ip_retry'
        )),
    severity varchar(16) NOT NULL
        CHECK (severity IN ('low', 'medium', 'high', 'critical')),
    subject_type varchar(16) NOT NULL,
    subject_hash char(64) NOT NULL,
    university_id bigint REFERENCES universities(id) ON DELETE RESTRICT,
    route varchar(255),
    event_count integer NOT NULL DEFAULT 1 CHECK (event_count > 0),
    status varchar(16) NOT NULL DEFAULT 'open'
        CHECK (status IN ('open', 'contained', 'resolved', 'false_positive')),
    detail jsonb NOT NULL DEFAULT '{}'::jsonb,
    first_seen_at timestamptz NOT NULL,
    last_seen_at timestamptz NOT NULL,
    created_at timestamptz NOT NULL,
    updated_at timestamptz NOT NULL,
    CHECK (subject_hash ~ '^[0-9a-f]{64}$')
);

CREATE INDEX IF NOT EXISTS ix_security_events_recent
    ON security_events (created_at DESC, status);

CREATE TABLE IF NOT EXISTS security_blocks (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    subject_type varchar(16) NOT NULL,
    subject_hash char(64) NOT NULL,
    category varchar(40) NOT NULL,
    severity varchar(16) NOT NULL,
    reason text NOT NULL,
    status varchar(16) NOT NULL DEFAULT 'active'
        CHECK (status IN ('active', 'expired', 'revoked')),
    starts_at timestamptz NOT NULL,
    ends_at timestamptz NOT NULL,
    created_by_user_id bigint REFERENCES users(id) ON DELETE RESTRICT,
    revoked_by_user_id bigint REFERENCES users(id) ON DELETE RESTRICT,
    revoked_at timestamptz,
    created_at timestamptz NOT NULL,
    updated_at timestamptz NOT NULL,
    CHECK (ends_at > starts_at),
    CHECK (subject_hash ~ '^[0-9a-f]{64}$'),
    CHECK (btrim(reason) <> '')
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_active_security_block
    ON security_blocks (subject_type, subject_hash)
    WHERE status = 'active';

CREATE INDEX IF NOT EXISTS ix_security_blocks_recent
    ON security_blocks (created_at DESC, status);

CREATE TABLE IF NOT EXISTS application_events (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    level varchar(16) NOT NULL
        CHECK (level IN ('info', 'warning', 'error', 'critical')),
    event_code varchar(64) NOT NULL,
    request_id varchar(64),
    route varchar(255),
    method varchar(12),
    status_code integer,
    university_id bigint REFERENCES universities(id) ON DELETE RESTRICT,
    actor_user_id bigint REFERENCES users(id) ON DELETE RESTRICT,
    summary text NOT NULL,
    detail jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL,
    CHECK (btrim(event_code) <> ''),
    CHECK (btrim(summary) <> '')
);

CREATE INDEX IF NOT EXISTS ix_application_events_recent
    ON application_events (created_at DESC, level);

COMMIT;
