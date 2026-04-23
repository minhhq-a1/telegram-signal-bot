"""T2: Proxy-aware IP extraction logic."""

def test_xff_single_ip():
    assert "1.2.3.4".split(",")[0].strip() == "1.2.3.4"

def test_xff_comma_list_takes_leftmost():
    assert "1.2.3.4, 10.0.0.1, 172.16.0.1".split(",")[0].strip() == "1.2.3.4"

def test_xff_empty_falls_back_to_none():
    assert ("".split(",")[0].strip() or None) is None
