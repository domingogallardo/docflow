"""Validate the typed inputs required by native Shortcuts actions."""

from utils.build_capture_shortcut import build_shortcut


def test_capture_saves_directly_without_menu_or_note_prompt():
    actions = build_shortcut()["WFWorkflowActions"]
    identifiers = {action["WFWorkflowActionIdentifier"] for action in actions}
    assert "is.workflow.actions.choosefrommenu" not in identifiers
    assert "is.workflow.actions.ask" not in identifiers
    record = next(
        action["WFWorkflowActionParameters"]["WFTextActionText"]
        for action in actions
        if action["WFWorkflowActionIdentifier"] == "is.workflow.actions.gettext"
    )
    assert record["Value"]["string"].endswith("\n- Note-Base64: \n")


def test_capture_record_is_connected_to_append_action():
    actions = build_shortcut()["WFWorkflowActions"]
    record = next(
        action["WFWorkflowActionParameters"]
        for action in actions
        if action["WFWorkflowActionIdentifier"] == "is.workflow.actions.gettext"
        and isinstance(action["WFWorkflowActionParameters"].get("WFTextActionText"), dict)
    )
    append = next(
        action["WFWorkflowActionParameters"]
        for action in actions
        if action["WFWorkflowActionIdentifier"] == "is.workflow.actions.file.append"
    )
    value = append["WFInput"]
    assert value["WFSerializationType"] == "WFTextTokenString"
    assert value["Value"]["attachmentsByRange"]["{0, 1}"]["OutputUUID"] == record["UUID"]


def test_date_and_url_actions_receive_their_native_text_parameters():
    actions = build_shortcut()["WFWorkflowActions"]
    date = next(
        action["WFWorkflowActionParameters"]
        for action in actions
        if action["WFWorkflowActionIdentifier"] == "is.workflow.actions.format.date"
    )
    assert date["WFDate"]["WFSerializationType"] == "WFTextTokenString"
    assert "WFInput" not in date
    links = next(
        action["WFWorkflowActionParameters"]
        for action in actions
        if action["WFWorkflowActionIdentifier"] == "is.workflow.actions.detect.link"
    )
    assert links["WFInput"]["WFSerializationType"] == "WFTextTokenString"
    assert links["WFInput"]["Value"]["attachmentsByRange"]["{0, 1}"]["Type"] == "ExtensionInput"
