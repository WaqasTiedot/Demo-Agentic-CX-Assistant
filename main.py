from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Dict
import os

app = FastAPI(title="Agentic CX Assistant")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class ChatRequest(BaseModel):
    message: str
    session_id: str = "default"

class ChatResponse(BaseModel):
    response: str
    agent_steps: List[Dict]
    tools_used: List[str]

@app.get("/health")
async def health():
    return {"status": "healthy"}

@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    # Placeholder - we'll add LangChain agent here
    return ChatResponse(
        response="Hello! I'm your CX assistant.",
        agent_steps=[],
        tools_used=[]
    )

@app.get("/")
async def root():
    return {"message": "Agentic CX Assistant API"}