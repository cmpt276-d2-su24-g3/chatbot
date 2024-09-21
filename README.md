
# Chatbot API Documentation

## Authentication

All endpoints require an `X-API-Key` to be included in the request headers.

## Endpoints

### 1 . `/chat`

This endpoint takes any string, a UUID v4 session id, and an ISO 8601 formatted time in the user's time zone, then streams back the model's response.

#### Input

```json
{
  "input": "str",
  "session_id": "str",
  "time": "str"
}
```

#### Output

- Plain text via HTTP stream
- Streams an `<|tool_call|>` token when calling tools

#### Example Request

```json
{
  "input": "Tell me a joke.",
  "session_id": "123e4567-e89b-12d3-a456-426614174000",
  "time": "2024-07-25T10:15:30Z"
}
```

### 2. `/get-history`

This endpoint takes a UUID v4 session id and returns a plain text JSON containing all chat history for that session.

#### Input

```json
{
  "session_id": "str"
}
```

#### Output

- Plain text JSON containing chat history
- HTTP status 404 if history is not found

#### Example Request

```json
{
  "session_id": "123e4567-e89b-12d3-a456-426614174000"
}
```

### 3. `/delete-history`

This endpoint takes a UUID v4 session id and deletes the chat history for that session.

#### Input

```json
{
  "session_id": "str"
}
```

#### Output

- HTTP status 204 (No Content)
- If history is not found, returns HTTP status 204 and does nothing
- If deletion is not successful, returns HTTP status 409

### 4. `/generate-title`

This endpoint takes a UUID v4 session id and returns a title in plaintext based on the history related to the session id.

#### Input

```json
{
  "session_id": "str"
}
```

#### Output

- Plain text title
- HTTP status 404 if history is not found

## Tools

LLM has access to all function in [tool.py](tool.py):

- **get_pings**: Queries AWS DynamoDB for latency data between AWS regions or locations.
- **get_nth_ping_given_source**: Queries for the nth lowest or highest ping destination from a given source region within a specified time range.
- **get_nth_ping_given_destination**: Queries for the nth lowest or highest ping source to a given destination within a specified time range.
- **get_aws_health**: Fetches current AWS health incidents and announcements.
- **get_aws_health_history**: Fetches AWS health history incidents within a specified time frame.
- **get_available_services**: Lists all services available in a given AWS region.

## Environment Variables

```shell
AWS_ACCESS_KEY_ID=
AWS_SECRET_ACCESS_KEY=
AWS_DEFAULT_REGION=
BEDROCK_MODEL_ID= #must work with streaming tool calls
CHATBOT_API_KEY=
```
