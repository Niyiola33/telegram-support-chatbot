# main.py
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup # For Telegram objects
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    filters, ContextTypes # For handling different types of updates
)
from sqlalchemy.orm import Session # For database session management
from sqlalchemy import or_, and_ # For advanced database queries
from sqlalchemy.sql import func # For database functions like func.now()
import asyncio # For asynchronous operations

# Import our configurations and database models
from config import TELEGRAM_BOT_TOKEN
from database import SessionLocal, User, SupportRequest, Message, init_db

# Configure logging: This helps you see what your bot is doing in the terminal
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- Helper Functions for Database Operations ---
# This function provides a database session for each handler
def get_db():
    db = SessionLocal()
    try:
        yield db # 'yield' makes this a generator, allowing us to use it with 'async for'
    finally:
        db.close() # Ensure the session is closed after use

# Decorator to automatically manage database sessions for our async handlers
def db_session_decorator(func):
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        # We need to manually iterate the generator and then close it
        db_generator = get_db()
        db = next(db_generator) # Get the session from the generator

        context.user_data['_db'] = db # Store it in context for easy access
        try:
            await func(update, context) # Run the actual handler function
        finally:
            # Ensure the session is closed, even if an error occurs in the handler
            db_generator.close()
            if '_db' in context.user_data: # Clean up after use
                del context.user_data['_db']
    return wrapper
# Helper to get an existing user or create a new one in the database
async def get_or_create_user(db: Session, telegram_id: int, username: str, first_name: str) -> User:
    user = db.query(User).filter_by(telegram_id=telegram_id).first()
    if not user:
        user = User(telegram_id=telegram_id, username=username, first_name=first_name)
        db.add(user)
        db.commit() # Save the new user to the database
        db.refresh(user) # Refresh the object to get its new ID
        logger.info(f"New user created: {user}")
    return user

# --- Bot Commands and Handlers ---

# /start command handler
@db_session_decorator
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    db: Session = context.user_data['_db'] # Get the database session
    user = await get_or_create_user(db, update.effective_user.id, update.effective_user.username, update.effective_user.first_name)

    if user.is_agent: # If the user is an agent
        await update.message.reply_text(
            f"Hello Agent {user.first_name}! You are currently {'available' if user.is_available else 'unavailable'}. "
            "Use /agent_status to change your availability, /agent_languages to manage your languages, or /view_requests to see pending requests."
        )
    else: # If the user is a customer
        # Offer language selection using inline keyboard buttons
        keyboard = [
            [InlineKeyboardButton("English 🇬🇧", callback_data="lang_en")],
            [InlineKeyboardButton("Español 🇪🇸", callback_data="lang_es")],
            [InlineKeyboardButton("Français 🇫🇷", callback_data="lang_fr")],
            [InlineKeyboardButton("Deutsch 🇩🇪", callback_data="lang_de")],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text("Welcome to Support! Please select your preferred language:", reply_markup=reply_markup)
        # Store state to know what to expect next from the customer
        context.user_data['state'] = 'awaiting_language_selection' 
        logger.info(f"Customer {user.telegram_id} initiated support via /start.")

# Handler for language selection buttons (callback queries starting with 'lang_')
@db_session_decorator
async def handle_language_selection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query # Get the callback query object
    await query.answer() # Acknowledge the callback query (removes loading spinner from button)

    db: Session = context.user_data['_db']
    user = await get_or_create_user(db, query.from_user.id, query.from_user.username, query.from_user.first_name)

    # Check if the user is in the correct state to select a language
    if context.user_data.get('state') != 'awaiting_language_selection':
        await query.edit_message_text("Please start a new support request with /start if you want to select a language again.")
        return

    selected_language = query.data.split('_')[1] # Extract language code (e.g., 'en' from 'lang_en')
    context.user_data['customer_language'] = selected_language # Store selected language

    await query.edit_message_text(f"You've selected {selected_language.upper()}. Please describe your issue.")
    context.user_data['state'] = 'awaiting_customer_issue' # Update customer state
    logger.info(f"Customer {user.telegram_id} selected language {selected_language}.")

# Handler for regular text messages from customers
@db_session_decorator
async def handle_customer_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    db: Session = context.user_data['_db']
    customer = await get_or_create_user(db, update.effective_user.id, update.effective_user.username, update.effective_user.first_name)

    if customer.is_agent: # If an agent sends a message that's not a command
        await handle_agent_message(update, context) # Delegate to agent message handler
        return

    # Check if this customer already has an active support request
    active_request = db.query(SupportRequest).filter(
        SupportRequest.customer_id == customer.id,
        or_(SupportRequest.status == 'pending', SupportRequest.status == 'assigned') # Request is either waiting or assigned
    ).first()

    if not active_request: # If no active request, this is likely the first issue description
        if context.user_data.get('state') == 'awaiting_customer_issue' and 'customer_language' in context.user_data:
            language = context.user_data['customer_language']
            # Create a new support request in the database
            support_request = SupportRequest(
                customer_id=customer.id,
                language=language,
                status='pending'
            )
            db.add(support_request)
            db.commit()
            db.refresh(support_request)

            # Log the initial customer message in the database
            msg = Message(
                support_request_id=support_request.id,
                sender_id=customer.id,
                text=update.message.text
            )
            db.add(msg)
            db.commit()

            await update.message.reply_text("Thank you. We are looking for an available agent to assist you.")
            logger.info(f"New support request created: {support_request.id} for customer {customer.telegram_id}.")

            # Notify eligible agents about the new request
            await notify_agents_about_new_request(db, support_request, context.application)
            context.user_data['state'] = 'request_pending' # Update customer state
        else:
            await update.message.reply_text("Please use /start to begin a new support request and select your language.")
    else: # If there's an active request
        if active_request.status == 'assigned': # If an agent is assigned, forward message to agent
            agent = db.query(User).get(active_request.agent_id)
            if agent:
                try:
                    # Forward customer's message to the assigned agent
                    await context.application.bot.send_message(
                        chat_id=agent.telegram_id,
                        text=f"From customer {customer.first_name or customer.username}:\n{update.message.text}"
                    )
                    # Log the message
                    msg = Message(
                        support_request_id=active_request.id,
                        sender_id=customer.id,
                        text=update.message.text
                    )
                    db.add(msg)
                    db.commit()
                    logger.info(f"Message from customer {customer.telegram_id} forwarded to agent {agent.telegram_id}.")
                except Exception as e:
                    logger.error(f"Failed to forward message from customer {customer.telegram_id} to agent {agent.telegram_id}: {e}")
                    await update.message.reply_text("There was an error forwarding your message. Please try again.")
            else:
                await update.message.reply_text("Assigned agent not found. Please wait, we are trying to reconnect you.")
        else: # If the request is pending, just inform the customer to wait
            await update.message.reply_text("Your request is still pending. Please wait for an agent to claim it.")
            # Also log subsequent messages even if pending
            msg = Message(
                support_request_id=active_request.id,
                sender_id=customer.id,
                text=update.message.text
            )
            db.add(msg)
            db.commit()

# Handler for regular text messages from agents (when assigned to a chat)
@db_session_decorator
async def handle_agent_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    db: Session = context.user_data['_db']
    agent = await get_or_create_user(db, update.effective_user.id, update.effective_user.username, update.effective_user.first_name)

    if not agent.is_agent:
        return # Should not happen if correctly delegated from handle_customer_message

    # Find the active request this agent is currently assigned to
    active_request = db.query(SupportRequest).filter(
        SupportRequest.agent_id == agent.id,
        SupportRequest.status == 'assigned'
    ).first()

    if active_request:
        customer = db.query(User).get(active_request.customer_id)
        if customer:
            try:
                # Forward agent's message to the customer
                await context.application.bot.send_message(
                    chat_id=customer.telegram_id,
                    text=f"From Agent {agent.first_name or agent.username}:\n{update.message.text}"
                )
                # Log the message
                msg = Message(
                    support_request_id=active_request.id,
                    sender_id=agent.id,
                    text=update.message.text
                )
                db.add(msg)
                db.commit()
                logger.info(f"Message from agent {agent.telegram_id} forwarded to customer {customer.telegram_id}.")
            except Exception as e:
                logger.error(f"Failed to forward message from agent {agent.telegram_id} to customer {customer.telegram_id}: {e}")
                await update.message.reply_text("There was an error forwarding your message. Please try again.")
        else:
            await update.message.reply_text("Assigned customer not found. This conversation might be stale.")
    else:
        await update.message.reply_text("You are not currently assigned to any active support request. Use /view_requests.")

# Function to notify eligible agents about a new pending support request
async def notify_agents_about_new_request(db: Session, support_request: SupportRequest, application: Application):
    customer = db.query(User).get(support_request.customer_id)
    # Get the first message from the customer for context
    initial_message = db.query(Message).filter_by(
        support_request_id=support_request.id,
        sender_id=customer.id
    ).order_by(Message.timestamp).first()

    # Find all available agents who are proficient in the request's language
    eligible_agents = db.query(User).filter(
        User.is_agent == True,
        User.is_available == True,
        User.language_proficiencies.like(f"%{support_request.language}%") # Simple check if language is in their proficiencies string
    ).all()

    if not eligible_agents:
        logger.warning(f"No available agents for language {support_request.language}.")
        await application.bot.send_message(
            chat_id=customer.telegram_id,
            text="No agents are currently available for your language. Please try again later or wait for an agent to become free."
        )
        return

    # Create a "Bid" button for agents
    keyboard = [[InlineKeyboardButton("Bid for this Request", callback_data=f"bid_{support_request.id}")]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    # Send notification to each eligible agent
    for agent in eligible_agents:
        try:
            await application.bot.send_message(
                chat_id=agent.telegram_id,
                text=(f"🚨 New Support Request! 🚨\n\n"
                      f"Customer: {customer.first_name or customer.username} (ID: {customer.telegram_id})\n"
                      f"Language: {support_request.language.upper()}\n"
                      f"Initial Query: \"{initial_message.text[:100]}...\"" if initial_message else "No initial message."
                      ),
                reply_markup=reply_markup
            )
            logger.info(f"Notified agent {agent.telegram_id} about request {support_request.id}.")
        except Exception as e:
            logger.error(f"Failed to notify agent {agent.telegram_id}: {e}")

# Handler for agent bidding on a request
@db_session_decorator
async def handle_bid(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer() # Acknowledge the button press

    db: Session = context.user_data['_db']
    agent = await get_or_create_user(db, query.from_user.id, query.from_user.username, query.from_user.first_name)

    if not agent.is_agent:
        await query.edit_message_text("You are not authorized to bid for support requests.")
        return

    request_id = int(query.data.split('_')[1]) # Extract request ID from callback data

    try:
        support_request = db.query(SupportRequest).get(request_id) # Get the request from DB

        if not support_request:
            await query.edit_message_text("This support request does not exist.")
            return

        if support_request.status == 'assigned': # Check if already claimed (race condition handling)
            await query.edit_message_text("This request has already been claimed by another agent.")
            logger.info(f"Agent {agent.telegram_id} tried to bid on already claimed request {request_id}.")
            return

        # If not assigned, assign it to this agent
        support_request.agent_id = agent.id
        support_request.status = 'assigned'
        support_request.assigned_at = func.now() # Set assignment timestamp
        db.add(support_request)
        db.commit() # Save changes to DB

        await query.edit_message_text(f"You have successfully claimed Request #{request_id}!")
        logger.info(f"Agent {agent.telegram_id} successfully claimed request {request_id}.")

        customer = db.query(User).get(support_request.customer_id)
        if customer:
            # Notify the customer that an agent has joined
            await context.application.bot.send_message(
                chat_id=customer.telegram_id,
                text=f"Good news! An agent ({agent.first_name or agent.username}) has joined your chat. They will be with you shortly."
            )
            # Send conversation history to the agent
            initial_messages = db.query(Message).filter_by(support_request_id=support_request.id).order_by(Message.timestamp).all()
            history_text = "\n".join([f"{msg.sender.first_name or msg.sender.username}: {msg.text}" for msg in initial_messages])
            if history_text:
                await context.application.bot.send_message(
                    chat_id=agent.telegram_id,
                    text=f"Conversation history for Request #{request_id}:\n{history_text}"
                )
        else:
            logger.warning(f"Customer {support_request.customer_id} not found for request {request_id} after agent claimed.")

    except Exception as e:
        db.rollback() # Rollback any changes if an error occurs
        logger.error(f"Error claiming request {request_id} by agent {agent.telegram_id}: {e}")
        await query.edit_message_text("Failed to claim the request. It might have been claimed by someone else or an error occurred.")
        # Re-fetch to check if it was claimed by another agent just before this one
        support_request_after_fail = db.query(SupportRequest).get(request_id)
        if support_request_after_fail and support_request_after_fail.status == 'assigned' and support_request_after_fail.agent_id != agent.id:
            await query.edit_message_text("This request was just claimed by another agent.")
        else:
            await query.edit_message_text("An error occurred while claiming the request. Please try again or contact admin.")


# /register_agent command handler
@db_session_decorator
async def register_agent(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    db: Session = context.user_data['_db']
    user = await get_or_create_user(db, update.effective_user.id, update.effective_user.username, update.effective_user.first_name)

    if user.is_agent:
        await update.message.reply_text("You are already registered as an agent.")
        return

    user.is_agent = True # Set user as an agent
    db.commit()
    await update.message.reply_text(
        "You are now registered as a support agent! "
        "Use /agent_languages to set your language proficiencies (e.g., `/agent_languages en,es`)."
        "And /agent_status to toggle your availability."
    )
    logger.info(f"User {user.telegram_id} registered as agent.")

# /agent_languages command handler
@db_session_decorator
async def set_agent_languages(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    db: Session = context.user_data['_db']
    user = await get_or_create_user(db, update.effective_user.id, update.effective_user.username, update.effective_user.first_name)

    if not user.is_agent:
        await update.message.reply_text("You are not registered as an agent. Use /register_agent first.")
        return

    if not context.args: # If no arguments provided with the command
        await update.message.reply_text(
            f"Usage: /agent_languages <lang1,lang2,...>\n"
            f"Your current languages: {user.language_proficiencies or 'None'}"
        )
        return

    languages = ",".join(arg.lower().strip() for arg in context.args[0].split(',')) # Process languages from arguments
    user.language_proficiencies = languages
    db.commit()
    await update.message.reply_text(f"Your language proficiencies have been set to: {languages}")
    logger.info(f"Agent {user.telegram_id} updated languages to {languages}.")

# /agent_status command handler
@db_session_decorator
async def toggle_agent_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    db: Session = context.user_data['_db']
    user = await get_or_create_user(db, update.effective_user.id, update.effective_user.username, update.effective_user.first_name)

    if not user.is_agent:
        await update.message.reply_text("You are not registered as an agent.")
        return

    user.is_available = not user.is_available # Toggle availability
    db.commit()
    status_text = "available" if user.is_available else "unavailable"
    await update.message.reply_text(f"Your status has been set to: {status_text}")
    logger.info(f"Agent {user.telegram_id} toggled status to {status_text}.")

# /close_request command handler (for agents)
@db_session_decorator
async def close_request(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    db: Session = context.user_data['_db']
    user = await get_or_create_user(db, update.effective_user.id, update.effective_user.username, update.effective_user.first_name)

    if not user.is_agent:
        await update.message.reply_text("Only agents can close requests.")
        return

    # Find the request currently assigned to this agent and is active
    active_request = db.query(SupportRequest).filter(
        SupportRequest.agent_id == user.id,
        SupportRequest.status == 'assigned'
    ).first()

    if not active_request:
        await update.message.reply_text("You are not currently assigned to an active request to close.")
        return

    active_request.status = 'closed' # Set status to closed
    active_request.closed_at = func.now() # Set closed timestamp
    db.commit()

    customer = db.query(User).get(active_request.customer_id)
    if customer:
        # Notify the customer that their request is closed
        await context.application.bot.send_message(
            chat_id=customer.telegram_id,
            text=f"Your support request has been closed by Agent {user.first_name or user.username}. "
                 "If you need further assistance, please start a new request with /start."
        )

    await update.message.reply_text(f"Request #{active_request.id} has been closed.")
    logger.info(f"Agent {user.telegram_id} closed request {active_request.id}.")

# /view_requests command handler (for agents)
@db_session_decorator
async def view_agent_requests(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    db: Session = context.user_data['_db']
    agent = await get_or_create_user(db, update.effective_user.id, update.effective_user.username, update.effective_user.first_name)

    if not agent.is_agent:
        await update.message.reply_text("You are not an agent.")
        return

    # Get requests currently assigned to this agent
    assigned_requests = db.query(SupportRequest).filter(
        SupportRequest.agent_id == agent.id,
        SupportRequest.status == 'assigned'
    ).all()

    assigned_text = "Your Assigned Requests:\n"
    if assigned_requests:
        for req in assigned_requests:
            customer = db.query(User).get(req.customer_id)
            assigned_text += f"- ID: {req.id}, Customer: {customer.first_name or customer.username}, Lang: {req.language}\n"
    else:
        assigned_text += "None.\n"

    # Get pending requests that this agent is proficient in
    # We split the agent's language proficiencies and check if the request language is in that list
    
    agent_langs = []
    if agent.language_proficiencies: # This checks if it's not None and not an empty string
        agent_langs = [lang.strip() for lang in agent.language_proficiencies.split(',')]

    pending_requests = db.query(SupportRequest).filter(
        SupportRequest.status == 'pending',
        SupportRequest.language.in_(agent_langs)
    ).all()

    await update.message.reply_text(assigned_text) # Send assigned requests first

    pending_text = "\nPending Requests (you can bid on):\n"
    if pending_requests:
        for req in pending_requests:
            customer = db.query(User).get(req.customer_id)
            keyboard = [[InlineKeyboardButton("Bid", callback_data=f"bid_{req.id}")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            # Send each pending request as a separate message with a "Bid" button
            await update.message.reply_text(
                f"🚨 Pending Request #{req.id} 🚨\n"
                f"Customer: {customer.first_name or customer.username}\n"
                f"Language: {req.language.upper()}\n"
                f"Status: Pending\n"
                f"Time: {req.created_at.strftime('%Y-%m-%d %H:%M:%S')}",
                reply_markup=reply_markup
            )
    else:
        await update.message.reply_text(pending_text + "None.") # If no pending requests


# Error handler: Catches any exceptions in your bot and logs them
async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Log the error and send a message to notify the user/developer."""
    logger.error("Exception while handling an update:", exc_info=context.error)
    if update.effective_message:
        await update.effective_message.reply_text("An internal error occurred. Please try again later.")

# --- Main function to run the bot ---
def main() -> None:
    # 1. Initialize the database (create tables if they don't exist)
    init_db()

    # 2. Build the Telegram Application instance (our bot)
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    # 3. Register Handlers: These tell the bot what to do when it receives different types of updates

    # Customer-facing handlers
    application.add_handler(CommandHandler("start", start)) # Handles /start command
    application.add_handler(CallbackQueryHandler(handle_language_selection, pattern="^lang_")) # Handles button presses for language selection
    # Handles any non-command text message. It intelligently delegates if it's an agent.
    application.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_customer_message, block=False))

    # Agent-facing handlers
    application.add_handler(CommandHandler("register_agent", register_agent)) # Handles /register_agent
    application.add_handler(CommandHandler("agent_languages", set_agent_languages)) # Handles /agent_languages
    application.add_handler(CommandHandler("agent_status", toggle_agent_status)) # Handles /agent_status
    application.add_handler(CommandHandler("close_request", close_request)) # Handles /close_request
    application.add_handler(CommandHandler("view_requests", view_agent_requests)) # Handles /view_requests
    application.add_handler(CallbackQueryHandler(handle_bid, pattern="^bid_")) # Handles button presses for bidding

    # 4. Register the global error handler
    application.add_error_handler(error_handler)

    # 5. Start the bot: This continuously checks for new updates from Telegram
    logger.info("Bot started polling...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()