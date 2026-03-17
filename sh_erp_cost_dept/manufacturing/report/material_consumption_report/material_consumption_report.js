// Copyright (c) 2024, Amir Mansi and contributors
// For license information, please see license.txt

frappe.query_reports["Material Consumption Report"] = {
	filters: [
		{
			fieldname: "company",
			label: __("Company"),
			fieldtype: "Link",
			options: "Company",
			default: frappe.defaults.get_user_default("Company"),
		},
		{
			fieldname: "from_date",
			label: __("From Date"),
			fieldtype: "Date",
			default: frappe.datetime.add_months(frappe.datetime.nowdate(), -1),
		},
		{
			fieldname: "to_date",
			label: __("To Date"),
			fieldtype: "Date",
			default: frappe.datetime.nowdate(),
		},
		{
			fieldname: "work_order",
			label: __("Work Order"),
			fieldtype: "Link",
			options: "Work Order",
		},
		{
			fieldname: "production_item",
			label: __("Production Item"),
			fieldtype: "Link",
			options: "Item",
		},
		{
			fieldname: "item_code",
			label: __("Material Item"),
			fieldtype: "Link",
			options: "Item",
		},
	],
};
