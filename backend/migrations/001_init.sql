CREATE TABLE schema_migrations (
	version VARCHAR(32) NOT NULL, 
	name VARCHAR(128) NOT NULL, 
	checksum VARCHAR(64) NOT NULL, 
	applied_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (version)
);

CREATE TABLE users (
	id VARCHAR(36) NOT NULL, 
	username VARCHAR(64) NOT NULL, 
	password_hash VARCHAR(255) NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	is_active BOOLEAN NOT NULL, 
	failed_login_count INTEGER NOT NULL, 
	locked_until TIMESTAMP WITH TIME ZONE, 
	PRIMARY KEY (id)
);

CREATE UNIQUE INDEX ix_users_username ON users (username);

CREATE TABLE budgets (
	id VARCHAR(36) NOT NULL, 
	user_id VARCHAR(36) NOT NULL, 
	month VARCHAR(7) NOT NULL, 
	category VARCHAR(24) NOT NULL, 
	encrypted_payload TEXT NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_budgets_user_month_category UNIQUE (user_id, month, category), 
	FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE
);

CREATE INDEX ix_budgets_month ON budgets (month);

CREATE INDEX ix_budgets_user_id ON budgets (user_id);

CREATE TABLE classification_rules (
	id VARCHAR(36) NOT NULL, 
	user_id VARCHAR(36) NOT NULL, 
	source VARCHAR(16) NOT NULL, 
	version INTEGER NOT NULL, 
	enabled BOOLEAN NOT NULL, 
	encrypted_payload TEXT NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE
);

CREATE INDEX ix_classification_rules_user_id ON classification_rules (user_id);

CREATE TABLE import_batches (
	id VARCHAR(36) NOT NULL, 
	user_id VARCHAR(36) NOT NULL, 
	source VARCHAR(16) NOT NULL, 
	ingestion_method VARCHAR(16) NOT NULL, 
	status VARCHAR(24) NOT NULL, 
	version INTEGER NOT NULL, 
	progress_current INTEGER NOT NULL, 
	progress_total INTEGER NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	started_at TIMESTAMP WITH TIME ZONE, 
	expires_at TIMESTAMP WITH TIME ZONE, 
	encrypted_filename TEXT, 
	encrypted_original TEXT, 
	encrypted_rows TEXT, 
	encrypted_issues TEXT, 
	confirmation_request_id VARCHAR(64), 
	request_body_digest VARCHAR(64), 
	encrypted_confirm_result TEXT, 
	PRIMARY KEY (id), 
	FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE
);

CREATE INDEX ix_import_batches_status ON import_batches (status);

CREATE INDEX ix_import_batches_user_id ON import_batches (user_id);

CREATE TABLE user_sessions (
	id VARCHAR(36) NOT NULL, 
	user_id VARCHAR(36) NOT NULL, 
	token_hash VARCHAR(64) NOT NULL, 
	csrf_token VARCHAR(64) NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	expires_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	last_seen_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	user_agent VARCHAR(255), 
	client_ip VARCHAR(64), 
	PRIMARY KEY (id), 
	FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE
);

CREATE UNIQUE INDEX ix_user_sessions_token_hash ON user_sessions (token_hash);

CREATE INDEX ix_user_sessions_user_id ON user_sessions (user_id);

CREATE TABLE transactions (
	id VARCHAR(36) NOT NULL, 
	user_id VARCHAR(36) NOT NULL, 
	import_batch_id VARCHAR(36), 
	version INTEGER NOT NULL, 
	month_index VARCHAR(7) NOT NULL, 
	source VARCHAR(16) NOT NULL, 
	flow_type VARCHAR(16) NOT NULL, 
	category VARCHAR(24) NOT NULL, 
	status VARCHAR(16) NOT NULL, 
	dedupe_digest VARCHAR(64) NOT NULL, 
	encrypted_payload TEXT NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	updated_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_transactions_user_dedupe UNIQUE (user_id, dedupe_digest), 
	FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE, 
	FOREIGN KEY(import_batch_id) REFERENCES import_batches (id) ON DELETE SET NULL
);

CREATE INDEX ix_transactions_category ON transactions (category);

CREATE INDEX ix_transactions_flow_type ON transactions (flow_type);

CREATE INDEX ix_transactions_import_batch_id ON transactions (import_batch_id);

CREATE INDEX ix_transactions_month_index ON transactions (month_index);

CREATE INDEX ix_transactions_source ON transactions (source);

CREATE INDEX ix_transactions_status ON transactions (status);

CREATE INDEX ix_transactions_user_category ON transactions (user_id, category);

CREATE INDEX ix_transactions_user_id ON transactions (user_id);

CREATE INDEX ix_transactions_user_month ON transactions (user_id, month_index);

CREATE TABLE correction_logs (
	id VARCHAR(36) NOT NULL, 
	user_id VARCHAR(36) NOT NULL, 
	transaction_id VARCHAR(36) NOT NULL, 
	created_at TIMESTAMP WITH TIME ZONE NOT NULL, 
	rule_created BOOLEAN NOT NULL, 
	encrypted_payload TEXT NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(user_id) REFERENCES users (id) ON DELETE CASCADE, 
	FOREIGN KEY(transaction_id) REFERENCES transactions (id) ON DELETE CASCADE
);

CREATE INDEX ix_correction_logs_transaction_id ON correction_logs (transaction_id);

CREATE INDEX ix_correction_logs_user_id ON correction_logs (user_id);

