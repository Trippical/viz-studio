import pytest

from viz.publish.denylist import denied_references, parse_deny


def test_parse_deny():
    assert parse_deny("") == []
    assert parse_deny(" HR , finance.payroll ,") == ["hr", "finance.payroll"]


def test_three_part_names_against_catalog_and_schema_entries():
    sql = "SELECT * FROM hr.people.salaries s JOIN sales.public.orders o ON 1=1"
    assert denied_references(sql, "hr") == ["hr.people.salaries"]
    assert denied_references(sql, "sales.public") == ["sales.public.orders"]
    assert denied_references(sql, "HR,Sales.Public") == ["hr.people.salaries", "sales.public.orders"]
    assert denied_references(sql, "finance") == []


def test_two_part_names_match_catalog_or_schema_part():
    assert denied_references("SELECT * FROM hr.salaries", "hr") == ["hr.salaries"]
    assert denied_references("SELECT * FROM payroll.runs", "finance.payroll") == ["payroll.runs"]
    assert denied_references("SELECT * FROM public.orders", "finance.payroll") == []


def test_no_double_counting_and_sorted_unique():
    sql = "SELECT a.b.c FROM hr.x.y, hr.x.y, hr.z.w"
    assert denied_references(sql, "hr") == ["hr.x.y", "hr.z.w"]


def test_empty_deny_list_never_matches():
    assert denied_references("SELECT * FROM hr.people.salaries", "") == []


@pytest.mark.parametrize("sql", [
    "SELECT * FROM `hr`.`people`.`salaries`",
    "SELECT * FROM hr . people . salaries",
    "SELECT * FROM hr.\n people.salaries",
    'SELECT * FROM "hr"."people"."salaries"',
])
def test_quoted_and_spaced_names_are_not_fail_open(sql):
    assert denied_references(sql, "hr") == ["hr.people.salaries"]
