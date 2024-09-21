from pydantic import BaseModel, Field


class chat_request_model(BaseModel):
    input: str
    session_id: str
    time: str


class history_request_model(BaseModel):
    session_id: str


class title_response_model(BaseModel):
    title: str = Field(description="Maximum 10 words.")
