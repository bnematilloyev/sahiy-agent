-- Ensure the localized FAQ columns exist on a pre-existing faq_embeddings table.
--
-- 0001 creates the table with these columns, but only IF NOT EXISTS: a database
-- carried over from the retired Python service already had a faq_embeddings
-- table, so 0001 was a no-op there and the localized columns were never added.
-- Every FAQ query selects them, so retrieval failed with
-- 'column "question_uz" does not exist' until this ran.
--
-- Idempotent, so it is a no-op on a database created by 0001.
ALTER TABLE faq_embeddings ADD COLUMN IF NOT EXISTS question_uz  TEXT;
ALTER TABLE faq_embeddings ADD COLUMN IF NOT EXISTS answer_uz    TEXT;
ALTER TABLE faq_embeddings ADD COLUMN IF NOT EXISTS question_cyr TEXT;
ALTER TABLE faq_embeddings ADD COLUMN IF NOT EXISTS answer_cyr   TEXT;
ALTER TABLE faq_embeddings ADD COLUMN IF NOT EXISTS question_ru  TEXT;
ALTER TABLE faq_embeddings ADD COLUMN IF NOT EXISTS answer_ru    TEXT;
ALTER TABLE faq_embeddings ADD COLUMN IF NOT EXISTS question_en  TEXT;
ALTER TABLE faq_embeddings ADD COLUMN IF NOT EXISTS answer_en    TEXT;
ALTER TABLE faq_embeddings ADD COLUMN IF NOT EXISTS question_zh  TEXT;
ALTER TABLE faq_embeddings ADD COLUMN IF NOT EXISTS answer_zh    TEXT;

-- Rows inserted before the columns existed keep their text only in the base
-- question/answer pair; mirror it into the Uzbek locale so language-specific
-- reads find something.
UPDATE faq_embeddings
   SET question_uz = question,
       answer_uz   = answer
 WHERE question_uz IS NULL;

-- The messages history window is read as "newest N for this session", which is
-- an index-only lookup with the sort key included.
CREATE INDEX IF NOT EXISTS ix_messages_session_created
    ON messages (session_id, created_at DESC);
