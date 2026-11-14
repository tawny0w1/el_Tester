"""The missing-element report texts (Reqirements.md, Phase 5 element 6). No window is opened."""
from report_form import MISSING_ELEMENT_TITLE, missing_element_texts


def test_title_asks_to_report() -> None:
    assert MISSING_ELEMENT_TITLE == "Clicked element not found on Target site. Please report a bug."


def test_summary_names_the_element() -> None:
    summary, _ = missing_element_texts("Button B")
    assert summary == "Element Button B not found"


def test_description_has_test_and_expected_result() -> None:
    _, description = missing_element_texts("Button B")
    assert description == ("Test Result:\nOn target page element Button B cannot be found.\n\n"
                           "Expected Result:\nClickable element should be present on target page.")
