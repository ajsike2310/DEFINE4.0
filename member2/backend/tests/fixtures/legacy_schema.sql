-- Frozen copy of the schema create_all produced before migrations existed (v0.1/0.2).
-- Used to prove the baseline migration matches databases already in use.
CREATE TABLE call_attempts (
	id INTEGER NOT NULL, 
	campaign_id INTEGER NOT NULL, 
	recipient_id INTEGER NOT NULL, 
	provider VARCHAR(20) NOT NULL, 
	is_simulated BOOLEAN NOT NULL, 
	provider_call_id VARCHAR(100), 
	attempt_number INTEGER NOT NULL, 
	mode VARCHAR(10) NOT NULL, 
	call_language VARCHAR(10) NOT NULL, 
	status VARCHAR(20) NOT NULL, 
	started_at DATETIME, 
	answered_at DATETIME, 
	completed_at DATETIME, 
	failure_reason VARCHAR(200), 
	next_retry_at DATETIME, 
	created_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_attempt_number UNIQUE (recipient_id, attempt_number), 
	FOREIGN KEY(campaign_id) REFERENCES campaigns (id), 
	FOREIGN KEY(recipient_id) REFERENCES recipients (id)
);
CREATE TABLE campaigns (
	id INTEGER NOT NULL, 
	event_id INTEGER NOT NULL, 
	name VARCHAR(200) NOT NULL, 
	purpose VARCHAR(50) NOT NULL, 
	messages JSON NOT NULL, 
	languages JSON NOT NULL, 
	status VARCHAR(20) NOT NULL, 
	scheduled_at DATETIME, 
	max_attempts INTEGER NOT NULL, 
	require_consent BOOLEAN NOT NULL, 
	is_demo BOOLEAN NOT NULL, 
	created_at DATETIME NOT NULL, 
	updated_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(event_id) REFERENCES events (id)
);
CREATE TABLE events (
	id INTEGER NOT NULL, 
	name VARCHAR(200) NOT NULL, 
	description VARCHAR(500) NOT NULL, 
	approved_info JSON NOT NULL, 
	organizer_contact VARCHAR(200), 
	is_demo BOOLEAN NOT NULL, 
	created_at DATETIME NOT NULL, 
	updated_at DATETIME NOT NULL, 
	PRIMARY KEY (id)
);
CREATE TABLE follow_ups (
	id INTEGER NOT NULL, 
	campaign_id INTEGER NOT NULL, 
	recipient_id INTEGER NOT NULL, 
	source_intent_id INTEGER, 
	action_type VARCHAR(30) NOT NULL, 
	status VARCHAR(20) NOT NULL, 
	scheduled_at DATETIME, 
	note VARCHAR(300) NOT NULL, 
	created_at DATETIME NOT NULL, 
	completed_at DATETIME, 
	PRIMARY KEY (id), 
	FOREIGN KEY(campaign_id) REFERENCES campaigns (id), 
	FOREIGN KEY(recipient_id) REFERENCES recipients (id), 
	FOREIGN KEY(source_intent_id) REFERENCES intent_results (id)
);
CREATE TABLE import_runs (
	id INTEGER NOT NULL, 
	kind VARCHAR(20) NOT NULL, 
	event_id INTEGER NOT NULL, 
	campaign_id INTEGER, 
	filename VARCHAR(200) NOT NULL, 
	rows_total INTEGER NOT NULL, 
	imported INTEGER NOT NULL, 
	rejected INTEGER NOT NULL, 
	reasons JSON NOT NULL, 
	is_demo BOOLEAN NOT NULL, 
	created_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(event_id) REFERENCES events (id), 
	FOREIGN KEY(campaign_id) REFERENCES campaigns (id)
);
CREATE TABLE intent_results (
	id INTEGER NOT NULL, 
	call_attempt_id INTEGER NOT NULL, 
	recipient_id INTEGER NOT NULL, 
	campaign_id INTEGER NOT NULL, 
	intent VARCHAR(30) NOT NULL, 
	score FLOAT NOT NULL, 
	method VARCHAR(10) NOT NULL, 
	detected_language VARCHAR(10) NOT NULL, 
	evidence TEXT NOT NULL, 
	notes JSON NOT NULL, 
	needs_review BOOLEAN NOT NULL, 
	next_action VARCHAR(30) NOT NULL, 
	processing_status VARCHAR(20) NOT NULL, 
	created_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	FOREIGN KEY(call_attempt_id) REFERENCES call_attempts (id), 
	FOREIGN KEY(recipient_id) REFERENCES recipients (id), 
	FOREIGN KEY(campaign_id) REFERENCES campaigns (id)
);
CREATE TABLE leads (
	id INTEGER NOT NULL, 
	event_id INTEGER NOT NULL, 
	name VARCHAR(200) NOT NULL, 
	phone VARCHAR(20) NOT NULL, 
	email VARCHAR(200), 
	source VARCHAR(30) NOT NULL, 
	interest VARCHAR(100), 
	preferred_language VARCHAR(10), 
	consent_status VARCHAR(20) NOT NULL, 
	status VARCHAR(20) NOT NULL, 
	notes VARCHAR(500) NOT NULL, 
	recipient_id INTEGER, 
	is_demo BOOLEAN NOT NULL, 
	created_at DATETIME NOT NULL, 
	updated_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_lead_event_phone UNIQUE (event_id, phone), 
	FOREIGN KEY(event_id) REFERENCES events (id), 
	FOREIGN KEY(recipient_id) REFERENCES recipients (id)
);
CREATE TABLE provider_events (
	id INTEGER NOT NULL, 
	provider VARCHAR(20) NOT NULL, 
	event_id VARCHAR(200) NOT NULL, 
	call_attempt_id INTEGER, 
	kind VARCHAR(20) NOT NULL, 
	result VARCHAR(100) NOT NULL, 
	received_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_provider_event UNIQUE (provider, event_id), 
	FOREIGN KEY(call_attempt_id) REFERENCES call_attempts (id)
);
CREATE TABLE recipients (
	id INTEGER NOT NULL, 
	campaign_id INTEGER NOT NULL, 
	external_ref VARCHAR(100), 
	name VARCHAR(200) NOT NULL, 
	phone VARCHAR(20) NOT NULL, 
	preferred_language VARCHAR(10), 
	segment VARCHAR(100), 
	consent_status VARCHAR(20) NOT NULL, 
	opted_out BOOLEAN NOT NULL, 
	outcome VARCHAR(30) NOT NULL, 
	is_demo BOOLEAN NOT NULL, 
	created_at DATETIME NOT NULL, 
	updated_at DATETIME NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_recipient_campaign_phone UNIQUE (campaign_id, phone), 
	FOREIGN KEY(campaign_id) REFERENCES campaigns (id)
);
CREATE INDEX ix_call_attempts_campaign_id ON call_attempts (campaign_id);
CREATE INDEX ix_call_attempts_provider_call_id ON call_attempts (provider_call_id);
CREATE INDEX ix_call_attempts_recipient_id ON call_attempts (recipient_id);
CREATE INDEX ix_campaigns_event_id ON campaigns (event_id);
CREATE INDEX ix_follow_ups_campaign_id ON follow_ups (campaign_id);
CREATE INDEX ix_follow_ups_recipient_id ON follow_ups (recipient_id);
CREATE INDEX ix_import_runs_event_id ON import_runs (event_id);
CREATE INDEX ix_intent_results_call_attempt_id ON intent_results (call_attempt_id);
CREATE INDEX ix_intent_results_campaign_id ON intent_results (campaign_id);
CREATE INDEX ix_intent_results_recipient_id ON intent_results (recipient_id);
CREATE INDEX ix_leads_event_id ON leads (event_id);
CREATE INDEX ix_recipients_campaign_id ON recipients (campaign_id);
