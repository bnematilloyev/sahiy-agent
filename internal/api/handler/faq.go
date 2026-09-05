package handler

import (
	"encoding/json"
	"errors"
	"net/http"

	"github.com/sahiy-backend/sahiy-agent/internal/api/schema"
	appfaq "github.com/sahiy-backend/sahiy-agent/internal/app/faq"
	"github.com/sahiy-backend/sahiy-agent/internal/domain/knowledge"
)

// IngestFAQ adds an entry to the knowledge base.
//
// This closes the learning loop: a question the assistant could not answer -
// and an operator had to - can be added here, and the next customer to ask it
// is answered from the knowledge base instead of escalating again.
func (h *Handler) IngestFAQ(w http.ResponseWriter, r *http.Request) {
	if h.faq == nil {
		writeError(w, http.StatusServiceUnavailable, "knowledge base is not available")
		return
	}

	var req schema.IngestFAQRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeError(w, http.StatusBadRequest, "invalid JSON body")
		return
	}

	locales := make(map[string]knowledge.Localized, len(req.Locales))
	for code, loc := range req.Locales {
		locales[code] = knowledge.Localized{Question: loc.Question, Answer: loc.Answer}
	}

	id, err := h.faq.Ingest(r.Context(), knowledge.Draft{
		Question: req.Question,
		Answer:   req.Answer,
		Category: req.Category,
		Locales:  locales,
	})
	if err != nil {
		// A missing question or answer is the caller's mistake, not a fault.
		if errors.Is(err, appfaq.ErrEmptyEntry) {
			writeError(w, http.StatusUnprocessableEntity, "question and answer are required")
			return
		}
		h.log.Error("faq ingest: failed", "error", err)
		writeError(w, http.StatusInternalServerError, "failed to add knowledge base entry")
		return
	}

	writeJSON(w, http.StatusCreated, schema.IngestFAQResponse{ID: id.Int()})
}
