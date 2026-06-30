package postgres

import (
	"context"
	"embed"
	"fmt"
	"log/slog"
	"sort"
	"strings"

	"github.com/jackc/pgx/v5/pgxpool"
)

//go:embed migrations/*.sql
var migrationFiles embed.FS

// Migrate applies every embedded *.up.sql migration not yet recorded in
// schema_migrations. Migrations use IF NOT EXISTS guards so they coexist safely
// with a schema previously created by the Python (Alembic) service.
func Migrate(ctx context.Context, pool *pgxpool.Pool, log *slog.Logger) error {
	if _, err := pool.Exec(ctx, `
		CREATE TABLE IF NOT EXISTS schema_migrations (
			version    TEXT PRIMARY KEY,
			applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
		)`); err != nil {
		return fmt.Errorf("migrate: ensure schema_migrations: %w", err)
	}

	entries, err := migrationFiles.ReadDir("migrations")
	if err != nil {
		return fmt.Errorf("migrate: read dir: %w", err)
	}

	var versions []string
	for _, e := range entries {
		if strings.HasSuffix(e.Name(), ".up.sql") {
			versions = append(versions, e.Name())
		}
	}
	sort.Strings(versions)

	for _, name := range versions {
		applied, err := isApplied(ctx, pool, name)
		if err != nil {
			return err
		}
		if applied {
			continue
		}

		sqlBytes, err := migrationFiles.ReadFile("migrations/" + name)
		if err != nil {
			return fmt.Errorf("migrate: read %s: %w", name, err)
		}

		tx, err := pool.Begin(ctx)
		if err != nil {
			return fmt.Errorf("migrate: begin %s: %w", name, err)
		}
		if _, err := tx.Exec(ctx, string(sqlBytes)); err != nil {
			_ = tx.Rollback(ctx)
			return fmt.Errorf("migrate: exec %s: %w", name, err)
		}
		if _, err := tx.Exec(ctx, `INSERT INTO schema_migrations (version) VALUES ($1)`, name); err != nil {
			_ = tx.Rollback(ctx)
			return fmt.Errorf("migrate: record %s: %w", name, err)
		}
		if err := tx.Commit(ctx); err != nil {
			return fmt.Errorf("migrate: commit %s: %w", name, err)
		}
		log.Info("migration applied", "version", name)
	}

	return nil
}

func isApplied(ctx context.Context, pool *pgxpool.Pool, version string) (bool, error) {
	var exists bool
	err := pool.QueryRow(ctx,
		`SELECT EXISTS (SELECT 1 FROM schema_migrations WHERE version = $1)`, version,
	).Scan(&exists)
	if err != nil {
		return false, fmt.Errorf("migrate: check %s: %w", version, err)
	}
	return exists, nil
}
