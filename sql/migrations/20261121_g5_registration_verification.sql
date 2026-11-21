BEGIN;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'uq_registry_id_university_id'
          AND conrelid = 'student_registry_records'::regclass
    ) THEN
        ALTER TABLE student_registry_records
            ADD CONSTRAINT uq_registry_id_university_id UNIQUE (id, university_id);
    END IF;
END
$$;

CREATE TABLE IF NOT EXISTS registration_verification_requests (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    university_id bigint NOT NULL REFERENCES universities(id) ON DELETE RESTRICT,
    student_registry_record_id bigint,
    student_no_hash char(64) NOT NULL,
    phone_hash char(64) NOT NULL,
    code_hash char(64),
    salt char(64),
    provider varchar(16),
    out_id varchar(64) NOT NULL UNIQUE,
    provider_message_id varchar(128),
    status varchar(16) NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'sent', 'ignored', 'consumed', 'failed', 'expired')),
    request_ip_hash char(64) NOT NULL,
    failed_attempts integer NOT NULL DEFAULT 0 CHECK (failed_attempts >= 0),
    resend_after timestamptz NOT NULL,
    expires_at timestamptz NOT NULL,
    sent_at timestamptz,
    consumed_at timestamptz,
    created_at timestamptz NOT NULL,
    FOREIGN KEY (student_registry_record_id, university_id)
        REFERENCES student_registry_records(id, university_id) ON DELETE RESTRICT,
    CHECK (btrim(out_id) <> ''),
    CHECK (student_no_hash ~ '^[0-9a-f]{64}$'),
    CHECK (phone_hash ~ '^[0-9a-f]{64}$'),
    CHECK (request_ip_hash ~ '^[0-9a-f]{64}$'),
    CHECK (code_hash IS NULL OR code_hash ~ '^[0-9a-f]{64}$'),
    CHECK (salt IS NULL OR salt ~ '^[0-9a-f]{64}$'),
    CHECK (provider IS NULL OR provider IN ('mock', 'aliyun_pnvs')),
    CHECK (
        (status = 'ignored'
            AND student_registry_record_id IS NULL
            AND code_hash IS NULL
            AND salt IS NULL
            AND provider IS NULL)
        OR
        (status <> 'ignored'
            AND student_registry_record_id IS NOT NULL
            AND provider IS NOT NULL)
    ),
    CHECK (
        provider IS DISTINCT FROM 'mock'
        OR (code_hash IS NOT NULL AND salt IS NOT NULL)
    ),
    CHECK (
        provider IS DISTINCT FROM 'aliyun_pnvs'
        OR (code_hash IS NULL AND salt IS NULL)
    ),
    CHECK (expires_at > created_at),
    CHECK (resend_after >= created_at)
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_active_registration_verification
    ON registration_verification_requests (student_registry_record_id)
    WHERE status IN ('pending', 'sent')
      AND student_registry_record_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS ix_registration_verification_phone_created
    ON registration_verification_requests (phone_hash, created_at DESC);

CREATE INDEX IF NOT EXISTS ix_registration_verification_ip_created
    ON registration_verification_requests (request_ip_hash, created_at DESC);

COMMIT;
