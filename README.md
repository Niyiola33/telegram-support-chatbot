# Telegram Multilingual Support Chatbot

A robust Telegram-based support chatbot designed to facilitate multilingual customer assistance. It routes customer queries to human agents based on language proficiency and utilizes a bidding mechanism for agents to claim support requests.

## Table of Contents

- [Features](#features)
- [Bot Username](#bot-username)
- [Technologies Used](#technologies-used)
- [Setup and Installation](#setup-and-installation)
- [How to Use the Bot](#how-to-use-the-bot)
  - [For Customers](#for-customers)
  - [For Agents](#for-agents)
- [Project Structure](#project-structure)
- [Known Limitations and Areas for Improvement](#known-limitations-and-areas-for-improvement)
- [Developer & Contact](#developer--contact)
- [License](#license)

## Features

* **Multilingual Support:** Customers can select their preferred language for support.
* **Agent Language Matching:** New support requests are broadcasted to agents who have declared proficiency in the customer's chosen language.
* **Bidding Mechanism:** Agents can "bid" (claim) available support requests via an inline keyboard button.
* **Exclusive Assignment:** Once an agent claims a request, it's locked to them, preventing other agents from bidding on the same conversation.
* **Direct Communication:** Once assigned, the bot facilitates seamless, direct messaging between the customer and their assigned agent.
* **Agent Availability Toggle:** Agents can set their status to "available" or "unavailable".
* **Request Management:** Agents can view their assigned requests and pending requests, and close completed conversations.
* **Database Persistence:** All user, agent, request, and message data is stored in a local SQLite database.

## Bot Username

You can interact with the deployed bot here (when the server is running):
**@ [YOUR_BOT_USERNAME]** (e.g., `@MySupportHelperBot`)

*Note: This bot runs locally. For it to be active, the `main.py` script must be running on the host machine.*

## Technologies Used

* **Python 3.x**: The primary programming language.
* **`python-telegram-bot` (v22.2 or higher)**: For interacting with the Telegram Bot API.
* **`SQLAlchemy`**: Python SQL toolkit and Object Relational Mapper for database interactions.
* **`SQLite`**: A lightweight, file-based SQL database (used for local data persistence).
* **`asyncio`**: Python's standard library for writing concurrent code.

## Setup and Installation

Follow these steps to get the bot running on your local machine:

1.  **Prerequisites:**
    * Ensure you have **Python 3.8+** installed. You can download it from [python.org](https://www.python.org/downloads/).
    * `pip` (Python package installer) should be available.
    * `git` should be installed if cloning from GitHub.

2.  **Clone the Repository (if applicable):**
    ```bash
    git clone [https://github.com/](https://github.com/)[YOUR_GITHUB_USERNAME]/telegram-support-chatbot.git
    cd telegram-support-chatbot
    ```
    *If you received a `.zip` file, unzip it and navigate to the extracted folder.*

3.  **Create and Activate a Virtual Environment:**
    It's highly recommended to use a virtual environment to manage dependencies.
    ```bash
    python -m venv venv
    ```
    * **On Windows (PowerShell):**
        ```powershell
        .\venv\Scripts\Activate.ps1
        ```
    * **On macOS/Linux:**
        ```bash
        source venv/bin/activate
        ```

4.  **Install Required Libraries:**
    ```bash
    pip install python-telegram-bot==22.2 SQLAlchemy # Adjust ptb version if different
    ```

5.  **Get Your Telegram Bot Token:**
    * Go to Telegram and find **@BotFather**.
    * Send `/newbot` to create a new bot, or `/mybots` then select your bot to manage existing ones.
    * BotFather will provide you with an **HTTP API Token**. Copy this token.
    * **Crucial Security Step:** If your token was ever exposed (e.g., in public logs), **immediately use BotFather's `/revoke` command** to get a new token.

6.  **Configure the Bot:**
    * Open `config.py` in your project folder.
    * Replace `"YOUR_BOT_TOKEN_HERE"` with the token you obtained from BotFather:
        ```python
        # config.py
        TELEGRAM_BOT_TOKEN = "YOUR_NEW_BOT_TOKEN_HERE"
        DATABASE_URL = "sqlite:///support_bot.db"
        ```
    * Save the `config.py` file.

7.  **Initialize the Database:**
    This script creates the `support_bot.db` file and sets up the necessary tables.
    ```bash
    python database.py
    ```

8.  **Run the Bot:**
    ```bash
    python main.py
    ```
    The bot will start polling for updates. Keep this terminal window open as long as you want the bot to be active.

## How to Use the Bot

Interact with your bot (`@YOUR_BOT_USERNAME`) in Telegram.

### For Customers

1.  **Start a new conversation:** Send `/start` to the bot.
2.  **Select Language:** You will be prompted to choose your preferred language for support (e.g., English, Spanish).
3.  **Describe your issue:** Send your query or problem description to the bot.
4.  **Wait for an agent:** The bot will notify you when an agent has claimed your request and will then forward messages between you and the agent.

### For Agents

*(Use a **different** Telegram account than the customer for testing the agent flow.)*

1.  **Register as an Agent:** Send `/register_agent` to the bot.
2.  **Set Language Proficiencies:** Tell the bot which languages you can support.
    * Command: `/agent_languages <comma_separated_languages>`
    * Example: `/agent_languages en,es,fr` (for English, Spanish, French)
3.  **Set Agent Status:** Toggle your availability.
    * Command: `/agent_status`
    * When available, you will receive notifications for new requests matching your language proficiencies.
4.  **View Requests:** See your assigned and pending support requests.
    * Command: `/view_requests`
    * From here, you can bid on pending requests (if available and matching your languages) or interact with assigned ones.
5.  **Bid for a Request:** When a new request comes in, the bot will notify available agents with an inline "Bid for this Request" button. Tap this button to claim the request.
6.  **Communicate with Customer:** Once a request is assigned to you, any messages you send to the bot will be forwarded to the customer, and their replies will come directly to you.
7.  **Close a Request:** Once the support issue is resolved, close the conversation.
    * Command: `/close_request` (while in an active conversation with a customer).

## Project Structure
