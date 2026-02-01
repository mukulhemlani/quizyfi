from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import random, re, time
import warnings
import os

# ---------- WIKIPEDIA SETUP ----------

try:
    import wikipedia
    from bs4 import GuessedAtParserWarning
    warnings.filterwarnings("ignore", category=GuessedAtParserWarning)
    WIKI = True
except Exception:
    WIKI = False

# ---------- APP ----------

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

rooms = {}

# ---------- MODELS ----------

class CreateRoom(BaseModel):
    topic: str
    count: int

class JoinRoom(BaseModel):
    room: str
    name: str

class Submit(BaseModel):
    room: str
    name: str
    answer: str | None

# ---------- HELPERS ----------

def clean(text: str) -> str:
    text = re.sub(r"\([^)]*\)", "", text)
    text = re.sub(r"[^a-zA-Z0-9. ]", " ", text)
    return re.sub(r"\s+", " ", text).strip()

def wiki_text(topic: str) -> str:
    if not WIKI:
        return ""
    try:
        wikipedia.set_lang("en")
        return wikipedia.page(topic, auto_suggest=True).content[:40000]
    except Exception:
        try:
            return wikipedia.summary(topic, sentences=200)
        except Exception:
            return ""

def extract_concepts(text: str):
    words = text.split()
    concepts = []

    for w in words:
        if w and w[0].isupper() and len(w) > 4 and w not in concepts:
            concepts.append(w)

    if len(concepts) < 6:
        for w in words:
            if len(w) > 7 and w not in concepts:
                concepts.append(w)

    return concepts[:40]

def generate_mcqs(topic: str, count: int):
    text = clean(wiki_text(topic))
    sentences = [s.strip() for s in text.split(".") if 8 <= len(s.split()) <= 25]

    if not sentences:
        sentences = [
            f"{topic} is an important concept in computer science",
            f"{topic} is widely used in modern systems",
            f"{topic} plays a major role in engineering",
            f"{topic} is studied extensively in academia",
        ]

    concepts = extract_concepts(text)
    if len(concepts) < 4:
        concepts = ["Algorithm", "Model", "System", "Data", "Process"]

    quiz, used = [], set()

    while len(quiz) < count:
        s = random.choice(sentences)
        valid = [c for c in concepts if c in s and c not in used]

        if not valid:
            continue

        ans = valid[0]
        used.add(ans)

        distractors = [c for c in concepts if c != ans]
        if len(distractors) < 3:
            continue

        options = random.sample(distractors, 3) + [ans]
        random.shuffle(options)

        quiz.append({
            "q": s.replace(ans, "_____") + "?",
            "options": options,
            "answer": ans
        })

    return quiz

# ---------- ROUTES ----------

@app.post("/create-room")
def create_room(data: CreateRoom):
    code = ''.join(random.choices("ABCDEFGHJKMNPQRSTUVWXYZ23456789", k=5))
    rooms[code] = {
        "quiz": generate_mcqs(data.topic, data.count),
        "students": {},
        "current": 0,
        "started": False,
        "ended": False,
        "duration": 30,
        "start_time": None
    }
    return {"room": code}

@app.post("/join-room")
def join_room(data: JoinRoom):
    if data.room not in rooms:
        return {"error": "Invalid room"}

    rooms[data.room]["students"][data.name] = {
        "score": 0,
        "answered": False,
        "times": [],
        "answers": [],
        "q_start": None
    }
    return {"ok": True}

@app.post("/start/{room}")
def start_quiz(room: str):
    r = rooms.get(room)
    if not r:
        return {"error": "Invalid room"}

    r["started"] = True
    r["start_time"] = time.time()

    for s in r["students"].values():
        s["q_start"] = time.time()

    return {"ok": True}

@app.post("/submit")
def submit(data: Submit):
    r = rooms.get(data.room)
    if not r or data.name not in r["students"]:
        return {"error": "Invalid submission"}

    s = r["students"][data.name]

    if s["answered"]:
        return {"ok": True}

    q = r["quiz"][r["current"]]
    elapsed = int(time.time() - s["q_start"])

    s["times"].append(elapsed)
    s["answers"].append({
        "question": q["q"],
        "selected": data.answer,
        "correct": q["answer"],
        "is_correct": data.answer == q["answer"]
    })

    if data.answer == q["answer"]:
        s["score"] += 1

    s["answered"] = True
    return {"ok": True}

@app.get("/state/{room}")
def state(room: str):
    r = rooms.get(room)
    if not r:
        return {"error": "Invalid room"}

    leaderboard = sorted(
        [{
            "name": name,
            "score": s["score"],
            "total_time": sum(s["times"]),
            "answers": s["answers"]
        } for name, s in r["students"].items()],
        key=lambda x: (-x["score"], x["total_time"])
    )

    if r["ended"]:
        return {"ended": True, "leaderboard": leaderboard}

    if not r["started"]:
        return {
            "started": False,
            "students": list(r["students"].keys())
        }

    elapsed = int(time.time() - r["start_time"])
    remaining = r["duration"] - elapsed

    if remaining <= 0:
        q = r["quiz"][r["current"]]

        for s in r["students"].values():
            if not s["answered"]:
                s["times"].append(r["duration"])
                s["answers"].append({
                    "question": q["q"],
                    "selected": None,
                    "correct": q["answer"],
                    "is_correct": False
                })

            s["answered"] = False
            s["q_start"] = time.time()

        r["current"] += 1

        if r["current"] >= len(r["quiz"]):
            r["ended"] = True
            return {"ended": True, "leaderboard": leaderboard}

        r["start_time"] = time.time()
        remaining = r["duration"]

    q = r["quiz"][r["current"]]

    return {
        "started": True,
        "question": q["q"],
        "options": q["options"],
        "remaining": remaining,
        "qno": r["current"] + 1,
        "total": len(r["quiz"]),
        "leaderboard": leaderboard
    }

# ---------- PRACTICE SESSION ----------

@app.post("/practice")
def practice(data: CreateRoom):
    quiz = generate_mcqs(data.topic, data.count)
    return {"quiz": quiz}
