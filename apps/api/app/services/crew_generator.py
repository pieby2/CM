from crewai import Agent, Task, Crew, Process
from pydantic import BaseModel, Field
from typing import List
from langchain_google_genai import ChatGoogleGenerativeAI
from app.config import settings

class GeneratedFlashcard(BaseModel):
    front: str
    back: str
    card_type: str
    concept: str
    difficulty: float

class FlashcardList(BaseModel):
    cards: List[GeneratedFlashcard]

def generate_cards_with_crew(content: str, subject: str = "general", num_cards: int = 10) -> List[dict]:
    """Generates flashcards using a CrewAI multi-agent pipeline."""
    
    # Initialize the LLM (Gemini 2.0 Flash)
    llm = ChatGoogleGenerativeAI(
        model="gemini-2.0-flash", 
        google_api_key=settings.gemini_api_key,
        temperature=0.4
    )

    # Agent 1: The Researcher
    researcher = Agent(
        role='Subject Matter Expert',
        goal=f'Analyze the text and extract the {num_cards} most critical concepts, definitions, and relationships.',
        backstory='You are a world-class academic researcher who can distill complex texts into their core components perfectly.',
        verbose=True,
        allow_delegation=False,
        llm=llm
    )

    # Agent 2: The Educator (Writer)
    educator = Agent(
        role='Expert Educator',
        goal='Create clear, pedagogically sound flashcards from the extracted concepts.',
        backstory='You are a master teacher known for creating flashcards that are easy to understand but rigorously test knowledge. You use diverse formats like definitions, relationships, worked examples, edge cases, and cloze deletions.',
        verbose=True,
        allow_delegation=False,
        llm=llm
    )

    # Agent 3: The QA Reviewer
    reviewer = Agent(
        role='Quality Assurance Reviewer',
        goal='Review the flashcards for accuracy against the original text, ensuring no hallucinations and perfect JSON formatting.',
        backstory='You are a strict QA engineer who ensures educational material is 100% accurate and formatted perfectly according to the schema.',
        verbose=True,
        allow_delegation=False,
        llm=llm
    )

    # Task 1: Extract Concepts
    task1 = Task(
        description=f'Analyze the following text and list the top {num_cards} concepts that must be learned:\n\n{content[:6000]}\n\nSubject: {subject}',
        expected_output=f'A detailed list of the {num_cards} most important concepts, including their definitions and why they matter.',
        agent=researcher
    )

    # Task 2: Create Flashcards
    task2 = Task(
        description=f'Using the concepts identified, write exactly {num_cards} flashcards. Each card must have a front (question/cloze), back (answer), type, concept (1-3 words), and difficulty (0.5 to 3.0).',
        expected_output='A raw list of flashcard drafts with front, back, type, concept, and difficulty.',
        agent=educator
    )

    # Task 3: Review and Output JSON
    task3 = Task(
        description='Review the flashcards created by the Educator. Ensure they are accurate based on the original text. Output ONLY a valid JSON array of objects matching the FlashcardList schema. Do not include markdown code blocks, just the JSON.',
        expected_output='A JSON array of flashcard objects.',
        agent=reviewer,
        output_json=FlashcardList
    )

    # Assemble the Crew
    crew = Crew(
        agents=[researcher, educator, reviewer],
        tasks=[task1, task2, task3],
        process=Process.sequential,
        verbose=True
    )

    # Execute
    result = crew.kickoff()
    
    # Result should be a dict conforming to FlashcardList if output_json is respected.
    # CrewAI sometimes returns a CrewOutput object, we can extract the dict from the final task output.
    if hasattr(result, 'pydantic') and result.pydantic:
        cards_dict = result.pydantic.model_dump()
        return cards_dict.get('cards', [])
    elif hasattr(result, 'json_dict') and result.json_dict:
        return result.json_dict.get('cards', [])
    else:
        # Fallback parsing if CrewAI didn't map it automatically
        import json
        import re
        raw_text = str(result)
        cleaned = re.sub(r"^```(?:json)?\s*", "", raw_text.strip())
        cleaned = re.sub(r"\s*```$", "", cleaned)
        data = json.loads(cleaned)
        if isinstance(data, dict) and 'cards' in data:
            return data['cards']
        return data
