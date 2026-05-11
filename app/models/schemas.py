"""
Pydantic models for request/response validation
"""
from pydantic import BaseModel, Field, EmailStr
from datetime import datetime, date
from typing import Optional, List, Dict, Any
from uuid import UUID


# ============================================================================
# AUTH SCHEMAS
# ============================================================================

class LoginPayload(BaseModel):
    email: EmailStr
    password: str


class User(BaseModel):
    id: UUID
    email: str
    name: str
    role: str
    authority_level: int
    airport_id: str
    department: Optional[str] = None
    designation: Optional[str] = None
    employee_id: Optional[str] = None
    is_active: bool
    created_at: datetime


class LoginResponse(BaseModel):
    token: str
    user: User
    expires_at: datetime


# ============================================================================
# INGRESS SCHEMAS
# ============================================================================

class IngestMessagePayload(BaseModel):
    raw_content: str
    message_type: str  # 'task'|'info'|'alert'|'approval'|'escalation'
    flight_context: Optional[str] = None


class IngestMessageResponse(BaseModel):
    msg_id: UUID
    status: str
    pipeline: str
    received_at: datetime


class IngestChatPayload(BaseModel):
    raw_content: str
    query_type: Optional[str] = None  # 'general_query'|'leave'|'cab'|'hotel'|None
    session_id: Optional[str] = None
    conversation_history: Optional[List[Dict[str, str]]] = None


class IngestChatResponse(BaseModel):
    chat_id: UUID
    status: str
    pipeline: str
    session_id: Optional[str] = None


# ============================================================================
# OPS CARD SCHEMAS
# ============================================================================

class OpsCard(BaseModel):
    event_id: str
    airport_id: str
    type: str
    title: str
    summary: str
    actions_required: List[str] = []
    entities: Dict[str, Any] = {}
    urgency_score: int
    priority_score: float
    priority_label: str
    deadline_utc: Optional[datetime] = None
    authority_level: int
    impact: int
    confidence: float
    dedup_hash: Optional[str] = None
    policy_flags: List[str] = []
    lineage: Dict[str, Any] = {}
    source_msg_id: Optional[UUID] = None
    routing_status: str = "pending"
    status: str = "unprocessed"


# ============================================================================
# TASK & ACTIVITY SCHEMAS
# ============================================================================

class Task(BaseModel):
    task_id: str
    airport_id: str
    ops_card_id: Optional[str] = None
    flight_no: Optional[str] = None
    title: str
    description: Optional[str] = None
    status: str = "New"  # 'New'|'Ack'|'InProgress'|'Blocked'|'Done'
    priority: float
    priority_label: str
    assignee_id: Optional[UUID] = None
    ack_by_id: Optional[UUID] = None
    ack_at_utc: Optional[datetime] = None
    sla_deadline_utc: Optional[datetime] = None
    visible_to_levels: List[int] = [1, 2, 3]
    escalation_level: int = 0
    labels: List[str] = []
    audit: List[Dict[str, Any]] = []
    created_at: datetime
    updated_at: datetime


class Activity(BaseModel):
    activity_id: str
    airport_id: str
    flight_no: Optional[str] = None
    name: str
    start_utc: datetime
    end_utc: Optional[datetime] = None
    depends_on: List[str] = []
    resource_type: Optional[str] = None
    resource_id: Optional[str] = None
    state: str = "Planned"
    source_ops_card_ids: List[str] = []
    critical_path: bool = False
    created_at: datetime
    updated_at: datetime


# ============================================================================
# ROSTER & LEAVE SCHEMAS
# ============================================================================

class LeaveBalance(BaseModel):
    employee_id: UUID
    financial_year: str
    casual_total: int = 12
    casual_used: int = 0
    sick_total: int = 10
    sick_used: int = 0
    planned_total: int = 15
    planned_used: int = 0
    updated_at: datetime


class LeaveRequest(BaseModel):
    id: UUID
    employee_id: UUID
    leave_type: str
    start_date: date
    end_date: date
    reason: Optional[str] = None
    status: str = "Pending"
    backup_assigned_to: Optional[UUID] = None
    approved_by: Optional[UUID] = None
    source_chat_id: Optional[UUID] = None
    created_at: datetime
    updated_at: datetime


class RosterEntry(BaseModel):
    id: UUID
    employee_id: UUID
    designation: str
    duty_date: date
    shift_start_utc: datetime
    shift_end_utc: datetime
    status: str = "Scheduled"
    flight_no: Optional[str] = None
    airport_id: str
    rest_hours_before: Optional[float] = None
    is_backup: bool = False
    notes: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class BackupRecommendation(BaseModel):
    rank: int
    employee_id: UUID
    name: str
    designation: str
    rest_hours_available: float
    duty_date: date
    compliance: str
    reason: str


# ============================================================================
# VENDOR TICKET SCHEMAS
# ============================================================================

class VendorTicket(BaseModel):
    id: UUID
    ticket_id: str
    ticket_type: str  # 'cab'|'hotel'
    requester_id: Optional[UUID] = None
    vendor_id: Optional[UUID] = None
    details: Dict[str, Any] = {}
    status: str = "Open"
    resolution_notes: Optional[str] = None
    sla_deadline_utc: Optional[datetime] = None
    resolved_at: Optional[datetime] = None
    review_ticket: bool = False
    source_chat_id: Optional[UUID] = None
    created_at: datetime
    updated_at: datetime


class VendorTicketResolve(BaseModel):
    resolution_notes: str


# ============================================================================
# AGENT PROCESS SCHEMAS
# ============================================================================

class SummarizerInput(BaseModel):
    id: UUID
    sender_name: str
    sender_role: str
    authority_level: int
    airport_id: str
    raw_content: str
    message_type: str
    flight_context: Optional[str] = None
    received_at: datetime


class SummarizerOutput(BaseModel):
    event_id: str
    airport_id: str
    type: str
    title: str
    summary: str
    actions_required: List[str]
    entities: Dict[str, Any]
    urgency_score: int
    priority_score: float
    priority_label: str
    deadline_utc: Optional[datetime]
    authority_level: int
    impact: int
    confidence: float
    dedup_hash: str
    policy_flags: List[str]
    lineage: Dict[str, Any]
    source_msg_id: UUID


class RouterInput(BaseModel):
    ops_card: OpsCard


class RouterOutput(BaseModel):
    task_id: str
    activity_id: Optional[str] = None


class QueryAgentInput(BaseModel):
    chat_id: Optional[UUID] = None
    query_text: str
    employee_id: UUID
    query_type: str = "general_query"
    conversation_history: List[Dict[str, str]] = []
    context: Optional[Dict[str, Any]] = None


class QueryAgentOutput(BaseModel):
    response: str
    intent_detected: Optional[str] = None
    source: str
    action_taken: bool = False
    data: Optional[Dict[str, Any]] = None
    sources: Optional[List[str]] = None


class ChatSyncPayload(BaseModel):
    user_message: str
    conversation_history: Optional[List[Dict[str, str]]] = None
    session_id: Optional[str] = None


class ChatSyncResponse(BaseModel):
    response: str
    session_id: Optional[str] = None
    sources: Optional[List[str]] = None


class RosterAgentInput(BaseModel):
    event_type: str  # 'leave_request'|'query'
    employee_id: Optional[UUID] = None
    leave_type: Optional[str] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    reason: Optional[str] = None
    chat_id: Optional[UUID] = None
    query_text: Optional[str] = None
    airport_id: Optional[str] = None


class RosterAgentOutput(BaseModel):
    response: str
    leave_request_id: Optional[UUID] = None
    affected_duty_slots: Optional[int] = None
    backup_recommendations: Optional[List[BackupRecommendation]] = None
    manager_action_required: Optional[bool] = None
    data: Optional[Dict[str, Any]] = None
    source: str


class CabHotelAgentInput(BaseModel):
    chat_id: Optional[UUID] = None
    ticket_type: str  # 'cab'|'hotel'
    requester_id: UUID
    airport_id: str
    query_text: str


class CabHotelAgentOutput(BaseModel):
    response: str
    ticket_id: str
    vendor_name: str
    sla_deadline: datetime
    data: Dict[str, Any]
    source: str


# ============================================================================
# DASHBOARD SCHEMAS
# ============================================================================

class KanbanBucket(BaseModel):
    New: List[Task] = []
    Ack: List[Task] = []
    InProgress: List[Task] = []
    Blocked: List[Task] = []
    Done: List[Task] = []


class KanbanResponse(BaseModel):
    airport_id: str
    authority_level: int
    kanban: KanbanBucket
    counts: Dict[str, int]


class GanttResponse(BaseModel):
    airport_id: str
    date: str
    activities: List[Activity]


class ManagerLeaveRequestsResponse(BaseModel):
    leave_requests: List[LeaveRequest]


class ManagerRosterResponse(BaseModel):
    date: str
    airport_id: str
    roster: List[Dict[str, Any]]


class EscalationsResponse(BaseModel):
    tasks: List[Task]


# ============================================================================
# FLIGHT SCHEMAS
# ============================================================================

class Flight(BaseModel):
    id: UUID
    flight_no: str
    origin: str
    destination: str
    scheduled_departure: Optional[datetime] = None
    scheduled_arrival: Optional[datetime] = None
    actual_departure: Optional[datetime] = None
    actual_arrival: Optional[datetime] = None
    gate_assigned: Optional[str] = None
    stand_assigned: Optional[str] = None
    status: str = "Scheduled"
    airport_id: str
    aircraft_type: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class CreateFlightPayload(BaseModel):
    flight_no: str
    origin: str
    destination: str
    scheduled_departure: datetime
    scheduled_arrival: datetime
    airport_id: str
    aircraft_type: Optional[str] = None


# ============================================================================
# COMMON SCHEMAS
# ============================================================================

class ErrorResponse(BaseModel):
    detail: str
    error_code: Optional[str] = None


class SuccessResponse(BaseModel):
    message: str
    data: Optional[Dict[str, Any]] = None
