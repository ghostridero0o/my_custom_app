frappe.query_reports["Delivery Note Item Summary"] = {
    filters: [
      {
        fieldname: "company",
        label: "Company",
        fieldtype: "Link",
        options: "Company",
        default: frappe.defaults.get_default("company"),
        reqd: 1
      },
      {
        fieldname: "customer",
        label: "Customer",
        fieldtype: "Link",
        options: "Customer"
      },
      {
        fieldname: "item_group",
        label: __("Item Group"),
        fieldtype: "Link",
        options: "Item Group"
      },
      {
        fieldname: "item_code",
        label: __("Item"),
        fieldtype: "MultiSelectList",
        options: "Item",
        get_data: function (txt) {
          const item_group = frappe.query_report.get_filter_value("item_group");
          return frappe.db.get_link_options("Item", txt, {
            ...(item_group && { item_group })
          });
        }
      },
      {
        fieldname: "project",
        label: __("Project"),
        fieldtype: "MultiSelectList",
        options: "Project",
        get_data: function (txt) {
          return frappe.db.get_link_options("Project", txt, {
            company: frappe.query_report.get_filter_value("company")
          });
        }
      },
      {
        fieldname: "view_mode",
        label: "View Mode",
        fieldtype: "Select",
        options: ["By Item", "By Delivery Date", "By Delivery Note"],
        default: "By Item"
      }
    ]
  };
