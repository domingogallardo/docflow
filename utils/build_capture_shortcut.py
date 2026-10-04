"""Build the portable A Docflow shortcut; sign with Apple's shortcuts CLI."""
from __future__ import annotations

import argparse
import plistlib
from pathlib import Path
from uuid import uuid4


def attachment(identity: str) -> dict:
    return {"Value": {"Type": "ActionOutput", "OutputUUID": identity}, "WFSerializationType": "WFTextTokenAttachment"}


def token_text(parts: list[str | dict]) -> dict:
    text, ranges = "", {}
    for part in parts:
        if isinstance(part, str):
            text += part
        else:
            # Apple's ranges count UTF-16 code units.
            ranges[f"{{{len(text.encode('utf-16-le')) // 2}, 1}}"] = part["Value"]
            text += "\ufffc"
    return {"Value": {"string": text, "attachmentsByRange": ranges}, "WFSerializationType": "WFTextTokenString"}


def build_shortcut() -> dict:
    actions = []

    def add(name: str, **parameters) -> str:
        identity = str(uuid4()).upper()
        actions.append({"WFWorkflowActionIdentifier": "is.workflow.actions." + name,
                        "WFWorkflowActionParameters": {**parameters, "UUID": identity}})
        return identity

    raw = add("detect.text", WFInput={"Value": {"Type": "ExtensionInput"}, "WFSerializationType": "WFTextTokenAttachment"})
    encoded = add("base64encode", WFInput=attachment(raw), WFEncodeMode="Encode", WFBase64LineBreakMode="None")
    urls = add("detect.link", WFInput=token_text([
        {"Value": {"Type": "ExtensionInput"}, "WFSerializationType": "WFTextTokenAttachment"},
    ]))
    url_text = add("detect.text", WFInput=attachment(urls))
    encoded_urls = add("base64encode", WFInput=attachment(url_text), WFEncodeMode="Encode", WFBase64LineBreakMode="None")
    date = add("date", WFDateActionMode="Current Date")
    formatted = add("format.date", WFDate=token_text([attachment(date)]), WFDateFormatStyle="Custom", WFDateFormat="yyyy-MM-dd'T'HH:mm:ss.SSSXXX")
    record = add("gettext", WFTextActionText=token_text([
        "### Capture\n- Added: ", attachment(formatted),
        "\n- Input-Base64: ", attachment(encoded),
        "\n- URLs-Base64: ", attachment(encoded_urls),
        "\n- Note-Base64: \n",
    ]))
    add("file.append", WFInput=token_text([attachment(record)]), WFFilePath="Docflow/queue.md", WFFileStorageService="iCloud Drive", WFAppendOnNewLine=True)
    add("exit")
    return {
        "WFWorkflowClientVersion": "4711", "WFWorkflowMinimumClientVersion": 1106,
        "WFWorkflowMinimumClientVersionString": "1106",
        "WFWorkflowIcon": {"WFWorkflowIconStartColor": 4274264319, "WFWorkflowIconGlyphNumber": 59511},
        "WFWorkflowTypes": ["ActionExtension"],
        "WFWorkflowInputContentItemClasses": ["WFURLContentItem", "WFStringContentItem", "WFSafariWebPageContentItem"],
        "WFWorkflowHasShortcutInputVariables": True,
        "WFWorkflowActions": actions,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    args.output.write_bytes(plistlib.dumps(build_shortcut(), fmt=plistlib.FMT_BINARY))
    print(f"Shortcut written: {args.output}")


if __name__ == "__main__":
    main()
