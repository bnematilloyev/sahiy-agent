// Package logger builds the application's structured logger.
package logger

import (
	"log/slog"
	"os"
	"strings"
)

// New returns a configured slog.Logger. When json is true it emits JSON lines,
// otherwise a human-friendly text format. The level string accepts the usual
// DEBUG/INFO/WARN/ERROR names (case-insensitive).
func New(level string, json bool) *slog.Logger {
	opts := &slog.HandlerOptions{Level: parseLevel(level)}

	var handler slog.Handler
	if json {
		handler = slog.NewJSONHandler(os.Stdout, opts)
	} else {
		handler = slog.NewTextHandler(os.Stdout, opts)
	}
	return slog.New(handler)
}

func parseLevel(level string) slog.Level {
	switch strings.ToUpper(strings.TrimSpace(level)) {
	case "DEBUG":
		return slog.LevelDebug
	case "WARN", "WARNING":
		return slog.LevelWarn
	case "ERROR":
		return slog.LevelError
	default:
		return slog.LevelInfo
	}
}
