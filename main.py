import ast
import asyncio
from functools import partial
from typing import AsyncGenerator

import boto3
from fastapi import FastAPI, HTTPException, Response
from langchain_community.chat_message_histories import DynamoDBChatMessageHistory
from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.runnables.history import RunnableWithMessageHistory
from langchain_aws import ChatBedrock
from starlette.responses import StreamingResponse

from prompts import *
from pydantic_models import chat_request_model, history_request_model
from timezone import convert_to_utc
from tools import *

TABLE_NAME = "chat_history"

app = FastAPI()


@app.post("/chat")
async def chat_api(chat_request: chat_request_model) -> StreamingResponse:
    llm = ChatBedrock(model_id="meta.llama3-1-8b-instruct-v1:0", streaming=True)
    llm = llm.bind_tools(
        [
            get_available_services,
            get_aws_health,
            get_nth_ping_given_destination,
            get_nth_ping_given_source,
            get_pings,
        ]
    )
    prompt_template = ChatPromptTemplate.from_messages(
        [
            SystemMessage(SYSTEM_PROMPT),
            MessagesPlaceholder(variable_name="messages"),
        ]
    )

    def init_history(session_id: str) -> DynamoDBChatMessageHistory:
        return DynamoDBChatMessageHistory(table_name=TABLE_NAME, session_id=session_id)

    chain = RunnableWithMessageHistory(prompt_template | llm, init_history)

    inference = partial(
        chain.astream,
        config={"configurable": {"session_id": chat_request.session_id}},
    )

    async def get_response() -> AsyncGenerator[str, None]:
        time_stamp = MESSAGE_TIME_STAMP.format(
            chat_request.time, await convert_to_utc(chat_request.time)
        )
        message = [HumanMessage(chat_request.input + time_stamp)]
        while True:
            gathered = None
            async for chunk in inference(input={"messages": message}):
                if gathered is None:
                    gathered = chunk
                else:
                    gathered = gathered + chunk

                yield chunk.content

            if gathered.tool_call_chunks:
                yield "<|tool_call|>"

                message = []
                for tool_call in gathered.tool_call_chunks:
                    tools = {
                        "get_available_services": get_available_services,
                        "get_aws_health": get_aws_health,
                        "get_nth_ping_given_destination": get_nth_ping_given_destination,
                        "get_nth_ping_given_source": get_nth_ping_given_source,
                        "get_pings": get_pings,
                    }
                    selected_tool = tools[tool_call["name"]]
                    tool_args = ast.literal_eval(
                        tool_call["args"]
                        .replace("true", "True")
                        .replace("false", "False")
                    )
                    tool_output = await selected_tool.ainvoke(tool_args)

                    message.append(
                        ToolMessage(tool_output, tool_call_id=tool_call["id"])
                    )
            else:
                break

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

    if "Item" in response:
        return HTTPException(
            status_code=409,
            detail=f"Error deleting session history {history_request.session_id}",
        )

    return Response(status_code=204)


@app.post("/fake-chat")
async def test_api(_: chat_request_model) -> StreamingResponse:
    async def get_response():
        for c in "0123456789-._~:/?#[]@!$&'\"()*+,;=%":
            yield c
            await asyncio.sleep(0.05)

        yield "<|tool_call|>"
        await asyncio.sleep(0.5)

        for c in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz":
            yield c
            await asyncio.sleep(0.05)

    return StreamingResponse(get_response(), media_type="text/plain")
