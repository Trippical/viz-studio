import json

import pyarrow as pa
import pytest

from viz import schemas
from viz.publish import stage
from viz.publish.cli import main


@pytest.fixture
def csv(tmp_path):
    path = tmp_path / "in.csv"
    path.write_text("month,region,revenue\n2024-01-01,EMEA,10.5\n2024-02-01,NA,20\n", encoding="utf-8")
    return path


def test_stage_from_csv(env, staging_root, csv, capsys):
    assert main(["stage", "--from", str(csv), "--id", "sales/from-csv"]) == 0
    out = capsys.readouterr().out
    assert out.splitlines()[0].split() == ["column", "type", "non-null", "samples"]
    assert "staged: " in out
    chart = staging_root / "charts" / "sales" / "from-csv" / "chart.json"
    doc = schemas.validate_chart(json.loads(chart.read_text(encoding="utf-8")))
    assert doc["author"] == "tester@example.com"
    assert doc["data"]["rows"] == 2
    assert "source" not in doc
    assert (staging_root / "charts" / "sales" / "from-csv" / "data.json").is_file()


def test_stage_honours_staging_flag(env, tmp_path, csv):
    other = tmp_path / "elsewhere"
    assert main(["stage", "--from", str(csv), "--id", "sales/x", "--staging", str(other)]) == 0
    assert (other / "charts" / "sales" / "x" / "chart.json").is_file()


def test_stage_warns_on_pii_and_can_drop(env, staging_root, tmp_path, capsys):
    path = tmp_path / "people.csv"
    path.write_text("month,customer_email,revenue\n2024-01-01,a@b.c,1\n", encoding="utf-8")
    assert main(["stage", "--from", str(path), "--id", "sales/pii"]) == 0
    err = capsys.readouterr().err
    assert "warning: possible PII columns: customer_email (use --drop-columns customer_email)" in err

    assert main(["stage", "--from", str(path), "--id", "sales/pii", "--drop-columns", "customer_email"]) == 0
    assert "warning" not in capsys.readouterr().err, "the only PII column was dropped before the warning was computed"
    doc = json.loads((staging_root / "charts" / "sales" / "pii" / "chart.json").read_text(encoding="utf-8"))
    assert [c["name"] for c in doc["data"]["columns"]] == ["month", "revenue"]

    assert main(["stage", "--from", str(path), "--id", "sales/pii", "--drop-columns", "nope"]) == 1
    assert "error: unknown column 'nope'" in capsys.readouterr().err


def test_stage_errors(env, tmp_path, csv, capsys):
    assert main(["stage", "--from", str(tmp_path / "missing.csv"), "--id", "sales/x"]) == 2
    assert "error: input file not found" in capsys.readouterr().err

    other = tmp_path / "in.xlsx"
    other.write_bytes(b"")
    assert main(["stage", "--from", str(other), "--id", "sales/x"]) == 2
    assert "xlsx" in capsys.readouterr().err

    assert main(["stage", "--from", str(csv), "--id", "Bad Id"]) == 1
    assert "error: invalid id" in capsys.readouterr().err


def test_python_stage_api(env, staging_root):
    table = pa.table({"region": ["EMEA", "NA"], "orders": [3, 4]})
    out = stage(table, "sales/api")
    assert out == staging_root / "charts" / "sales" / "api"
    doc = schemas.validate_chart(json.loads((out / "chart.json").read_text(encoding="utf-8")))
    assert doc["author"] == "tester@example.com"
    assert doc["data"]["columns"] == [{"name": "region", "type": "string"}, {"name": "orders", "type": "integer"}]


def test_python_stage_api_explicit_root_and_type_error(env, tmp_path):
    table = pa.table({"a": [1]})
    out = stage(table, "sales/explicit", staging_root=tmp_path / "root")
    assert out == tmp_path / "root" / "charts" / "sales" / "explicit"
    with pytest.raises(TypeError):
        stage([{"a": 1}], "sales/list")


def test_python_stage_api_warns_on_pii(env, staging_root, capsys):
    table = pa.table({"customer_email": ["a@b.c"], "revenue": [1.5]})
    stage(table, "sales/api-pii")
    err = capsys.readouterr().err
    assert "warning: possible PII columns: customer_email (use --drop-columns customer_email)" in err
