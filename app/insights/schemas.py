from pydantic import BaseModel
from typing import Optional


class AskQuestionIn(BaseModel):
    question: str


class AskQuestionOut(BaseModel):
    answer: str
    usedLlm: bool  # false means the LLM wasn't available and this is a basic fallback


class TopItemOut(BaseModel):
    name: str
    qty: int
    revenue: float


class AnalyticsSnapshotOut(BaseModel):
    periodDays: int
    totalRevenue: float
    totalOrders: int
    avgOrderValue: float
    topItems: list[TopItemOut]
    revenueByMode: dict[str, float]
    newCustomers: int
    repeatCustomers: int


class ChurnCandidateOut(BaseModel):
    customerNumber: str
    customerName: Optional[str] = None
    lastOrderDaysAgo: int
    totalOrdersPlaced: int
    lastOrderedItem: Optional[str] = None


class UpsellSuggestionOut(BaseModel):
    suggestionId: str
    title: str
    description: str
    suggestedMessage: str
    customerNumbers: list[str]
    customerCount: int
    usedLlm: bool


class SendWinbackIn(BaseModel):
    customerNumbers: list[str]
    message: str


class SendWinbackOut(BaseModel):
    sentCount: int
    failedCount: int
