# database.py
from sqlalchemy import create_engine, Column, Integer, String, Boolean, DateTime, ForeignKey, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from sqlalchemy.sql import func
from config import DATABASE_URL # Import DATABASE_URL from our config file

Base = declarative_base() # This is the base class for our database models

# User Model: Represents a customer or a support agent
class User(Base):
    __tablename__ = 'users' # Table name in the database
    id = Column(Integer, primary_key=True) # Unique ID for each user
    telegram_id = Column(Integer, unique=True, nullable=False) # Their Telegram user ID
    username = Column(String, nullable=True) # Their Telegram username (optional)
    first_name = Column(String, nullable=True) # Their Telegram first name (optional)
    is_agent = Column(Boolean, default=False) # True if this user is a support agent
    language_proficiencies = Column(String) # e.g., "en,es,fr" comma-separated languages an agent can handle
    is_available = Column(Boolean, default=True) # Agents can toggle their availability
    created_at = Column(DateTime, server_default=func.now()) # When the user was added

    # Relationships to other tables
    support_requests_as_customer = relationship("SupportRequest", foreign_keys="[SupportRequest.customer_id]", back_populates="customer")
    support_requests_as_agent = relationship("SupportRequest", foreign_keys="[SupportRequest.agent_id]", back_populates="agent")
    messages = relationship("Message", back_populates="sender")

    def __repr__(self):
        return f"<User(telegram_id={self.telegram_id}, username='{self.username}', is_agent={self.is_agent})>"

# SupportRequest Model: Represents a customer's support conversation
class SupportRequest(Base):
    __tablename__ = 'support_requests'
    id = Column(Integer, primary_key=True)
    customer_id = Column(Integer, ForeignKey('users.id'), nullable=False) # Link to the customer who opened the request
    agent_id = Column(Integer, ForeignKey('users.id'), nullable=True) # Link to the agent assigned (null until assigned)
    language = Column(String, nullable=False) # The language of the request (e.g., "en", "es")
    status = Column(String, default='pending') # Status: 'pending', 'assigned', 'closed'
    created_at = Column(DateTime, server_default=func.now()) # When the request was created
    assigned_at = Column(DateTime, nullable=True) # When an agent was assigned
    closed_at = Column(DateTime, nullable=True) # When the request was closed

    # Relationships
    customer = relationship("User", foreign_keys=[customer_id], back_populates="support_requests_as_customer")
    agent = relationship("User", foreign_keys=[agent_id], back_populates="support_requests_as_agent")
    messages = relationship("Message", back_populates="support_request", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<SupportRequest(id={self.id}, customer_id={self.customer_id}, status='{self.status}')>"

# Message Model: Represents individual messages within a support request
class Message(Base):
    __tablename__ = 'messages'
    id = Column(Integer, primary_key=True)
    support_request_id = Column(Integer, ForeignKey('support_requests.id'), nullable=False) # Link to the parent support request
    sender_id = Column(Integer, ForeignKey('users.id'), nullable=False) # The actual sender of the message (customer or agent)
    text = Column(Text, nullable=False) # The content of the message
    timestamp = Column(DateTime, server_default=func.now()) # When the message was sent

    # Relationships
    support_request = relationship("SupportRequest", back_populates="messages")
    sender = relationship("User", back_populates="messages")

    def __repr__(self):
        return f"<Message(id={self.id}, sender_id={self.sender_id}, support_request_id={self.support_request_id})>"

# Setup the database engine and session
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Function to create all tables in the database
def init_db():
    Base.metadata.create_all(bind=engine)
    print("Database initialized.")

# This block ensures init_db() is called only when database.py is run directly
if __name__ == "__main__":
    init_db()