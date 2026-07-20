"""Demo: turn receipt messages in a Raven channel into draft accounting documents.

The integration is intentionally conservative: AI extracts structured data, while
this module validates master data and creates draft documents only.
"""

from __future__ import annotations

import base64
import json
import mimetypes
import re
import time
from html import escape
from pathlib import Path

import frappe
from frappe.utils import add_to_date, cint, flt, get_url, nowdate

from my_custom_app.raven.settings import (
	expense_accounts,
	get_channel_settings,
	get_company_cost_center,
	get_settings,
	resolve_account,
	setting_value,
)


SUPPORTED_MESSAGE_TYPES = {"Text", "Image", "File"}
SUPPORTED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".pdf"}
DEFAULT_CHANNEL_NAMES = {"thu-chi", "thu chi", "thu–chi"}
SOURCE_MARKER = "RAVEN-AI-SOURCE:"


def on_raven_message(doc, method=None):
	"""Queue eligible channel messages after Raven has finished saving them."""
	if not _enabled() or doc.is_bot_message or doc.message_type not in SUPPORTED_MESSAGE_TYPES:
		return

	channel = frappe.get_cached_doc("Raven Channel", doc.channel_id)
	if channel.is_direct_message or channel.is_thread or not _is_accounting_channel(channel):
		return
	if doc.message_type in {"Image", "File"} and not doc.file:
		return

	# Raven saves the text before the upload completes. The on_update hook runs
	# once the file URL exists, so nearby text can now be collected safely.
	frappe.enqueue(
		"my_custom_app.raven.accounting_agent.process_message_bundle",
		queue="long",
		enqueue_after_commit=True,
		job_id=f"raven-accounting-{doc.channel_id}-{doc.owner}",
		deduplicate=True,
		message_name=doc.name,
		at_front=False,
	)


def process_message_bundle(message_name: str):
	"""Collect nearby messages, ask AI for JSON, then create a safe draft."""
	# Raven stores an image upload and its explanation as separate messages. Give
	# the user a short window to finish the pair before collecting the bundle.
	time.sleep(8)
	message = frappe.get_doc("Raven Message", message_name)
	lock_name = f"raven-accounting:{message.channel_id}:{message.owner}"

	with frappe.cache.lock(lock_name, timeout=120):
		messages = _collect_bundle(message)
		if not messages:
			return

		source_ids = sorted(row.name for row in messages)
		bundle_id = messages[0].name
		if _already_processed(bundle_id):
			return

		text = "\n".join(row.content for row in messages if row.content).strip()
		files = _collect_files(messages)
		if not files and not _has_meaningful_text(messages):
			# Nothing useful was attached or described, so there is no accounting
			# context for the AI to inspect.
			return

		try:
			analysis = _analyse_with_ai(text, files)
			analysis["source_message"] = bundle_id
			analysis["source_messages"] = source_ids
			analysis["source_channel"] = message.channel_id
			_create_accounting_request(message, analysis, files)
		except ClarificationRequired as exc:
			_send_bot_message(message.channel_id, f"⚠️ AI chưa thể tạo chứng từ: {escape(str(exc))}")
		except NotAccountingContext:
			return
		except Exception:
			frappe.log_error(frappe.get_traceback(), "Raven Accounting Agent")
			_send_bot_message(
				message.channel_id,
				"❌ Không thể xử lý chứng từ. Chi tiết đã được lưu trong Error Log.",
			)


@frappe.whitelist()
def retry_as_accounting_request(message_name: str):
	"""Allow a System Manager to recreate a proposal after fixing configuration."""
	if "System Manager" not in frappe.get_roles():
		frappe.throw("System Manager role is required.", frappe.PermissionError)
	message = frappe.get_doc("Raven Message", message_name)
	messages = _collect_bundle(message)
	files = _collect_files(messages)
	if not files and not _has_meaningful_text(messages):
		frappe.throw("An accounting image or description is required.")
	analysis = _analyse_with_ai("\n".join(row.content for row in messages if row.content), files)
	analysis["source_message"] = messages[0].name
	analysis["source_messages"] = [row.name for row in messages]
	analysis["source_channel"] = message.channel_id
	return _create_accounting_request(message, analysis, files).name


def _enabled() -> bool:
	return cint(get_settings().enabled) == 1


def _is_accounting_channel(channel) -> bool:
	settings = get_settings()
	if any(row.channel == channel.name for row in settings.get("channel_configurations") or []):
		return True
	configured_id = settings.channel
	if configured_id:
		return channel.name == configured_id
	return (channel.channel_name or "").strip().lower() in DEFAULT_CHANNEL_NAMES


def _collect_bundle(message):
	if message.message_type == "Text" and not _has_recent_file(message):
		return [message]
	start = add_to_date(message.creation, seconds=-120)
	end = add_to_date(message.creation, seconds=120)
	return frappe.get_all(
		"Raven Message",
		filters={
			"channel_id": message.channel_id,
			"owner": message.owner,
			"is_bot_message": 0,
			"message_type": ["in", list(SUPPORTED_MESSAGE_TYPES)],
			"creation": ["between", [start, end]],
		},
		fields=["name", "content", "file", "message_type", "creation"],
		order_by="creation asc",
	)


def _collect_files(messages):
	files = []
	seen = set()
	for message in messages:
		urls = [message.file] if message.file else []
		urls.extend(
			frappe.get_all(
				"File",
				filters={"attached_to_doctype": "Raven Message", "attached_to_name": message.name},
				pluck="file_url",
			)
		)
		for file_url in urls:
			if file_url and file_url not in seen and Path(file_url.split("?", 1)[0]).suffix.lower() in SUPPORTED_EXTENSIONS:
				seen.add(file_url)
				files.append({"url": file_url, "message": message.name})
	return files


def _has_recent_file(message) -> bool:
	return bool(
		frappe.db.exists(
			"Raven Message",
			{
				"channel_id": message.channel_id,
				"owner": message.owner,
				"is_bot_message": 0,
				"message_type": ["in", ["Image", "File"]],
				"file": ["is", "set"],
				"creation": ["between", [add_to_date(message.creation, seconds=-120), message.creation]],
			},
		)
	)


def _has_meaningful_text(messages) -> bool:
	for message in messages:
		content = (message.content or "").strip()
		if not content:
			continue
		if message.message_type == "Text":
			return True
		if Path(content.split("?", 1)[0]).suffix.lower() not in SUPPORTED_EXTENSIONS:
			return True
	return False


def _analyse_with_ai(user_text: str, files: list[dict]) -> dict:
	from raven.ai.openai_client import get_open_ai_client

	client = get_open_ai_client()
	content = [{"type": "text", "text": _accounting_prompt(user_text)}]
	for item in files:
		if Path(item["url"].split("?", 1)[0]).suffix.lower() == ".pdf":
			raise ClarificationRequired("Demo hiện nhận ảnh JPG/PNG/WEBP; PDF sẽ bổ sung ở bước tiếp theo.")
		content.append({"type": "image_url", "image_url": {"url": _data_url(item["url"])}})

	model = get_settings().ai_model or "gpt-4.1-mini"
	response = client.chat.completions.create(
		model=model,
		messages=[{"role": "user", "content": content}],
		response_format={"type": "json_object"},
		temperature=0,
	)
	raw = response.choices[0].message.content or "{}"
	data = json.loads(raw)
	_normalise_null_values(data)
	_apply_explicit_text_rules(data, user_text)
	_validate_analysis(data)
	return data


def _normalise_null_values(data):
	for key, value in data.items():
		if isinstance(value, str) and value.strip().lower() in {"null", "none"}:
			data[key] = None


def _apply_explicit_text_rules(data: dict, user_text: str):
	"""Let an explicit accounting instruction override ambiguous image content."""
	text = (user_text or "").lower()
	explicit_amount = _extract_explicit_vnd_amount(text)
	if explicit_amount:
		data["amount"] = explicit_amount
		data["currency"] = "VND"
	if "chi tiền mặt" in text:
		data["document_type"] = "Petty Expense"
		data["transaction_type"] = "Expense"
		data["mode_of_payment"] = get_settings().mode_of_payment
		missing = set(data.get("missing_fields") or [])
		data["missing_fields"] = sorted(
			missing - {"party", "party_type", "reference_no", "document_type"}
		)
		if "văn phòng phẩm" in text:
			data["expense_category"] = "office"


def _extract_explicit_vnd_amount(text: str) -> float | None:
	"""Extract an amount explicitly suffixed by đ/VND from Vietnamese text."""
	matches = re.findall(r"(?<!\d)(\d{1,3}(?:[.,]\d{3})+|\d+)\s*(?:đ|vnd)\b", text, flags=re.IGNORECASE)
	if not matches:
		return None
	normalised = matches[-1].replace(".", "").replace(",", "")
	return flt(normalised) or None


def _accounting_prompt(user_text: str) -> str:
	return f"""Bạn là trợ lý kế toán ERPNext. Đọc ảnh chứng từ và nội dung người dùng.
Chỉ trả về một JSON object, không markdown, theo schema:
{{
  "is_accounting_context": true,
  "document_type": "Payment Entry|Journal Entry|Petty Expense|Need Clarification|Not Accounting",
  "transaction_type": "Pay|Receive|Internal Transfer|Expense|Adjustment",
  "posting_date": "YYYY-MM-DD",
  "amount": 0,
  "currency": "VND",
  "party_type": "Customer|Supplier|Employee|null",
  "party": "tên đối tác hoặc null",
  "mode_of_payment": "Cash|Bank Transfer|null",
  "description": "mô tả ngắn",
  "expense_category": "office|meal|travel|other|null",
  "reference_no": "số chứng từ hoặc null",
  "confidence": 0.0,
  "missing_fields": []
}}
Quy tắc: chi tiền nhỏ có hóa đơn -> Petty Expense. Petty Expense không bắt buộc party hoặc
reference_no và không được chọn Need Clarification chỉ vì thiếu hai trường này.
Nếu text không ghi số tiền nhưng có ảnh bill, phải đọc trường Tổng cộng/Tổng thanh toán/
Thành tiền trên bill; ưu tiên tổng cuối cùng sau giảm giá, không dùng đơn giá hay số lượng.
Số tiền không kèm đơn vị tiền tệ (ví dụ "200") vẫn là dữ liệu hợp lệ; giữ đúng giá trị
để user kiểm tra và sửa trong form trước khi tạo chứng từ.
Trả/nhận tiền đối tác -> Payment Entry;
chuyển nội bộ hoặc điều chỉnh hai tài khoản -> Journal Entry. Nếu không chắc đã thanh toán,
không rõ số tiền, hoặc thiếu dữ liệu cốt lõi -> Need Clarification. Tin không liên quan đến
thu tiền, chi tiền, thanh toán, tạm ứng, hoàn ứng hoặc chuyển tiền phải trả
is_accounting_context=false và document_type=Not Accounting. Không tự bịa party/account.
Ngày hiện tại: {nowdate()}
Nội dung người dùng: {user_text or '(không có)'}"""


def _validate_analysis(data):
	allowed = {"Payment Entry", "Journal Entry", "Petty Expense", "Need Clarification", "Not Accounting"}
	if data.get("document_type") not in allowed:
		raise ClarificationRequired("AI không xác định được loại chứng từ.")
	if data.get("is_accounting_context") is False or data.get("document_type") == "Not Accounting":
		raise NotAccountingContext
	missing = set(data.get("missing_fields") or [])
	if (
		data.get("document_type") == "Need Clarification"
		and data.get("transaction_type") == "Expense"
		and flt(data.get("amount")) > 0
		and missing.issubset({"party", "party_type", "reference_no", "document_type"})
	):
		data["document_type"] = "Petty Expense"
		data["missing_fields"] = []
	if data["document_type"] == "Need Clarification":
		missing_text = ", ".join(data.get("missing_fields") or [])
		raise ClarificationRequired(missing_text or "Thông tin trên ảnh hoặc nội dung chưa đủ rõ.")
	if flt(data.get("amount")) <= 0:
		raise ClarificationRequired("Không đọc được số tiền hợp lệ.")
	if flt(data.get("confidence")) < flt(get_settings().min_confidence or 0.75):
		raise ClarificationRequired("Độ tin cậy thấp; vui lòng ghi rõ số tiền và mục đích chi.")


def _create_draft(data, files, ignore_permissions=False):
	doctype = data["document_type"]
	if doctype == "Payment Entry":
		doc = _create_payment_entry(data)
	elif doctype == "Journal Entry":
		doc = _create_journal_entry(data)
	else:
		doc = _create_petty_expense(data)
	doc.insert(ignore_permissions=ignore_permissions)
	_attach_files(doc, files)
	return doc


def _create_accounting_request(message, analysis, files):
	existing = frappe.db.exists("Raven Accounting Request", {"source_message": analysis["source_message"]})
	if existing:
		return frappe.get_doc("Raven Accounting Request", existing)

	request = frappe.get_doc(
		{
			"doctype": "Raven Accounting Request",
			"source_message": analysis["source_message"],
			"source_channel": message.channel_id,
			"requested_by": message.owner,
			"status": "Awaiting User",
			"suggested_document_type": analysis["document_type"],
			"transaction_type": analysis.get("transaction_type"),
			"amount": analysis.get("amount"),
			"confidence": analysis.get("confidence"),
			"extracted_data": json.dumps(analysis, ensure_ascii=False),
		}
	).insert(ignore_permissions=True)

	bot_message = _send_bot_message(
		message.channel_id,
		f"AI phát hiện giao dịch <b>{escape(analysis.get('transaction_type') or '')}</b> "
		f"với số tiền <b>{escape(str(analysis.get('amount') or 0))}</b>.<br>"
		f"🟠 <b>Chờ tạo bút toán</b> — "
		f"<a href=\"/app/raven-accounting-request/{request.name}?open_accounting_dialog=1\">"
		f"Mở form tạo chứng từ</a>.",
	)
	request.db_set("proposal_message", bot_message.name, update_modified=False)
	return request


def _create_payment_entry(data):
	from erpnext.accounts.utils import get_account_currency

	payment_type = data.get("transaction_type") if data.get("transaction_type") in {"Pay", "Receive", "Internal Transfer"} else "Pay"
	party_type = data.get("party_type")
	party = _resolve_link(party_type, data.get("party")) if party_type else None
	if payment_type != "Internal Transfer" and (not party_type or not party):
		raise ClarificationRequired("Payment Entry cần Customer/Supplier/Employee hợp lệ.")
	mode = data.get("mode_of_payment")
	if not mode or not frappe.db.exists("Mode of Payment", {"name": mode, "enabled": 1}):
		raise ClarificationRequired("Chưa xác định được Mode of Payment hợp lệ.")
	company = _company(data)
	bank_account = frappe.db.get_value(
		"Mode of Payment Account",
		{"parent": mode, "company": company},
		"default_account",
	)
	if not bank_account:
		raise ClarificationRequired(
			f"Mode of Payment {mode} chưa có tài khoản mặc định cho công ty {company}."
		)
	values = {
		"doctype": "Payment Entry",
		"payment_type": payment_type,
		"company": company,
		"posting_date": data.get("posting_date") or nowdate(),
		"mode_of_payment": mode,
		"paid_amount": flt(data["amount"]),
		"received_amount": flt(data["amount"]),
		"reference_no": data.get("reference_no") or f"AI-{data['source_message']}",
		"reference_date": data.get("reference_date") or data.get("posting_date") or nowdate(),
		"remarks": _remarks(data),
	}
	if payment_type == "Internal Transfer":
		paid_from = bank_account
		paid_to = data.get("paid_to")
		if not paid_from or not paid_to:
			raise ClarificationRequired("Internal Transfer cần tài khoản chuyển đi và tài khoản nhận.")
		values.update({
			"paid_from": paid_from,
			"paid_to": paid_to,
			"paid_from_account_currency": get_account_currency(paid_from),
			"paid_to_account_currency": get_account_currency(paid_to),
		})
	elif payment_type == "Pay":
		values.update({
			"party_type": party_type,
			"party": party,
			"paid_from": bank_account,
			"paid_from_account_currency": get_account_currency(bank_account),
		})
	else:
		values.update({
			"party_type": party_type,
			"party": party,
			"paid_to": bank_account,
			"paid_to_account_currency": get_account_currency(bank_account),
		})
	return frappe.get_doc(values)


def _create_journal_entry(data):
	settings = get_channel_settings(data.get("source_channel"))
	company = _company(data)
	debit = resolve_account(
		company,
		data.get("debit_account") or setting_value(settings, "journal_debit_account"),
	)
	credit = resolve_account(
		company,
		data.get("credit_account") or setting_value(settings, "journal_credit_account"),
	)
	if not debit or not credit:
		raise ClarificationRequired(
			"Journal Entry cần tài khoản Nợ/Có trên form hoặc trong Raven Accounting Settings."
		)
	amount = flt(data["amount"])
	doc = frappe.get_doc({
		"doctype": "Journal Entry",
		"company": company,
		"posting_date": data.get("posting_date") or nowdate(),
		"voucher_type": "Journal Entry",
		"user_remark": _remarks(data),
	})
	doc.append("accounts", {"account": debit, "debit_in_account_currency": amount})
	doc.append("accounts", {"account": credit, "credit_in_account_currency": amount})
	return doc


def _create_petty_expense(data):
	settings = get_channel_settings(data.get("source_channel"))
	mapping = expense_accounts(settings)
	company = _company(data)
	configured_expense = data.get("expense_account") or mapping.get(data.get("expense_category")) or mapping.get("other")
	expense_account = resolve_account(company, configured_expense)
	mode_of_payment = data.get("mode_of_payment") or setting_value(settings, "mode_of_payment")
	cost_center = data.get("cost_center") or get_company_cost_center(settings, company)
	if not expense_account or not mode_of_payment or not cost_center:
		raise ClarificationRequired("Chưa cấu hình expense account, Mode of Payment hoặc Cost Center cho Petty Expense demo.")
	meta = frappe.get_meta("Petty Expense")
	values = {
		"doctype": "Petty Expense",
		"company": company,
		"date": data.get("posting_date") or nowdate(),
		"amount": flt(data["amount"]),
		"description": _remarks(data),
		"expense_account": expense_account,
		"mode_of_payment": mode_of_payment,
		"cost_center": cost_center,
	}
	# Different Petty Expense apps may require these fields.
	for fieldname, value in (("cost_center", cost_center), ("petty_expense_type", settings.petty_expense_type)):
		if meta.has_field(fieldname) and value:
			values[fieldname] = value
	return frappe.get_doc(values)


def _company(data=None):
	company = (
		(data or {}).get("company")
		or frappe.defaults.get_user_default("Company")
		or get_channel_settings((data or {}).get("source_channel")).company
		or frappe.defaults.get_global_default("company")
	)
	if not company:
		raise ClarificationRequired("Chưa cấu hình Company cho accounting agent.")
	return company


def _resolve_link(doctype, value):
	if not value or not frappe.db.exists("DocType", doctype):
		return None
	if frappe.db.exists(doctype, value):
		return value
	return frappe.db.get_value(doctype, {"name": ["like", value]})


def _remarks(data):
	return f"{data.get('description') or 'Tạo từ Raven AI'}\n{SOURCE_MARKER}{data['source_message']}"


def _already_processed(source_message):
	if frappe.db.exists("Raven Accounting Request", {"source_message": source_message}):
		return True
	marker = f"%{SOURCE_MARKER}{source_message}%"
	return bool(
		frappe.db.exists("Payment Entry", {"remarks": ["like", marker]})
		or frappe.db.exists("Journal Entry", {"user_remark": ["like", marker]})
		or frappe.db.exists("Petty Expense", {"description": ["like", marker]})
	)


def _attach_files(doc, files):
	for item in files:
		source = frappe.db.get_value("File", {"file_url": item["url"]}, ["file_url", "is_private"], as_dict=True)
		if source:
			frappe.get_doc({
				"doctype": "File",
				"file_url": source.file_url,
				"is_private": source.is_private,
				"attached_to_doctype": doc.doctype,
				"attached_to_name": doc.name,
			}).insert(ignore_permissions=True)


def _data_url(file_url):
	file_doc = frappe.get_doc("File", {"file_url": file_url})
	path = file_doc.get_full_path()
	mime = mimetypes.guess_type(path)[0] or "application/octet-stream"
	encoded = base64.b64encode(Path(path).read_bytes()).decode("ascii")
	return f"data:{mime};base64,{encoded}"


def _send_result(channel_id, analysis, doc):
	url = f"{get_url()}/app/{frappe.scrub(doc.doctype).replace('_', '-')}/{doc.name}"
	amount = frappe.format_value(flt(analysis["amount"]), {"fieldtype": "Currency", "options": analysis.get("currency") or "VND"})
	_send_bot_message(
		channel_id,
		f"✅ Đã tạo <b>{escape(doc.doctype)}</b> nháp: <a href=\"{escape(url)}\">{escape(doc.name)}</a><br>"
		f"Số tiền: <b>{escape(amount)}</b><br>Độ tin cậy AI: {flt(analysis.get('confidence')) * 100:.0f}%",
	)


def _send_bot_message(channel_id, text, message_json=None):
	channel_settings = get_channel_settings(channel_id)
	bot_name = channel_settings.bot or get_settings().bot
	bot_user = frappe.db.get_value("Raven Bot", bot_name, "raven_user") if bot_name else None
	return frappe.get_doc({
		"doctype": "Raven Message",
		"channel_id": channel_id,
		"text": text,
		"message_type": "Text",
		"is_bot_message": 1,
		"bot": bot_user,
		"json": message_json,
	}).insert(ignore_permissions=True)


class ClarificationRequired(Exception):
	pass


class NotAccountingContext(Exception):
	pass
