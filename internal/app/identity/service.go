// Package identity verifies customer phones and Sahiy user ids, persisting markers
// into the conversation session aggregate.
package identity

import (
	"context"
	"fmt"
	"log/slog"
	"strconv"

	"github.com/sahiy-backend/sahiy-agent/internal/domain/conversation"
	domainidentity "github.com/sahiy-backend/sahiy-agent/internal/domain/identity"
	"github.com/sahiy-backend/sahiy-agent/internal/domain/shared"
)

// CustomerVerifier looks up customers in the Sahiy API.
type CustomerVerifier interface {
	FindUserIDByPhone(ctx context.Context, phone string) (int64, error)
	UserExists(ctx context.Context, userID int64) (bool, error)
}

// PhoneVerifyResult is the outcome of a phone lookup against Sahiy.
type PhoneVerifyResult struct {
	OK          bool
	Phone       string
	SahiyUserID int64
	Error       string // invalid_format | not_found | api_unavailable
}

// Service validates and persists customer identity markers.
type Service struct {
	verifier CustomerVerifier
	log      *slog.Logger
}

// New constructs the identity service. A nil verifier treats API as unavailable.
func New(verifier CustomerVerifier, log *slog.Logger) *Service {
	return &Service{verifier: verifier, log: log}
}

// VerifyPhone validates format and resolves the Sahiy user id.
func (s *Service) VerifyPhone(ctx context.Context, phone string) PhoneVerifyResult {
	candidates := domainidentity.PhoneSearchCandidates(phone)
	if len(candidates) == 0 {
		return PhoneVerifyResult{Error: "invalid_format"}
	}
	if s.verifier == nil {
		return PhoneVerifyResult{Error: "api_unavailable"}
	}
	for _, candidate := range candidates {
		userID, err := s.verifier.FindUserIDByPhone(ctx, candidate)
		if err != nil {
			s.log.Warn("identity: phone lookup failed", "phone", candidate, "error", err)
			return PhoneVerifyResult{Error: "api_unavailable"}
		}
		if userID > 0 {
			stored := domainidentity.ValidateUzbekPhone(candidate)
			if stored == "" {
				stored = candidate
			}
			s.log.Info("identity: phone verified", "phone", stored, "sahiy_user_id", userID)
			return PhoneVerifyResult{OK: true, Phone: stored, SahiyUserID: userID}
		}
	}
	s.log.Info("identity: phone not found", "phone", phone, "candidates", candidates)
	return PhoneVerifyResult{Error: "not_found", Phone: candidates[0]}
}

// PersistIdentity appends PHONE:/SAHIY_USER: markers to the session aggregate.
func (s *Service) PersistIdentity(session *conversation.Session, phone string, sahiyUserID int64) error {
	if _, err := session.Append(conversation.RoleUser, content(domainidentity.PhoneMessagePrefix+phone), ""); err != nil {
		return fmt.Errorf("identity: persist phone marker: %w", err)
	}
	marker := domainidentity.SahiyUserMessagePrefix + strconv.FormatInt(sahiyUserID, 10)
	if _, err := session.Append(conversation.RoleUser, content(marker), ""); err != nil {
		return fmt.Errorf("identity: persist user marker: %w", err)
	}
	return nil
}

// RegisterPhoneInSession verifies phone, persists markers, and returns the Sahiy user id.
// replyText is set on user-facing errors or identity-only confirmation messages.
func (s *Service) RegisterPhoneInSession(ctx context.Context, session *conversation.Session, phone string, lang shared.Language, identityOnly bool) (int64, string, error) {
	result := s.VerifyPhone(ctx, phone)
	switch result.Error {
	case "invalid_format":
		return 0, domainidentity.InvalidPhoneFormatText(lang), nil
	case "api_unavailable":
		return 0, domainidentity.APIUnavailableText(lang), nil
	case "not_found":
		return 0, domainidentity.PhoneNotRegisteredText(lang), nil
	}
	if !result.OK || result.SahiyUserID == 0 || result.Phone == "" {
		return 0, domainidentity.PhoneNotRegisteredText(lang), nil
	}
	if err := s.PersistIdentity(session, result.Phone, result.SahiyUserID); err != nil {
		return 0, "", err
	}
	if identityOnly {
		return result.SahiyUserID, domainidentity.PhoneVerifiedText(lang), nil
	}
	return result.SahiyUserID, "", nil
}

// RegisterSahiyUserIDInSession verifies and persists a Sahiy account id marker.
func (s *Service) RegisterSahiyUserIDInSession(ctx context.Context, session *conversation.Session, sahiyUserID int64, lang shared.Language, identityOnly bool) (int64, string, error) {
	if sahiyUserID < 1 {
		return 0, domainidentity.SahiyUserIDInvalidText(lang), nil
	}
	if s.verifier != nil {
		ok, err := s.verifier.UserExists(ctx, sahiyUserID)
		if err != nil {
			s.log.Warn("identity: user verify failed", "sahiy_user_id", sahiyUserID, "error", err)
			return 0, domainidentity.APIUnavailableText(lang), nil
		}
		if !ok {
			return 0, domainidentity.SahiyUserIDNotFoundText(lang), nil
		}
	}
	marker := domainidentity.SahiyUserMessagePrefix + strconv.FormatInt(sahiyUserID, 10)
	if _, err := session.Append(conversation.RoleUser, content(marker), ""); err != nil {
		return 0, "", fmt.Errorf("identity: persist user marker: %w", err)
	}
	if identityOnly {
		return sahiyUserID, domainidentity.SahiyUserIDVerifiedText(lang), nil
	}
	return sahiyUserID, "", nil
}

// EnsureVerified blocks Telegram traffic until a Sahiy user id is known.
// When replyText is non-empty the caller should return it immediately.
func (s *Service) EnsureVerified(ctx context.Context, session *conversation.Session, text string, meta map[string]any, lang shared.Language) (replyText string, err error) {
	if meta == nil {
		return domainidentity.IdentityRequiredText(lang), nil
	}
	if uid, ok := metaInt64(meta["sahiy_user_id"]); ok && uid > 0 {
		return "", nil
	}

	if sahiyID := domainidentity.ExtractSahiyUserID(text); sahiyID > 0 {
		uid, msg, err := s.RegisterSahiyUserIDInSession(ctx, session, sahiyID, lang, domainidentity.IsIdentityOnlyMessage(text))
		if err != nil {
			return "", err
		}
		meta["sahiy_user_id"] = uid
		return msg, nil
	}

	if phone := domainidentity.ExtractRegistrationPhone(text); phone != "" {
		uid, msg, err := s.RegisterPhoneInSession(ctx, session, phone, lang, domainidentity.IsIdentityOnlyMessage(text))
		if err != nil {
			return "", err
		}
		meta["verified_phone"] = phone
		meta["sahiy_user_id"] = uid
		return msg, nil
	}

	return domainidentity.IdentityRequiredText(lang), nil
}

func content(raw string) conversation.Content {
	c, err := conversation.NewContent(raw)
	if err != nil {
		panic("identity: invalid marker content: " + err.Error())
	}
	return c
}

func metaInt64(v any) (int64, bool) {
	switch n := v.(type) {
	case int64:
		return n, n > 0
	case int:
		return int64(n), n > 0
	case float64:
		return int64(n), n > 0
	default:
		return 0, false
	}
}
