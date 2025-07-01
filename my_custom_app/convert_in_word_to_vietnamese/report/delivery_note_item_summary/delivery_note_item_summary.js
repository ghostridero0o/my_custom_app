frappe.query_reports["Delivery Note Item Summary"] = {
    filters: [
      {
        fieldname: "company",
        label: "Company",
        fieldtype: "Link",
        options: "Company",
        reqd: 1
      },
      {
        fieldname: "customer",
        label: "Customer",
        fieldtype: "Link",
        options: "Customer"
      },
      {
        fieldname: "project",
        label: "Project",
        fieldtype: "Link",
        options: "Project"
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
  