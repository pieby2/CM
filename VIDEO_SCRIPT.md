# Video Walkthrough Script — Cue Math Flashcard Engine
**Target Duration: 3-4 minutes**

---

## SCENE 1: Intro (0:00 - 0:20)
**Show:** The landing page of Cue Math (https://cue-math-web.onrender.com)

**Say:**
> "Hey! So I built a smart flashcard engine called Cue Math for Problem 1. The idea is simple — you drop in any PDF, and the AI turns it into a full deck of flashcards that actually helps you remember things long term. Let me walk you through how it works."

---

## SCENE 2: Login & Dashboard (0:20 - 0:35)
**Show:** Type the email `student@cue.local`, press Enter. Show the Review tab (empty state).

**Say:**
> "So first you log in. Right now I have no decks, so let's create one by importing a PDF."

---

## SCENE 3: PDF Import — The Core Feature (0:35 - 1:30)
**Show:**
1. Click the **"Import PDF"** tab
2. Click the **Groq API Key** field at the top right — show that the key is already saved
3. Drag and drop the `sample_math.pdf` file (or click to browse)
4. Type deck name: `Quadratic Equations`
5. Set subject to: `mathematics`
6. Click **"Upload & Generate Cards"**
7. Wait for the progress steps: uploading → extracting → chunking → generating → done

**Say:**
> "I go to Import PDF, drop in my math chapter — this one is about quadratic equations. I give it a name, set the subject, and hit generate. Behind the scenes, the app uses PyMuPDF to extract text and images from the PDF. Then it chunks the content into sections and sends each section to the Groq AI — which is Llama 3 — and the AI creates a mix of card types: definitions, relationships, worked examples, edge cases, and even fill-in-the-blank cloze cards. It's not just shallow questions, it tries to cover the material like a good teacher would."

---

## SCENE 4: Review Session — Spaced Repetition (1:30 - 2:30)
**Show:**
1. Switch to the **"Review"** tab
2. Select the new deck from the dropdown
3. Click **"Start Review"**
4. Show the flashcard front — point out the **card type badge** (e.g., "definition", "cloze")
5. If a **cloze card** shows up, point out the `[...]` blank on the front
6. Press **Space** to flip (or click)
7. Show the answer — if cloze, point out the highlighted revealed word
8. Click **"💡 Need a mnemonic?"** button — wait for AI to generate a memory trick
9. Show the mnemonic result in the dashed box
10. Grade the card as **"Good"** or **"Hard"**
11. Do 2-3 more cards quickly
12. Point out the **progress bar** at the top filling up
13. If possible, finish the session to show **confetti animation** 🎉

**Say:**
> "Now I go to Review and start studying. Notice each card has a type badge — this one is a definition, this one is a cloze card where the answer is hidden as a blank. I press Space to flip it. Now here's a cool feature — if I'm struggling, I can click 'Need a mnemonic?' and the AI instantly generates a creative memory trick for that exact card. 
>
> When I grade a card, I pick Again, Hard, Good, or Easy. The app uses the SM-2 spaced repetition algorithm — cards I know well fade away, and cards I struggle with keep showing up more often. After 5+ reviews, it even switches to a Half-Life Regression model that predicts exactly when I'm about to forget something. And when I finish — confetti! Small thing, but it makes studying less boring."

---

## SCENE 5: Chat with your Deck (2:30 - 3:10)
**Show:**
1. Click the **"Chat"** tab
2. The selected deck name should appear in the header
3. Type a question like: `"What happens when the discriminant is negative?"`
4. Press Send, wait for the AI response
5. Ask one more: `"Can you give me a real world example of quadratic equations?"`

**Say:**
> "Now this is one of my favourite features — Chat with your Deck. Instead of just flipping cards, I can actually ask questions about the material. The AI reads all the flashcards in my deck as context and answers based on what I've studied. So if I forget something during a study session, I just ask. It's like having a tutor sitting next to you."

---

## SCENE 6: Deck Management & Stats (3:10 - 3:30)
**Show:**
1. Click **"Decks"** tab
2. Show the deck cards with names and dates
3. Show the **search bar** — type something to filter
4. Go back to **Review** tab — point out the **stats panel** (New, Learning, Mature counts)
5. Point out the **Weak Concepts** section and the **Streak** counter

**Say:**
> "For deck management, I can search, browse, and delete decks. On the review page I also track my progress — how many cards are new, which ones I'm still learning, and which I've mastered. It also shows my weak concepts so I know exactly where to focus. And there's a streak counter to keep me motivated."

---

## SCENE 7: Add Card Manually (3:30 - 3:40)
**Show:**
1. Click **"Add Card"** tab
2. Quickly type a front and back
3. Show the **type dropdown** — scroll to show "cloze" is an option
4. Click **"Add Card"**

**Say:**
> "I can also add cards manually if I want. I just type the question and answer, pick a type — including cloze for fill-in-the-blank — and add it to any deck."

---

## SCENE 8: Architecture Wrap-up (3:40 - 4:00)
**Show:** Either keep the app visible or briefly switch to your code editor showing the project structure

**Say:**
> "Quick note on architecture — this is a React frontend with a FastAPI backend. The AI uses Groq's Llama 3 models. For spaced repetition I built a hybrid system — SM-2 for new cards and a separate Half-Life Regression microservice for mature cards. The whole thing is deployed on Render with a Postgres database and Redis cache. If I had more time, I'd add mobile support and let students share their decks with each other. Thanks for watching!"

---

## TIPS FOR RECORDING:
- **Use Loom** (free, easiest) — install the Chrome extension
- Keep your browser **full screen** and **zoomed in slightly** so text is readable
- **Don't rush** — pause a moment on each feature so the viewer can see it
- If the AI takes a few seconds to respond (Groq rate limits), just say "it's thinking..." naturally
- **Pre-load** the PDF in your Downloads so drag-and-drop is smooth
- Have your **API key already saved** so you don't waste time on setup
