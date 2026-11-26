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
