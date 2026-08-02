from __future__ import annotations

import json
import os
import re
from typing import Any

import requests


API_BASE_URL = "https://generativelanguage.googleapis.com/v1beta/models"


def _extract_json(text: str) -> dict[str, Any]:
    cleaned = re.sub(r"^```json\s*|\s*```$", "", text.strip(), flags=re.S)
    return json.loads(cleaned)


def call_json_model(
    messages: list[dict[str, str]],
    model: str,
    temperature: float = 0.4,
    max_tokens: int = 4000,
) -> dict[str, Any]:
    """Gemini APIを呼び出し、JSONオブジェクトだけを返す。"""
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError(
            "GEMINI_API_KEY がありません。請求先未設定のGoogle Cloudプロジェクトで"
            "作成したキーをGitHub Actions Secretへ登録してください"
        )

    if os.environ.get("GEMINI_FREE_TIER_ONLY", "true").lower() != "true":
        raise RuntimeError("無料枠限定設定が無効なため、AI呼び出しを停止しました")

    system_parts: list[str] = []
    contents: list[dict[str, Any]] = []
    for message in messages:
        role = message.get("role", "user")
        content = str(message.get("content", ""))
        if role == "system":
            system_parts.append(content)
            continue
        contents.append(
            {
                "role": "model" if role == "assistant" else "user",
                "parts": [{"text": content}],
            }
        )

    payload: dict[str, Any] = {
        "contents": contents,
        "generationConfig": {
            "temperature": temperature,
            "maxOutputTokens": max_tokens,
            "responseMimeType": "application/json",
        },
    }
    if system_parts:
        payload["systemInstruction"] = {
            "parts": [{"text": "\n\n".join(system_parts)}]
        }

    response = requests.post(
        f"{API_BASE_URL}/{model}:generateContent",
        headers={
            "Content-Type": "application/json",
            "x-goog-api-key": api_key,
        },
        json=payload,
        timeout=180,
    )

    if response.status_code == 429:
        raise RuntimeError(
            "Gemini APIの無料枠またはレート上限に達したため、公開を停止しました"
        )
    response.raise_for_status()

    result = response.json()
    try:
        parts = result["candidates"][0]["content"]["parts"]
        text = "".join(str(part.get("text", "")) for part in parts)
    except (KeyError, IndexError, TypeError) as exc:
        raise RuntimeError("Gemini APIの応答本文を取得できませんでした") from exc

    if not text.strip():
        raise RuntimeError("Gemini APIから空の応答が返されました")
    return _extract_json(text)
