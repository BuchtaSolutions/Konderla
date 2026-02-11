from sqlalchemy import Column, Integer, String, Float, ForeignKey, DateTime, JSON, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from database import Base
import uuid

class Project(Base):
    __tablename__ = "projects"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, server_default=text("gen_random_uuid()"), index=True)
    name = Column(String, index=True)
    description = Column(String, nullable=True)

    rounds = relationship("Round", back_populates="project", cascade="all, delete-orphan")
    chat_history = relationship("ChatHistory", back_populates="project", cascade="all, delete-orphan")
    chat_sessions = relationship("ChatSession", back_populates="project", cascade="all, delete-orphan")

class Round(Base):
    __tablename__ = "rounds"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, server_default=text("gen_random_uuid()"), index=True)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id"))
    name = Column(String)
    order = Column(Integer)
    status = Column(String, default="open")  # open, closed

    project = relationship("Project", back_populates="rounds")
    budgets = relationship("Budget", back_populates="round", cascade="all, delete-orphan")
    duplicates = relationship("RoundDuplicate", back_populates="round", cascade="all, delete-orphan")

class RoundDuplicate(Base):
    __tablename__ = "round_duplicates"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, server_default=text("gen_random_uuid()"), index=True)
    round_id = Column(UUID(as_uuid=True), ForeignKey("rounds.id"))
    data = Column(JSON) # { "original_item": ..., "new_item": ..., "similarity": float }
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    round = relationship("Round", back_populates="duplicates")

class Budget(Base):
    __tablename__ = "budgets"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, server_default=text("gen_random_uuid()"), index=True)
    round_id = Column(UUID(as_uuid=True), ForeignKey("rounds.id"))
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id"))
    parent_budget_id = Column(UUID(as_uuid=True), ForeignKey("budgets.id"), nullable=True)
    
    name = Column(String)
    notes = Column(String, nullable=True)
    score = Column(Float, nullable=True)
    file_path = Column(String, nullable=True)
    
    labels = Column(JSON, default={})
    items = Column(JSON, default=[]) # list[dict(name: str, price: float)]
    dynamic_fields = Column(JSON, default={})

    round = relationship("Round", back_populates="budgets")
    parent = relationship("Budget", remote_side=[id], backref="children")
    notes_history = relationship("BudgetNote", back_populates="budget", cascade="all, delete-orphan")

class BudgetNote(Base):
    __tablename__ = "budget_notes"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, server_default=text("gen_random_uuid()"), index=True)
    budget_id = Column(UUID(as_uuid=True), ForeignKey("budgets.id"))
    content = Column(String)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    budget = relationship("Budget", back_populates="notes_history")

class ChatSession(Base):
    __tablename__ = "chat_sessions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, server_default=text("gen_random_uuid()"), index=True)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id"))
    name = Column(String, default="New Chat")
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    project = relationship("Project", back_populates="chat_sessions")
    history = relationship("ChatHistory", back_populates="session", cascade="all, delete-orphan")

class ChatHistory(Base):
    __tablename__ = "chat_history"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, server_default=text("gen_random_uuid()"), index=True)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id"))
    session_id = Column(UUID(as_uuid=True), ForeignKey("chat_sessions.id"), nullable=True)
    role = Column(String) # user, model
    content = Column(String)
    timestamp = Column(DateTime(timezone=True), server_default=func.now())

    project = relationship("Project", back_populates="chat_history")
    session = relationship("ChatSession", back_populates="history")
