# Project Write-Up: The Flashcard Engine (Cue Math)

**Problem Picked:** Problem 1 - The Flashcard Engine

Hello! I am very excited to share my project for the Flashcard Engine problem. I chose this problem because I always struggle with reading notes passively, and I wanted to build something that actually forces students to remember things long-term.

## 1. What I built and the problem I picked
I picked Problem 1: The Flashcard Engine. I built **Cue Math**, a full-stack web application using React for the front-end and FastAPI for the back-end.

Instead of just scraping text from a PDF, my app makes a smart deck. A student can upload a PDF (like math notes or a history chapter). Then the app uses `PyMuPDF` to extract the text and even the images from the pages. I send this to Groq AI (Llama 3 models) to generate very good flashcards. 

It does not just make simple definition cards. It makes:
- **Relationship cards**
- **Edge case cards**
- **Step-by-step worked example cards**
- **"Fill in the blank" (cloze) cards** 

Sometimes it even puts images from the PDF directly on the flashcard!

For studying, I implemented a spaced repetition system. It uses the SM-2 algorithm for new cards. But when you review a card many times (more than 5), it sends data to my custom Half-Life Regression (HLR) microservice. This predicts your exact memory decay so it shows the card exactly when you are about to forget it. Also, to make it fun and not boring, I added 3D flipping animations, keyboard shortcuts, and confetti when you finish a session.

## 2. Key decisions and tradeoffs I made
* **Two Schedulers Instead of One:** I decided to use SM-2 for new cards and HLR for mature cards. The tradeoff is it is more complex to build two systems, but HLR needs a lot of data to work well. SM-2 is better for fresh cards.
* **Microservice for HLR:** I put the HLR model in its own FastAPI server instead of the main API. This was a tradeoff. It means I have to manage two servers, but it is much better because machine learning models use a lot of memory. If it crashes, the main app still works and just falls back to SM-2.
* **Using Groq API:** I used Groq because it is very, very fast. The tradeoff is they have strict rate limits on the free tier (15 requests per minute). I had to write a batching script that pauses for 4.5 seconds between chunks so the upload does not fail.

## 3. What I would improve or add with more time
If I had more time, I would like to build a native mobile app version maybe using React Native. Students study best when they are on the bus or waiting in line, so a phone app is very important.

Also, I want to add an **"Anki Export" button**. Many medical and law students already dedicate their life to Anki. If I let them export my AI decks to Anki format, they would use my app every day. Lastly, I want to add a community page where students can publish their best decks for other people to search and download.

## 4. Any interesting challenges I hit and how I solved them
**Challenge 1: Extracting Images from PDFs**
One really big challenge was extracting images from the PDF. PDFs are very messy. I tried to use standard libraries but they only give me text. So I had to dig deep into `PyMuPDF` to find the image coordinates, save them to my local `/storage` folder, and then put special markdown tags like `![Image_1](/api/storage/...)` into the text. Then, I wrote logic that checks if the text has an image. If it does, my code automatically switches over to the special `llama-3.2-90b-vision-preview` model, encodes the image as base64, and sends it to the AI so the AI can test the student on the diagram.

**Challenge 2: Making the UI less boring**
Flashcards are usually just black text on white screen. So I added a feature called **"Chat with your Deck"** where you can message a chatbot to explain things if you are confused. And I added a **"💡 Need a mnemonic?"** button that you can press when you grade a card "Hard", and the AI makes up a funny story to help you remember it.
