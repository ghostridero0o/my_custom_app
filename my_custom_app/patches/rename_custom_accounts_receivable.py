import json
import frappe

OLD = 'Custom Accounts Receivable'
NEW = 'Các Khoản Phải Thu'


def execute():
    if frappe.db.exists('Report', OLD) and not frappe.db.exists('Report', NEW):
        frappe.rename_doc('Report', OLD, NEW, force=True)
    if frappe.db.exists('Report', NEW):
        frappe.db.set_value('Report', NEW, {'report_name': NEW, 'prepared_report': 0,
                                           'disable_prepared_report_automation': 1})
    # Workspace content embeds report links as JSON, outside Link-field rename handling.
    for workspace in frappe.get_all('Workspace', fields=['name', 'content']):
        if workspace.content and OLD in workspace.content:
            def replace(value):
                if isinstance(value, str):
                    return NEW if value == OLD else value
                if isinstance(value, list):
                    return [replace(x) for x in value]
                if isinstance(value, dict):
                    return {k: replace(v) for k, v in value.items()}
                return value
            frappe.db.set_value('Workspace', workspace.name, 'content',
                                json.dumps(replace(json.loads(workspace.content)), ensure_ascii=False))
    frappe.clear_cache()
