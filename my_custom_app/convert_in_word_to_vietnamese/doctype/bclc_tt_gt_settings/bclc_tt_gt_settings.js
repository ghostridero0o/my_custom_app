frappe.ui.form.on("BCLC TT GT Settings", {
	refresh(frm) {
		frm.add_custom_button(__("Reset Default Mapping"), () => {
			frappe.confirm(
				__("Reset cash accounts and mapping rules to the default BCLC TT99 indirect mapping?"),
				() => {
					frappe.call({
						method:
							"my_custom_app.convert_in_word_to_vietnamese.doctype.bclc_tt_gt_settings.bclc_tt_gt_settings.reset_default_settings",
						callback(r) {
							frappe.show_alert({
								message: r.message || __("BCLC TT GT Settings reset to default mapping"),
								indicator: "green",
							});
							frm.reload_doc();
						},
					});
				}
			);
		});
	},
});
