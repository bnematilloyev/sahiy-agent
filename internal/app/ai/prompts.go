package ai

import (
	"fmt"
	"strings"

	"github.com/sahiy-backend/sahiy-agent/internal/domain/shared"
)

// RouterSystemPrompt instructs the model to classify a message into a route and
// detect the reply language, returning strict JSON.
func RouterSystemPrompt() string {
	return strings.TrimSpace(`
You are the router for Sahiy customer support (an e-commerce and logistics
service shipping goods from China to Uzbekistan). Classify the user's latest
message into exactly one route and detect the language they want a reply in.

Routes:
- faq: general questions about the service, policies, prices, how it works.
- api: questions about a specific order or parcel status / tracking number.
- ticket: the user explicitly wants a human operator, or reports a serious complaint.
- product_search: the user wants to find or buy a specific product.
- category: the user wants to browse catalog categories.
- pickup: the user asks about pickup point locations.
- chitchat: greetings, thanks, or small talk with no informational request.

reply_language is one of: uz (Uzbek Latin), cyr (Uzbek Cyrillic), ru, en, zh.

Respond with ONLY a compact JSON object, no prose:
{"route":"<route>","reply_language":"<lang>","search_query":"<query or empty>"}`)
}

// BuildRouterUser renders the conversation history and the current message for
// the router prompt.
func BuildRouterUser(history []Message, text string) string {
	var b strings.Builder
	if len(history) > 0 {
		b.WriteString("Recent conversation:\n")
		for _, m := range history {
			b.WriteString(fmt.Sprintf("%s: %s\n", m.Role, m.Content))
		}
		b.WriteString("\n")
	}
	b.WriteString("Latest user message: ")
	b.WriteString(text)
	return b.String()
}

// RAGSystemPrompt instructs the model to answer strictly from provided context.
func RAGSystemPrompt(lang shared.Language) string {
	return fmt.Sprintf(strings.TrimSpace(`
You are Sahiy's customer-support assistant. Answer the user's question using
ONLY the knowledge-base context provided. If the context does not contain the
answer, say politely that you are not certain and suggest contacting an operator.
Be concise, friendly and accurate. Answer in %s.`), lang.EnglishName())
}

// BuildRAGUser renders the retrieved documents and the question.
func BuildRAGUser(contextDocs, question string) string {
	return fmt.Sprintf("Knowledge base context:\n%s\n\nUser question: %s", contextDocs, question)
}

// GenericSystemPrompt is used when no relevant knowledge-base entry is found.
func GenericSystemPrompt(lang shared.Language) string {
	return fmt.Sprintf(strings.TrimSpace(`
You are Sahiy's helpful customer-support assistant for an e-commerce and
logistics service that ships goods from China to Uzbekistan. Answer concisely
and helpfully. If you are unsure or the request needs account-specific data,
suggest contacting a human operator. Answer in %s.`), lang.EnglishName())
}

// OrderSystemPrompt instructs the model to answer a parcel/order inquiry using
// the provided order data context retrieved from the Sahiy API.
func OrderSystemPrompt(lang shared.Language) string {
	return fmt.Sprintf(strings.TrimSpace(`
You are Sahiy's customer-support assistant. You have been given structured data
about a customer's order(s) from the Sahiy logistics platform (goods shipped
from China to Uzbekistan). Use ONLY this data to answer the customer's question.
Be concise, friendly and accurate. If the data does not contain the specific
detail asked about, say so politely and suggest contacting an operator.
Answer in %s.`), lang.EnglishName())
}

// BuildOrderUser renders the order context and the customer's question for the LLM.
func BuildOrderUser(orderContext, question string) string {
	return fmt.Sprintf("Order data:\n%s\n\nCustomer question: %s", orderContext, question)
}
