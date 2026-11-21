BEGIN;

CREATE TABLE universities (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    code varchar(32) NOT NULL UNIQUE,
    name varchar(128) NOT NULL,
    province varchar(32) NOT NULL,
    city varchar(64) NOT NULL,
    education_level varchar(16) NOT NULL
        CHECK (education_level IN ('undergraduate', 'college')),
    ownership varchar(16) NOT NULL
        CHECK (ownership IN ('public', 'private')),
    authority_name varchar(128),
    source_url varchar(512),
    source_updated_on date,
    status varchar(16) NOT NULL DEFAULT 'active'
        CHECK (status IN ('active', 'inactive')),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CHECK (btrim(code) <> ''),
    CHECK (btrim(name) <> '')
);

CREATE TABLE campuses (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    university_id bigint NOT NULL REFERENCES universities(id) ON DELETE RESTRICT,
    code varchar(32) NOT NULL,
    name varchar(128) NOT NULL,
    address varchar(255),
    is_primary boolean NOT NULL DEFAULT false,
    verification_status varchar(16) NOT NULL DEFAULT 'temporary'
        CHECK (verification_status IN ('official', 'temporary')),
    source_url varchar(512),
    source_updated_on date,
    status varchar(16) NOT NULL DEFAULT 'active'
        CHECK (status IN ('active', 'inactive')),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (university_id, code),
    UNIQUE (id, university_id),
    CHECK (btrim(code) <> ''),
    CHECK (btrim(name) <> '')
);

CREATE UNIQUE INDEX uq_primary_campus_per_university
    ON campuses (university_id)
    WHERE is_primary;

CREATE TABLE users (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    university_id bigint REFERENCES universities(id) ON DELETE RESTRICT,
    campus_id bigint,
    login_name varchar(64) UNIQUE,
    student_no varchar(32),
    phone_hash char(64),
    password_hash varchar(255) NOT NULL,
    password_must_change boolean NOT NULL DEFAULT false,
    nickname varchar(64) NOT NULL,
    avatar_object_key varchar(512),
    role varchar(32) NOT NULL DEFAULT 'student'
        CHECK (role IN ('student', 'station_manager', 'platform_admin', 'university_admin')),
    status varchar(16) NOT NULL DEFAULT 'active'
        CHECK (status IN ('active', 'disabled')),
    last_login_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (id, university_id),
    FOREIGN KEY (campus_id, university_id)
        REFERENCES campuses(id, university_id) ON DELETE RESTRICT,
    CHECK (btrim(nickname) <> ''),
    CHECK (
        (role = 'platform_admin'
            AND university_id IS NULL
            AND campus_id IS NULL
            AND student_no IS NULL
            AND phone_hash IS NULL
            AND login_name IS NOT NULL)
        OR
        (role IN ('station_manager', 'university_admin')
            AND university_id IS NOT NULL
            AND login_name IS NOT NULL)
        OR
        (role = 'student'
            AND university_id IS NOT NULL
            AND campus_id IS NOT NULL
            AND student_no IS NOT NULL
            AND phone_hash IS NOT NULL
            AND login_name IS NULL)
    ),
    CHECK (login_name IS NULL OR btrim(login_name) <> ''),
    CHECK (phone_hash IS NULL OR phone_hash ~ '^[0-9a-f]{64}$')
);

CREATE UNIQUE INDEX uq_users_university_student_no
    ON users (university_id, student_no)
    WHERE student_no IS NOT NULL;

CREATE UNIQUE INDEX uq_users_university_phone
    ON users (university_id, phone_hash)
    WHERE phone_hash IS NOT NULL;

CREATE INDEX ix_users_university_role_status
    ON users (university_id, role, status);

CREATE TABLE stations (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    university_id bigint NOT NULL REFERENCES universities(id) ON DELETE RESTRICT,
    campus_id bigint NOT NULL,
    name varchar(128) NOT NULL,
    station_type varchar(16) NOT NULL
        CHECK (station_type IN ('recycle', 'charity', 'mixed')),
    address varchar(255) NOT NULL,
    service_hours varchar(128),
    status varchar(16) NOT NULL DEFAULT 'active'
        CHECK (status IN ('active', 'inactive')),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (university_id, campus_id, name),
    UNIQUE (id, university_id),
    FOREIGN KEY (campus_id, university_id)
        REFERENCES campuses(id, university_id) ON DELETE RESTRICT,
    CHECK (btrim(name) <> ''),
    CHECK (btrim(address) <> '')
);

CREATE TABLE station_manager_assignments (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    university_id bigint NOT NULL REFERENCES universities(id) ON DELETE RESTRICT,
    station_id bigint NOT NULL,
    user_id bigint NOT NULL,
    started_on date NOT NULL,
    ended_on date,
    status varchar(16) NOT NULL DEFAULT 'active'
        CHECK (status IN ('active', 'ended')),
    created_at timestamptz NOT NULL DEFAULT now(),
    FOREIGN KEY (station_id, university_id)
        REFERENCES stations(id, university_id) ON DELETE RESTRICT,
    FOREIGN KEY (user_id, university_id)
        REFERENCES users(id, university_id) ON DELETE RESTRICT,
    CHECK (ended_on IS NULL OR ended_on >= started_on)
);

CREATE UNIQUE INDEX uq_active_station_manager
    ON station_manager_assignments (station_id, user_id)
    WHERE status = 'active';

CREATE INDEX ix_station_manager_user
    ON station_manager_assignments (user_id, status);

CREATE TABLE student_import_batches (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    university_id bigint NOT NULL REFERENCES universities(id) ON DELETE RESTRICT,
    uploaded_by_user_id bigint NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    original_filename varchar(255) NOT NULL,
    file_sha256 char(64) NOT NULL,
    total_rows integer NOT NULL DEFAULT 0 CHECK (total_rows >= 0),
    success_rows integer NOT NULL DEFAULT 0 CHECK (success_rows >= 0),
    failed_rows integer NOT NULL DEFAULT 0 CHECK (failed_rows >= 0),
    status varchar(16) NOT NULL DEFAULT 'processing'
        CHECK (status IN ('processing', 'completed', 'failed')),
    error_summary jsonb NOT NULL DEFAULT '[]'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    completed_at timestamptz,
    UNIQUE (id, university_id),
    CHECK (success_rows + failed_rows <= total_rows),
    CHECK (file_sha256 ~ '^[0-9a-f]{64}$')
);

CREATE TABLE student_registry_records (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    university_id bigint NOT NULL REFERENCES universities(id) ON DELETE RESTRICT,
    campus_id bigint NOT NULL,
    latest_import_batch_id bigint NOT NULL,
    student_no varchar(32) NOT NULL,
    full_name varchar(64) NOT NULL,
    phone_hash char(64) NOT NULL,
    phone_last4 char(4) NOT NULL,
    grade varchar(32) NOT NULL,
    class_name varchar(64) NOT NULL,
    major varchar(128) NOT NULL,
    college varchar(128) NOT NULL,
    status varchar(16) NOT NULL DEFAULT 'active'
        CHECK (status IN ('active', 'disabled')),
    registered_user_id bigint UNIQUE,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (university_id, student_no),
    UNIQUE (university_id, phone_hash),
    FOREIGN KEY (campus_id, university_id)
        REFERENCES campuses(id, university_id) ON DELETE RESTRICT,
    FOREIGN KEY (latest_import_batch_id, university_id)
        REFERENCES student_import_batches(id, university_id) ON DELETE RESTRICT,
    FOREIGN KEY (registered_user_id, university_id)
        REFERENCES users(id, university_id) ON DELETE RESTRICT,
    CHECK (phone_hash ~ '^[0-9a-f]{64}$'),
    CHECK (phone_last4 ~ '^[0-9]{4}$'),
    CHECK (btrim(full_name) <> '')
);

CREATE TABLE login_verification_codes (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id bigint NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    purpose varchar(16) NOT NULL DEFAULT 'login'
        CHECK (purpose IN ('login')),
    code_hash char(64) NOT NULL,
    expires_at timestamptz NOT NULL,
    used_at timestamptz,
    failed_attempts integer NOT NULL DEFAULT 0 CHECK (failed_attempts >= 0),
    created_at timestamptz NOT NULL DEFAULT now(),
    CHECK (expires_at > created_at),
    CHECK (code_hash ~ '^[0-9a-f]{64}$')
);

CREATE INDEX ix_login_codes_user_created
    ON login_verification_codes (user_id, created_at DESC);

CREATE TABLE item_categories (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    slug varchar(64) NOT NULL UNIQUE,
    name varchar(64) NOT NULL,
    display_order integer NOT NULL DEFAULT 0,
    is_active boolean NOT NULL DEFAULT true,
    created_at timestamptz NOT NULL DEFAULT now(),
    CHECK (btrim(slug) <> ''),
    CHECK (btrim(name) <> '')
);

CREATE TABLE items (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    university_id bigint NOT NULL REFERENCES universities(id) ON DELETE RESTRICT,
    campus_id bigint NOT NULL,
    owner_user_id bigint NOT NULL,
    category_id bigint NOT NULL REFERENCES item_categories(id) ON DELETE RESTRICT,
    mode varchar(16) NOT NULL
        CHECK (mode IN ('borrow', 'sale', 'give', 'recycle')),
    title varchar(160) NOT NULL,
    description text NOT NULL,
    condition varchar(16) NOT NULL
        CHECK (condition IN ('new', 'like_new', 'good', 'fair')),
    sale_price_cents integer,
    status varchar(24) NOT NULL DEFAULT 'active'
        CHECK (status IN ('active', 'reserved', 'in_progress', 'completed', 'off_shelf', 'on_hold')),
    moderation_status varchar(16) NOT NULL DEFAULT 'normal'
        CHECK (moderation_status IN ('normal', 'hidden')),
    moderation_reason varchar(500),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (id, university_id),
    UNIQUE (id, mode),
    FOREIGN KEY (campus_id, university_id)
        REFERENCES campuses(id, university_id) ON DELETE RESTRICT,
    FOREIGN KEY (owner_user_id, university_id)
        REFERENCES users(id, university_id) ON DELETE RESTRICT,
    CHECK (btrim(title) <> ''),
    CHECK (btrim(description) <> ''),
    CHECK (
        (mode = 'sale' AND sale_price_cents IS NOT NULL AND sale_price_cents > 0)
        OR (mode <> 'sale' AND sale_price_cents IS NULL)
    )
);

CREATE INDEX ix_items_discovery
    ON items (university_id, status, mode, category_id, created_at DESC);

CREATE INDEX ix_items_owner
    ON items (owner_user_id, created_at DESC);

CREATE TABLE item_images (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    item_id bigint NOT NULL REFERENCES items(id) ON DELETE RESTRICT,
    object_key varchar(512) NOT NULL UNIQUE,
    content_type varchar(32) NOT NULL
        CHECK (content_type IN ('image/jpeg', 'image/png', 'image/webp')),
    byte_size integer NOT NULL CHECK (byte_size BETWEEN 1 AND 3145728),
    sort_order smallint NOT NULL CHECK (sort_order BETWEEN 0 AND 4),
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (item_id, sort_order),
    CHECK (btrim(object_key) <> '')
);

CREATE TABLE circulation_requests (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    university_id bigint NOT NULL REFERENCES universities(id) ON DELETE RESTRICT,
    item_id bigint NOT NULL,
    requester_user_id bigint NOT NULL,
    owner_user_id bigint NOT NULL,
    mode varchar(16) NOT NULL
        CHECK (mode IN ('borrow', 'sale', 'give', 'recycle')),
    status varchar(24) NOT NULL DEFAULT 'pending'
        CHECK (status IN (
            'pending',
            'accepted',
            'payment_pending',
            'handover_pending',
            'in_progress',
            'return_pending',
            'inspection_pending',
            'completed',
            'rejected',
            'cancelled',
            'disputed'
        )),
    request_note text,
    responded_at timestamptz,
    completed_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (id, university_id),
    FOREIGN KEY (item_id, university_id)
        REFERENCES items(id, university_id) ON DELETE RESTRICT,
    FOREIGN KEY (item_id, mode)
        REFERENCES items(id, mode) ON DELETE RESTRICT,
    FOREIGN KEY (requester_user_id, university_id)
        REFERENCES users(id, university_id) ON DELETE RESTRICT,
    FOREIGN KEY (owner_user_id, university_id)
        REFERENCES users(id, university_id) ON DELETE RESTRICT,
    CHECK (requester_user_id <> owner_user_id),
    CHECK (mode = 'sale' OR status <> 'payment_pending'),
    CHECK (mode = 'borrow' OR status NOT IN ('in_progress', 'return_pending')),
    CHECK (mode = 'recycle' OR status <> 'inspection_pending')
);

CREATE UNIQUE INDEX uq_active_request_per_item
    ON circulation_requests (item_id)
    WHERE status IN (
        'pending',
        'accepted',
        'payment_pending',
        'handover_pending',
        'in_progress',
        'return_pending',
        'inspection_pending',
        'disputed'
    );

CREATE INDEX ix_requests_requester
    ON circulation_requests (requester_user_id, created_at DESC);

CREATE INDEX ix_requests_owner
    ON circulation_requests (owner_user_id, status, created_at DESC);

CREATE TABLE borrow_details (
    request_id bigint PRIMARY KEY REFERENCES circulation_requests(id) ON DELETE RESTRICT,
    start_date date NOT NULL,
    due_date date NOT NULL,
    return_note text,
    return_submitted_at timestamptz,
    returned_at timestamptz,
    return_confirmed_at timestamptz,
    condition_ok boolean,
    CHECK (due_date >= start_date)
);

CREATE INDEX ix_borrow_dates
    ON borrow_details (start_date, due_date);

CREATE TABLE sale_details (
    request_id bigint PRIMARY KEY REFERENCES circulation_requests(id) ON DELETE RESTRICT,
    agreed_price_cents integer NOT NULL CHECK (agreed_price_cents > 0),
    payment_status varchar(24) NOT NULL DEFAULT 'not_started'
        CHECK (payment_status IN ('not_started', 'paid', 'failed', 'cancelled')),
    payment_reference varchar(64),
    paid_at timestamptz,
    CHECK (
        (payment_status = 'paid' AND paid_at IS NOT NULL)
        OR payment_status <> 'paid'
    )
);

CREATE TABLE recycle_details (
    request_id bigint PRIMARY KEY REFERENCES circulation_requests(id) ON DELETE RESTRICT,
    station_id bigint NOT NULL REFERENCES stations(id) ON DELETE RESTRICT,
    preferred_start_at timestamptz NOT NULL,
    preferred_end_at timestamptz NOT NULL,
    inspection_status varchar(16) NOT NULL DEFAULT 'pending'
        CHECK (inspection_status IN ('pending', 'accepted', 'rejected')),
    inspection_note text,
    inspected_by_user_id bigint REFERENCES users(id) ON DELETE RESTRICT,
    inspected_at timestamptz,
    CHECK (preferred_end_at > preferred_start_at),
    CHECK (
        (inspection_status = 'pending'
            AND inspected_by_user_id IS NULL
            AND inspected_at IS NULL)
        OR
        (inspection_status IN ('accepted', 'rejected')
            AND inspected_by_user_id IS NOT NULL
            AND inspected_at IS NOT NULL)
    )
);

CREATE INDEX ix_recycle_station_status
    ON recycle_details (station_id, inspection_status);

CREATE TABLE handover_records (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    request_id bigint NOT NULL UNIQUE REFERENCES circulation_requests(id) ON DELETE RESTRICT,
    code_hash char(64) NOT NULL UNIQUE,
    code_version integer NOT NULL DEFAULT 1 CHECK (code_version > 0),
    generated_by_user_id bigint NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    generated_at timestamptz NOT NULL DEFAULT now(),
    expires_at timestamptz NOT NULL,
    consumed_by_user_id bigint REFERENCES users(id) ON DELETE RESTRICT,
    consumed_at timestamptz,
    status varchar(16) NOT NULL DEFAULT 'active'
        CHECK (status IN ('active', 'used', 'revoked')),
    CHECK (expires_at > generated_at),
    CHECK (code_hash ~ '^[0-9a-f]{64}$'),
    CHECK (
        (status = 'used' AND consumed_by_user_id IS NOT NULL AND consumed_at IS NOT NULL)
        OR (status <> 'used')
    )
);

CREATE TABLE status_history (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    university_id bigint NOT NULL REFERENCES universities(id) ON DELETE RESTRICT,
    entity_type varchar(32) NOT NULL
        CHECK (entity_type IN (
            'item',
            'circulation_request',
            'charity_project',
            'charity_donation'
        )),
    entity_id bigint NOT NULL,
    from_status varchar(32),
    to_status varchar(32) NOT NULL,
    actor_user_id bigint REFERENCES users(id) ON DELETE RESTRICT,
    reason text,
    created_at timestamptz NOT NULL DEFAULT now(),
    CHECK (from_status IS NULL OR btrim(from_status) <> ''),
    CHECK (btrim(to_status) <> '')
);

CREATE INDEX ix_status_history_entity
    ON status_history (entity_type, entity_id, created_at DESC);

CREATE TABLE notifications (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    university_id bigint NOT NULL REFERENCES universities(id) ON DELETE RESTRICT,
    recipient_user_id bigint NOT NULL,
    category varchar(32) NOT NULL,
    title varchar(160) NOT NULL,
    body text NOT NULL,
    related_entity_type varchar(32),
    related_entity_id bigint,
    read_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    FOREIGN KEY (recipient_user_id, university_id)
        REFERENCES users(id, university_id) ON DELETE RESTRICT,
    CHECK (btrim(category) <> ''),
    CHECK (btrim(title) <> ''),
    CHECK (btrim(body) <> '')
);

CREATE INDEX ix_notifications_unread
    ON notifications (recipient_user_id, read_at, created_at DESC);

CREATE TABLE disputes (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    university_id bigint NOT NULL REFERENCES universities(id) ON DELETE RESTRICT,
    circulation_request_id bigint NOT NULL,
    opened_by_user_id bigint NOT NULL,
    reason text NOT NULL,
    status varchar(16) NOT NULL DEFAULT 'open'
        CHECK (status IN ('open', 'reviewing', 'resolved', 'withdrawn')),
    resolution text,
    resolved_by_user_id bigint REFERENCES users(id) ON DELETE RESTRICT,
    resolved_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    FOREIGN KEY (circulation_request_id, university_id)
        REFERENCES circulation_requests(id, university_id) ON DELETE RESTRICT,
    FOREIGN KEY (opened_by_user_id, university_id)
        REFERENCES users(id, university_id) ON DELETE RESTRICT,
    CHECK (btrim(reason) <> ''),
    CHECK (
        (status = 'resolved'
            AND resolution IS NOT NULL
            AND resolved_by_user_id IS NOT NULL
            AND resolved_at IS NOT NULL)
        OR status <> 'resolved'
    )
);

CREATE UNIQUE INDEX uq_open_dispute_per_request
    ON disputes (circulation_request_id)
    WHERE status IN ('open', 'reviewing');

CREATE TABLE dispute_messages (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    dispute_id bigint NOT NULL REFERENCES disputes(id) ON DELETE RESTRICT,
    author_user_id bigint NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    body text NOT NULL,
    attachment_object_key varchar(512),
    created_at timestamptz NOT NULL DEFAULT now(),
    CHECK (btrim(body) <> '')
);

CREATE TABLE audit_logs (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    university_id bigint REFERENCES universities(id) ON DELETE RESTRICT,
    actor_user_id bigint REFERENCES users(id) ON DELETE RESTRICT,
    action varchar(80) NOT NULL,
    entity_type varchar(64) NOT NULL,
    entity_id bigint,
    detail jsonb NOT NULL DEFAULT '{}'::jsonb,
    ip_address inet,
    user_agent text,
    created_at timestamptz NOT NULL DEFAULT now(),
    CHECK (btrim(action) <> ''),
    CHECK (btrim(entity_type) <> '')
);

CREATE INDEX ix_audit_logs_university_created
    ON audit_logs (university_id, created_at DESC);

CREATE TABLE charity_projects (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    university_id bigint NOT NULL REFERENCES universities(id) ON DELETE RESTRICT,
    title varchar(160) NOT NULL,
    description text NOT NULL,
    recipient_org varchar(160) NOT NULL,
    public_summary text NOT NULL,
    deadline timestamptz NOT NULL,
    status varchar(16) NOT NULL DEFAULT 'draft'
        CHECK (status IN ('draft', 'active', 'completed', 'cancelled')),
    created_by_user_id bigint NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (id, university_id),
    CHECK (btrim(title) <> ''),
    CHECK (btrim(description) <> ''),
    CHECK (btrim(recipient_org) <> ''),
    CHECK (btrim(public_summary) <> '')
);

CREATE INDEX ix_charity_projects_university_status
    ON charity_projects (university_id, status, deadline);

CREATE TABLE charity_project_needs (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    project_id bigint NOT NULL REFERENCES charity_projects(id) ON DELETE RESTRICT,
    item_category_id bigint NOT NULL REFERENCES item_categories(id) ON DELETE RESTRICT,
    item_name varchar(128) NOT NULL,
    target_quantity integer NOT NULL CHECK (target_quantity > 0),
    accepted_quantity integer NOT NULL DEFAULT 0
        CHECK (accepted_quantity >= 0 AND accepted_quantity <= target_quantity),
    unit varchar(16) NOT NULL DEFAULT '件',
    status varchar(16) NOT NULL DEFAULT 'active'
        CHECK (status IN ('active', 'fulfilled', 'closed')),
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (project_id, item_category_id, item_name),
    UNIQUE (id, project_id),
    CHECK (btrim(item_name) <> ''),
    CHECK (btrim(unit) <> '')
);

CREATE TABLE charity_donations (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    university_id bigint NOT NULL REFERENCES universities(id) ON DELETE RESTRICT,
    project_id bigint NOT NULL,
    donor_user_id bigint NOT NULL,
    station_id bigint NOT NULL,
    status varchar(16) NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'received', 'rejected', 'cancelled')),
    donor_note text,
    submitted_at timestamptz NOT NULL DEFAULT now(),
    reviewed_by_user_id bigint REFERENCES users(id) ON DELETE RESTRICT,
    reviewed_at timestamptz,
    reject_reason text,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (id, project_id),
    FOREIGN KEY (project_id, university_id)
        REFERENCES charity_projects(id, university_id) ON DELETE RESTRICT,
    FOREIGN KEY (donor_user_id, university_id)
        REFERENCES users(id, university_id) ON DELETE RESTRICT,
    FOREIGN KEY (station_id, university_id)
        REFERENCES stations(id, university_id) ON DELETE RESTRICT,
    CHECK (
        status <> 'rejected'
        OR (reject_reason IS NOT NULL AND btrim(reject_reason) <> '')
    )
);

CREATE INDEX ix_charity_donations_station
    ON charity_donations (station_id, status, created_at DESC);

CREATE TABLE charity_donation_items (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    donation_id bigint NOT NULL,
    project_id bigint NOT NULL,
    project_need_id bigint NOT NULL,
    item_name varchar(128) NOT NULL,
    quantity integer NOT NULL CHECK (quantity > 0),
    accepted_quantity integer NOT NULL DEFAULT 0
        CHECK (accepted_quantity >= 0 AND accepted_quantity <= quantity),
    condition varchar(16) NOT NULL
        CHECK (condition IN ('new', 'like_new', 'good', 'fair')),
    note text,
    image_object_key varchar(512),
    created_at timestamptz NOT NULL DEFAULT now(),
    FOREIGN KEY (donation_id, project_id)
        REFERENCES charity_donations(id, project_id) ON DELETE RESTRICT,
    FOREIGN KEY (project_need_id, project_id)
        REFERENCES charity_project_needs(id, project_id) ON DELETE RESTRICT,
    CHECK (btrim(item_name) <> '')
);

CREATE TABLE charity_receipts (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    university_id bigint NOT NULL REFERENCES universities(id) ON DELETE RESTRICT,
    project_id bigint NOT NULL,
    station_id bigint NOT NULL,
    title varchar(160) NOT NULL,
    recipient_org varchar(160) NOT NULL,
    dispatched_at timestamptz,
    received_at timestamptz NOT NULL,
    public_note text NOT NULL,
    status varchar(16) NOT NULL DEFAULT 'draft'
        CHECK (status IN ('draft', 'published')),
    created_by_user_id bigint NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
    published_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    FOREIGN KEY (project_id, university_id)
        REFERENCES charity_projects(id, university_id) ON DELETE RESTRICT,
    FOREIGN KEY (station_id, university_id)
        REFERENCES stations(id, university_id) ON DELETE RESTRICT,
    CHECK (btrim(title) <> ''),
    CHECK (btrim(recipient_org) <> ''),
    CHECK (btrim(public_note) <> ''),
    CHECK (
        (status = 'published' AND published_at IS NOT NULL)
        OR status <> 'published'
    )
);

CREATE INDEX ix_charity_receipts_public
    ON charity_receipts (university_id, status, received_at DESC);

CREATE TABLE charity_receipt_items (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    receipt_id bigint NOT NULL REFERENCES charity_receipts(id) ON DELETE RESTRICT,
    donation_item_id bigint REFERENCES charity_donation_items(id) ON DELETE RESTRICT,
    item_name varchar(128) NOT NULL,
    quantity integer NOT NULL CHECK (quantity > 0),
    note varchar(255),
    CHECK (btrim(item_name) <> '')
);

COMMIT;
