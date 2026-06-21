from autoairtest.execution.state_graph import StateGraph, page_fingerprint


def test_page_fingerprint_is_stable_for_same_visible_elements_in_different_order():
    first = [
        {"resource_id": "btn_more", "text": "更多", "label": ""},
        {"resource_id": "idx_000001", "text": "上证指数", "label": ""},
    ]
    second = list(reversed(first))

    assert page_fingerprint(first) == page_fingerprint(second)


def test_state_graph_records_pages_elements_and_edges():
    graph = StateGraph()
    page_a = page_fingerprint([{"resource_id": "btn_more", "text": "更多", "label": ""}])
    page_b = page_fingerprint([{"resource_id": "title", "text": "国内指数", "label": ""}])

    graph.record_page(page_a, summary="行情-股指", screenshot="screenshots/001.png")
    graph.mark_element_seen(page_a, "text:更多")
    graph.record_edge(page_a, "click text:更多", page_b, case_id="TC_more")

    payload = graph.to_dict()
    assert payload["pages"][page_a]["visit_count"] == 1
    assert payload["pages"][page_a]["elements_seen"] == ["text:更多"]
    assert payload["edges"] == [
        {"from": page_a, "action": "click text:更多", "to": page_b, "case_id": "TC_more"}
    ]
