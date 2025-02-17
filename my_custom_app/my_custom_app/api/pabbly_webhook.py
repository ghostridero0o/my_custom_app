import frappe
import json
from frappe import _

@frappe.whitelist(allow_guest=True)
def receive_pabbly_webhook():
    try:
        # L?y d? li?u t? webhook g?i lên
        data = frappe.request.get_data(as_text=True)  # Chuy?n d?i thành chu?i
        
        # Phân tích d? li?u JSON
        data = json.loads(data)

        # L?y tên s? ki?n t? d? li?u
        event_name = data.get("event_name")

        if event_name == "user_submit_info":
            # L?y các tru?ng thông tin t? d? li?u c?a Zalo
            sender = str(data.get("sender", {}).get("id", "")).strip()  # Chuy?n d?i thành chu?i
            lead_name = str(data.get("info", {}).get("name", "")).strip()  # Chuy?n d?i thành chu?i
            phone = str(data.get("info", {}).get("phone", "")).strip()  # Chuy?n d?i thành chu?i
            address = str(data.get("info", {}).get("address", "")).strip()  # Chuy?n d?i thành chu?i
            district = str(data.get("info", {}).get("district", "")).strip()  # Chuy?n d?i thành chu?i
            city = str(data.get("info", {}).get("city", "")).strip()  # Chuy?n d?i thành chu?i

            # Ki?m tra xem thông tin có d?y d? hay không
            if not lead_name or not phone:
                return {"status": "error", "message": "Missing lead information"}

            # Ki?m tra xem lead_name dã t?n t?i hay chua
            existing_lead = frappe.db.exists("CRM Lead", {"custom_user_id": sender})
            if existing_lead:
                return {
                    "status": "success",
                    "message": "Lead already exists, no new entry created."
                }

            # T?o m?t b?n ghi Lead m?i trong ERPNext
            lead = frappe.get_doc({
                "doctype": "CRM Lead",
                "custom_user_id": sender,
                "first_name": lead_name,
                "mobile_no": phone,
                "custom_city": city,
                "custom_district": district,
                "custom_address": address,
                "status": "New",
                "source": "Zalo OA"
            })
            lead.insert(ignore_permissions=True)
            frappe.db.commit()

            return {"status": "success", "message": "CRM Lead created successfully"}

        elif event_name == "user_send_text":
            # X? lý s? ki?n user_send_text
            user_id = str(data.get("sender", {}).get("id", "")).strip()  # Chuy?n d?i thành chu?i

            # Ki?m tra xem user_id dã t?n t?i hay chua
            existing_user_lead = frappe.db.exists("CRM Lead", {"first_name": user_id})
            if existing_user_lead:
                return {
                    "status": "success",
                    "message": "User Lead already exists, no new entry created."
                }

            lead = frappe.get_doc({
                "doctype": "CRM Lead",
                "first_name": user_id,                
                "status": "Junk",
                "source": "Zalo OA"
            })
            lead.insert(ignore_permissions=True)
            frappe.db.commit()

            

            # Th?c hi?n hành d?ng c?n thi?t v?i tin nh?n
            # Ví d?: ghi nh?n vào log ho?c x? lý theo cách nào dó
            frappe.log_error(f"Received message from user: {user_id}", "Zalo OA User Message")

            return {"status": "success", "message": "User message processed successfully"}

        else:
            return {"status": "error", "message": "Unknown event type"}
    except json.JSONDecodeError:
        # L?i JSON không h?p l?
        frappe.log_error("Invalid JSON format", "Zalo Webhook Error")
        return {"status": "error", "message": "Invalid JSON format"}

    except Exception as e:
        # Ghi l?i khác
        frappe.log_error(f"Error in zalo Webhook: {e}", "zalo Webhook Error")
        return {"status": "error", "message": str(e)}

