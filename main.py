from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Dict, Optional
import os
import uuid

from langchain.agents import AgentExecutor, create_tool_calling_agent

from langchain_anthropic import ChatAnthropic
from langchain_community.embeddings import HuggingFaceEmbeddings

from langchain.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain.tools import tool
from langchain.memory import ConversationBufferMemory
from langchain_community.vectorstores import Chroma

app = FastAPI(title="Agentic CX Assistant")

# CORS for Loveable frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize Claude
llm = ChatAnthropic(
    model="claude-3-5-sonnet-20241022",
    anthropic_api_key=os.getenv("ANTHROPIC_API_KEY"),
    temperature=0
)

# Define agent tools
@tool
def lookup_order(order_id: str) -> dict:
    """Look up order details by order ID. Use this when customer mentions an order number."""
    orders = {
        "12345": {
            "status": "Delivered",
            "date": "2024-01-15",
            "items": ["Laptop", "Mouse"],
            "total": "$1,299.99",
            "tracking": "TRACK123"
        },
        "67890": {
            "status": "In Transit",
            "date": "2024-01-20",
            "items": ["Headphones"],
            "total": "$299.99",
            "tracking": "TRACK456"
        }
    }
    result = orders.get(order_id, {"error": "Order not found"})
    return result

@tool
def process_refund(order_id: str, reason: str) -> dict:
    """Process a refund for an order. Only use after confirming order exists."""
    # Check if order exists first
    orders = ["12345", "67890"]
    if order_id not in orders:
        return {"error": "Cannot process refund - order not found"}
    
    return {
        "success": True,
        "refund_id": f"REF-{order_id}",
        "amount": "$299.99",
        "eta": "3-5 business days",
        "reason": reason,
        "message": "Refund processed successfully"
    }

# Initialize ChromaDB for knowledge base
try:
    embeddings = HuggingFaceEmbeddings(
    model_name="sentence-transformers/all-MiniLM-L6-v2",
    model_kwargs={'device': 'cpu'},
    encode_kwargs={'normalize_embeddings': True}
	)
    
    knowledge_articles = [
        "Refund Policy: We offer a 30-day money-back guarantee on all products. Simply contact support with your order ID and we'll process your refund within 3-5 business days.",
        "Shipping Policy: All orders ship within 24 hours of purchase. Domestic delivery takes 3-5 business days, international shipping takes 7-14 days. Free shipping on orders over $50.",
        "Return Process: To return an item, contact support with your order ID and reason for return. We'll provide a prepaid shipping label via email. Items must be in original condition.",
        "Warranty Information: All electronics come with a 1-year manufacturer warranty covering defects in materials and workmanship. Extended warranties available for purchase.",
        "Payment Methods: We accept all major credit cards (Visa, Mastercard, American Express), PayPal, Apple Pay, and Google Pay. All transactions are encrypted and secure.",
        "Order Tracking: Track your order using the tracking number sent to your email after shipping. Allow 24 hours for tracking to become active.",
        "Cancellation Policy: Orders can be cancelled within 2 hours of purchase for a full refund. After 2 hours, please contact support for assistance.",
        "International Shipping: We ship to over 50 countries worldwide. Customs fees and import duties are the responsibility of the customer and vary by country.",
        "Customer Support Hours: Our support team is available Monday-Friday 9am-6pm EST. Weekend support available via live chat. Emergency support: support@example.com",
        "Account Security: We recommend using strong passwords and enabling two-factor authentication. Never share your password. We'll never ask for your password via email."
    ]
    
    vectorstore = Chroma.from_texts(
        texts=knowledge_articles,
        embedding=embeddings,
        persist_directory="./chroma_db"
    )
    
    @tool
    def search_knowledge_base(query: str) -> str:
        """Search company knowledge base for policies, procedures, and information. Use this to answer policy questions."""
        docs = vectorstore.similarity_search(query, k=2)
        result = "\n\n".join([doc.page_content for doc in docs])
        return result
    
except Exception as e:
    print(f"Warning: ChromaDB initialization failed: {e}")
    # Fallback to simple dict-based search
    knowledge_dict = {
        "refund": "Refund Policy: 30-day money-back guarantee. Contact support with order ID.",
        "shipping": "Shipping Policy: Ships in 24hrs. 3-5 days domestic, 7-14 international.",
        "return": "Return Process: Contact support with order ID for prepaid label.",
    }
    
    @tool
    def search_knowledge_base(query: str) -> str:
        """Search company knowledge base for policies and information."""
        query_lower = query.lower()
        for key, value in knowledge_dict.items():
            if key in query_lower:
                return value
        return "Please contact support for more information."

# Create agent
tools = [lookup_order, process_refund, search_knowledge_base]

prompt = ChatPromptTemplate.from_messages([
    ("system", """You are a helpful customer service AI assistant for an e-commerce company.

Your capabilities:
- Look up order information using order IDs
- Process refunds when customers request them
- Search the knowledge base to answer policy questions

Guidelines:
1. Always be friendly and professional
2. If you need information (like an order ID), ask the customer politely
3. When using a tool, briefly explain what you're doing
4. After looking up an order, summarize the key information clearly
5. For refunds, confirm the order exists first, then process
6. Cite specific policies when answering policy questions

Remember: You're here to help customers efficiently and professionally.
"""),
    MessagesPlaceholder(variable_name="chat_history"),
    ("human", "{input}"),
    MessagesPlaceholder(variable_name="agent_scratchpad"),
])

agent = create_tool_calling_agent(llm=llm, tools=tools, prompt=prompt)

# Session memory storage
sessions = {}

def get_agent_executor(session_id: str):
    """Get or create agent executor for a session"""
    if session_id not in sessions:
        sessions[session_id] = ConversationBufferMemory(
            memory_key="chat_history",
            return_messages=True
        )
    
    return AgentExecutor(
        agent=agent,
        tools=tools,
        memory=sessions[session_id],
        verbose=True,
        return_intermediate_steps=True,
        max_iterations=5,
        handle_parsing_errors=True
    )

# API Models
class ChatRequest(BaseModel):
    message: str
    session_id: str = "default"

class AgentStep(BaseModel):
    tool: str
    input: str
    output: str

class ChatResponse(BaseModel):
    response: str
    agent_steps: List[AgentStep]
    tools_used: List[str]

# Endpoints
@app.get("/")
async def root():
    return {
        "message": "Agentic CX Assistant API",
        "status": "operational",
        "version": "1.0",
        "endpoints": {
            "health": "/health",
            "chat": "/chat",
            "status": "/status"
        }
    }

@app.get("/health")
async def health():
    return {"status": "healthy", "agent": "ready"}

@app.get("/status")
async def status():
    return {
        "tools_available": [tool.name for tool in tools],
        "active_sessions": len(sessions),
        "vector_db": "chromadb",
        "llm": "claude-3.5-sonnet"
    }

@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """Main chat endpoint - processes messages through LangChain agent"""
    try:
        # Get agent executor for this session
        executor = get_agent_executor(request.session_id)
        
        # Execute agent
        result = executor.invoke({"input": request.message})
        
        # Extract agent steps and tools used
        agent_steps = []
        tools_used = []
        
        for step in result.get("intermediate_steps", []):
            action, observation = step
            tools_used.append(action.tool)
            agent_steps.append(AgentStep(
                tool=action.tool,
                input=str(action.tool_input),
                output=str(observation)[:500]  # Truncate long outputs
            ))
        
        return ChatResponse(
            response=result["output"],
            agent_steps=agent_steps,
            tools_used=list(set(tools_used))  # Unique tools
        )
    
    except Exception as e:
        print(f"Error in chat endpoint: {str(e)}")
        raise HTTPException(
            status_code=500, 
            detail=f"Agent error: {str(e)}"
        )

@app.delete("/session/{session_id}")
async def clear_session(session_id: str):
    """Clear a session's memory"""
    if session_id in sessions:
        del sessions[session_id]
        return {"message": f"Session {session_id} cleared"}
    return {"message": "Session not found"}