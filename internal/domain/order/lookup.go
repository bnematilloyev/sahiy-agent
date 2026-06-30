package order

// LookupRequest carries optional verified customer context for order queries.
type LookupRequest struct {
	Query          string
	VerifiedUserID int64
	VerifiedPhone  string
}
