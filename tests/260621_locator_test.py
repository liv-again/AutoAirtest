from autoairtest.execution.locator import Locator


class FakePoco:
    def __init__(self, status="success"):
        self.status = status
        self.clicks = []

    def click(self, text):
        self.clicks.append(text)
        return {"status": self.status, "query": text}


class FakeOCR:
    def __init__(self, texts=None):
        self.texts = texts or [{"text": "更多", "bounds": [0, 0, 10, 10]}]
        self.images = []

    def recognize(self, image_path):
        self.images.append(image_path)
        return {"status": "success", "texts": self.texts, "image_path": image_path}


class FakeAirtest:
    def __init__(self):
        self.touches = []

    def touch(self, target):
        self.touches.append(target)
        return {"status": "success", "target": target}


def test_locator_uses_poco_first():
    result = Locator(FakePoco(), FakeOCR(), FakeAirtest()).locate_and_act("更多", "screenshots/a.png")

    assert result["locator_level"] == "poco"
    assert result["response"]["status"] == "success"
    assert result["selected_element"]["text"] == "更多"
    assert result["correction_step"] is None


def test_locator_falls_back_to_ocr_when_poco_fails():
    airtest = FakeAirtest()

    result = Locator(FakePoco(status="unavailable"), FakeOCR(), airtest).locate_and_act("更多", "screenshots/a.png")

    assert result["locator_level"] == "ocr"
    assert result["response"]["status"] == "success"
    assert result["response"]["target"] == (5, 5)
    assert airtest.touches == [(5, 5)]
    assert result["correction_step"]["type"] == "ocr_fallback"


def test_locator_uses_dump_bounds_before_ocr():
    airtest = FakeAirtest()
    dump = {
        "status": "success",
        "elements": [{"text": "更多", "bounds": [100, 200, 160, 240]}],
        "visible_texts": ["更多"],
    }

    result = Locator(FakePoco(status="unavailable"), FakeOCR(), airtest).locate_from_dump_and_screenshot(
        "更多",
        dump,
        "screenshots/a.png",
    )

    assert result["locator_level"] == "dump_bounds"
    assert result["response"]["status"] == "success"
    assert result["response"]["target"] == (130, 220)
    assert airtest.touches == [(130, 220)]


def test_locator_reports_unavailable_when_ocr_has_no_match():
    result = Locator(
        FakePoco(status="unavailable"),
        FakeOCR(texts=[{"text": "行情", "bounds": [0, 0, 10, 10]}]),
        FakeAirtest(),
    ).locate_and_act("更多", "screenshots/a.png")

    assert result["locator_level"] == "ocr"
    assert result["response"]["status"] == "unavailable"
    assert result["response"]["reason"] == "ocr target not found"
