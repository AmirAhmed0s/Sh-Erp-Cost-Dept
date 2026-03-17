# Copyright (c) 2024, Amir Mansi and contributors
# For license information, please see license.txt

"""
User Assignment Control
========================
Controls which users a manager/department-head is allowed to assign tasks to.

- If apply_scope = "Full System": restriction applies across all DocTypes.
- If apply_scope = "Custom Selection": restriction only applies for the
  DocTypes listed in the allowed_doctypes child table.
"""

import frappe
from frappe import _
from frappe.model.document import Document


class UserAssignmentControl(Document):
	def validate(self):
		self._validate_no_duplicate_users()
		self._validate_no_duplicate_doctypes()

	def _validate_no_duplicate_users(self):
		seen = set()
		for row in self.allowed_users or []:
			if row.user in seen:
				frappe.throw(
					_("Row {0}: User {1} is duplicated in the Allowed Users table.").format(
						row.idx, frappe.bold(row.user)
					)
				)
			seen.add(row.user)

	def _validate_no_duplicate_doctypes(self):
		if self.apply_scope != "Custom Selection":
			return
		seen = set()
		for row in self.allowed_doctypes or []:
			if row.doctype_name in seen:
				frappe.throw(
					_("Row {0}: DocType {1} is duplicated in the Allowed DocTypes table.").format(
						row.idx, frappe.bold(row.doctype_name)
					)
				)
			seen.add(row.doctype_name)
