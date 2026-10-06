"""사용자 입력 문자열 정규화. 저장·중복 검사·길이 검사 모두 정규화된 값 기준으로 한다.

길이 검사보다 먼저 정규화해야 한다. 그래야 " a "(공백 포함 3자)가 "a"(1자)로 저장되거나,
casefold로 길어진 식별자("ß"→"ss")가 DB 컬럼 길이를 넘는 일이 없다.
"""

from __future__ import annotations

import re
import unicodedata
from typing import NamedTuple


def normalize_identity(value: str) -> str:
    """1인 1계정 식별자: NFKC 호환 정규화 + 대소문자 무시(casefold) + 앞뒤 공백 제거.

    전각·반각, 조합형·완성형 한글처럼 겉보기에 같은 식별자를 하나로 본다.
    """
    folded = unicodedata.normalize("NFKC", value).casefold()
    return unicodedata.normalize("NFKC", folded).strip()


def normalize_text(value: str) -> str:
    """이름·학과 같은 표시용 문자열: NFC 정규화(조합형 한글 → 완성형) + 앞뒤 공백 제거."""
    return unicodedata.normalize("NFC", value).strip()


def normalize_student_id(value: str) -> str:
    """학번: NFKC(전각 숫자 → 반각) + 앞뒤 공백 제거. 형식(숫자 10자리)은 스키마가 검사한다."""
    return unicodedata.normalize("NFKC", value).strip()


def normalize_nickname(value: str) -> str:
    """닉네임: NFC 정규화(조합형 한글 → 완성형) + 앞뒤 공백 제거. 대소문자는 보존한다."""
    return unicodedata.normalize("NFC", value).strip()


SCHOOL_EMAIL_DOMAINS = frozenset({"skku.edu", "g.skku.edu"})
"""가입을 받는 학교 메일 도메인. 하위 도메인은 받지 않는다(정확히 일치)."""
CANONICAL_SCHOOL_DOMAIN = "g.skku.edu"
"""1인 1계정 판정용 도메인. 같은 ID의 skku.edu·g.skku.edu는 같은 사람이라 이 도메인으로 합친다."""

# 학교 계정 ID: 영문 소문자·숫자와 . _ - (처음·끝은 영숫자, 마침표 연속 금지).
# '+'는 받지 않는다. abc+1@g.skku.edu도 abc에게 배달되어 한 사람이 여러 주소를 만들 수 있다.
_LOCAL_PART = re.compile(r"[a-z0-9](?:[a-z0-9._-]{0,62}[a-z0-9])?")


class SchoolEmail(NamedTuple):
    address: str
    """인증 메일을 보낼 주소(입력한 도메인 그대로, 정규화됨)."""
    canonical: str
    """1인 1계정 판정 키. 저장·중복 검사는 이 값으로 한다."""


class SchoolEmailError(ValueError):
    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code
        """INVALID_EMAIL(메일 주소 형식이 아님) 또는 EMAIL_DOMAIN_NOT_ALLOWED."""


def parse_school_email(value: str) -> SchoolEmail:
    """학교 메일 주소를 정규화하고 1인 1계정 키를 만든다. 아니면 SchoolEmailError.

    식별자와 같은 정규화(NFKC·casefold·공백 제거)를 먼저 해서 전각 입력도 같은 주소로 본다.
    """
    email = normalize_identity(value)
    local, at, domain = email.rpartition("@")
    if not at or not local:
        raise SchoolEmailError("INVALID_EMAIL")
    if domain not in SCHOOL_EMAIL_DOMAINS:
        raise SchoolEmailError("EMAIL_DOMAIN_NOT_ALLOWED")
    if not _LOCAL_PART.fullmatch(local) or ".." in local:
        raise SchoolEmailError("INVALID_EMAIL")
    return SchoolEmail(f"{local}@{domain}", f"{local}@{CANONICAL_SCHOOL_DOMAIN}")


def mask_value(value: str, keep: int = 2) -> str:
    """로그용으로 앞 keep자만 남기고 가린다: 2026123456 → 20***(10자)."""
    return f"{value[:keep]}***({len(value)}자)" if value else "(빈 값)"


def mask_email(address: str) -> str:
    """본인 응답용 가린 주소: kim@g.skku.edu → k***@g.skku.edu."""
    local, _, domain = address.partition("@")
    return f"{local[:1]}***@{domain}"
