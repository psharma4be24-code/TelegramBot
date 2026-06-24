# Hinglish Telegram Bot

A 24/7 Telegram bot powered by Google Gemini that replies to messages in friendly Hinglish.

## Run & Operate

- Workflow: `Telegram Bot` — runs `python3 bot/main.py` continuously
- Required secrets: `BOT_TOKEN` (Telegram), `GEMINI_API_KEY` (Google Gemini)

## Stack

- Python 3.11
- python-telegram-bot 22+
- google-genai (Gemini 2.5 Flash)

## Where things live

- `bot/main.py` — the entire bot: Telegram handler + Gemini prompt logic

## Product

Users message the bot on Telegram; the bot replies in friendly Hinglish using Gemini 2.5 Flash.

## User preferences

_Populate as you build — explicit user instructions worth remembering across sessions._

## Gotchas

- Always restart the `Telegram Bot` workflow after editing `bot/main.py`
- Secrets `BOT_TOKEN` and `GEMINI_API_KEY` must be set before starting the workflow
