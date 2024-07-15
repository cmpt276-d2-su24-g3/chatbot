from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

CHAT_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            "You are a helpful assistant. Answer all questions to the best of your ability.",
        ),
        MessagesPlaceholder(variable_name="messages"),
    ]
)

PING_NOT_RECORDED_ERROR = {
    "default": "No ping data recorded between {} and {}.",
    "between": "No ping data recorded between {} and {} from {} to {}.",
    "after": "No ping data recorded between {} and {} after {}.",
    "before": "No ping data recorded between {} and {} befpre {}.",
    "single": "No ping data recorded for {}",
}

NOT_ENOUGH_ENTRY_ERROR = "Not enough data recorded to find the {}th highest/lowest ping, {} deduplicated entries avaiable in the given time range."

DYNAMODB_QUERY_ERROR = "Error querying DynamoDB: {}."