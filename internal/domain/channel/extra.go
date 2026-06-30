// Package channel defines transport-specific reply attachments (Telegram cards, keyboards).
package channel

const (
	KeyInlineKeyboard              = "inline_keyboard"
	KeyProductSearchItems          = "product_search_items"
	KeyProductSearchCNYToUZS       = "product_search_cny_to_uzs"
	KeyProductSearchSeeAllKeyword  = "product_search_see_all_keyword"
	KeyProductSearchSeeAllCategory = "product_search_see_all_category"
	KeyProductSearchSeeAllName     = "product_search_see_all_display_name"
	KeyDisableStream               = "disable_stream"
	KeyTelegramMessages            = "telegram_messages"
	KeyMediaPhotos                 = "media_photos"
	KeyPickupPointsCount           = "pickup_points_count"
)

// InlineButton is one Telegram inline keyboard button.
type InlineButton struct {
	Text         string `json:"text"`
	CallbackData string `json:"callback_data,omitempty"`
	URL          string `json:"url,omitempty"`
}

// DisableStream reports whether streaming UX should be skipped.
func DisableStream(extra map[string]any) bool {
	if extra == nil {
		return false
	}
	v, _ := extra[KeyDisableStream].(bool)
	return v
}
