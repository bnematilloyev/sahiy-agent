package handler

import (
	"encoding/json"
	"errors"
	"net/http"
	"strings"

	"github.com/sahiy-backend/sahiy-agent/internal/api/schema"
	"github.com/sahiy-backend/sahiy-agent/internal/app/chat"
	"github.com/sahiy-backend/sahiy-agent/internal/domain/conversation"
)

// Process is the main chat entry point used by the sahiy-market orchestrator.
func (h *Handler) Process(w http.ResponseWriter, r *http.Request) {
	var req schema.ProcessRequest
	if err := json.NewDecoder(r.Body).Decode(&req); err != nil {
		writeError(w, http.StatusBadRequest, "invalid JSON body")
		return
	}

	if strings.TrimSpace(req.UserID) == "" {
		writeError(w, http.StatusUnprocessableEntity, "user_id is required")
		return
	}
	if strings.TrimSpace(req.Text) == "" {
		writeError(w, http.StatusUnprocessableEntity, "text is required")
		return
	}

	channel := "api"
	if req.Context != nil {
		if c, ok := req.Context["channel"].(string); ok && c != "" {
			channel = c
		}
	}

	reply, err := h.reply.Reply(r.Context(), chat.ReplyCommand{
		SessionID: req.SessionID,
		UserID:    req.UserID,
		Text:      req.Text,
		Channel:   channel,
		Metadata:  req.Context,
	})
	if err != nil {
		if errors.Is(err, conversation.ErrAccessDenied) {
			writeError(w, http.StatusForbidden, "session belongs to another user")
			return
		}
		h.log.Error("process: reply failed", "error", err)
		writeError(w, http.StatusInternalServerError, "failed to process message")
		return
	}

	writeJSON(w, http.StatusOK, toProcessResponse(reply))
}

func toProcessResponse(reply chat.Reply) schema.ProcessResponse {
	resp := schema.ProcessResponse{
		Type:       reply.Type.String(),
		Text:       reply.Text,
		Confidence: reply.Confidence.Float(),
		Escalate:   reply.Escalate,
		TicketID:   reply.TicketID,
	}
	if !reply.HandoffReason.IsZero() {
		code := reply.HandoffReason.Code()
		resp.HandoffReason = &code
	}
	return resp
}
