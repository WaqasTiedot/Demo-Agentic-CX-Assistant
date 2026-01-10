from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional, List, Dict
import os
from dotenv import load_dotenv
from datetime import datetime, timedelta
import random

# LangChain imports
from langchain_anthropic import ChatAnthropic
from langchain.agents import AgentExecutor, create_tool_calling_agent
from langchain.tools import tool
from langchain.memory import ConversationBufferMemory
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

# Load environment variables
load_dotenv()

# Initialize FastAPI
app = FastAPI(title="Agentic CX Assistant")

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Session storage
sessions: Dict[str, ConversationBufferMemory] = {}

# Simple knowledge base (lightweight, no vector DB)
knowledge_base = {
    "refund": "Refund Policy: We offer a 30-day money-back guarantee on all products. Contact support with your order ID and we'll process your refund within 3-5 business days. Refunds are issued to the original payment method.",
    "shipping": "Shipping Policy: All orders ship within 24 hours of purchase. Domestic delivery takes 3-5 business days, international shipping takes 7-14 days. Free shipping on orders over $50. Tracking numbers sent via email.",
    "return": "Return Process: To return an item, contact support with your order ID and reason for return. We'll provide a prepaid shipping label via email within 24 hours. Items must be in original condition with tags attached.",
    "warranty": "Warranty Information: All electronics come with a 1-year manufacturer warranty covering defects in materials and workmanship. Extended warranties available for purchase at checkout. Claims processed within 5 business days.",
    "payment": "Payment Methods: We accept all major credit cards (Visa, Mastercard, American Express, Discover), PayPal, Apple Pay, and Google Pay. All transactions are encrypted and secure with PCI DSS compliance.",
    "tracking": "Order Tracking: Track your order using the tracking number sent to your email after shipping. Allow 24 hours for tracking to become active. Contact support if tracking hasn't updated within 48 hours.",
    "cancel": "Cancellation Policy: Orders can be cancelled within 2 hours of purchase for a full refund. After 2 hours but before shipping, contact support for assistance. Once shipped, standard return policy applies.",
    "international": "International Shipping: We ship to over 50 countries worldwide. Customs fees and import duties are the responsibility of the customer. Delivery times vary by destination (7-21 business days).",
    "support": "Customer Support Hours: Our support team is available Monday-Friday 9am-6pm EST, Saturday 10am-4pm EST. Weekend live chat available. Average response time: under 2 hours during business hours.",
    "security": "Account Security: We recommend using strong passwords (min 12 characters) and enabling two-factor authentication. Never share your password. We'll never ask for your password via email or phone."
}

# Helper function to generate recent date
def get_random_recent_date():
    """Generate a random date within the last 7 days"""
    days_ago = random.randint(1, 7)
    date = datetime.now() - timedelta(days=days_ago)
    return date.strftime("%Y-%m-%d")

# Define Tools
@tool
def lookup_order(order_id: str) -> dict:
    """Look up order details by order ID. Returns order information including items, status, and tracking."""
    # Generate dynamic recent date
    recent_date = get_random_recent_date()
    
    # Mock database with dynamic dates
    orders = {
        "12345": {
            "order_id": "12345",
            "items": ["Laptop", "Wireless Mouse"],
            "total": "$1,299.99",
            "status": "Delivered",
            "delivery_date": recent_date,
            "tracking": "TRACK123"
        },
        "67890": {
            "order_id": "67890",
            "items": ["Headphones"],
            "total": "$299.99",
            "status": "In Transit",
            "estimated_delivery": (datetime.now() + timedelta(days=random.randint(2, 5))).strftime("%Y-%m-%d"),
            "tracking": "TRACK456"
        }
    }
    
    order = orders.get(order_id)
    if order:
        return order
    else:
        return {"error": f"Order {order_id} not found"}

@tool
def process_refund(order_id: str, reason: str) -> dict:
    """Process a refund for an order. Requires order ID and reason for refund."""
    # Validate order exists
    order = lookup_order.invoke({"order_id": order_id})
    
    if "error" in order:
        return {"error": f"Cannot process refund - order {order_id} not found"}
    
    # Process refund
    refund_amount = order.get("total", "$0.00")
    return {
        "status": "success",
        "refund_id": f"REF-{order_id}",
        "amount": refund_amount,
        "estimated_days": "3-5 business days",
        "reason": reason
    }

@tool
def search_knowledge_base(query: str) -> str:
    """Search company knowledge base for policies and information."""
    query_lower = query.lower()
    
    # Direct keyword matching
    for key, value in knowledge_base.items():
        if key in query_lower:
            return value
    
    # Common synonyms and variations
    if any(word in query_lower for word in ["refund", "money back", "return money"]):
        return knowledge_base["refund"]
    if any(word in query_lower for word in ["ship", "delivery", "deliver", "shipping"]):
        return knowledge_base["shipping"]
    if any(word in query_lower for word in ["return", "send back"]):
        return knowledge_base["return"]
    if any(word in query_lower for word in ["warranty", "guarantee", "coverage"]):
        return knowledge_base["warranty"]
    if any(word in query_lower for word in ["pay", "payment", "credit card", "paypal"]):
        return knowledge_base["payment"]
    if any(word in query_lower for word in ["track", "tracking", "where is my order", "order status"]):
        return knowledge_base["tracking"]
    if any(word in query_lower for word in ["cancel", "cancellation"]):
        return knowledge_base["cancel"]
    if any(word in query_lower for word in ["international", "overseas", "abroad"]):
        return knowledge_base["international"]
    if any(word in query_lower for word in ["support", "help", "contact", "hours"]):
        return knowledge_base["support"]
    if any(word in query_lower for word in ["security", "password", "account safety", "2fa"]):
        return knowledge_base["security"]
    
    return "I don't have specific information about that in our knowledge base. Please contact our support team at support@example.com or call 1-800-SUPPORT for assistance."

# Initialize LangChain Agent
tools = [lookup_order, process_refund, search_knowledge_base]

# Create prompt template
prompt = ChatPromptTemplate.from_messages([
    ("system", """You are a helpful customer service agent. You have access to tools to:
1. Look up order information
2. Process refunds
3. Search the knowledge base for policies

When a customer asks about an order, use the lookup_order tool.
When a customer wants a refund, first look up the order, then process the refund.
When a customer asks about policies, use the search_knowledge_base tool.

Be friendly, helpful, and professional. Always explain what you're doing."""),
    MessagesPlaceholder(variable_name="chat_history"),
    ("human", "{input}"),
    MessagesPlaceholder(variable_name="agent_scratchpad"),
])

# Initialize LLM
llm = ChatAnthropic(
    model="claude-sonnet-4-5-20250929",
    temperature=0,
    api_key=os.getenv("ANTHROPIC_API_KEY")
)

# Create agent
agent = create_tool_calling_agent(llm=llm, tools=tools, prompt=prompt)

# Request/Response models
class ChatRequest(BaseModel):
    message: str
    session_id: str = "default"

class ChatResponse(BaseModel):
    response: str
    agent_steps: List[Dict] = []
    tools_used: List[str] = []

# API Endpoints
@app.get("/health")
def health_check():
    return {"status": "healthy", "agent": "ready"}

@app.get("/status")
def status():
    return {
        "tools_available": [tool.name for tool in tools],
        "active_sessions": len(sessions),
        "llm": "claude-sonnet-4-5-20250929"
    }

@app.post("/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    try:
        # Get or create session memory
        if request.session_id not in sessions:
            sessions[request.session_id] = ConversationBufferMemory(
                memory_key="chat_history",
                return_messages=True
            )
        
        memory = sessions[request.session_id]
        
        # Create executor with memory
        executor = AgentExecutor(
            agent=agent,
            tools=tools,
            memory=memory,
            verbose=True,
            return_intermediate_steps=True,
            max_iterations=5,
            handle_parsing_errors=True
        )
        
        # Execute agent
        result = executor.invoke({"input": request.message})
        
        # Extract response text - handle both string and list formats
        output = result.get("output", "")
        
        # Handle different output formats from new LangChain versions
        response_text = ""
        if isinstance(output, list):
            # Extract text from list of message chunks
            for item in output:
                if isinstance(item, dict):
                    if "text" in item:
                        response_text += item["text"]
                    elif "content" in item:
                        response_text += str(item["content"])
                elif isinstance(item, str):
                    response_text += item
                else:
                    response_text += str(item)
        elif isinstance(output, str):
            response_text = output
        else:
            response_text = str(output)
        
        # Fallback if response is empty
        if not response_text or response_text.strip() == "":
            response_text = "I processed your request but encountered an issue formatting the response. Please try again."
        
        # Extract agent steps and tools used
        agent_steps = []
        tools_used = []
        
        if "intermediate_steps" in result:
            for step in result["intermediate_steps"]:
                action, output = step
                agent_steps.append({
                    "tool": action.tool,
                    "input": str(action.tool_input),
                    "output": str(output)
                })
                if action.tool not in tools_used:
                    tools_used.append(action.tool)
        
        return ChatResponse(
            response=response_text,
            agent_steps=agent_steps,
            tools_used=tools_used
        )
        
    except Exception as e:
        print(f"Error: {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

@app.delete("/session/{session_id}")
def clear_session(session_id: str):
    if session_id in sessions:
        del sessions[session_id]
        return {"status": "cleared", "session_id": session_id}
    return {"status": "not_found", "session_id": session_id}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)