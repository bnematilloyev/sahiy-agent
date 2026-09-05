package chat

import (
	"context"
	"fmt"
	"log/slog"
	"time"

	"github.com/sahiy-backend/sahiy-agent/internal/app/ai"
	appidentity "github.com/sahiy-backend/sahiy-agent/internal/app/identity"
	"github.com/sahiy-backend/sahiy-agent/internal/domain/conversation"
	"github.com/sahiy-backend/sahiy-agent/internal/domain/feedback"
	domainidentity "github.com/sahiy-backend/sahiy-agent/internal/domain/identity"
	"github.com/sahiy-backend/sahiy-agent/internal/domain/shared"
	domainsupport "github.com/sahiy-backend/sahiy-agent/internal/domain/support"
)

// telemetryTimeout bounds a background learning-loop write.
const telemetryTimeout = 5 * time.Second

// ReplyService is the Reply use case. It resolves the session aggregate, records
// the user turn, asks the Responder for an answer, records the assistant turn,
// persists the aggregate as a unit, then publishes its domain events.
type ReplyService struct {
	sessions    conversation.Repository
	tickets     domainsupport.Repository
	responder   Responder
	identity    *appidentity.Service
	events      EventPublisher
	feedback    feedback.Recorder
	idleTimeout time.Duration
	log         *slog.Logger
}

// NewReplyService wires the use case with its dependencies.
func NewReplyService(
	sessions conversation.Repository,
	tickets domainsupport.Repository,
	responder Responder,
	identity *appidentity.Service,
	events EventPublisher,
	recorder feedback.Recorder,
	idleTimeout time.Duration,
	log *slog.Logger,
) *ReplyService {
	return &ReplyService{
		sessions:    sessions,
		tickets:     tickets,
		responder:   responder,
		identity:    identity,
		events:      events,
		feedback:    recorder,
		idleTimeout: idleTimeout,
		log:         log,
	}
}

// Reply processes one user message and returns the assistant reply.
func (s *ReplyService) Reply(ctx context.Context, cmd ReplyCommand) (Reply, error) {
	start := time.Now()
	userID, err := shared.NewUserID(cmd.UserID)
	if err != nil {
		return Reply{}, err
	}
	channel := conversation.NewChannel(cmd.Channel)

	userContent, err := conversation.NewContent(cmd.Text)
	if err != nil {
		return Reply{}, err
	}

	session, err := s.resolveSession(ctx, cmd.SessionID, userID, channel)
	if err != nil {
		return Reply{}, err
	}
	// Tag the context once here so every LLM call made while answering this
	// message - router, FAQ, and any route handler - is attributable to this
	// session in token-usage accounting, without each of them having to know.
	ctx = ai.WithSessionID(ctx, session.ID().String())

	if _, err := session.Append(conversation.RoleUser, userContent, ""); err != nil {
		return Reply{}, err
	}

	meta := cmd.Metadata
	if meta == nil {
		meta = map[string]any{}
	}
	domainidentity.EnrichMetadata(meta, domainidentity.FromMessages(session.Messages()))

	// Persist a new session before Respond so FK-dependent writes (e.g. support
	// tickets referencing chat_sessions.id) succeed inside handlers.
	if !session.IsPersisted() {
		if err := s.sessions.Save(ctx, session); err != nil {
			return Reply{}, fmt.Errorf("chat: persist session before respond: %w", err)
		}
	}

	if s.identity != nil && domainidentity.RequiresCustomerIdentity(cmd.Channel) {
		lang := languageFromMeta(meta, cmd.Text)
		block, err := s.identity.EnsureVerified(ctx, session, cmd.Text, meta, lang)
		if err != nil {
			return Reply{}, fmt.Errorf("chat: identity gate: %w", err)
		}
		if block != "" {
			reply, rerr := s.completeReply(ctx, session, block, conversation.MessageTypeAuto, shared.NewConfidence(1), false, shared.NoHandoff, nil, nil)
			if rerr == nil {
				// The identity gate answered instead of a route, so it is
				// recorded under its own name rather than an empty route.
				s.recordTurn(ctx, session, cmd.Channel, Outcome{
					Route: "identity", Language: lang.Code(), Confidence: shared.NewConfidence(1),
				}, start)
			}
			return reply, rerr
		}
		if len(session.PendingMessages()) > 0 {
			if err := s.sessions.Save(ctx, session); err != nil {
				return Reply{}, fmt.Errorf("chat: persist identity markers: %w", err)
			}
		}
	}

	outcome, err := s.responder.Respond(ctx, session, cmd.Text, meta)
	if err != nil {
		return Reply{}, fmt.Errorf("chat: responder: %w", err)
	}

	reply, err := s.completeReply(ctx, session, outcome.Text, outcome.Type, outcome.Confidence, outcome.Escalate, outcome.HandoffReason, outcome.TicketID, outcome.ChannelExtra)
	if err == nil {
		s.recordTurn(ctx, session, cmd.Channel, outcome, start)
	}
	return reply, err
}

// recordTurn hands one answered message to the learning loop. It runs on a
// detached context in the background: the customer already has their reply,
// and a slow telemetry write must not hold the turn open.
func (s *ReplyService) recordTurn(_ context.Context, session *conversation.Session, channel string, out Outcome, start time.Time) {
	if s.feedback == nil {
		return
	}
	turn := feedback.Turn{
		SessionID:     session.ID().String(),
		Channel:       channel,
		Route:         out.Route,
		ReplyLanguage: out.Language,
		Confidence:    out.Confidence.Float(),
		Escalated:     out.Escalate,
		HandoffReason: out.HandoffReason.Code(),
		Degraded:      out.Degraded,
		Duration:      time.Since(start),
	}
	go func() {
		ctx, cancel := context.WithTimeout(context.Background(), telemetryTimeout)
		defer cancel()
		s.feedback.RecordTurn(ctx, turn)
	}()
}

// RecordRating stores a customer's star rating for their current conversation.
//
// Unlike turn telemetry this runs inline rather than in the background: a
// rating is a direct customer action that only ever happens once per session,
// so it is worth the single insert to not lose it. Errors are returned for the
// caller to log; they must not change what the customer is told, since they
// have already been thanked.
func (s *ReplyService) RecordRating(ctx context.Context, userID, channel string, stars int) error {
	if s.feedback == nil {
		return nil
	}
	uid, err := shared.NewUserID(userID)
	if err != nil {
		return err
	}

	// Attach the rating to the conversation it is about, when there is still
	// one open. A rating given after the session rotated is kept anyway, just
	// without a session to join it to.
	var sessionID string
	if session, serr := s.sessions.FindActive(ctx, uid, conversation.NewChannel(channel)); serr != nil {
		s.log.Warn("chat: could not resolve session for rating", "error", serr, "user_id", userID)
	} else if session != nil {
		sessionID = session.ID().String()
	}

	rating, err := feedback.NewRating(userID, channel, sessionID, stars)
	if err != nil {
		return err
	}
	s.feedback.RecordRating(ctx, rating)
	return nil
}

// RegisterVerifiedPhone validates a Telegram contact phone against Sahiy and
// persists identity markers on the user's active session.
func (s *ReplyService) RegisterVerifiedPhone(ctx context.Context, userID string, channel string, phone string, lang shared.Language) (sahiyUserID int64, errText string, err error) {
	if s.identity == nil {
		return 0, domainidentity.APIUnavailableText(lang), nil
	}
	uid, uerr := shared.NewUserID(userID)
	if uerr != nil {
		return 0, "", uerr
	}
	ch := conversation.NewChannel(channel)

	session, serr := s.sessions.FindActive(ctx, uid, ch)
	if serr != nil {
		return 0, "", fmt.Errorf("chat: find active session: %w", serr)
	}
	if session == nil {
		session = conversation.Open(uid, ch)
	}

	sahiyUID, msg, rerr := s.identity.RegisterPhoneInSession(ctx, session, phone, lang, false)
	if rerr != nil {
		return 0, "", rerr
	}
	if msg != "" {
		return 0, msg, nil
	}
	if err := s.sessions.Save(ctx, session); err != nil {
		return 0, "", fmt.Errorf("chat: persist verified phone: %w", err)
	}
	s.events.Publish(ctx, session.PullEvents())
	return sahiyUID, "", nil
}

func (s *ReplyService) completeReply(
	ctx context.Context,
	session *conversation.Session,
	text string,
	msgType conversation.MessageType,
	confidence shared.Confidence,
	escalate bool,
	handoff shared.HandoffReason,
	ticketID *string,
	channelExtra map[string]any,
) (Reply, error) {
	assistantContent, err := conversation.NewContent(text)
	if err != nil {
		return Reply{}, fmt.Errorf("chat: empty assistant reply: %w", err)
	}
	if _, err := session.Append(conversation.RoleAssistant, assistantContent, msgType); err != nil {
		return Reply{}, fmt.Errorf("chat: append assistant message: %w", err)
	}

	if err := s.sessions.Save(ctx, session); err != nil {
		return Reply{}, fmt.Errorf("chat: save session: %w", err)
	}
	s.events.Publish(ctx, session.PullEvents())

	return Reply{
		SessionID:     session.ID(),
		Type:          msgType,
		Text:          text,
		Confidence:    confidence,
		Escalate:      escalate,
		HandoffReason: handoff,
		TicketID:      ticketID,
		ChannelExtra:  channelExtra,
	}, nil
}

func languageFromMeta(meta map[string]any, text string) shared.Language {
	return shared.ResolveReplyLanguage(text, shared.LanguageHintFromMeta(meta), nil)
}

// resolveSession honours an explicit session id, otherwise reuses the user's
// active session or opens a fresh one. Idle sessions are rotated.
func (s *ReplyService) resolveSession(ctx context.Context, rawID string, userID shared.UserID, channel conversation.Channel) (*conversation.Session, error) {
	if id, ok := conversation.ParseSessionID(rawID); ok {
		existing, err := s.sessions.FindByID(ctx, id)
		if err != nil {
			return nil, err
		}
		if existing != nil {
			if !existing.BelongsTo(userID) {
				return nil, conversation.ErrAccessDenied
			}
			return s.rotateIfIdle(ctx, existing, channel)
		}
		// Map an unknown external session id onto a new local session.
		return conversation.OpenWithID(id, userID, channel), nil
	}

	active, err := s.sessions.FindActive(ctx, userID, channel)
	if err != nil {
		return nil, err
	}
	if active != nil {
		return s.rotateIfIdle(ctx, active, channel)
	}
	return conversation.Open(userID, channel), nil
}

// rotateIfIdle closes a session that has been silent past the idle timeout and
// returns a fresh one in its place.
func (s *ReplyService) rotateIfIdle(ctx context.Context, session *conversation.Session, channel conversation.Channel) (*conversation.Session, error) {
	lastActivity, err := s.sessions.LastActivityAt(ctx, session.ID())
	if err != nil {
		return nil, err
	}
	if !session.IsIdle(lastActivity, s.idleTimeout) {
		return session, nil
	}

	s.log.Info("rotating idle session", "session_id", session.ID().String())
	session.Close()
	if s.tickets != nil {
		if err := s.tickets.CloseBySession(ctx, session.ID()); err != nil {
			s.log.Warn("chat: close tickets for idle session", "session_id", session.ID().String(), "error", err)
		}
	}
	if err := s.sessions.Save(ctx, session); err != nil {
		return nil, err
	}
	s.events.Publish(ctx, session.PullEvents())
	return conversation.Open(session.UserID(), channel), nil
}
