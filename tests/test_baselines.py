import xml.etree.ElementTree as ET

from omr.baselines import run

PAGE = '<score-partwise><part-list/><part id="P1">{bars}</part></score-partwise>'


def _page(path, numbers):
    bars = "".join(f'<measure number="{n}"/>' for n in numbers)
    path.write_text(PAGE.format(bars=bars), encoding="utf-8")
    return path


def test_homr_pages_are_joined_with_continuing_bar_numbers(tmp_path):
    a = _page(tmp_path / "a.xml", [1, 2, 3])
    b = _page(tmp_path / "b.xml", [1, 2])
    run._merge_pages([a, b], tmp_path / "out.xml")
    numbers = [m.get("number") for m in ET.parse(tmp_path / "out.xml").getroot().find("part")]
    assert numbers == ["1", "2", "3", "4", "5"]


def test_missing_tool_is_a_plain_failure(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("OMR_HOMR_EXE", str(tmp_path / "none.exe"))
    assert run.run_homr(tmp_path / "x.pdf", tmp_path) == 1
    assert "homr not found" in capsys.readouterr().err
