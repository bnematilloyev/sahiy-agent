-- Lexical FAQ search that works without an embeddings API.
--
-- The previous fallback was `question ILIKE '%<whole query>%'`, which only ever
-- matched when the customer's entire sentence was a literal substring of a
-- stored question - in practice, never. Trigram similarity scores partial and
-- misspelled overlaps instead, which is what a fallback needs to do.
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- One index per language column: a Russian query scores against question_ru, an
-- Uzbek one against question_uz, so multilingual lookup needs no transliteration.
CREATE INDEX IF NOT EXISTS ix_faq_question_trgm
    ON faq_embeddings USING gin (question gin_trgm_ops);
CREATE INDEX IF NOT EXISTS ix_faq_question_uz_trgm
    ON faq_embeddings USING gin (question_uz gin_trgm_ops);
CREATE INDEX IF NOT EXISTS ix_faq_question_cyr_trgm
    ON faq_embeddings USING gin (question_cyr gin_trgm_ops);
CREATE INDEX IF NOT EXISTS ix_faq_question_ru_trgm
    ON faq_embeddings USING gin (question_ru gin_trgm_ops);
CREATE INDEX IF NOT EXISTS ix_faq_question_en_trgm
    ON faq_embeddings USING gin (question_en gin_trgm_ops);
CREATE INDEX IF NOT EXISTS ix_faq_question_zh_trgm
    ON faq_embeddings USING gin (question_zh gin_trgm_ops);
