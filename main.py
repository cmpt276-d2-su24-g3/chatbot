import ast
import os
from functools import partial
from typing import AsyncGenerator

import boto3
from fastapi import FastAPI, HTTPException, Response, Security
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security.api_key import APIKeyHeader
from langchain_aws import ChatBedrock
from langchain_community.chat_message_histories import DynamoDBChatMessageHistory
from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.runnables.history import RunnableWithMessageHistory
from starlette.responses import StreamingResponse

from prompts import *
from pydantic_models import *
from timezone import convert_to_utc
from tools import *

TABLE_NAME = "chat_history"

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

api_key_header = APIKeyHeader(name="X-API-Key")


def get_api_key(api_key: str = Security(api_key_header)):
    if api_key == os.getenv("CHATBOT_API_KEY"):
        return api_key
    else:
        raise HTTPException(status_code=403)


@app.post("/chat", dependencies=[Security(get_api_key)])
async def chat_api(chat_request: chat_request_model) -> StreamingResponse:
    llm = ChatBedrock(streaming=True, model_id=os.getenv("BEDROCK_MODEL_ID"))
    llm = llm.bind_tools(
        [
            get_available_services,
            get_aws_health,
            get_aws_health_history,
            get_nth_ping_given_destination,
            get_nth_ping_given_source,
            get_pings,
            search_duckduckgo,
            url_loader,
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

        yield "<|message_received|>"
        while True:
            gathered = None
            async for chunk in inference(input={"messages": message}):
                if gathered is None:
                    gathered = chunk
                else:
                    gathered = gathered + chunk

                if chunk.content:
                    if "text" in chunk.content[0]:
                        yield chunk.content[0]["text"]

            if gathered.tool_call_chunks:
                yield "<|tool_call|>"

                message = []
                for tool_call in gathered.tool_call_chunks:
                    tools = {
                        "get_available_services": get_available_services,
                        "get_aws_health": get_aws_health,
                        "get_aws_health_history": get_aws_health_history,
                        "get_nth_ping_given_destination": get_nth_ping_given_destination,
                        "get_nth_ping_given_source": get_nth_ping_given_source,
                        "get_pings": get_pings,
                        "search_duckduckgo": search_duckduckgo,
                        "url_loader": url_loader,
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


@app.post("/get-history", dependencies=[Security(get_api_key)])
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


@app.post("/delete-history", dependencies=[Security(get_api_key)])
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


@app.post("/generate-title", dependencies=[Security(get_api_key)])
async def generate_title_api(history_request: history_request_model):
    llm = ChatBedrock(model_id=os.getenv("BEDROCK_MODEL_ID"))
    llm = llm.with_structured_output(title_response_model)

    prompt_template = ChatPromptTemplate.from_messages(
        [
            SystemMessage(GENERATE_TITLE_SYSTEM_PROMPT),
            MessagesPlaceholder(variable_name="history"),
        ]
    )

    chain = prompt_template | llm

    try:
        history = str(await get_history_api(history_request))
    except HTTPException as e:
        raise e

    response: title_response_model = chain.invoke({"history": [HumanMessage(history)]})

    return response.title


@app.get("/")
async def health_check():
    return Response(status_code=200)
