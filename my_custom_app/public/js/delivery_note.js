frappe.ui.form.on("Delivery Note", {
	refresh(frm) {
		if (frm.doc.docstatus !== 0 || frm.doc.is_return || !frm.has_perm("write")) return;

		frm.add_custom_button(
			__("Gói hàng hóa"),
			() => {
				const dialog = new frappe.ui.Dialog({
					title: __("Lấy hàng hóa từ gói"),
					fields: [
						{
							fieldname: "group_item",
							label: __("Gói hàng hóa"),
							fieldtype: "Link",
							options: "Item Package",
							reqd: 1,
						},
						{
							fieldname: "number_of_sets",
							label: __("Số bộ"),
							fieldtype: "Float",
							default: 1,
							reqd: 1,
						},
					],
					primary_action_label: __("Get Items"),
					primary_action(values) {
						frappe.call({
							method: "my_custom_app.api.group_item.get_items",
							args: { group_item: values.group_item },
							callback(r) {
								if (!r.message) return;
								r.message.forEach((source) => {
									const row = frm.add_child("items");
									["item_code", "item_name", "description", "rate", "uom"].forEach((field) => {
										if (source[field] !== undefined) row[field] = source[field];
									});
									row.qty = flt(source.qty) * flt(values.number_of_sets);
								});
								frm.refresh_field("items");
								dialog.hide();
							},
						});
					},
				});
				dialog.show();
			},
			__("Get Items From")
		);
	},
});
