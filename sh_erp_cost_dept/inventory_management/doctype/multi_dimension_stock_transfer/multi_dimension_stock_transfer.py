# Copyright (c) 2024, Amir Mansi and contributors
# For license information, please see license.txt

"""
Multi Dimension Stock Transfer
================================
Allows row-level stock movements across Warehouse, Batch, and Brand dimensions.
On submission, generates Stock Ledger Entries (and GL Entries when applicable)
that include the custom_item_brand field for full brand-level traceability.
"""

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, flt, now_datetime, nowdate
from frappe.utils.data import get_datetime


class MultiDimensionStockTransfer(Document):
	# ------------------------------------------------------------------ #
	#  Standard lifecycle hooks                                            #
	# ------------------------------------------------------------------ #

	def validate(self):
		self._set_missing_values()
		self._validate_items()
		self._calculate_totals()

	def on_submit(self):
		self._validate_stock_availability()
		self._make_stock_ledger_entries()
		self._make_gl_entries()

	def on_cancel(self):
		self._cancel_stock_ledger_entries()

	# ------------------------------------------------------------------ #
	#  Private helpers                                                     #
	# ------------------------------------------------------------------ #

	def _set_missing_values(self):
		if not self.posting_date:
			self.posting_date = nowdate()

	def _validate_items(self):
		for row in self.transfer_items:
			if not row.item_code:
				frappe.throw(_("Row {0}: Item Code is required.").format(row.idx))
			if not row.qty or flt(row.qty) <= 0:
				frappe.throw(_("Row {0}: Qty must be greater than zero.").format(row.idx))
			if not row.from_warehouse and not row.to_warehouse:
				frappe.throw(
					_("Row {0}: At least one of From Warehouse or To Warehouse must be specified.").format(row.idx)
				)
			self._validate_brand_belongs_to_item(row)
			self._validate_batch_belongs_to_item(row)
			# Compute row amount
			row.amount = flt(row.qty) * flt(row.valuation_rate)

	def _validate_brand_belongs_to_item(self, row):
		"""Ensure from_brand and to_brand are in the item's custom_brands child table."""
		for brand_field in ("from_brand", "to_brand"):
			brand = row.get(brand_field)
			if not brand:
				continue
			valid = frappe.db.exists(
				"Item Brand",
				{"parent": row.item_code, "parentfield": "custom_brands", "brand": brand},
			)
			if not valid:
				frappe.throw(
					_(
						"Row {0}: Brand '{1}' is not linked to Item '{2}'.<br>"
						"الصف {0}: البراند '{1}' غير مرتبط بالصنف '{2}'."
					).format(row.idx, brand, row.item_code)
				)

	def _validate_batch_belongs_to_item(self, row):
		"""Ensure from_batch belongs to the item."""
		if not row.from_batch:
			return
		valid = frappe.db.exists(
			"Batch", {"name": row.from_batch, "item": row.item_code}
		)
		if not valid:
			frappe.throw(
				_(
					"Row {0}: Batch '{1}' does not belong to Item '{2}'.<br>"
					"الصف {0}: الدفعة '{1}' لا تنتمي إلى الصنف '{2}'."
				).format(row.idx, row.from_batch, row.item_code)
			)

	def _calculate_totals(self):
		self.total_qty = sum(flt(r.qty) for r in self.transfer_items)
		self.total_amount = sum(flt(r.amount) for r in self.transfer_items)

	# ------------------------------------------------------------------ #
	#  Stock availability check                                            #
	# ------------------------------------------------------------------ #

	def _validate_stock_availability(self):
		"""
		For each transfer row that has a from_warehouse, verify that the
		Item + Warehouse + Batch + Brand combination has enough actual_qty.
		"""
		for row in self.transfer_items:
			if not row.from_warehouse:
				continue
			available = self._get_actual_qty(
				row.item_code, row.from_warehouse, row.from_batch, row.from_brand
			)
			if flt(available) < flt(row.qty):
				frappe.throw(
					_(
						"Row {0}: Not enough stock for Item <b>{1}</b> in Warehouse <b>{2}</b>.<br>"
						"Available: {3} | Required: {4}<br><br>"
						"الصف {0}: لا توجد كمية كافية للصنف <b>{1}</b> في المستودع <b>{2}</b>.<br>"
						"المتاح: {3} | المطلوب: {4}"
					).format(
						row.idx,
						row.item_code,
						row.from_warehouse,
						available,
						row.qty,
					)
				)

	def _get_actual_qty(self, item_code, warehouse, batch_no=None, brand=None):
		"""
		Return the current actual_qty from tabStock Ledger Entry considering
		item + warehouse + batch + brand dimensions.
		"""
		conditions = {
			"item_code": item_code,
			"warehouse": warehouse,
			"is_cancelled": 0,
		}
		if batch_no:
			conditions["batch_no"] = batch_no
		if brand:
			conditions["custom_item_brand"] = brand

		result = frappe.db.sql(
			"""
			SELECT SUM(actual_qty)
			FROM `tabStock Ledger Entry`
			WHERE item_code = %(item_code)s
			  AND warehouse = %(warehouse)s
			  AND is_cancelled = 0
			  {batch_cond}
			  {brand_cond}
			""".format(
				batch_cond="AND batch_no = %(batch_no)s" if batch_no else "",
				brand_cond="AND custom_item_brand = %(custom_item_brand)s" if brand else "",
			),
			{
				"item_code": item_code,
				"warehouse": warehouse,
				"batch_no": batch_no,
				"custom_item_brand": brand,
			},
		)
		return flt(result[0][0]) if result and result[0][0] is not None else 0.0

	# ------------------------------------------------------------------ #
	#  Stock Ledger Entry creation                                         #
	# ------------------------------------------------------------------ #

	def _make_stock_ledger_entries(self):
		"""
		For each transfer row create two SLE entries:
		  1. Negative SLE at the source (from_warehouse)
		  2. Positive SLE at the destination (to_warehouse)

		The custom_item_brand field carries the brand dimension.
		"""
		sle_list = []
		for row in self.transfer_items:
			if row.from_warehouse:
				sle_list.append(
					self._build_sle(
						row=row,
						warehouse=row.from_warehouse,
						actual_qty=-flt(row.qty),
						batch_no=row.from_batch,
						brand=row.from_brand,
					)
				)
			if row.to_warehouse:
				sle_list.append(
					self._build_sle(
						row=row,
						warehouse=row.to_warehouse,
						actual_qty=flt(row.qty),
						batch_no=row.to_batch,
						brand=row.to_brand,
					)
				)

		for sle_data in sle_list:
			self._insert_sle(sle_data)

	def _build_sle(self, row, warehouse, actual_qty, batch_no=None, brand=None):
		return frappe._dict(
			{
				"doctype": "Stock Ledger Entry",
				"item_code": row.item_code,
				"warehouse": warehouse,
				"actual_qty": actual_qty,
				"valuation_rate": flt(row.valuation_rate),
				"batch_no": batch_no or "",
				"custom_item_brand": brand or "",
				"voucher_type": self.doctype,
				"voucher_no": self.name,
				"voucher_detail_no": row.name,
				"company": self.company,
				"posting_date": row.posting_date or self.posting_date,
				"posting_time": now_datetime().strftime("%H:%M:%S"),
				"is_cancelled": 0,
				"stock_uom": row.uom,
			}
		)

	def _insert_sle(self, sle_data):
		sle = frappe.get_doc(sle_data)
		sle.flags.ignore_permissions = True
		sle.flags.ignore_links = True
		sle.insert()

	# ------------------------------------------------------------------ #
	#  GL Entry creation                                                   #
	# ------------------------------------------------------------------ #

	def _make_gl_entries(self):
		"""
		Generate GL Entries if source and target warehouses belong to
		different stock accounts.
		"""
		from erpnext.accounts.general_ledger import make_gl_entries

		gl_entries = []
		for row in self.transfer_items:
			if not row.from_warehouse or not row.to_warehouse:
				continue
			from_account = self._get_warehouse_account(row.from_warehouse)
			to_account = self._get_warehouse_account(row.to_warehouse)
			if not from_account or not to_account:
				continue
			if from_account == to_account:
				continue  # Same account — no GL impact needed

			amount = flt(row.qty) * flt(row.valuation_rate)
			if not amount:
				continue

			# Debit the destination account
			gl_entries.append(
				self._build_gle(
					account=to_account,
					debit=amount,
					credit=0,
					cost_center=self._get_cost_center(),
					brand=row.to_brand,
					remarks=f"Transfer from {row.from_warehouse} to {row.to_warehouse}",
				)
			)
			# Credit the source account
			gl_entries.append(
				self._build_gle(
					account=from_account,
					debit=0,
					credit=amount,
					cost_center=self._get_cost_center(),
					brand=row.from_brand,
					remarks=f"Transfer from {row.from_warehouse} to {row.to_warehouse}",
				)
			)

		if gl_entries:
			try:
				make_gl_entries(gl_entries, cancel=False, adv_adj=False)
			except Exception as e:
				frappe.log_error(str(e), "Multi Dimension Stock Transfer - GL Error")
				frappe.msgprint(
					_("GL Entries could not be created: {0}").format(str(e)), alert=True
				)

	def _build_gle(self, account, debit, credit, cost_center, brand=None, remarks=""):
		return frappe._dict(
			{
				"doctype": "GL Entry",
				"posting_date": self.posting_date,
				"account": account,
				"debit": debit,
				"credit": credit,
				"debit_in_account_currency": debit,
				"credit_in_account_currency": credit,
				"against": self.company,
				"voucher_type": self.doctype,
				"voucher_no": self.name,
				"company": self.company,
				"cost_center": cost_center,
				"custom_item_brand": brand or "",
				"remarks": remarks,
				"is_opening": "No",
			}
		)

	def _get_warehouse_account(self, warehouse):
		"""Return the account linked to a warehouse (if any)."""
		if not warehouse:
			return None
		account = frappe.db.get_value("Warehouse", warehouse, "account")
		return account

	def _get_cost_center(self):
		return frappe.db.get_value("Company", self.company, "cost_center")

	# ------------------------------------------------------------------ #
	#  Cancel SLE entries                                                  #
	# ------------------------------------------------------------------ #

	def _cancel_stock_ledger_entries(self):
		frappe.db.sql(
			"""
			UPDATE `tabStock Ledger Entry`
			SET is_cancelled = 1
			WHERE voucher_type = %s AND voucher_no = %s
			""",
			(self.doctype, self.name),
		)

	# ------------------------------------------------------------------ #
	#  Whitelisted API methods                                             #
	# ------------------------------------------------------------------ #

	@frappe.whitelist()
	def get_item_brands(item_code):
		"""Return list of brands linked to an item via custom_brands child table."""
		if not item_code:
			return []
		brands = frappe.db.get_all(
			"Item Brand",
			filters={"parent": item_code, "parentfield": "custom_brands"},
			fields=["brand", "unit_definition_by_brand"],
		)
		return brands

	@frappe.whitelist()
	def get_item_batches(item_code, warehouse=None):
		"""Return available batches for an item (optionally filtered by warehouse stock)."""
		if not item_code:
			return []
		filters = {"item": item_code}
		batches = frappe.db.get_all("Batch", filters=filters, fields=["name as batch_id"])
		if warehouse:
			# Only return batches with positive stock in the warehouse
			available = frappe.db.sql(
				"""
				SELECT batch_no
				FROM `tabStock Ledger Entry`
				WHERE item_code = %s AND warehouse = %s AND is_cancelled = 0
				GROUP BY batch_no
				HAVING SUM(actual_qty) > 0
				""",
				(item_code, warehouse),
				as_dict=True,
			)
			available_names = {r.batch_no for r in available}
			batches = [b for b in batches if b.batch_id in available_names]
		return batches


# -----------------------------------------------------------------------
# Module-level whitelisted functions used by JS set_query
# -----------------------------------------------------------------------


@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def get_brands_for_item(doctype, txt, searchfield, start, page_len, filters):
	"""
	set_query handler: return brands that are linked to the given item
	through its custom_brands child table.
	"""
	item_code = (filters or {}).get("item_code") or ""
	if not item_code:
		return []

	return frappe.db.sql(
		"""
		SELECT ib.brand
		FROM `tabItem Brand` ib
		WHERE ib.parent = %(item_code)s
		  AND ib.parentfield = 'custom_brands'
		  AND ib.brand LIKE %(txt)s
		ORDER BY ib.brand
		LIMIT %(start)s, %(page_len)s
		""",
		{
			"item_code": item_code,
			"txt": f"%{txt}%",
			"start": cint(start),
			"page_len": cint(page_len),
		},
	)


@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def get_batches_for_item_warehouse(doctype, txt, searchfield, start, page_len, filters):
	"""
	set_query handler: return batches for an item that have positive
	stock in the given warehouse.
	"""
	item_code = (filters or {}).get("item") or ""
	warehouse = (filters or {}).get("warehouse") or ""

	if not item_code:
		return []

	if warehouse:
		return frappe.db.sql(
			"""
			SELECT sle.batch_no
			FROM `tabStock Ledger Entry` sle
			WHERE sle.item_code = %(item_code)s
			  AND sle.warehouse = %(warehouse)s
			  AND sle.is_cancelled = 0
			  AND sle.batch_no LIKE %(txt)s
			GROUP BY sle.batch_no
			HAVING SUM(sle.actual_qty) > 0
			ORDER BY sle.batch_no
			LIMIT %(start)s, %(page_len)s
			""",
			{
				"item_code": item_code,
				"warehouse": warehouse,
				"txt": f"%{txt}%",
				"start": cint(start),
				"page_len": cint(page_len),
			},
		)
	else:
		return frappe.db.sql(
			"""
			SELECT b.name
			FROM `tabBatch` b
			WHERE b.item = %(item_code)s
			  AND b.name LIKE %(txt)s
			ORDER BY b.name
			LIMIT %(start)s, %(page_len)s
			""",
			{
				"item_code": item_code,
				"txt": f"%{txt}%",
				"start": cint(start),
				"page_len": cint(page_len),
			},
		)
