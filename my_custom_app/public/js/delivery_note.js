frappe.ui.form.on("Delivery Note", {
	refresh(frm) {
		if (frm.doc.docstatus === 1 && !frm.doc.is_return && frm.has_perm("write")) {
			frm.add_custom_button(__("Link to Sales Order"), () => show_sales_order_link_dialog(frm));
		}

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

function show_sales_order_link_dialog(frm) {
	const dialog = new frappe.ui.Dialog({
		title: __("Link to Sales Order"),
		fields: [
			{
				fieldname: "sales_order",
				label: __("Sales Order"),
				fieldtype: "Link",
				options: "Sales Order",
				reqd: 1,
				get_query() {
					return {
						filters: {
							company: frm.doc.company,
							customer: frm.doc.customer,
							docstatus: 1,
						},
					};
				},
				onchange() {
					load_sales_order_link_preview(frm, dialog);
				},
			},
			{
				fieldname: "preview",
				fieldtype: "HTML",
				label: __("Matching Preview"),
			},
		],
		primary_action_label: __("Link Sales Order"),
		primary_action(values) {
			frappe.confirm(
				__("Link the matched Delivery Note items to {0}?", [values.sales_order]),
				() => {
					frappe.call({
						method: "my_custom_app.api.delivery_note.link_submitted_delivery_note_to_sales_order",
						args: { delivery_note: frm.doc.name, sales_order: values.sales_order },
						freeze: true,
						freeze_message: __("Linking Sales Order..."),
						callback(r) {
							if (!r.message) return;
							dialog.hide();
							frappe.show_alert({
								message: __("Linked {0} item(s) to Sales Order {1}", [
									r.message.linked_count,
									values.sales_order,
								]),
								indicator: "green",
							});
							frm.reload_doc();
						},
					});
				}
			);
		},
	});

	dialog.fields_dict.preview.$wrapper.html(
		`<div class="text-muted">${__("Select a Sales Order to preview matching items")}</div>`
	);
	dialog.show();
	dialog.get_primary_btn().prop("disabled", true);
}

function load_sales_order_link_preview(frm, dialog) {
	const sales_order = dialog.get_value("sales_order");
	const wrapper = dialog.fields_dict.preview.$wrapper;
	if (!sales_order) {
		dialog.get_primary_btn().prop("disabled", true);
		wrapper.html(`<div class="text-muted">${__("Select a Sales Order to preview matching items")}</div>`);
		return;
	}

	dialog.get_primary_btn().prop("disabled", true);
	wrapper.html(`<div class="text-muted">${__("Loading preview...")}</div>`);
	frappe.call({
		method: "my_custom_app.api.delivery_note.get_sales_order_link_preview",
		args: { delivery_note: frm.doc.name, sales_order },
		callback(r) {
			const preview = r.message;
			if (!preview) return;
			dialog.get_primary_btn().prop("disabled", !preview.can_link);

			const escape = (value) => frappe.utils.escape_html(cstr(value || ""));
			const rows = preview.rows.map((row) => `
				<tr>
					<td>${escape(row.item_code)}</td>
					<td>${escape(row.uom)}</td>
					<td class="text-right">${format_number(row.qty)}</td>
					<td>${escape(row.sales_order_item || "-")}</td>
					<td>${escape(row.status)}</td>
				</tr>
			`).join("");

			const notices = [];
			if (preview.linkable_count) {
				notices.push(
					`<div class="alert alert-success">${__("{0} matched item(s) will be linked.", [
						preview.linkable_count,
					])}</div>`
				);
			}
			if (preview.unmatched_count) {
				notices.push(
					`<div class="alert alert-warning">${__("{0} unmatched item(s) will remain unchanged.", [
						preview.unmatched_count,
					])}</div>`
				);
			}
			if (preview.linked_count) {
				notices.push(
					`<div class="alert alert-info">${__("{0} item(s) are already linked.", [
						preview.linked_count,
					])}</div>`
				);
			}
			wrapper.html(`
				${notices.join("")}
				<table class="table table-bordered table-hover">
					<thead>
						<tr>
							<th>${__("Item")}</th>
							<th>${__("UOM")}</th>
							<th class="text-right">${__("Qty")}</th>
							<th>${__("Sales Order Item")}</th>
							<th>${__("Status")}</th>
						</tr>
					</thead>
					<tbody>${rows}</tbody>
				</table>
			`);
		},
	});
}
