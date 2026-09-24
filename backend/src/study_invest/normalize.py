"""사용자 입력 문자열 정규화. 저장·중복 검사·길이 검사 모두 정규화된 값 기준으로 한다.

길이 검사보다 먼저 정규화해야 한다. 그래야 " a "(공백 포함 3자)가 "a"(1자)로 저장되거나,
casefold로 길어진 식별자("ß"→"ss")가 DB 컬럼 길이를 넘는 일이 없다.
"""

from __future__ import annotations

import unicodedata


def normalize_identity(value: str) -> str:
    """1인 1계정 식별자: NFKC 호환 정규화 + 대소문자 무시(casefold) + 앞뒤 공백 제거.

    전각·반각, 조합형·완성형 한글처럼 겉보기에 같은 식별자를 하나로 본다.
    """
    folded = unicodedata.normalize("NFKC", value).casefold()
    return unicodedata.normalize("NFKC", folded).strip()


def normalize_nickname(value: str) -> str:
    """닉네임: NFC 정규화(조합형 한글 → 완성형) + 앞뒤 공백 제거. 대소문자는 보존한다."""
    return unicodedata.normalize("NFC", value).strip()
