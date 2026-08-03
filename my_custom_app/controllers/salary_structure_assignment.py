from hrms.payroll.doctype.salary_structure_assignment.salary_structure_assignment import (
	SalaryStructureAssignment,
)


class CustomSalaryStructureAssignment(SalaryStructureAssignment):
	def _get_component_eval_context(self):
		"""Provide a full-cycle value for the custom Salary Slip field.

		Salary Structure Assignment evaluates component formulas before a Salary
		Slip exists. Actual slips still receive attendance-based ``present_days``
		from the custom Payroll Entry implementation.
		"""
		data = super()._get_component_eval_context()
		data.present_days = data.total_working_days
		return data
