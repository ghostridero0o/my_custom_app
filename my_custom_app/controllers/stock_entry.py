import frappe
from frappe import _
from frappe.desk.reportview import get_match_cond
from frappe.desk.search import validate_and_sanitize_search_inputs


@frappe.whitelist()
@validate_and_sanitize_search_inputs
def item_query(doctype, txt, searchfield, start, page_len, filters):
	project = filters.get("project")
	if not project:
		frappe.throw(_("Vui lòng chọn Project trước khi lọc Item theo Project."))

	return frappe.db.sql(
		"""
			select distinct `tabItem`.name, `tabItem`.item_name, `tabItem`.item_group, `tabItem`.stock_uom
			from `tabItem`
			inner join `tabStock Ledger Entry` sle on sle.item_code = `tabItem`.name
			where sle.project = %(project)s
				and sle.is_cancelled = 0
				and `tabItem`.disabled = 0
				and `tabItem`.is_stock_item = 1
				and (
					`tabItem`.name like %(txt)s
					or `tabItem`.item_name like %(txt)s
					or `tabItem`.item_group like %(txt)s
				)
				{match_cond}
			order by
				case when `tabItem`.name like %(txt)s then 0 else 1 end,
				`tabItem`.name
			limit %(page_len)s offset %(start)s
		""".format(match_cond=get_match_cond(doctype)),
		{
			"project": project,
			"txt": f"%{txt}%",
			"start": start,
			"page_len": page_len,
		},
	)
