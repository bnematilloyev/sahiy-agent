// Package config loads service configuration from environment variables.
//
// It mirrors the settings of the Python sahiy-agent so the Go service can read
// the very same .env file during the migration period. Values are grouped into
// focused structs to keep call sites readable and intent obvious.
package config

import (
	"os"
	"strconv"
	"strings"
	"time"

	"github.com/joho/godotenv"
)

// Config is the aggregate of every configuration group used by the service.
type Config struct {
	App       App
	DB        DB
	AI        AI
	Telegram  Telegram
	Sahiy     Sahiy
	Exchange  Exchange
	Session   Session
	GoBackend GoBackend
}

// App holds process-wide settings.
type App struct {
	Name     string
	Env      string
	Debug    bool
	LogJSON  bool
	LogLevel string
	Host     string
	Port     int
}

func (a App) IsDevelopment() bool { return a.Env == "development" }

// DB holds database connection settings.
type DB struct {
	// URL is normalized to a pgx-compatible DSN (postgres://...).
	URL string
}

// AI holds LLM and embedding settings.
type AI struct {
	Provider          string // auto | openai | anthropic | rules
	ProviderChain     string // optional explicit comma list
	MaxConcurrent     int
	Timeout           time.Duration
	OpenAIKey         string
	OpenAIModel       string
	OpenAIEmbedding   string
	AnthropicKey      string
	AnthropicModel    string
	EmbeddingProvider string // auto | openai | mock
	RagThreshold      float64
	RagTopK           int
	RagMaxTokens      int
	OrderMaxTokens    int
	EmbeddingDim      int
	// EscalationThreshold: replies below this confidence are escalated.
	EscalationThreshold float64
	// ServiceToken is the shared secret for Go <-> agent internal calls.
	ServiceToken string
}

func (a AI) HasOpenAI() bool    { return strings.TrimSpace(a.OpenAIKey) != "" }
func (a AI) HasAnthropic() bool { return strings.TrimSpace(a.AnthropicKey) != "" }

// ChainProviders returns the ordered list of real LLM providers to try, mirroring
// the Python service. The rules fallback is appended by the chain at runtime.
func (a AI) ChainProviders() []string {
	if chain := strings.TrimSpace(a.ProviderChain); chain != "" {
		var out []string
		for _, name := range strings.Split(chain, ",") {
			if n := strings.ToLower(strings.TrimSpace(name)); n != "" {
				out = append(out, n)
			}
		}
		return out
	}

	switch strings.ToLower(strings.TrimSpace(a.Provider)) {
	case "rules":
		return nil
	case "openai":
		out := []string{"openai"}
		if a.HasAnthropic() {
			out = append(out, "anthropic")
		}
		return out
	case "anthropic":
		out := []string{"anthropic"}
		if a.HasOpenAI() {
			out = append(out, "openai")
		}
		return out
	default: // auto
		var out []string
		if a.HasAnthropic() {
			out = append(out, "anthropic")
		}
		if a.HasOpenAI() {
			out = append(out, "openai")
		}
		return out
	}
}

// EmbeddingChainProviders returns the ordered embedding providers; mock is always
// the final fallback.
func (a AI) EmbeddingChainProviders() []string {
	switch strings.ToLower(strings.TrimSpace(a.EmbeddingProvider)) {
	case "mock":
		return []string{"mock"}
	case "openai":
		return []string{"openai", "mock"}
	default: // auto
		if a.HasOpenAI() {
			return []string{"openai", "mock"}
		}
		return []string{"mock"}
	}
}

// Telegram holds bot channel settings (used from Phase 4 onward).
type Telegram struct {
	BotToken         string
	HTTPTimeout      time.Duration
	SendRetries      int
	TypingInterval   time.Duration
	StreamEnabled    bool
	RatingInactivity time.Duration
}

// Sahiy holds Sahiy Laravel API integration settings.
type Sahiy struct {
	BaseURL              string
	Timeout              time.Duration
	ServiceUserPhone     string
	ServiceUserPass      string
	ServiceUserDevice    string
	TokenBuffer          time.Duration
	AdminUsername        string
	AdminPassword        string
	AdminAccessToken     string
	AdminTokenTTL        time.Duration
	SKUPhotosEnabled     bool
	DaigouPageSize       int
	DaigouMaxPagesSearch int
	ProductSearchPage    int
	ProductSearchSort    string
	GoodsDeeplinkBase    string
	SearchDeeplinkBase   string
	CategoryDeeplinkBase string
	CategoriesCacheTTL   time.Duration
	PickupCacheTTL       time.Duration
}

func (s Sahiy) HasServiceUser() bool {
	return strings.TrimSpace(s.BaseURL) != "" &&
		strings.TrimSpace(s.ServiceUserPhone) != "" &&
		s.ServiceUserPass != ""
}

func (s Sahiy) HasAdminAPI() bool {
	return strings.TrimSpace(s.AdminAccessToken) != "" ||
		(strings.TrimSpace(s.AdminUsername) != "" && strings.TrimSpace(s.AdminPassword) != "")
}

// Exchange holds CNY->UZS rate settings.
type Exchange struct {
	APIURL      string
	ClientUUID  string
	CacheTTL    time.Duration
	UZSFallback float64
}

// Session holds chat-session lifecycle settings.
type Session struct {
	// IdleTimeout closes a session after this duration without messages (0 = disabled).
	IdleTimeout time.Duration
}

// GoBackend holds settings for the fallback call to the sahiy-market backend.
type GoBackend struct {
	URL     string
	Timeout time.Duration
}

// Load reads the .env file (if present) and builds a Config from the
// environment. Missing values fall back to sensible defaults that match the
// Python service.
func Load() (*Config, error) {
	// Best-effort: a missing .env is not an error (env vars may be set directly).
	_ = godotenv.Load()

	cfg := &Config{
		App: App{
			Name:     env("APP_NAME", "sahiy-agent"),
			Env:      env("APP_ENV", "development"),
			Debug:    envBool("DEBUG", true),
			LogJSON:  envBool("LOG_JSON", false),
			LogLevel: env("LOG_LEVEL", "INFO"),
			Host:     env("HOST", "0.0.0.0"),
			Port:     envInt("PORT", 8001),
		},
		DB: DB{
			URL: normalizeDSN(env("DATABASE_URL", "postgres://sahiy:sahiy_test@localhost:5433/sahiy_agent")),
		},
		AI: AI{
			Provider:            env("AI_PROVIDER", "auto"),
			ProviderChain:       env("AI_PROVIDER_CHAIN", ""),
			MaxConcurrent:       envInt("AI_MAX_CONCURRENT", 10),
			Timeout:             envSeconds("AI_TIMEOUT_SECONDS", 30),
			OpenAIKey:           env("OPENAI_API_KEY", ""),
			OpenAIModel:         env("OPENAI_MODEL", "gpt-4o-mini"),
			OpenAIEmbedding:     env("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small"),
			AnthropicKey:        env("ANTHROPIC_API_KEY", ""),
			AnthropicModel:      env("ANTHROPIC_MODEL", "claude-haiku-4-5-20251001"),
			EmbeddingProvider:   env("EMBEDDING_PROVIDER", "auto"),
			RagThreshold:        envFloat("RAG_SIMILARITY_THRESHOLD", 0.85),
			RagTopK:             envInt("RAG_TOP_K", 7),
			RagMaxTokens:        envInt("RAG_MAX_TOKENS", 1024),
			OrderMaxTokens:      envInt("AI_ORDER_MAX_TOKENS", 1024),
			EmbeddingDim:        envInt("EMBEDDING_DIMENSION", 1536),
			EscalationThreshold: envFloat("AI_ESCALATION_THRESHOLD", 0.45),
			ServiceToken:        env("AI_SERVICE_TOKEN", ""),
		},
		Telegram: Telegram{
			BotToken:         env("TELEGRAM_BOT_TOKEN", ""),
			HTTPTimeout:      envSeconds("TELEGRAM_HTTP_TIMEOUT_SECONDS", 60),
			SendRetries:      envInt("TELEGRAM_SEND_RETRIES", 3),
			TypingInterval:   envSecondsF("TELEGRAM_TYPING_INTERVAL_SECONDS", 4.0),
			StreamEnabled:    envBool("TELEGRAM_STREAM_ENABLED", true),
			RatingInactivity: envSecondsF("TELEGRAM_RATING_INACTIVITY_SECONDS", 1800.0),
		},
		Sahiy: Sahiy{
			BaseURL:              env("SAHIY_API_BASE_URL", ""),
			Timeout:              envSeconds("SAHIY_API_TIMEOUT_SECONDS", 15),
			ServiceUserPhone:     env("SERVICE_USER_PHONE", ""),
			ServiceUserPass:      env("SERVICE_USER_PASSWORD", ""),
			ServiceUserDevice:    env("SERVICE_USER_DEVICE_ID", "sahiy-agent"),
			TokenBuffer:          envSeconds("SERVICE_USER_TOKEN_BUFFER_SECONDS", 60),
			AdminUsername:        env("SAHIY_ADMIN_USERNAME", ""),
			AdminPassword:        env("SAHIY_ADMIN_PASSWORD", ""),
			AdminAccessToken:     env("SAHIY_ADMIN_ACCESS_TOKEN", ""),
			AdminTokenTTL:        envSeconds("SAHIY_ADMIN_TOKEN_TTL_SECONDS", 3000),
			SKUPhotosEnabled:     envBool("SAHIY_SKU_PHOTOS_ENABLED", true),
			DaigouPageSize:       envInt("SAHIY_DAIGOU_PAGE_SIZE", 10),
			DaigouMaxPagesSearch: envInt("SAHIY_DAIGOU_MAX_PAGES_SEARCH", 5),
			ProductSearchPage:    envInt("SAHIY_PRODUCT_SEARCH_PAGE_SIZE", 4),
			ProductSearchSort:    env("SAHIY_PRODUCT_SEARCH_SORT", "asc"),
			GoodsDeeplinkBase:    env("SAHIY_GOODS_DEEPLINK_BASE", "https://sahiy.uz/GoodsDetailView?u="),
			SearchDeeplinkBase:   env("SAHIY_PRODUCT_SEARCH_DEEPLINK_BASE", "https://sahiy.uz/search"),
			CategoryDeeplinkBase: env("SAHIY_CATEGORY_SEARCH_DEEPLINK_BASE", "https://sahiy.uz/search"),
			CategoriesCacheTTL:   envSeconds("SAHIY_1688_CATEGORIES_CACHE_TTL_SECONDS", 86400),
			PickupCacheTTL:       envSeconds("PICKUP_POINTS_CACHE_TTL_SECONDS", 3600),
		},
		Exchange: Exchange{
			APIURL:      env("SAHIY_EXCHANGE_API_URL", "https://api.abusahiy.uz/api/client/exchange/rates"),
			ClientUUID:  env("SAHIY_EXCHANGE_CLIENT_UUID", ""),
			CacheTTL:    envSeconds("SAHIY_EXCHANGE_CACHE_TTL_SECONDS", 3600),
			UZSFallback: envFloat("SAHIY_EXCHANGE_CNY_UZS_FALLBACK", 1750.0),
		},
		Session: Session{
			IdleTimeout: time.Duration(envFloat("SESSION_IDLE_HOURS", 24.0) * float64(time.Hour)),
		},
		GoBackend: GoBackend{
			URL:     env("GO_BACKEND_URL", "http://localhost:8080"),
			Timeout: envSeconds("GO_BACKEND_TIMEOUT_SECONDS", 10),
		},
	}

	return cfg, nil
}

// normalizeDSN converts a Python SQLAlchemy URL (postgresql+asyncpg://...) into
// a DSN that the pgx driver understands (postgres://...).
func normalizeDSN(raw string) string {
	raw = stripInlineComment(raw)
	raw = strings.ReplaceAll(raw, "postgresql+asyncpg://", "postgres://")
	raw = strings.ReplaceAll(raw, "postgresql+psycopg://", "postgres://")
	raw = strings.ReplaceAll(raw, "postgresql://", "postgres://")
	return raw
}

// --- small env helpers -----------------------------------------------------

func env(key, def string) string {
	if v, ok := os.LookupEnv(key); ok {
		v = stripInlineComment(v)
		if v != "" {
			return v
		}
	}
	return def
}

// stripInlineComment removes a trailing " # comment" from a .env value, matching
// the Python service's lenient parsing of inline comments.
func stripInlineComment(v string) string {
	if idx := strings.Index(v, " #"); idx != -1 {
		v = v[:idx]
	}
	return strings.TrimSpace(v)
}

func envInt(key string, def int) int {
	if v := env(key, ""); v != "" {
		if n, err := strconv.Atoi(v); err == nil {
			return n
		}
	}
	return def
}

func envFloat(key string, def float64) float64 {
	if v := env(key, ""); v != "" {
		if f, err := strconv.ParseFloat(v, 64); err == nil {
			return f
		}
	}
	return def
}

func envBool(key string, def bool) bool {
	if v := env(key, ""); v != "" {
		if b, err := strconv.ParseBool(strings.ToLower(v)); err == nil {
			return b
		}
	}
	return def
}

func envSeconds(key string, defSeconds int) time.Duration {
	return time.Duration(envInt(key, defSeconds)) * time.Second
}

func envSecondsF(key string, defSeconds float64) time.Duration {
	return time.Duration(envFloat(key, defSeconds) * float64(time.Second))
}
