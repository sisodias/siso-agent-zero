-- 021_voice_utterances — the SISO Voice mirror: every dictation transcript
-- (TEXT ONLY, never audio) lands here, one row per freeflow utterance.
-- The freeflow app appends NDJSON to ~/.siso/voice-outbox.ndjson; voice-sync.py
-- drains it to braind /voice/utterance, which INSERTs here. client_id (the
-- freeflow UUID) is the dedup key so the mirror is idempotent.

CREATE TABLE IF NOT EXISTS voice_utterances (
    id                TEXT PRIMARY KEY,                    -- 'vu_' + hex
    client_id         TEXT NOT NULL,                       -- freeflow PipelineHistoryItem.id (UUID) — dedup key
    captured_at       DATETIME NOT NULL,                   -- device speak-time (ISO8601 from the Mac)
    received_at       DATETIME DEFAULT CURRENT_TIMESTAMP,  -- when braind landed it
    raw_transcript    TEXT NOT NULL,                       -- rawTranscript
    cleaned_transcript TEXT,                               -- postProcessedTranscript
    intent            TEXT DEFAULT 'dictation',            -- dictation|command:automatic|command:manual
    app_name          TEXT,                                -- contextAppName
    bundle_id         TEXT,                                -- contextBundleIdentifier
    window_title      TEXT,                                -- contextWindowTitle
    model             TEXT,                                -- transcription/post-processing model
    word_count        INTEGER,                             -- words in raw_transcript
    machine           TEXT,                                -- device hostname
    agent_id          TEXT,                                -- optional: routed-to agent
    task_id           TEXT,                                -- optional: associated task
    session_id        TEXT,                                -- optional: associated session
    embedding         BLOB,                                -- optional: vector (text-only, never audio)
    embedding_model   TEXT,
    metadata          TEXT,                                -- optional JSON blob
    landed            INTEGER DEFAULT 0                     -- 1 once projected downstream
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_vu_client ON voice_utterances(client_id);
CREATE INDEX IF NOT EXISTS idx_vu_captured ON voice_utterances(captured_at DESC);
CREATE INDEX IF NOT EXISTS idx_vu_app ON voice_utterances(app_name);
