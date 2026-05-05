from typing import Any, Dict, List
from sqlalchemy.orm import Session
from sqlalchemy import select
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_google_genai import ChatGoogleGenerativeAI, GoogleGenerativeAIEmbeddings
from langchain.agents import AgentExecutor, create_tool_calling_agent
from langchain_core.tools import tool
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from app.config import settings
from app.models import Section, AgentSession

# Define the models globally to avoid re-initialization
llm = ChatGoogleGenerativeAI(
    model="gemini-2.0-flash", 
    google_api_key=settings.gemini_api_key,
    temperature=0.3
)
embeddings = GoogleGenerativeAIEmbeddings(
    model="models/text-embedding-004", 
    google_api_key=settings.gemini_api_key
)

@tool
def search_document(query: str, deck_id: str, db_session: Session = None) -> str:
    """Searches the user's document for relevant information based on the query. 
    Use this to answer questions about the study material."""
    if not db_session:
        return "Database session unavailable."
    
    query_embedding = embeddings.embed_query(query)
    # Using pgvector cosine distance `<=>`
    # We join with ImportJob/Deck if needed, but for simplicity, we can search all user sections or specific ones.
    # For now, we will search all sections for the user or just the closest 3 sections overall.
    # We can pass deck_id or just query all sections globally for a simple RAG.
    
    stmt = (
        select(Section)
        .order_by(Section.embedding.cosine_distance(query_embedding))
        .limit(3)
    )
    results = db_session.execute(stmt).scalars().all()
    
    if not results:
        return "No relevant information found in the document."
    
    context = []
    for r in results:
        context.append(f"Title: {r.title}\nContent: {r.content}")
        
    return "\n\n---\n\n".join(context)

tools = [search_document]

prompt = ChatPromptTemplate.from_messages([
    ("system", "You are a helpful AI Tutor. Your goal is to help the user understand their study material. "
               "You can search their documents to answer questions. Be encouraging and concise."),
    MessagesPlaceholder(variable_name="chat_history"),
    ("human", "{input}"),
    MessagesPlaceholder(variable_name="agent_scratchpad"),
])

# Create the agent
agent = create_tool_calling_agent(llm, tools, prompt)
agent_executor = AgentExecutor(agent=agent, tools=tools, verbose=True)


def handle_chat(db: Session, user_id: str, session_id: str | None, message: str) -> dict:
    # Get or create session
    if session_id:
        agent_session = db.get(AgentSession, session_id)
        if not agent_session or agent_session.user_id != user_id:
            agent_session = None
    else:
        agent_session = None

    if not agent_session:
        agent_session = AgentSession(user_id=user_id, history=[])
        db.add(agent_session)
        db.commit()
        db.refresh(agent_session)

    # Convert history to LangChain messages
    chat_history = []
    for msg in agent_session.history:
        if msg["role"] == "user":
            chat_history.append(HumanMessage(content=msg["content"]))
        elif msg["role"] == "assistant":
            chat_history.append(AIMessage(content=msg["content"]))

    # We need to bind the db_session to the tool. 
    # A cleaner way in LangChain is to use a Tool object or just pass it through somehow.
    # For simplicity here, we can set a global or thread-local, but the safest is to pass it in `tool_kwargs`.
    # As `search_document` expects db_session, we can use `partial` or `StructuredTool`.
    
    # Let's recreate the tool with the db session injected
    from langchain_core.tools import StructuredTool
    
    def search_doc_with_db(query: str, deck_id: str = "") -> str:
        return search_document.invoke({"query": query, "deck_id": deck_id, "db_session": db})
    
    injected_tool = StructuredTool.from_function(
        func=search_doc_with_db,
        name="search_document",
        description="Searches the user's document for relevant information based on the query. Use this to answer questions about the study material."
    )
    
    injected_tools = [injected_tool]
    
    agent = create_tool_calling_agent(llm, injected_tools, prompt)
    agent_executor = AgentExecutor(agent=agent, tools=injected_tools, verbose=False)

    response = agent_executor.invoke({
        "input": message,
        "chat_history": chat_history
    })

    # Update history
    new_history = list(agent_session.history)
    new_history.append({"role": "user", "content": message})
    new_history.append({"role": "assistant", "content": response["output"]})
    agent_session.history = new_history
    db.commit()

    return {
        "session_id": agent_session.id,
        "reply": response["output"]
    }
