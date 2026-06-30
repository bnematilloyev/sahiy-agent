package shared

// HandoffReason is a value object enumerating why a conversation must be handed
// off to a human operator. The zero value means "no handoff".
type HandoffReason struct {
	code string
}

// Predefined handoff reasons. These codes are part of the contract shared with
// the sahiy-market orchestrator.
var (
	NoHandoff               = HandoffReason{code: ""}
	HandoffOperatorRequest  = HandoffReason{code: "operator_request"}
	HandoffLowConfidence    = HandoffReason{code: "low_confidence"}
	HandoffConcreteIncident = HandoffReason{code: "concrete_incident"}
	HandoffOffTopic         = HandoffReason{code: "off_topic"}
	HandoffAIError          = HandoffReason{code: "ai_error"}
)

// Code returns the wire representation ("" when no handoff is needed).
func (h HandoffReason) Code() string { return h.code }

// IsZero reports whether no handoff is requested.
func (h HandoffReason) IsZero() bool { return h.code == "" }
