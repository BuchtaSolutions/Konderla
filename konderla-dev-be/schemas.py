from pydantic import BaseModel, validator
from typing import List, Optional, Dict, Any, Union
from datetime import datetime
from uuid import UUID

# Budget Schemas
class BudgetNoteBase(BaseModel):
    content: str

class BudgetNoteCreate(BudgetNoteBase):
    pass

class BudgetNote(BudgetNoteBase):
    id: UUID
    budget_id: UUID
    created_at: datetime

    class Config:
        orm_mode = True

class RoundDuplicateBase(BaseModel):
    data: Dict[str, Any]

class RoundDuplicateCreate(RoundDuplicateBase):
    round_id: UUID

class RoundDuplicate(RoundDuplicateBase):
    id: UUID
    round_id: UUID
    created_at: datetime

    class Config:
        orm_mode = True

class BudgetBase(BaseModel):
    name: str
    notes: Optional[str] = None
    score: Optional[float] = None
    file_path: Optional[str] = None
    labels: Optional[Dict[str, Any]] = {}
    items: Optional[Any] = []
    dynamic_fields: Optional[Dict[str, Any]] = {}

class BudgetCreate(BudgetBase):
    round_id: UUID
    project_id: UUID
    parent_budget_id: Optional[UUID] = None

class BudgetUpdate(BaseModel):
    name: Optional[str] = None
    notes: Optional[str] = None
    score: Optional[float] = None
    labels: Optional[Dict[str, Any]] = None
    items: Optional[List[Dict[str, Any]]] = None
    dynamic_fields: Optional[Dict[str, Any]] = None

class Budget(BudgetBase):
    id: UUID
    round_id: UUID
    project_id: UUID
    parent_budget_id: Optional[UUID] = None

    class Config:
        orm_mode = True

# Round Schemas
class RoundBase(BaseModel):
    name: str
    order: int
    status: str = "open"

class RoundCreate(RoundBase):
    project_id: UUID

class Round(RoundBase):
    id: UUID
    project_id: UUID
    budgets: List[Budget] = []

    class Config:
        orm_mode = True

# Project Schemas
class ProjectBase(BaseModel):
    name: str
    description: Optional[str] = None

class ProjectCreate(ProjectBase):
    pass

class ProjectUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None

class Project(ProjectBase):
    id: UUID
    rounds: List[Round] = []

    class Config:
        orm_mode = True

# Chat Schemas
class ChatHistoryBase(BaseModel):
    role: str
    content: str

class ChatHistoryCreate(ChatHistoryBase):
    project_id: UUID
    session_id: Optional[UUID] = None

class ChatHistory(ChatHistoryBase):
    id: UUID
    project_id: UUID
    session_id: Optional[UUID] = None
    timestamp: datetime

    class Config:
        orm_mode = True

# Promote Schema
class PromoteRequest(BaseModel):
    project_id: UUID
    current_round_id: UUID
    budget_ids: List[UUID] # IDs of budgets to promote
    new_round_name: str

# Chat Request
class ChatRequest(BaseModel):
    project_id: UUID
    session_id: Optional[UUID] = None
    message: str

class ChatSessionBase(BaseModel):
    name: str

class ChatSessionCreate(ChatSessionBase):
    project_id: UUID

class ChatSession(ChatSessionBase):
    id: UUID
    project_id: UUID
    created_at: datetime
    
    class Config:
        orm_mode = True

class ChatHistoryBase(BaseModel):
    project_id: UUID
    role: str
    content: str
    session_id: Optional[UUID] = None

class ChatHistoryCreate(ChatHistoryBase):
    pass

class ChatHistory(ChatHistoryBase):
    id: UUID
    timestamp: datetime

    class Config:
        orm_mode = True

class MergeItemsRequest(BaseModel):
    source_name: str
    target_name: str
    new_name: str
