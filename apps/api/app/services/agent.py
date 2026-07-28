from sqlalchemy.orm import Session
from sqlalchemy import select
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.tools import StructuredTool
from langchain.agents import AgentExecutor, create_tool_calling_agent
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from app.config import settings
from app.models import Section, AgentSession

# Prompt template is pure config — safe to define at module level (no API calls)
TUTOR_PROMPT = ChatPromptTemplate.from_messages([
    ("system", "You are a helpful AI Tutor. Your goal is to help the user understand their study material. "
               "You can search their documents to answer questions. Be encouraging and concise."),
    MessagesPlaceholder(variable_name="chat_history"),
    ("human", "{input}"),
    MessagesPlaceholder(variable_name="agent_scratchpad"),
])


def _get_llm():
    """Lazily initialize the LLM so it's only built when first needed, not at import time."""
    from langchain_google_genai import ChatGoogleGenerativeAI
    return ChatGoogleGenerativeAI(
        model="gemini-2.0-flash",
        google_api_key=settings.gemini_api_key,
        temperature=0.3,
    )


def _get_embeddings():
    """Lazily initialize the embeddings model."""
    from langchain_google_genai import GoogleGenerativeAIEmbeddings
    return GoogleGenerativeAIEmbeddings(
        model="models/text-embedding-004",
        google_api_key=settings.gemini_api_key,
    )


def _build_search_tool(db: Session) -> StructuredTool:
    """Build a document search tool with the DB session injected at call time."""
    embeddings = _get_embeddings()

    def search_document(query: str, deck_id: str = "") -> str:
        """Searches the user's document for relevant information based on the query.
        Use this to answer questions about the study material."""
        query_embedding = embeddings.embed_query(query)
        
        # In-memory cosine similarity (since we dropped pgvector)
        def cosine_similarity(v1: list[float], v2: list[float]) -> float:
            if not v1 or not v2: return -1.0
            dot_product = sum(a * b for a, b in zip(v1, v2))
            mag1 = sum(a * a for a in v1) ** 0.5
            mag2 = sum(b * b for b in v2) ** 0.5
            if mag1 * mag2 == 0: return 0.0
            return dot_product / (mag1 * mag2)
            
        all_sections = db.execute(select(Section)).scalars().all()
        scored_sections = []
        for section in all_sections:
            if section.embedding:
                score = cosine_similarity(query_embedding, section.embedding)
                scored_sections.append((score, section))
                
        scored_sections.sort(key=lambda x: x[0], reverse=True)
        results = [s for score, s in scored_sections[:3]]

        if not results:
            return "No relevant information found in the document."

        return "\n\n---\n\n".join(f"Title: {r.title}\nContent: {r.content}" for r in results)

    return StructuredTool.from_function(
        func=search_document,
        name="search_document",
        description="Searches the user's document for relevant information based on the query. Use this to answer questions about the study material.",
    )


def handle_chat(db: Session, user_id: str, session_id: str | None, message: str) -> dict:
    # Get or create session
    agent_session = None
    if session_id:
        agent_session = db.get(AgentSession, session_id)
        if agent_session and agent_session.user_id != user_id:
            agent_session = None

    if not agent_session:
        agent_session = AgentSession(user_id=user_id, history=[])
        db.add(agent_session)
        db.commit()
        db.refresh(agent_session)

    # Convert persisted history to LangChain message objects
    chat_history = []
    for msg in agent_session.history:
        if msg["role"] == "user":
            chat_history.append(HumanMessage(content=msg["content"]))
        elif msg["role"] == "assistant":
            chat_history.append(AIMessage(content=msg["content"]))

    # Build agent lazily — only initialized on first real request
    llm = _get_llm()
    tools = [_build_search_tool(db)]
    agent = create_tool_calling_agent(llm, tools, TUTOR_PROMPT)
    executor = AgentExecutor(agent=agent, tools=tools, verbose=False)

    response = executor.invoke({
        "input": message,
        "chat_history": chat_history,
    })

    # Persist conversation turn
    new_history = list(agent_session.history)
    new_history.append({"role": "user", "content": message})
    new_history.append({"role": "assistant", "content": response["output"]})
    agent_session.history = new_history
    db.commit()

    return {
        "session_id": agent_session.id,
        "reply": response["output"],
    }
