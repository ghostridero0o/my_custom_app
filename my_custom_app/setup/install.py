import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

def after_install():
    create_custom_fields(get_custom_fields(), ignore_validate=True)

def get_custom_fields():
    return {
        "Employee Attendance Tool": [
            {
                "fieldname": "project",
                "label": "Project",
                "fieldtype": "Link",
                "options": "Project",
                "insert_after": "shift",  # thêm sau trường 'shift'
                "reqd": 0,
                "in_list_view": 0
            }
        ],
        "Stock Entry": [
            {
                "fieldname": "custom_only_items_in_project",
                "label": "Chỉ chọn item trong project này",
                "fieldtype": "Check",
                "insert_after": "items_section",
                "default": "0",
                "depends_on": "",
                "description": "Chỉ hiển thị Item đã có phát sinh tồn kho thuộc Project đang chọn.",
            }
        ],
    }
