from pydantic import Field
from pydantic import field_validator
from pydantic import model_validator

from .base_schema import TaskIdMixin
from .base_schema import TextTypeMixin
from .base_schema import TextTypeEnum


class ProcessTextRequest(TaskIdMixin, TextTypeMixin):
    text: str = Field(
        min_length=1,
        title='Text',
        description='Text to process',
        examples=['Hey!/// Just wanted to confirm if we\'re still meeting for '
                  'lunch tomorrow at 12 pm.'],
    )

    @field_validator('text')
    def validate_non_empty(cls, value):
        if value.strip():
            return value
        else:
            raise ValueError(
                'The string must contain at least one non-whitespace character'
            )

    @model_validator(mode='after')
    def validate_text_length_based_on_type(cls, obj):
        text = obj.text
        type_ = obj.type

        match type_:
            case TextTypeEnum.chat_item:
                if len(text) > 300:
                    raise ValueError(
                        'For "chat_item", the text must be at most 300 characters long'
                    )
            case TextTypeEnum.summary:
                if len(text) > 3_000:
                    raise ValueError(
                        'For "summary", the text must be at most 3000 characters long'
                    )
            case TextTypeEnum.article:
                if not (300_000 <= len(text) <= 1_000_000):
                    raise ValueError(
                        'For "article," the text length must be at least 300,000 '
                        'characters but not exceed 1,000,000'
                    )

        return obj


class ProcessTextResponse(TaskIdMixin):
    pass
