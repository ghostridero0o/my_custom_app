import json

import frappe
from frappe import _
from frappe.utils import now_datetime

from my_custom_app.raven.accounting_agent import _collect_files, _create_draft
from my_custom_app.raven.settings import get_settings


@frappe.whitelist()
def get_request(name: str):
	request = _get_allowed_request(name)
	data = _json(request.extracted_data)
	data["company"] = _default_company()
	data["available_mode_of_payments"] = _available_mode_of_payments(data["company"])
	data["reference_date"] = data.get("reference_date") or data.get("posting_date")
	if data.get("mode_of_payment") and data["mode_of_payment"] not in data["available_mode_of_payments"]:
		data["mode_of_payment"] = None
	party_type = data.get("party_type")
	if party_type and data.get("party") and not frappe.db.exists(party_type, data["party"]):
		data["party"] = None
	data.update(
		{
			"name": request.name,
			"status": request.status,
			"target_doctype": request.target_doctype,
			"target_document": request.target_document,
		}
	)
	return data


@frappe.whitelist()
def create_entry(name: str, values=None):
	request = _get_allowed_request(name)
	if request.status == "Created":
		return _result(request)
	if request.status not in {"Awaiting User", "Editing", "Failed"}:
		frappe.throw(_("This accounting request is currently {0}.").format(request.status))

	values = _json(values)
	data = _json(request.extracted_data)
	allowed_fields = {
		"document_type", "transaction_type", "posting_date", "amount", "currency",
		"party_type", "party", "mode_of_payment", "description", "expense_category",
		"reference_no", "reference_date", "paid_from", "paid_to", "company",
	}
	data.update({key: value for key, value in values.items() if key in allowed_fields})
	_validate_form(data)
	data["source_message"] = request.source_message

	request.db_set("status", "Creating", update_modified=True)
	try:
		messages = frappe.get_all(
			"Raven Message",
			filters={"name": ["in", data.get("source_messages") or [request.source_message]]},
			fields=["name", "file", "message_type", "content", "creation"],
		)
		files = _collect_files(messages)
		doc = _create_draft(data, files, ignore_permissions=False)
		request.db_set(
			{
				"status": "Created",
				"target_doctype": doc.doctype,
				"target_document": doc.name,
				"created_by": frappe.session.user,
				"created_on": now_datetime(),
				"error": None,
			},
			update_modified=True,
		)
		_update_card(request, doc)
		return _result(request)
	except Exception:
		request.db_set({"status": "Failed", "error": frappe.get_traceback()}, update_modified=True)
		raise


@frappe.whitelist()
def ignore_request(name: str):
	request = _get_allowed_request(name)
	if request.status != "Created":
		request.db_set("status", "Ignored", update_modified=True)
		_update_card(request)
	return {"status": request.status}


def sync_document_status(doc, method=None):
	request_name = frappe.db.get_value(
		"Raven Accounting Request",
		{"target_doctype": doc.doctype, "target_document": doc.name},
		"name",
	)
	if not request_name:
		return
	request = frappe.get_doc("Raven Accounting Request", request_name)
	status = "Cancelled" if method == "on_cancel" or doc.docstatus == 2 else "Submitted"
	request.db_set("status", status, update_modified=True)
	_update_card(request, doc)


def _get_allowed_request(name):
	request = frappe.get_doc("Raven Accounting Request", name)
	if request.requested_by != frappe.session.user and "System Manager" not in frappe.get_roles():
		frappe.throw(_("You cannot act on this accounting request."), frappe.PermissionError)
	return request


def _validate_form(data):
	if data.get("document_type") not in {"Petty Expense", "Payment Entry", "Journal Entry"}:
		frappe.throw(_("Please select a valid document type."))
	if not data.get("amount") or float(data["amount"]) <= 0:
		frappe.throw(_("Amount must be greater than zero."))
	if not data.get("posting_date"):
		frappe.throw(_("Posting date is required."))
	if not data.get("company") or not frappe.db.exists("Company", data["company"]):
		frappe.throw(_("Please select a valid Company."))
	if data["document_type"] == "Payment Entry" and data.get("transaction_type") != "Internal Transfer" and (not data.get("party_type") or not data.get("party")):
		frappe.throw(_("Party Type and Party are required for Payment Entry."))
	if data["document_type"] == "Payment Entry":
		if data.get("transaction_type") not in {"Pay", "Receive", "Internal Transfer"}:
			frappe.throw(_("Please select a valid Payment Type."))
		if not data.get("reference_no") or not data.get("reference_date"):
			frappe.throw(_("Reference No and Reference Date are required for Payment Entry."))
		if data["transaction_type"] == "Internal Transfer":
			if not data.get("paid_from") or not data.get("paid_to"):
				frappe.throw(_("Paid From and Paid To are required for Internal Transfer."))
			if data["paid_from"] == data["paid_to"]:
				frappe.throw(_("Paid From and Paid To must be different accounts."))
			company = data["company"]
			for account in (data["paid_from"], data["paid_to"]):
				if not frappe.db.exists("Account", {"name": account, "company": company, "is_group": 0}):
					frappe.throw(_("Please select valid ledger accounts for company {0}.").format(company))
		else:
			if data.get("party_type") not in {"Customer", "Supplier", "Employee"}:
				frappe.throw(_("Please select a valid Party Type."))
			if not frappe.db.exists(data["party_type"], data["party"]):
				frappe.throw(_("Please select a valid Party from the ERP link field."))
	if data["document_type"] != "Journal Entry":
		mode = data.get("mode_of_payment")
		if not mode or not frappe.db.exists("Mode of Payment", {"name": mode, "enabled": 1}):
			frappe.throw(_("Please select an active Mode of Payment."))
		company = data["company"]
		if not frappe.db.exists(
			"Mode of Payment Account", {"parent": mode, "company": company, "default_account": ["is", "set"]}
		):
			frappe.throw(
				_("Mode of Payment {0} has no default account for company {1}.").format(mode, company)
			)
		default_account = frappe.db.get_value(
			"Mode of Payment Account", {"parent": mode, "company": company}, "default_account"
		)
		if frappe.db.get_value("Account", default_account, "account_type") not in {"Cash", "Bank"}:
			frappe.throw(_("Mode of Payment {0} must use a default Cash or Bank account.").format(mode))


def _available_mode_of_payments(company):
	rows = frappe.get_all(
		"Mode of Payment Account",
		filters={"company": company, "default_account": ["is", "set"]},
		fields=["parent", "default_account"],
	)
	parents = [
		row.parent for row in rows
		if frappe.db.get_value("Account", row.default_account, "account_type") in {"Cash", "Bank"}
	]
	if not parents:
		return []
	return frappe.get_all(
		"Mode of Payment",
		filters={"name": ["in", parents], "enabled": 1},
		order_by="name asc",
		pluck="name",
	)


@frappe.whitelist()
def get_available_mode_of_payments(company):
	if not company or not frappe.db.exists("Company", company):
		return []
	return _available_mode_of_payments(company)


def _default_company():
	return (
		frappe.defaults.get_user_default("Company")
		or get_settings().company
		or frappe.defaults.get_global_default("company")
	)


def _update_card(request, doc=None):
	if not request.proposal_message or not frappe.db.exists("Raven Message", request.proposal_message):
		return
	message = frappe.get_doc("Raven Message", request.proposal_message)
	message.json = None
	doctype = doc.doctype if doc else request.target_doctype
	docname = doc.name if doc else request.target_document
	doc_url = f"/app/{frappe.scrub(doctype).replace('_', '-')}/{docname}" if doctype and docname else None
	if request.status == "Submitted":
		message.text = f"🟢 <b>Hoàn tất tạo bút toán</b> — <a href=\"{doc_url}\">{doctype} {docname}</a>."
	elif request.status == "Cancelled":
		message.text = f"🔴 <b>Bút toán bị hủy</b> — <a href=\"{doc_url}\">{doctype} {docname}</a>."
	elif doc:
		message.text = f"🔵 <b>Đã tạo bút toán nháp</b> — <a href=\"{doc_url}\">{doctype} {docname}</a>."
	elif request.status == "Ignored":
		message.text = "⚪ <b>Đề xuất bút toán đã được bỏ qua</b>."
	else:
		message.text = (
			f"🟠 <b>Chờ tạo bút toán</b> — "
			f"<a href=\"/app/raven-accounting-request/{request.name}?open_accounting_dialog=1\">"
			f"Mở form tạo chứng từ</a>."
		)
	message.flags.is_ai_streaming = True
	message.save(ignore_permissions=True)


def refresh_all_request_messages():
	for name in frappe.get_all("Raven Accounting Request", filters={"proposal_message": ["is", "set"]}, pluck="name"):
		request = frappe.get_doc("Raven Accounting Request", name)
		doc = None
		if request.target_doctype and request.target_document and frappe.db.exists(request.target_doctype, request.target_document):
			doc = frappe.get_doc(request.target_doctype, request.target_document)
		_update_card(request, doc)


def _result(request):
	return {
		"status": request.status,
		"doctype": request.target_doctype,
		"document": request.target_document,
	}


def _json(value):
	if not value:
		return {}
	if isinstance(value, dict):
		return value
	return json.loads(value)
