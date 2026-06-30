package shared

// Confidence is a value object representing a 0..1 certainty score produced by
// the RAG/LLM layer. Out-of-range inputs are clamped so the invariant
// (0 <= value <= 1) always holds.
type Confidence struct {
	value float64
}

// NewConfidence clamps raw into [0, 1] and returns the value object.
func NewConfidence(raw float64) Confidence {
	switch {
	case raw < 0:
		raw = 0
	case raw > 1:
		raw = 1
	}
	return Confidence{value: raw}
}

// Float returns the underlying score.
func (c Confidence) Float() float64 { return c.value }

// Below reports whether the score is strictly below the given threshold.
func (c Confidence) Below(threshold float64) bool { return c.value < threshold }
