// Copyright (c) 2024, Amir Mansi and contributors
// For license information, please see license.txt

/**
 * Task Intelligence Dashboard
 * ----------------------------
 * Client-side filter configuration and custom column formatter for the
 * enterprise Task report.  Provides:
 *   • Filter panel (date range, status, priority, assigned-to, project)
 *   • Colored status badges
 *   • Colored priority badges
 *   • Overdue indicator (red flag icon)
 *   • Assigned-to user badges
 */

frappe.query_reports["Task Intelligence Dashboard"] = {
	// ------------------------------------------------------------------ //
	// Filters
	// ------------------------------------------------------------------ //
	filters: [
		{
			fieldname: "from_date",
			label: __("From Date"),
			fieldtype: "Date",
		},
		{
			fieldname: "to_date",
			label: __("To Date"),
			fieldtype: "Date",
		},
		{
			fieldname: "status",
			label: __("Status"),
			fieldtype: "Select",
			options:
				"\nOpen\nWorking\nPending Review\nOverdue\nTemplate\nCompleted\nCancelled",
		},
		{
			fieldname: "priority",
			label: __("Priority"),
			fieldtype: "Select",
			options: "\nLow\nMedium\nHigh\nUrgent",
		},
		{
			fieldname: "assigned_to",
			label: __("Assigned To"),
			fieldtype: "Link",
			options: "User",
		},
		{
			fieldname: "project",
			label: __("Project"),
			fieldtype: "Link",
			options: "Project",
		},
	],

	// ------------------------------------------------------------------ //
	// Column formatter – renders badges and indicators
	// ------------------------------------------------------------------ //
	formatter: function (value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);

		if (!data) return value;

		// ---- Status badge -------------------------------------------- //
		if (column.fieldname === "status") {
			const STATUS_COLORS = {
				Open: "#6c757d",
				Working: "#007bff",
				"Pending Review": "#fd7e14",
				Overdue: "#dc3545",
				Template: "#6f42c1",
				Completed: "#28a745",
				Cancelled: "#343a40",
			};
			const raw = (data.status || "").trim();
			const color = STATUS_COLORS[raw] || "#6c757d";
			return `<span style="
				background:${color};
				color:#fff;
				padding:3px 10px;
				border-radius:12px;
				font-size:11px;
				font-weight:600;
				white-space:nowrap;
			">${frappe.utils.escape_html(raw)}</span>`;
		}

		// ---- Priority badge ------------------------------------------ //
		if (column.fieldname === "priority") {
			const PRIORITY_COLORS = {
				Low: "#17a2b8",
				Medium: "#ffc107",
				High: "#fd7e14",
				Urgent: "#dc3545",
			};
			const raw = (data.priority || "").trim();
			const color = PRIORITY_COLORS[raw] || "#6c757d";
			return `<span style="
				background:${color};
				color:${raw === "Medium" ? "#000" : "#fff"};
				padding:3px 10px;
				border-radius:12px;
				font-size:11px;
				font-weight:600;
				white-space:nowrap;
			">${frappe.utils.escape_html(raw)}</span>`;
		}

		// ---- Overdue indicator --------------------------------------- //
		if (column.fieldname === "is_overdue") {
			if (data.is_overdue) {
				return `<span style="color:#dc3545;font-size:16px;" title="${__("Overdue")}">&#9888;</span>`;
			}
			return `<span style="color:#28a745;font-size:14px;" title="${__("On Time")}">&#10003;</span>`;
		}

		// ---- Assigned-to user badges --------------------------------- //
		if (column.fieldname === "assigned_to_users") {
			const raw = (data.assigned_to_users || "").trim();
			if (!raw) return `<span style="color:#aaa;">${__("Unassigned")}</span>`;

			const users = raw.split(",").map((u) => u.trim()).filter(Boolean);
			const badges = users
				.map(
					(u) =>
						`<span style="
							background:#e9ecef;
							color:#495057;
							padding:2px 8px;
							border-radius:10px;
							font-size:11px;
							margin-right:3px;
							display:inline-block;
						">${frappe.utils.escape_html(u)}</span>`
				)
				.join("");
			return badges;
		}

		// ---- Task Title with priority colour ----------------------- //
		if (column.fieldname === "task_title") {
			const PRIORITY_TEXT = {
				Low: "#17a2b8",
				Medium: "#856404",
				High: "#fd7e14",
				Urgent: "#dc3545",
			};
			const color = PRIORITY_TEXT[data.priority] || "inherit";
			return `<span style="color:${color};font-weight:600;">${frappe.utils.escape_html(
				data.task_title || ""
			)}</span>`;
		}

		return value;
	},

	// ------------------------------------------------------------------ //
	// Custom table style injected once when report loads
	// ------------------------------------------------------------------ //
	onload: function (report) {
		_inject_dashboard_styles();
	},
};

// ---------------------------------------------------------------------------
// CSS injection for the report table
// ---------------------------------------------------------------------------

function _inject_dashboard_styles() {
	if (document.getElementById("tid-report-styles")) return;

	const style = document.createElement("style");
	style.id = "tid-report-styles";
	style.textContent = `
		/* Task Intelligence Dashboard – custom table styles */
		.datatable .dt-row:hover .dt-cell {
			background: #f0f7ff !important;
		}
		.datatable .dt-header .dt-cell__content {
			background: #343a40 !important;
			color: #fff !important;
			font-weight: 700;
			font-size: 12px;
			padding: 8px 6px;
		}
		/* Sticky header */
		.datatable thead {
			position: sticky;
			top: 0;
			z-index: 10;
		}
	`;
	document.head.appendChild(style);
}
