frappe.ui.form.on("Stock Entry", {
	refresh(frm) {
		set_project_item_query(frm);
	},

	project(frm) {
		if (!frm.doc.project && frm.doc.custom_only_items_in_project) {
			frm.set_value("custom_only_items_in_project", 0);
		}
		set_project_item_query(frm);
	},

	custom_only_items_in_project(frm) {
		if (frm.doc.custom_only_items_in_project && !frm.doc.project) {
			frappe.msgprint(__("Vui lòng chọn Project trước khi bật bộ lọc Item theo Project."));
			frm.set_value("custom_only_items_in_project", 0);
		}
		set_project_item_query(frm);
	},
});

function set_project_item_query(frm) {
	frm.set_query("item_code", "items", () => {
		if (frm.doc.custom_only_items_in_project && frm.doc.project) {
			return {
				query: "my_custom_app.controllers.stock_entry.item_query",
				filters: { project: frm.doc.project },
			};
		}

		return erpnext.queries.item({ is_stock_item: 1 });
	});
}
