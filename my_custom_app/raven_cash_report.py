import json
import re
from datetime import timedelta

import frappe
from frappe.utils import add_days, get_datetime, now_datetime


CHANNELS = {
	"phu_chau": {
		"channel_id": "Raven-thu-chi-phu-chau-2026",
		"title": "Phu Chau",
	},
	"pc33": {
		"channel_id": "Raven-thu-chi-pc33",
		"title": "PC33",
	},
}
REPORT_CHANNEL_NAME = "bao-cao"
REPORT_CHANNEL_ID = "Raven-bao-cao"

MONEY_RE = re.compile(
	r"(?P<num>\d{1,3}(?:[.,]\d{3})+|\d+)\s*(?P<unit>trieu|triệu|tr|k|nghin|nghìn|vnd|vnđ|đ|d)?",
	re.IGNORECASE,
)
AMOUNT_LABEL_RE = re.compile(
	r"(?:"
	r"số tiền|so tien|amount(?: transferred)?|"
	r"giá trị giao dịch|gia tri giao dich|"
	r"số tiền giao dịch|so tien giao dich|"
	r"thành tiền|thanh tien"
	r")\s*:?\s*(?P<amount>\d{1,3}(?:[.,]\d{3})+|\d+)\s*(?P<unit>trieu|triệu|tr|k|nghin|nghìn|vnd|vnđ|đ|d)?",
	re.IGNORECASE,
)
NOTE_AMOUNT_RE = re.compile(
	r"\b(?:thu|chi|nộp|nop|trả|tra|tt|thanh toán|thanh toan|ck|chuyển|chuyen)\b[^\d]{0,30}"
	r"(?P<amount>\d{1,3}(?:[.,]\d{3})+|\d+)\s*(?P<unit>trieu|triệu|tr|k|nghin|nghìn|vnd|vnđ|đ|d)?",
	re.IGNORECASE,
)
TRAILING_NOTE_AMOUNT_RE = re.compile(
	r"\b(?:thu|chi|nộp|nop|trả|tra|tt|thanh toán|thanh toan|ck|chuyển|chuyen)\b"
	r".*?[:：]\s*(?P<amount>\d{1,3}(?:[.,]\d{3})+|\d+)\s*(?P<unit>trieu|triệu|tr|k|nghin|nghìn|vnd|vnđ|đ|d)?\s*$",
	re.IGNORECASE,
)


def scheduled_send_daily_reports():
	"""Scheduler entrypoint. Runs every day at 19:00 from hooks.py."""
	send_daily_reports()


@frappe.whitelist()
def test_daily_reports(report_date=None, send=0):
	"""Manual test endpoint. Returns reports; sends only if send=1."""
	return send_daily_reports(report_date=report_date, send=bool(int(send or 0)))


def send_daily_reports(report_date=None, send=True):
	start, end, report_day = get_report_window(report_date)
	bot = frappe.get_doc("Raven Bot", "Data Bot")
	report_channel_id = get_report_channel_id()
	results = {}
	reports = []

	for config in CHANNELS.values():
		messages = get_channel_messages(config["channel_id"], start, end)
		entries = build_entries(messages)
		report = render_report(config["title"], report_day, entries)
		results[config["channel_id"]] = report
		reports.append(report)

	combined_report = "\n\n---\n\n".join(reports)
	results["sent_to"] = report_channel_id
	if send:
		bot.send_message(report_channel_id, combined_report, markdown=True)

	return results


def get_report_channel_id():
	channel_id = frappe.db.get_value(
		"Raven Channel",
		{
			"channel_name": REPORT_CHANNEL_NAME,
			"is_archived": 0,
		},
		"name",
	)
	return channel_id or REPORT_CHANNEL_ID


def get_report_window(report_date=None):
	if report_date:
		end = get_datetime(str(report_date) + " 19:00:00")
	else:
		now = now_datetime()
		end = now.replace(hour=19, minute=0, second=0, microsecond=0)
	start = add_days(end, -1)
	return start, end, end.date()


def get_channel_messages(channel_id, start, end):
	return frappe.get_all(
		"Raven Message",
		filters={
			"channel_id": channel_id,
			"creation": ["between", [start, end]],
		},
		fields=[
			"name",
			"creation",
			"owner",
			"channel_id",
			"text",
			"content",
			"file",
			"message_type",
			"is_bot_message",
		],
		order_by="creation asc",
		limit_page_length=1000,
	)


def build_entries(messages):
	entries = []
	skip_names = set()

	for index, message in enumerate(messages):
		if message.name in skip_names or is_existing_report(message):
			continue

		note = clean_text(message.get("text") or "")
		if not note and message.get("message_type") != "Image":
			note = clean_text(message.get("content") or "")

		if message.get("file") and index + 1 < len(messages):
			next_message = messages[index + 1]
			delta = get_datetime(next_message.creation) - get_datetime(message.creation)
			if (
				not next_message.get("file")
				and not is_existing_report(next_message)
				and timedelta(seconds=0) <= delta <= timedelta(minutes=3)
			):
				next_note = clean_text(next_message.get("text") or next_message.get("content") or "")
				if next_note:
					note = next_note
					skip_names.add(next_message.name)

		ocr_text = ""
		if message.get("file"):
			ocr_text = extract_document_text(message.file)

		amount = extract_amount(note, ocr_text)
		if not amount:
			continue

		source_account, counterparty = parse_parties(ocr_text, message.owner)
		kind = classify(note, ocr_text)
		entries.append(
			{
				"when": get_datetime(message.creation),
				"kind": kind,
				"amount": amount,
				"source_account": source_account,
				"counterparty": counterparty,
				"note": note or "Theo anh dinh kem",
			}
		)

	return entries


def is_existing_report(message):
	text = clean_text(message.get("text") or message.get("content") or "")
	return text.lower().startswith("bao cao thu chi") or text.lower().startswith("báo cáo thu chi")


def extract_document_text(file_url):
	bot = frappe.get_doc("Raven Bot", "Data Bot")

	if bot.get("use_google_document_parser") and bot.get("google_document_processor_id"):
		try:
			from raven.ai.google_ai import run_document_ai_processor

			extension = file_url.rsplit(".", 1)[-1].lower()
			result = run_document_ai_processor(
				bot.google_document_processor_id, file_url, extension
			)
			return stringify_processor_result(result)
		except Exception:
			frappe.log_error(frappe.get_traceback(), "Raven Document AI failed")

	return ""


def stringify_processor_result(result):
	if not result:
		return ""
	if isinstance(result, str):
		return result
	if isinstance(result, dict):
		return json.dumps(result, ensure_ascii=False)
	if isinstance(result, (list, tuple)):
		return "\n".join(stringify_processor_result(item) for item in result)
	if hasattr(result, "document") and getattr(result.document, "text", None):
		return result.document.text
	if hasattr(result, "text"):
		return result.text
	return str(result)


def clean_text(value):
	if not value:
		return ""
	value = re.sub(r"<br\s*/?>", "\n", value, flags=re.I)
	value = re.sub(r"<[^>]+>", " ", value)
	value = re.sub(r"\s+", " ", value)
	return value.strip()


def extract_amount(note, ocr_text):
	for text in [note or "", ocr_text or ""]:
		amount = extract_labeled_amount(text)
		if amount:
			return amount
	return extract_note_amount(note or "")


def extract_labeled_amount(text):
	text = re.sub(r"\b[\w-]+\.(?:png|jpe?g|webp)\b", " ", text, flags=re.I)
	for match in AMOUNT_LABEL_RE.finditer(text):
		amount = money_to_int(match)
		if amount >= 1000:
			return amount
	return 0


def extract_note_amount(text):
	match = TRAILING_NOTE_AMOUNT_RE.search(text)
	if match:
		amount = money_to_int(match)
		if amount >= 1000:
			return amount
	for match in NOTE_AMOUNT_RE.finditer(text):
		amount = money_to_int(match)
		if amount >= 1000:
			return amount
	for match in MONEY_RE.finditer(text):
		amount = money_to_int(match)
		unit = (match.group("unit") or "").lower()
		if amount >= 1000 and unit in {"trieu", "triệu", "tr", "k", "nghin", "nghìn", "vnd", "vnđ", "đ", "d"}:
			return amount
	return 0


def money_to_int(match):
	raw = (match.groupdict().get("num") or match.groupdict().get("amount")).replace(".", "").replace(",", "")
	amount = int(raw)
	unit = (match.group("unit") or "").lower()
	if unit in {"trieu", "triệu", "tr"}:
		amount *= 1000000
	elif unit in {"k", "nghin", "nghìn"}:
		amount *= 1000
	return amount


def classify(note, ocr_text):
	note_lowered = (note or "").lower()
	ocr_lowered = (ocr_text or "").lower()
	if re.search(r"\b(thu|nhập quỹ|nhap quy|nộp tiền|nop tien|trả lại|tra lai)\b", note_lowered):
		return "Thu"
	if re.search(r"\b(chi|trả tiền|tra tien|tt|thanh toán|thanh toan|ck đi|ck di)\b", note_lowered):
		return "Chi"
	if any(keyword in ocr_lowered for keyword in ["nhận tiền", "nhan tien", "credited", "received"]):
		return "Thu"
	if any(keyword in ocr_lowered for keyword in ["chuyển tiền thành công", "chuyen tien thanh cong", "amount transferred", "recipient"]):
		return "Chi"
	return "Chua ro"


def parse_parties(ocr_text, fallback_sender):
	compact = re.sub(r"\s+", " ", ocr_text or "").strip()
	source = ""
	counterparty = ""

	source_patterns = [
		r"(?:Từ|From)\s+([^\\n]+?)(?:Phí|Fee|$)",
		r"([A-Z ]+)\s+(?:chuyen tien|chuyển tiền)",
		r"Sender(?:'s)? Account[^:]*:\s*([^\\n]+)",
	]
	for pattern in source_patterns:
		match = re.search(pattern, compact, re.I)
		if match:
			source = match.group(1).strip(" :-")
			break

	counterparty_patterns = [
		r"Họ tên người nhận\s+([A-Z0-9 ._-]+)",
		r"Tên người nhận\s+([A-Z0-9 ._-]+)",
		r"Recipient(?:'s)? Name\s*:?\s*([A-Z0-9 ._-]+)",
		r"\n([A-Z ]{6,})\n(?:\d|[A-Z]{3,})",
	]
	for pattern in counterparty_patterns:
		match = re.search(pattern, ocr_text or "", re.I)
		if match:
			counterparty = match.group(1).strip(" :-")
			break

	if not source:
		source = "Chua doc duoc"
	if not counterparty:
		counterparty = "Chua doc duoc"

	return source, counterparty


def render_report(title, report_day, entries):
	lines = [
		f"Bao cao thu chi ngay {report_day.strftime('%d/%m/%Y')} (den 19h) cho {title}",
		"",
	]

	if not entries:
		lines.append("Khong co giao dich trong ky bao cao.")

	for index, entry in enumerate(entries, 1):
		kind_note = " (khong tinh vao tong)" if entry["kind"] == "Chua ro" else ""
		lines.append(
			f"{index}. {entry['when'].strftime('%H:%M %d/%m')} - {entry['kind']}{kind_note} {format_money(entry['amount'])}"
			f" - TK chuyen di: {entry['source_account']}"
			f" - Nguoi nhan/nguoi nop: {entry['counterparty']}"
			f" - {entry['note']}"
		)

	total_in = sum(entry["amount"] for entry in entries if entry["kind"] == "Thu")
	total_out = sum(entry["amount"] for entry in entries if entry["kind"] == "Chi")
	lines.extend(
		[
			"",
			f"Tong thu: {format_money(total_in)}",
			f"Tong chi: {format_money(total_out)}",
			f"Chenh lech: {format_money(total_in - total_out)}",
		]
	)
	return "\n".join(lines)


def format_money(value):
	return f"{int(value):,}".replace(",", ".")
