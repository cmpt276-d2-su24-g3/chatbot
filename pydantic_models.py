from pydantic import BaseModel


class chat_request_model(BaseModel):
    input: str
    session_id: str
    time: str


class history_request_model(BaseModel):
    session_id: str
