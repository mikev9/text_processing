import re

import langdetect


# Language detection algorithm is non-deterministic. To enforce consistent results:
langdetect.DetectorFactory.seed = 0


class LangDetectError(Exception):
    pass


not_allowed_re = re.compile(r"[^-\w\s:(),.!?“”']")


def count_words(text: str) -> int:
    words = text.split()
    return len(words)


def detect_language(text: str) -> str:
    try:
        lang = langdetect.detect(text)
    except Exception as exc:
        raise LangDetectError(exc)

    if isinstance(lang, str) and lang.isalpha() and len(lang) == 2:
        return lang
    else:
        raise LangDetectError(
            'Unable to detect language. Detect result: "%s"' % lang
        )


def clean_text(text: str) -> str:
    return not_allowed_re.sub('', text)
