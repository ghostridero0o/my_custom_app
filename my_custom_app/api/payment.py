import frappe
from frappe.utils import nowdate, get_url, get_traceback, generate_hash
from erpnext.accounts.utils import get_account_currency
from erpnext.accounts.doctype.payment_entry.payment_entry import (
    set_party_account,
    get_party_details
)

@frappe.whitelist()
def create_paid_entry(**kwargs):
    try:
        values = frappe.form_dict.get("values", {})
        party_type = values.get("party_type")
        party = values.get("party")
        mode_of_payment = values.get("mode_of_payment")
        paid_amount = values.get("paid_amount")

        message_id = (
            frappe.form_dict.get("message_id") or 
            kwargs.get("message_id") or
            values.get("message_id")
        )
        
        # Lấy channel_id từ Raven Message
        channel_id = None
        if message_id:
            channel_id = frappe.db.get_value("Raven Message", message_id, "channel_id")

        company = frappe.defaults.get_user_default("Company")

        if not (party_type and party and mode_of_payment and paid_amount):
            frappe.throw("Thiếu thông tin bắt buộc")

        # Khởi tạo PE
        doc = frappe.new_doc("Payment Entry")
        doc.update({
            "payment_type": "Pay",
            "party_type": party_type,
            "party": party,
            "mode_of_payment": mode_of_payment,
            "paid_amount": paid_amount,
            "received_amount": paid_amount,
            "posting_date": nowdate(),
            "company": company
        })

        set_party_account("Payment Entry", None, doc, party_type)

         # Set Paid To
        set_party_account("Payment Entry", None, doc, party_type)
        if not doc.paid_to:
            doc.paid_to = frappe.db.get_value("Company", company, "default_payable_account")
            if not doc.paid_to:
                frappe.throw(f"Company {company} không có Default Payable Account được cấu hình.")
            doc.paid_to_account_currency = frappe.db.get_value("Account", doc.paid_to, "account_currency")

        doc.update(get_party_details(
            party_type=party_type, party=party, company=company, date=nowdate()
        ))

        paid_from = frappe.db.get_value(
            "Mode of Payment Account",
            {"parent": mode_of_payment, "company": company},
            "default_account"
        )
        if not paid_from:
            frappe.throw("Không tìm thấy Paid From mặc định")

        doc.paid_from = paid_from
        doc.paid_from_account_currency = get_account_currency(paid_from)

        doc.run_method("set_exchange_rate")
        doc.run_method("set_missing_values")
        doc.run_method("set_amounts")

        doc.reference_no = doc.reference_no or f"AUTO-{generate_hash(length=6)}"
        doc.reference_date = doc.reference_date or nowdate()

        doc.insert(ignore_permissions=True)

        # ✅ Attach ảnh như file đính kèm (not comment)
        attached_files = []
        if message_id:
            files = frappe.get_all(
                "File",
                filters={"attached_to_name": message_id},
                fields=["file_url", "is_private"]
            )

            for f in files:
                if f["file_url"].lower().endswith((".jpg", ".jpeg", ".png", ".gif", ".webp")):
                    file_doc = frappe.get_doc({
                        "doctype": "File",
                        "file_url": f["file_url"],
                        "attached_to_doctype": "Payment Entry",
                        "attached_to_name": doc.name,
                        "is_private": f["is_private"]
                    }).insert(ignore_permissions=True)
                    attached_files.append(file_doc.name)

        # ✅ Gửi lại tin nhắn lên Raven
        if channel_id:
            try:
                link = f"{get_url()}/app/payment-entry/{doc.name}"
                content = f"Payment Entry nháp được tạo: {link}"

                frappe.get_doc({
                    "doctype": "Raven Message",
                    "channel_id": channel_id,
                    "text": content,
                    "message_type": "Text",
                    "owner": frappe.session.user
                }).insert(ignore_permissions=True)

            except Exception:
                frappe.log_error("❌ Raven Message Send Failed", get_traceback())
        else:
            frappe.log_error("⚠️ Thiếu channel_id", {
                "message_id": message_id,
                "form_dict": frappe.form_dict,
                "doc_name": doc.name
            })

        return {
            "name": doc.name,
            "message": f"<a href='/app/payment-entry/{doc.name}'><b>{doc.name}</b></a> đã tạo thành công."
        }

    except Exception:
        frappe.log_error("❌ create_paid_entry() FAILED", get_traceback())
        frappe.throw("Đã xảy ra lỗi khi tạo Payment Entry. Xem error log để biết thêm chi tiết.")
