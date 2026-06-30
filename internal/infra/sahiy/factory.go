package sahiy

import (
	"log/slog"
	"net/http"

	"github.com/sahiy-backend/sahiy-agent/internal/config"
)

// ServiceStack is the shared Sahiy service-user HTTP stack. One token cache and
// connection pool backs every Phase 3 adapter (order, catalog, pickup).
type ServiceStack struct {
	Client      *Client
	CustomerAPI *CustomerAPI
}

// NewServiceStack builds a single authenticated client and the APIs that share it.
func NewServiceStack(cfg config.Sahiy, log *slog.Logger) *ServiceStack {
	httpClient := &http.Client{Timeout: cfg.Timeout}
	auth := newServiceUserAuth(cfg, httpClient, log)
	client := newClient(cfg.BaseURL, auth, cfg.Timeout, log)
	return &ServiceStack{
		Client:      client,
		CustomerAPI: newCustomerAPI(client, cfg, log),
	}
}

// NewClient builds the authenticated Sahiy HTTP client (service_user auth).
// Prefer NewServiceStack when wiring multiple adapters from the composition root.
func NewClient(cfg config.Sahiy, log *slog.Logger) *Client {
	return NewServiceStack(cfg, log).Client
}

func newCustomerAPI(client *Client, cfg config.Sahiy, log *slog.Logger) *CustomerAPI {
	api := &CustomerAPI{
		client:         client,
		daigouList:     NewDaigouList(client, log),
		daigouPageSize: cfg.DaigouPageSize,
		skuEnabled:     cfg.SKUPhotosEnabled,
		log:            log,
	}
	if cfg.HasAdminAPI() && cfg.SKUPhotosEnabled {
		adminAuth := NewAdminAuth(cfg)
		adminClient := NewAdminClient(cfg, adminAuth, log)
		api.daigou = NewDaigouAdmin(adminClient, log)
		log.Info("sahiy daigou SKU enrichment enabled")
	}
	return api
}
