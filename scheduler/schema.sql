/* ---------------------------------------------------------------------------------------------------------------------
Scheduled jobs: reminders, birthdays, periodic messages, etc. (`shared.scheduler`)

The scheduler runs this file on start, so it's safe to run again. Table names are unqualified on purpose:
the table goes into the first schema of the connection's `search_path`, i.e. each bot gets its own.

Times: `local_due` is the time on the clocks of `timezone` (UTC for absolute jobs like "in 2 hours").
The moment a job fires is derived as `local_due AT TIME ZONE timezone` whenever it's needed,
so a change of a timezone's rules can't shift jobs that people set in their local time.
--------------------------------------------------------------------------------------------------------------------- */

CREATE TABLE
    IF NOT EXISTS scheduled_jobs (
        id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
        kind TEXT NOT NULL, -- which handler runs it, e.g. 'reminder'
        key TEXT UNIQUE, -- optional unique name, e.g. 'birthday:123'
        user_id BIGINT, -- who the job belongs to
        guild_id BIGINT, -- which guild the job belongs to
        local_due TIMESTAMP NOT NULL, -- wall clock time of the next occurrence in `timezone`
        timezone TEXT NOT NULL DEFAULT 'UTC', -- IANA key
        rule TEXT, -- RFC 5545 RRULE for repeating jobs
        data JSONB NOT NULL DEFAULT '{}'::JSONB,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        claimed_at TIMESTAMPTZ, -- set while a scheduler holds the job to run it
        retry_at TIMESTAMPTZ, -- overrides the due moment: retries after failures and "run now"
        attempts INTEGER NOT NULL DEFAULT 0, -- failures of the current occurrence
        last_error TEXT -- traceback of the last failure
    );

CREATE INDEX IF NOT EXISTS scheduled_jobs_kind_user_id_idx ON scheduled_jobs (kind, user_id);

CREATE INDEX IF NOT EXISTS scheduled_jobs_guild_id_idx ON scheduled_jobs (guild_id)
WHERE
    guild_id IS NOT NULL;

-- added later, so `ADD COLUMN IF NOT EXISTS` for tables created before
ALTER TABLE scheduled_jobs
ADD COLUMN IF NOT EXISTS paused_at TIMESTAMPTZ; -- paused jobs don't fire until resumed

/* ---------------------------------------------------------------------------------------------------------------------
Waking the scheduler up: every change that leaves a job waiting (a new job, a retry, a release, `run_now` from
another process) notifies the `scheduled_jobs` channel with the schema's name, so the scheduler polls right away
instead of on its next round. Claims (`claimed_at` set) don't notify, or the scheduler would wake itself in a loop.
--------------------------------------------------------------------------------------------------------------------- */

CREATE OR REPLACE FUNCTION scheduled_jobs_notify() RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    PERFORM pg_notify('scheduled_jobs', TG_TABLE_SCHEMA);
    RETURN NULL;
END
$$;

CREATE OR REPLACE TRIGGER scheduled_jobs_notify
AFTER INSERT OR UPDATE ON scheduled_jobs
FOR EACH ROW WHEN (NEW.claimed_at IS NULL)
EXECUTE FUNCTION scheduled_jobs_notify();

/* ---------------------------------------------------------------------------------------------------------------------
History: one row per handler run (or skipped occurrence), kept for `HISTORY_DAYS` days.
--------------------------------------------------------------------------------------------------------------------- */

CREATE TABLE
    IF NOT EXISTS scheduled_job_runs (
        id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
        job_id BIGINT NOT NULL, -- not a foreign key: the job is usually gone by the time anyone looks
        kind TEXT NOT NULL,
        key TEXT,
        user_id BIGINT,
        guild_id BIGINT,
        due_at TIMESTAMPTZ NOT NULL, -- when the occurrence was due
        fired_at TIMESTAMPTZ NOT NULL, -- when the handler was called (or the occurrence skipped)
        finished_at TIMESTAMPTZ NOT NULL,
        attempt INTEGER NOT NULL, -- 1 for the first try
        outcome TEXT NOT NULL, -- 'done', 'rescheduled', 'stopped', 'skipped', 'failed', 'gave_up'
        error TEXT -- traceback, for 'failed' and 'gave_up'
    );

CREATE INDEX IF NOT EXISTS scheduled_job_runs_finished_at_idx ON scheduled_job_runs (finished_at);

CREATE INDEX IF NOT EXISTS scheduled_job_runs_kind_user_id_idx ON scheduled_job_runs (kind, user_id);
