import asyncio
from functools import partial
from typing import AsyncGenerator

import boto3
from fastapi import FastAPI, HTTPException, Response
from langchain_community.chat_message_histories import DynamoDBChatMessageHistory
from langchain_core.messages import HumanMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.runnables.history import RunnableWithMessageHistory
from langchain_openai import ChatOpenAI
from starlette.responses import StreamingResponse

from pydantic_models import chat_request_model, history_request_model


TABLE_NAME = "chat_history"

app = FastAPI()


@app.post("/chat")
async def chat_api(chat_request: chat_request_model) -> StreamingResponse:
    llm = ChatOpenAI(streaming=True)

    prompt = ChatPromptTemplate.from_messages(
        [
            (
                "system",
                "You are a helpful assistant.",
            ),
            MessagesPlaceholder(variable_name="messages"),
        ]
    )

    def init_history(session_id: str) -> DynamoDBChatMessageHistory:
        return DynamoDBChatMessageHistory(table_name=TABLE_NAME, session_id=session_id)

    chain = RunnableWithMessageHistory(prompt | llm, init_history)

    inference = partial(
        chain.astream,
        input={"messages": [HumanMessage(content=chat_request.input)]},
        config={"configurable": {"session_id": chat_request.session_id}},
    )

    async def get_response() -> AsyncGenerator[str, None]:
        async for token in inference():
            yield token.content

    return StreamingResponse(
        get_response(),
        media_type="text/plain",
    )


@app.post("/get-history")
async def get_history_api(history_request: history_request_model):
    dynamodb = boto3.resource("dynamodb")
    table = dynamodb.Table(TABLE_NAME)

    history = table.get_item(Key={"SessionId": history_request.session_id})

    if "Item" in history:
        filtered_history = [
            {"type": entry["type"], "content": entry["data"]["content"]}
            for entry in history["Item"]["History"]
        ]
        return filtered_history

    raise HTTPException(
        status_code=404,
        detail=f"Session history {history_request.session_id} not found",
    )


@app.post("/delete-history")
async def delete_history_api(history_request: history_request_model):
    dynamodb = boto3.resource("dynamodb")
    table = dynamodb.Table(TABLE_NAME)

    table.delete_item(Key={"SessionId": history_request.session_id})

    response = table.get_item(Key={"SessionId": history_request.session_id})
    print(response)
    if "Item" in response:
        return HTTPException(
            status_code=409,
            detail=f"Error deleting session history {history_request.session_id}",
        )

    return Response(status_code=204)


@app.post("/fake-chat")
async def test_api(_: chat_request_model) -> StreamingResponse:
    async def get_response():
        for (
            w
        ) in "0123456789-._~:/?#[]@!$&'\"()*+,;=%ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz":
            yield w
            await asyncio.sleep(0.05)

    return StreamingResponse(get_response(), media_type="text/plain")
