# Member 2 checklist: database and backend architecture

Status key: `[x]` done and verified, `[~]` done with a stated limit, `[ ]` not done. Evidence names the test or command that proves it.
Last full run: **336 tests pass** (116 shared suites in member3 and member4, untouched, plus 220 in `member2/backend/tests`).

## A. Schema integrity
| | Item | Evidence |
|---|---|---|
| [x] | Stable constraint and index names (naming convention) so migrations are deterministic | `core/db.py` `NAMING_CONVENTION`; `test_names_follow_the_convention` |
| [x] | One module of enums is the single source of truth; models, schemas and state machines agree | `models/enums.py`; CHECKs and `PURPOSES`/`LEAD_*` built from it; `test_enums_match_the_state_machines` |
| [x] | CHECK constraints on every closed vocabulary, phone format and numeric range | `test_unknown_vocabulary_value_is_rejected` (13 cases), `test_phone_must_look_like_e164`, `test_numeric_ranges` |
| [~] | Opt-out wins enforced by the database | **Not a CHECK, deliberately** (decision 23): member 4's quality test plants this violation to prove its audit works. Enforced in code, audited by the quality page and `cli db check` (`test_check_command_fails_loudly_when_data_is_inconsistent`) |
| [x] | Foreign keys enforced at runtime with an explicit ON DELETE rule on each | `PRAGMA foreign_keys=ON` per connection; `test_foreign_keys_are_enforced`, `test_delete_rules` (restrict, cascade, set null) |
| [x] | One classified response per call attempt | `test_one_classified_response_per_call` |
| [x] | One open human-review follow-up per participant | `test_one_open_review_per_participant` (partial unique index) |
| [x] | Provider call id unique per provider | `test_provider_call_id_identifies_one_attempt_per_provider` (partial unique index) |
| [x] | Server defaults so a hand-written INSERT cannot create a half-filled row | `test_server_defaults_fill_what_the_code_omits` |

## B. Indexes
| | Item | Evidence |
|---|---|---|
| [x] | An index for every hot query: lists, suppression lookup, scheduler due scan, queue, leads, analytics | 24 indexes and unique constraints, each documented against its query in `docs/DATA_MODEL.md` (`test_docs.py` keeps the list honest) |
| [x] | Every foreign-key column is covered by the start of some index | `test_every_foreign_key_is_the_start_of_some_index` (it found two gaps, both fixed) |
| [x] | Redundant single-column indexes replaced by composites | `test_no_index_is_a_redundant_prefix_of_another` |
| [x] | `EXPLAIN QUERY PLAN` tests prove the key queries use their index | 12 plan tests in `test_indexes.py` |
| [x] | Benchmark on tens of thousands of rows, before and after | `python -m member2.backend.scripts.benchmark_indexes`: 50,000 participants, opt-out lookup 10.6x, participants by outcome 31.5x, follow-up queue 7.4x, responses by intent 25.4x. Unchanged where already indexed; the scan of a 50-row table is 0.09 ms slower (reported in DATA_MODEL.md) |

## C. Migrations
| | Item | Evidence |
|---|---|---|
| [x] | Alembic configured (programmatic and command line), SQLite rebuild helper | `migrations/env.py`, `rebuild.py`; `test_the_alembic_command_line_works_against_the_same_database` |
| [x] | Baseline revision reproduces the schema of databases already in use | `test_baseline_revision_reproduces_the_shipped_schema` (against a frozen dump) |
| [x] | Revision adding constraints, foreign-key rules, defaults and indexes | `versions/0002_constraints_and_indexes.py` |
| [x] | Existing databases adopted and upgraded automatically, with a backup first | `test_legacy_database_is_adopted_and_upgraded_without_losing_anything`, `test_a_backup_is_written_first_and_is_a_faithful_copy`, `test_tables_added_after_the_first_release_are_created_when_adopting` |
| [x] | Models and migrations cannot drift | `test_head_schema_is_exactly_what_the_models_declare`, `test_autogenerate_finds_no_difference_between_models_and_migrations`, `test_frozen_snapshot_matches_the_models` |
| [x] | Bad existing data stops the migration and changes nothing | `test_data_that_breaks_a_new_rule_...`, `test_rows_pointing_at_missing_records_...`, `test_duplicate_responses_for_one_call_...` |
| [x] | Downgrade works and keeps every row | `test_downgrade_restores_the_baseline_schema_and_keeps_every_row` |
| [x] | Your real `data/app.db` migrated safely | Backend restarted: log `database migrated 0001 -> 0002 (adopted pre-migration database)`; backup `data/backups/app-pre-0002-*.db`; row counts identical (29 participants, 30 attempts, 24 responses, 30 leads, ...); `db check` ok; 9 pages render with no errors |

## D. Runtime database behaviour
| | Item | Evidence |
|---|---|---|
| [x] | SQLite pragmas: foreign keys on, WAL, busy timeout, synchronous NORMAL | `test_a_running_database_uses_foreign_keys_wal_and_a_busy_timeout`; `db stats` on the real file shows `wal`, foreign keys on |
| [x] | Migrations run with foreign keys off, then `foreign_key_check` must be clean, in one transaction | `rebuild.py`; the three "stops and changes nothing" tests prove the rollback |
| [x] | Health reports schema revision and whether it is current | `GET /api/health` -> `schema{current, head, up_to_date}`; `test_starting_the_app_on_a_legacy_database_...` |

## E. Operations
| | Item | Evidence |
|---|---|---|
| [x] | `db` command line: upgrade, downgrade, current, history, check, backup, stats, optimize | `app/cli.py`; `test_command_line_tools` |
| [x] | Integrity check: `integrity_check`, `foreign_key_check` and six consistency rules | `core/dbtools.py`; `GET /api/health/database`; `cli db check` exits 1 when anything is wrong |
| [x] | Online backup that is safe while the API runs | SQLite backup API; backups pruned to the newest 10 (`test_backups_are_pruned_to_the_newest_few`) |

## F. Architecture
| | Item | Evidence |
|---|---|---|
| [x] | Models split by aggregate (compatibility import kept) | `models/events.py`, `calling.py`, `leads.py`, `enums.py`; `entities.py` re-exports |
| [x] | Schemas split by area (compatibility import kept) | `schemas/common.py`, `events.py`, `campaigns.py`, `participants.py`, `followups.py`, `leads.py`, `webhooks.py`; `api.py` re-exports |
| [x] | Repository layer: routers, services, repositories, models | `repositories/` (8 modules); every query moved |
| [x] | Routers contain no query code | `test_routers_contain_no_query_code` |
| [~] | Services contain no query code | `test_services_build_no_queries_except_sample_data_tooling`: all but `services/demo.py` (the sample-data seed and wipe tool, writes and deletes directly) |
| [x] | Layering enforced by a test | `test_each_module_imports_only_from_layers_below` (one case per file); shown to fail on three planted violations |
| [x] | Logging configured in one place | `core/logs.py`; `test_logging_is_configured_in_one_place_only`; `LOG_LEVEL` setting |
| [x] | Work-queue N+1 removed | `repositories/followups.queue_rows`: one joined query instead of four lookups per follow-up |

## G. Documentation and proof
| | Item | Evidence |
|---|---|---|
| [x] | `docs/DATA_MODEL.md` with entity diagram, constraints and indexes | rewritten; `test_docs.py` fails if it drifts from the database |
| [x] | `member2/README.md`, `docs/ARCHITECTURE.md`, decisions 22-24, known issues, API contracts, `migrations/README.md`; stale "no migrations" statements corrected | done |
| [x] | Full test suite green, including the shared suites in member3 and member4 | 283 passed |
| [x] | Running backend restarted and smoke-tested on your real database | all read endpoints 200 at 9-54 ms; frontend pages rendered read-only in headless Chrome without console or network errors |

## H. Exotel readiness (backend side)
| | Item | Evidence |
|---|---|---|
| [x] | Handover document for the integrator | `member2/EXOTEL_HANDOFF.md` (start path, exact contract, safety rails, what is unverified) |
| [x] | Callback handling moved into a service, behaviour unchanged | `services/exotel_webhooks.py`; member 4's Exotel tests pass untouched |
| [x] | Every authenticated callback kept, masked, with how it was handled | `webhook_logs` table (migration 0003), `GET /api/webhooks/log`, `cli exotel webhooks`; tests: token and whole numbers never stored, failures and duplicates visible, bad token not stored, logging failure never breaks a callback, pruning, off switch |
| [x] | Readiness doctor, optionally proving the tunnel reaches the backend | `cli exotel doctor --probe`, `GET /api/settings/exotel-readiness?probe=true`; tests with mocked tunnel (reachable, warning page, 502, refused, missing URL) |
| [x] | Settings validated at start-up | token length, allow-list format, https region URL, rate and cap ranges: `test_bad_exotel_settings_fail_fast` |
| [x] | Calls paced to Exotel's documented 200/min | `services/pacing.py`; `test_pacer_...` |
| [x] | First-test cap (`REAL_CALLS_PER_START`) with held-back participants | `test_the_per_press_cap_holds_the_rest_back_...`; simulated calls exempt |
| [x] | A failed placement is retried (bounded) instead of stranding the participant | `test_a_placement_failure_schedules_a_bounded_retry` (found and fixed a real gap) |
| [x] | Numbers outside the allow-list skipped with a reason, no failed attempt left behind | `test_numbers_outside_the_allow_list_...` |
| [x] | Calls whose result never arrived are reconciled with the provider, never guessed | `services/reconcile.py`, `POST /campaigns/{id}/reconcile`, scheduler; 8 tests incl. late callback = duplicate, provider errors, no-SID call closed without retry |
| [x] | Tests cannot be broken by filling in the real `.env` | repo-level `conftest.py`; verified by running all 322 then-current tests with a complete fake Exotel `.env` |
| [x] | `.env` prepared | webhook token generated, `REAL_CALLS_PER_START=3`, new keys added (values for Exotel's own keys left blank) |
| [x] | Dress rehearsal over real HTTP: real provider, real backend process, stand-in Exotel | `python -m member2.backend.scripts.exotel_rehearsal`: 22 of 22 checks (readiness probe, allow-list skip, documented request fields, callbacks incl. CustomField fallback, keypad 1 and 9, duplicate, wrong token, reconcile, masked log, integrity) |
| [ ] | Anything on a live Exotel account | not possible from here: see "Still unverified" in the handoff |

## What changed for the other members
* **Nothing in member1, member3 or member4 was edited.** Their code and tests pass unchanged.
* One database rule was dropped because of member 4's test (A, "opt-out wins" CHECK). Everything else is enforced.
* New endpoints for the frontend, if wanted: `GET /api/health/database`; `schema` in `GET /api/health`.
