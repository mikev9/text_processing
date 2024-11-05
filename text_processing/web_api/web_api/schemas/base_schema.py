from uuid import uuid4
from uuid import UUID

from pydantic import BaseModel as PydanticBaseModel
from pydantic import Field
from pydantic import field_serializer
from pydantic import ConfigDict
from pydantic import UUID4

from shared.db.models.tasks import TextTypeEnum


class BaseModel(PydanticBaseModel):
    model_config = ConfigDict(
        extra='forbid',
    )


class TaskIdMixin(BaseModel):
    task_id: UUID4 = Field(
        title='Task Id',
        default_factory=uuid4,
        description='UUID4 Task Id',
        examples=['8c8b4e08-34ac-41f9-8cad-44b9f938180a'],
    )

    @field_serializer('task_id', when_used='json')
    def serialize_uuid_as_hex(self, task_id: UUID) -> str:
        return task_id.hex


class TextTypeMixin(BaseModel):
    type: TextTypeEnum = Field(title='type', description='Text type')
