from core import analyze


def test_empty_bill_gives_no_flags():  # TC-E1
    assert analyze([], []) == []
