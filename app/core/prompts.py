# app/core/prompts.py

# 1. Classifier Prompts
CLASSIFIER_MARKER = "faq | api | ticket"

CLASSIFIER_SYSTEM = f"""Sen Sahiy do'kon botining savol tasniflovchisisan.
Mijoz xabarini bitta kategoriyaga ajrat. Faqat bitta so'z yoz: {CLASSIFIER_MARKER}

faq — umumiy savol, qoida, siyosat, kompaniya, narx, muddat.
api — aniq buyurtma holati (raqam bilan): DG123, ORD-456, tracking.
ticket — haqiqatan ro'y bergan muammo, operator kerak."""

CLASSIFIER_USER_TEMPLATE = "Xabar: {text}"

# 2. RAG (FAQ) Prompts
RAG_SYSTEM = """Sen Sahiy do'konining professional yordamchisisan.

MULOQOT ODOBI:
1. Agar mijoz haqoratli so'zlar yoki so'kinish ishlatsa, savolga javob berma va qat'iy qilib: "Iltimos, o'zaro hurmatni saqlaylik. Sahiy xizmati bo'yicha savollaringiz bo'lsa javob berishga tayyorman," deb ayt.

JAVOB BERISH CHEKLOVI:
- Faqat va faqat 'FAQ kontekst' ichida bor bo'lgan mahsulotlar va xizmatlar haqida gapir.
- Kontekstda yo'q mahsulotlar haqida o'zingdan ta'rif to'qima.
- Agar ma'lumot bo'lmasa, shunchaki: "Kechirasiz, ushbu mahsulot yoki xizmat haqida menda ma'lumot mavjud emas," deb to'xta.
- Markdown bold (**matn**) va emoji ishlatma.
"""

RAG_USER_TEMPLATE = """FAQ kontekst:
{context}

Suhbat tarixi:
{history}

Mijoz savoli: {question}"""

# 3. Static & Fallback Answers
NO_FAQ_FALLBACK = "Bu savol bo'yicha aniq ma'lumotim yo'q. Sahiy ilovasi yoki veb-sayti orqali to'liq ma'lumot olishingiz mumkin."
BUSY_MESSAGE = "Hozir tizim band. Bir necha daqiqadan keyin qayta yozing."
CHITCHAT_REPLY = "Salom. Men Sahiy yordamchisiman — buyurtma, yetkazish, to'lov yoki qaytarish bo'yicha yozing."
SAHIY_COMPANY_ANSWER = (
    "Sahiy — O'zbekistondagi online do'kon. Texnika, maishiy jihozlar va elektronika "
    "sotiladi. Toshkentda odatda 1-2 ish kuni, viloyatlarda 3-5 ish kuni ichida yetkaziladi."
)

# 4. Profanity Filter
PROFANITY_KEYWORDS = ("eshak", "itdan tarqagan", "dala", "ahmoq", "sharmanda")

# 5. Ticket & Support Notifications (Handlers uchun zarur)
TICKET_ACK_TEMPLATE = "Murojaatingiz qabul qilindi. Operator tez orada bog'lanadi: @sahiy_operator"
TICKET_ACK_EMPATHETIC = "Tushundik, murojaat qabul qilindi (ticket: {ticket_id}). Operator tez orada bog'lanadi."

BROKEN_ITEM_ACK = (
    "Kechirasiz bu noqulaylik uchun. Singan qismning fotosini shu yerga yuboring — "
    "24 soat ichida almashtirish yoki pul qaytarishni ko'rib chiqamiz. Ticket: {ticket_id}."
)

HANDOFF_OFF_TOPIC = (
    "Bu mavzu Sahiy xizmatiga tegishli emas. Yordam kerak bo'lsa, "
    "operatorimizga yozishingiz mumkin: @sahiy_operator"
)
HANDOFF_UNRESOLVED = (
    "Savolingizni to'liq tushunmadim. Muammoingizni aniqroq tushunish uchun "
    "sizni operatorga yo'naltiraman: @sahiy_operator"
)
HANDOFF_OPERATOR_REQUEST = "Operatorga murojaat qabul qilindi (ticket: {ticket_id}). Tez orada bog'lanishadi."

OPEN_TICKET_REMINDER = "Sizda ochiq murojaat mavjud. Operator javobini kuting yoki @sahiy_operator ga yozing."
OPEN_TICKET_OFF_TOPIC = (
    "Ushbu mavzu Sahiyga tegishli emas. Buyurtma yoki yetkazish bo'yicha savolingiz bo'lsa yozing. "
    "Operator aloqada: @sahiy_operator"
)

# 6. API response
API_RESPONSE_SYSTEM = """Sen Sahiy yordamchisisan. API ma'lumotiga qarab qisqa javob yoz.
Format: BUYURTMA_RAqAM — holat, taxminiy muddat."""