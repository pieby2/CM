import re
import requests
from bs4 import BeautifulSoup
from youtube_transcript_api import YouTubeTranscriptApi
from app.services.pdf_pipeline import SectionDraft, chunk_lines_into_sections, ExtractedLine

class WebProcessingError(Exception):
    pass

def extract_youtube_video_id(url: str) -> str | None:
    # Match standard youtube.com and youtu.be URLs
    match = re.search(r"(?:v=|\/)([0-9A-Za-z_-]{11}).*", url)
    return match.group(1) if match else None

def extract_youtube_transcript(url: str) -> str:
    video_id = extract_youtube_video_id(url)
    if not video_id:
        raise WebProcessingError("Invalid YouTube URL")
    
    try:
        transcript_list = YouTubeTranscriptApi.get_transcript(video_id)
        text = " ".join([item['text'] for item in transcript_list])
        return text.replace('\n', ' ')
    except Exception as e:
        raise WebProcessingError(f"Could not extract transcript: {str(e)}")

def extract_article_text(url: str) -> str:
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
        response = requests.get(url, headers=headers, timeout=10)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Remove scripts, styles, and nav elements
        for element in soup(["script", "style", "nav", "footer", "header"]):
            element.decompose()
            
        text = soup.get_text(separator='\n')
        # Clean up whitespace
        lines = (line.strip() for line in text.splitlines())
        chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
        text = '\n'.join(chunk for chunk in chunks if chunk)
        
        return text
    except Exception as e:
        raise WebProcessingError(f"Could not extract article: {str(e)}")

def process_url_into_sections(url: str, min_chars: int = 700, max_chars: int = 1800) -> list[SectionDraft]:
    if "youtube.com" in url or "youtu.be" in url:
        text = extract_youtube_transcript(url)
        title = "YouTube Video Transcript"
    else:
        text = extract_article_text(url)
        title = "Web Article"
        
    if not text.strip():
        raise WebProcessingError("No text extracted from URL")
        
    # Convert text to dummy ExtractedLines to reuse the chunking logic
    lines = []
    for idx, line in enumerate(text.split('\n')):
        if line.strip():
            lines.append(ExtractedLine(page_number=1, text=line.strip(), font_size=12.0, is_bold=False))
            
    sections = chunk_lines_into_sections(lines, min_section_chars=min_chars, max_section_chars=max_chars)
    
    # If the chunker didn't preserve our title, let's inject it
    for i, sec in enumerate(sections):
        if sec.title == "Section 1" or sec.title == "Introduction":
            sec.title = f"{title} (Part {i+1})"
            
    return sections
