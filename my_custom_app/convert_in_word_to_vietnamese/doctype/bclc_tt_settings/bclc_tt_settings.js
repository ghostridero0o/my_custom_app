frappe.ui.form.on("BCLC TT Settings", {
	refresh(frm) {
		frm.add_custom_button(__("Reset Default Settings"), () => {
			frappe.confirm(
				__("Reset cash accounts and mapping rules to the default BCLC TT mapping?"),
				() => {
					frappe.call({
						method: "my_custom_app.convert_in_word_to_vietnamese.doctype.bclc_tt_settings.bclc_tt_settings.reset_default_settings",
						freeze: true,
						freeze_message: __("Resetting default settings..."),
						callback(r) {
							if (!r.exc) {
								frappe.show_alert({
									message: r.message || __("BCLC TT Settings reset to default mapping"),
									indicator: "green",
								});
								frm.reload_doc();
							}
						},
					});
				}
			);
		});
	},
});
