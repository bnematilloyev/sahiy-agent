package config

import (
	"strings"
	"testing"
)

// A production process must refuse to start without a service token rather than
// come up with POST /process open to anyone who can reach it.
func TestLoadRejectsMissingServiceTokenOutsideDevelopment(t *testing.T) {
	for _, env := range []string{"production", "staging"} {
		t.Setenv("APP_ENV", env)
		t.Setenv("AI_SERVICE_TOKEN", "")

		_, err := Load()
		if err == nil {
			t.Fatalf("APP_ENV=%s: Load() succeeded, want an error", env)
		}
		if !strings.Contains(err.Error(), "AI_SERVICE_TOKEN") {
			t.Errorf("APP_ENV=%s: error = %v, want it to name the missing variable", env, err)
		}
	}
}

func TestLoadAcceptsProductionWithServiceToken(t *testing.T) {
	t.Setenv("APP_ENV", "production")
	t.Setenv("AI_SERVICE_TOKEN", "s3cret")

	cfg, err := Load()
	if err != nil {
		t.Fatalf("Load: %v", err)
	}
	if cfg.AI.ServiceToken != "s3cret" {
		t.Errorf("ServiceToken = %q", cfg.AI.ServiceToken)
	}
}

// Local development stays frictionless: no token required.
func TestLoadAllowsEmptyTokenInDevelopment(t *testing.T) {
	t.Setenv("APP_ENV", "development")
	t.Setenv("AI_SERVICE_TOKEN", "")

	if _, err := Load(); err != nil {
		t.Fatalf("Load: %v", err)
	}
}

// Whitespace is not a token.
func TestLoadRejectsBlankServiceToken(t *testing.T) {
	t.Setenv("APP_ENV", "production")
	t.Setenv("AI_SERVICE_TOKEN", "   ")

	if _, err := Load(); err == nil {
		t.Fatal("Load() succeeded with a whitespace-only token, want an error")
	}
}
