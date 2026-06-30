// Package schema defines the HTTP request/response payloads. They intentionally
// match the contract the sahiy-market Go orchestrator already speaks, so the new
// service is a drop-in replacement for the Python agent's POST /process.
package schema

// ProcessRequest is the body of POST /process.
type ProcessRequest struct {
	SessionID string         `json:"session_id"`
	UserID    string         `json:"user_id"`
	Text      string         `json:"text"`
	Context   map[string]any `json:"context"`
}

// ProcessResponse is the body returned by POST /process.
type ProcessResponse struct {
	Type          string  `json:"type"` // auto | api | ticket | error
	Text          string  `json:"text"`
	TicketID      *string `json:"ticket_id"`
	Confidence    float64 `json:"confidence"`
	Escalate      bool    `json:"escalate"`
	HandoffReason *string `json:"handoff_reason"`
}

// HealthResponse is the body returned by GET /health.
type HealthResponse struct {
	Status  string `json:"status"`
	Service string `json:"service"`
	DB      string `json:"db"`
}

// ErrorResponse is the body returned for error statuses.
type ErrorResponse struct {
	Message string `json:"message"`
}
