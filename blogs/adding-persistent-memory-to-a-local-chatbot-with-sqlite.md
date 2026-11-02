# Adding Persistent Memory to a Local Chatbot With SQLite

Local large language models running on consumer hardware have changed how we handle sensitive text processing, coding assistance, and offline automation. Tools like Ollama and Llama.cpp make deploying models straightforward. However, out of the box, these tools are stateless. Every time you start a fresh script or clear your context window, the model forgets everything you discussed previously. 

Implementing a local ai chatbot memory system does not require complex vector databases or expensive cloud infrastructure for basic recall. A simple relational database like SQLite provides a lightweight, robust backend to store and retrieve conversation history. This tutorial covers how to hook SQLite into a Python-based local LLM pipeline to achieve persistent, searchable memory.

## Understanding the State Problem in Local LLMs

When you interact with a chat endpoint, the model does not inherently remember past sessions. The illusion of memory is maintained by passing the entire conversation history back and forth with every new prompt. As the conversation grows, this context window fills up, consuming more RAM and increasing inference time. 

If you restart your application, the array holding that history is wiped from volatile memory. To solve this, you need a persistence layer. SQLite is well-suited for this task because it is serverless, writes to a single local file, and requires zero configuration. By serializing chat turns into a SQLite database, you can load only the relevant history back into your LLM context when a new session begins.

## Setting Up the SQLite Schema for Chat History

Before writing any inference code, design a database schema capable of handling chat turns. You need to store the session identifier, the role of the speaker (system, user, or assistant), the message content, and a timestamp for chronological sorting.

Create a new file called database.py and set up the initialization logic using Python's built-in sqlite3 module.

```python
import sqlite3

def init_db(db_name="chat_memory.db"):
    conn = sqlite3.connect(db_name)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()

if __name__ == "__main__":
    init_db()
    print("Database initialized successfully.")
```

This simple schema allows you to isolate conversations by a unique session ID. This means a single local ai chatbot memory implementation can manage multiple distinct chat threads, such as coding help versus creative writing, without mixing the contexts.

## Integrating SQLite with an Ollama Pipeline

Now that the storage layer exists, you need to write the logic that saves user inputs and model outputs, while also fetching past messages to inject into the active prompt context. 

The following script demonstrates how to connect to a local Ollama instance running a model like Llama 3, query the SQLite database for recent history, and append new interactions.

```python
import sqlite3
import requests

OLLAMA_URL = "http://localhost:11434/api/chat"
DB_NAME = "chat_memory.db"

def save_message(session_id, role, content):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO messages (session_id, role, content) VALUES (?, ?, ?)",
        (session_id, role, content)
    )
    conn.commit()
    conn.close()

def get_history(session_id, limit=10):
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute(
        """SELECT role, content FROM messages 
           WHERE session_id = ? 
           ORDER BY timestamp DESC LIMIT ?""",
        (session_id, limit)
    )
    rows = cursor.fetchall()
    conn.close()
    
    # Reverse to restore chronological order
    history = [{"role": row[0], "content": row[1]} for row in reversed(rows)]
    return history

def chat(session_id, user_prompt):
    # Save the user input to SQLite
    save_message(session_id, "user", user_prompt)
    
    # Retrieve recent history for context
    messages = get_history(session_id, limit=10)
    
    payload = {
        "model": "llama3",
        "messages": messages,
        "stream": False
    }
    
    response = requests.post(OLLAMA_URL, json=payload)
    if response.status_code == 200:
        assistant_response = response.json()["message"]["content"]
        # Save the model output to SQLite
        save_message(session_id, "assistant", assistant_response)
        return assistant_response
    else:
        raise Exception(f"Error from local model: {response.text}")

if __name__ == "__main__":
    current_session = "default_user"
    print("Chat session started. Type 'exit' to quit.")
    while True:
        prompt = input("\nUser: ")
        if prompt.lower() == 'exit':
            break
        reply = chat(current_session, prompt)
        print(f"\nAssistant: {reply}")
```

This script ensures that even if you terminate the Python process, the conversation state remains safely stored on disk. When you run the script again with the same session identifier, the model retains awareness of the previous dialogue.

## Handling Context Window Limits and Summarization

As SQLite accumulates thousands of rows for a single session_id, passing all of them back to the LLM will eventually exceed the model's context window. Even if it fits, processing a massive context slows down token generation rates significantly.

To keep your local ai chatbot memory efficient, implement a sliding window or a summarization routine. The simple script above uses a hard limit on the SQL query via LIMIT 10, which grabs the ten most recent messages. While effective for short-term recall, this can drop important details discussed earlier in the chat. 

A more robust production approach involves periodically reading older messages, passing them to a fast local model to generate a paragraph summary, and storing that summary in a separate table or as a system prompt at the beginning of the message array. This keeps storage footprint minimal while preserving long-term context without bloating RAM.

## A Practical Option for Windows Users

Writing custom Python scripts and managing local databases offers maximum control, but it requires continuous maintenance and terminal interaction. If you prefer a pre-built setup, YUNA is one practical option for Windows users who want a local AI companion with a Live2D face, and you can find more details at https://ko-fi.com/s/45662d5cc0.

---

Disclosure: I am the developer of YUNA, the software mentioned in the last section.
