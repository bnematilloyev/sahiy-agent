package ai

import "context"

// sessionIDKey is the private context key for the chat session id.
type sessionIDKey struct{}

// WithSessionID tags a context with the chat session the work belongs to.
//
// Session id travels in the context rather than in CompletionRequest because
// it is request-scoped observability data, not part of any prompt: every LLM
// call made while handling one message belongs to that session, whichever
// route or handler happens to make it. Threading it through every application
// service signature would spread a telemetry concern across contracts that are
// otherwise about answering questions.
func WithSessionID(ctx context.Context, sessionID string) context.Context {
	if sessionID == "" {
		return ctx
	}
	return context.WithValue(ctx, sessionIDKey{}, sessionID)
}

// SessionIDFrom returns the session id carried by ctx, or "" when the call was
// not made on behalf of a chat session.
func SessionIDFrom(ctx context.Context) string {
	id, _ := ctx.Value(sessionIDKey{}).(string)
	return id
}
