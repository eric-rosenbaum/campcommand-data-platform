from openpyxl import Workbook

from campcommand.clients import FeedConfig, SourceFormat
from campcommand.coercion import ParseOptions
from campcommand.mapping import map_columns
from campcommand.readers import read_source


def feed(**overrides) -> FeedConfig:
    defaults = dict(
        feed="buildings",
        contract="buildings@1",
        files="*",
        format=SourceFormat(type="csv"),
        columns={"Bldg Code": "building_code", "Type": "building_type"},
        values={"building_type": {"Dining Hall": "dining"}},
        parse=ParseOptions(),
    )
    return FeedConfig(**(defaults | overrides))


def test_latin1_semicolon_csv(tmp_path):
    path = tmp_path / "batiments.csv"
    path.write_text(
        "Code du bâtiment;Nom\nCR-01;Chalet des Érables\n\nCR-02;Salle à manger\n", encoding="latin-1"
    )
    source = read_source(path, SourceFormat(type="csv", encoding="latin-1", delimiter=";"))
    assert source.headers == ["Code du bâtiment", "Nom"]
    assert [r["Nom"] for r in source.rows] == ["Chalet des Érables", "Salle à manger"]
    assert source.row_numbers == [2, 4]


def test_excel_with_title_rows(tmp_path):
    wb = Workbook()
    ws = wb.active
    ws.title = "Equipment"
    ws.append(["Camp Tall Pines: equipment"])
    ws.append(["Exported June 1"])
    ws.append(["Tag #", "Cost"])
    ws.append(["TP-00001", 1200.5])
    ws.append([None, None])
    ws.append(["TP-00002", 80])
    wb.save(tmp_path / "e.xlsx")

    source = read_source(tmp_path / "e.xlsx", SourceFormat(type="excel", sheet="Equipment", header_row=3))
    assert source.headers == ["Tag #", "Cost"]
    assert source.row_numbers == [4, 6]
    assert source.rows[0]["Cost"] == 1200.5


def test_headers_match_loosely_and_values_are_translated(tmp_path):
    path = tmp_path / "f.csv"
    path.write_text("  bldg   code ,TYPE,Notes\nTP-001,dining hall,x\nTP-002,Yurt,y\n")
    mapped = map_columns(read_source(path, SourceFormat(type="csv")), feed())
    assert mapped.rows == [
        {"building_code": "TP-001", "building_type": "dining"},
        {"building_code": "TP-002", "building_type": "Yurt"},
    ]
    assert mapped.unmapped_columns == ["Notes"]
    assert mapped.missing_columns == []


def test_missing_columns_are_reported(tmp_path):
    path = tmp_path / "f.csv"
    path.write_text("Bldg Code\nTP-001\n")
    mapped = map_columns(read_source(path, SourceFormat(type="csv")), feed())
    assert mapped.missing_columns == ["Type"]
