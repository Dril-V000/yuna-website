# Welcome to the YUNA Blog

> Your local AI companion, now with a place to share news and guides.

We're excited to launch the **YUNA blog** — a space for updates, tutorials, and behind-the-scenes looks at your favourite local AI companion.

## What you'll find here

- **Release notes** — every new YUNA version, explained simply.
- **Guides** — get the most out of voice, Live2D, and Ollama.
- **Tips** — custom personalities, prompts, and setups.

## Why a blog?

YUNA is built for privacy-first, offline AI. We think the tools should be as **transparent** as the philosophy. This blog is where we pull back the curtain.

### A quick code sample

```python
# Example: connect to Ollama from Python
import requests

response = requests.post(
    "http://localhost:11434/api/generate",
    json={"model": "llama3", "prompt": "Hello YUNA!"}
)
print(response.json()["response"])
```

## What's next

We're planning:

1. A guide on building custom Live2D characters
2. A deep-dive into YUNA's memory system
3. Community spotlights

Stay tuned — and thank you for being part of the journey.

— *The YUNA team*
