version: rewrite-v1

Rewrite the user's latest message into ONE standalone question that can be understood without the conversation. Keep all Symitar terms, identifiers, and numbers exactly as written. Do not answer it. Do not add information that is not in the conversation. If the latest message is already standalone, return it unchanged. Output only the question.

Conversation:
{history}

Latest message: {message}
