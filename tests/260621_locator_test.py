from autoairtest.execution.locator import Locator
from autoairtest.models import LocatorCandidate


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


def test_locator_matches_dump_content_desc_and_resource_id_aliases():
    airtest = FakeAirtest()
    dump = {
        "status": "success",
        "elements": [
            {
                "text": "",
                "desc": "950001",
                "resource_id": "com.example:id/etf_row",
                "bounds": [100, 200, 160, 240],
                "attributes": {"contentDescription": "950001"},
            }
        ],
        "visible_texts": ["950001"],
    }

    result = Locator(FakePoco(status="unavailable"), FakeOCR(), airtest).locate_from_dump_and_screenshot(
        "950001",
        dump,
        "screenshots/a.png",
    )

    assert result["locator_level"] == "dump_bounds"
    assert result["selected_element"]["matched_by"] == "desc"
    assert result["response"]["target"] == (130, 220)


def test_locator_reports_unavailable_when_ocr_has_no_match():
    result = Locator(
        FakePoco(status="unavailable"),
        FakeOCR(texts=[{"text": "行情", "bounds": [0, 0, 10, 10]}]),
        FakeAirtest(),
    ).locate_and_act("更多", "screenshots/a.png")

    assert result["locator_level"] == "ocr"
    assert result["response"]["status"] == "unavailable"
    assert result["response"]["reason"] == "ocr target not found"


def test_locator_uses_resource_id_before_text_candidate():
    class ResourcePoco(FakePoco):
        def __init__(self):
            super().__init__()
            self.resource_ids = []

        def click_resource_id(self, value):
            self.resource_ids.append(value)
            return {"status": "success", "query": value, "locator_type": "resource_id"}

    poco = ResourcePoco()
    result = Locator(poco, FakeOCR(), FakeAirtest()).locate_and_act(
        "返回",
        "screenshots/a.png",
        locators=[
            LocatorCandidate(type="resource_id", value="id/backButton"),
            LocatorCandidate(type="text", value="返回"),
        ],
    )

    assert result["locator_level"] == "poco_resource_id"
    assert result["selected_element"]["locator_type"] == "resource_id"
    assert poco.resource_ids == ["id/backButton"]
    assert poco.clicks == []


def test_locator_falls_back_from_resource_id_to_text_candidate():
    class ResourcePoco(FakePoco):
        def __init__(self):
            super().__init__()
            self.resource_ids = []

        def click_resource_id(self, value):
            self.resource_ids.append(value)
            return {"status": "unavailable", "reason": "not found", "query": value}

    poco = ResourcePoco()
    result = Locator(poco, FakeOCR(), FakeAirtest()).locate_and_act(
        "返回",
        "screenshots/a.png",
        locators=[
            LocatorCandidate(type="resource_id", value="id/backButton"),
            LocatorCandidate(type="text", value="返回"),
        ],
    )

    assert result["locator_level"] == "poco_text"
    assert poco.resource_ids == ["id/backButton"]
    assert poco.clicks == ["返回"]


def test_locator_uses_content_desc_candidate():
    class ContentDescPoco(FakePoco):
        def __init__(self):
            super().__init__()
            self.content_descs = []

        def click_content_desc(self, value):
            self.content_descs.append(value)
            return {"status": "success", "query": value, "locator_type": "content_desc"}

    poco = ContentDescPoco()
    result = Locator(poco, FakeOCR(), FakeAirtest()).locate_and_act(
        "行情",
        "screenshots/a.png",
        locators=[LocatorCandidate(type="content_desc", value="行情")],
    )

    assert result["locator_level"] == "poco_content_desc"
    assert result["selected_element"]["locator_type"] == "content_desc"
    assert poco.content_descs == ["行情"]
    assert poco.clicks == []
