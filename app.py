import streamlit as st
import speech_recognition as sr
import concurrent.futures
import time
import re
import random
from datetime import datetime, timezone
from gtts import gTTS
import io

# MongoDB helpers (gracefully degrade if DB unavailable)
try:
    from db import save_session, get_recent_sessions, get_aggregate_stats, clear_all_sessions, is_connected
    _DB_ENABLED = True
except Exception:
    _DB_ENABLED = False
    def save_session(d): return False
    def get_recent_sessions(n=10): return []
    def get_aggregate_stats(): return {}
    def clear_all_sessions(): return 0
    def is_connected(): return False

# ==========================================
# WARM PRACTICE PROMPTS
# ==========================================
FACTS = [
    "India recently achieved another major milestone in digital payments through the continued growth of the Unified Payments Interface, commonly known as UPI. It has transformed the way people send and receive money by allowing instant transactions through mobile phones. From small street vendors to large businesses, many people now depend on digital payments in daily life. This development shows how technology can improve financial inclusion, reduce cash dependency, and make transactions faster, safer, and more convenient.",

    "Climate change remains one of the most important global issues in current affairs. Many countries are now focusing on renewable energy sources such as solar, wind, and hydro power to reduce carbon emissions. International discussions continue on how to balance economic growth with environmental protection. This topic is important because it affects weather patterns, agriculture, water resources, and the future quality of life for people around the world.",

    "India’s space research organization, ISRO, continues to earn global attention through its achievements in space exploration. Missions such as Chandrayaan and Aditya-L1 have highlighted the country’s growing strength in science and technology. These missions are not only important for research but also inspire students and young scientists across the nation. Space exploration helps improve communication, weather forecasting, navigation, and our understanding of the universe.",

    "Artificial intelligence is becoming one of the most discussed topics in current affairs and general knowledge. AI is now being used in education, healthcare, banking, transport, and many other sectors. It can help people by improving efficiency, reducing manual work, and supporting decision-making. At the same time, experts are also discussing the ethical use of AI, including privacy, job impact, and the need for responsible development.",

    "The G20 has become an important international forum where major economies discuss global challenges such as trade, inflation, energy security, climate action, and sustainable development. When countries come together in such meetings, they can build stronger cooperation and share solutions to common problems. For students and job seekers, understanding the role of the G20 is useful because it connects economics, politics, diplomacy, and international relations.",

    "The Indian economy is often discussed in general knowledge because it is one of the fastest growing major economies in the world. Growth in sectors such as information technology, manufacturing, agriculture, and services has contributed to national development. Government policies related to startups, infrastructure, digital India, and skill development also play a major role. A strong economy creates employment opportunities and improves the country’s position at the global level.",

    "Cybersecurity has become a major concern in today’s digital world. As more people use the internet for banking, communication, education, and shopping, the risk of cyber attacks has also increased. Governments, companies, and individuals all need to protect their data from hacking, fraud, and online threats. Awareness about strong passwords, safe browsing, and digital privacy is now an essential part of general knowledge.",

    "The importance of renewable energy is increasing across the world as countries try to reduce pollution and dependence on fossil fuels. Solar panels, wind turbines, and electric vehicles are becoming more common in many regions. Renewable energy not only supports environmental protection but also creates new industries and jobs. This topic is important in current affairs because energy policy directly affects development, sustainability, and global cooperation.",

    "The role of education is changing rapidly in the modern world due to digital learning platforms, online courses, and smart classroom technologies. Students today have more access to information than ever before. However, this also brings challenges such as digital divide, screen dependency, and the need for practical skills. Education remains one of the strongest foundations for personal growth, national progress, and social development.",

    "Public health has gained worldwide attention in recent years because strong healthcare systems are necessary for the well-being of society. Governments now focus more on medical infrastructure, vaccination programs, sanitation, nutrition, and disease prevention. Health awareness is not only a medical issue but also a social and economic issue. A healthy population contributes more effectively to national productivity and long-term development."
]

# Initialize session state
if "practice_text" not in st.session_state:
    st.session_state.practice_text = FACTS[0]

def change_fact():
    """Selects a random prompt different from the current one."""
    new_fact = random.choice(FACTS)
    while new_fact == st.session_state.practice_text:
        new_fact = random.choice(FACTS)
    st.session_state.practice_text = new_fact


# ==========================================
# TEXT-TO-SPEECH MODULE
# ==========================================
def generate_audio_feedback(mode, score, pron_suggestions, habit_suggestions):
    speech_text = ""

    if mode == "Practice":
        speech_text += f"Your overall pronunciation score is {score} percent. "
        if pron_suggestions:
            clean_pron = [re.sub(r'\*|✅|⚠️|🐢|🐇', '', s).strip() for s in pron_suggestions]
            speech_text += " ".join(clean_pron) + " "
    else:
        speech_text += "Here is the feedback on your freestyle speech. "

    if habit_suggestions:
        clean_habits = [re.sub(r'\*|✅|⚠️|🐢|🐇|🗣️', '', s).strip() for s in habit_suggestions]
        speech_text += " ".join(clean_habits)

    tts = gTTS(text=speech_text, lang="en", slow=False)
    audio_buffer = io.BytesIO()
    tts.write_to_fp(audio_buffer)
    audio_buffer.seek(0)
    return audio_buffer


# ==========================================
# MODEL 1: Pronunciation Evaluation
# ==========================================
def nlp_pronunciation_model(expected, spoken):
    expected_words = re.sub(r"[^\w\s]", "", expected).lower().split()
    spoken_words = re.sub(r"[^\w\s]", "", spoken).lower().split()

    missing_words = [word for word in expected_words if word not in spoken_words]
    extra_words = [word for word in spoken_words if word not in expected_words]

    total_expected = len(expected_words)
    if total_expected == 0:
        return 0, []

    correct_count = total_expected - len(missing_words)
    score = max(0, int((correct_count / total_expected) * 100))

    suggestions = []
    if missing_words:
        suggestions.append(f"Focus on pronouncing these missing words: **{', '.join(missing_words)}**.")
    if extra_words:
        suggestions.append(f"You added extra words: **{', '.join(extra_words)}**.")
    if score >= 95:
        suggestions.append("✅ Excellent pronunciation accuracy!")

    return score, suggestions


# ==========================================
# MODEL 2: Speech Habit Analysis
# ==========================================
def nlp_habit_model(spoken, duration):
    filler_list = ["um", "uh", "like", "literally", "basically", "actually", "you know"]
    spoken_lower = spoken.lower()

    detected_fillers = []
    for filler in filler_list:
        if spoken_lower.count(filler) > 0:
            detected_fillers.append(filler)

    word_count = len(spoken.split())
    wpm = int((word_count / duration) * 60) if duration > 0 else 0

    suggestions = []
    if detected_fillers:
        suggestions.append(f"⚠️ Try pausing instead of using these filler words: **{', '.join(detected_fillers)}**.")
    else:
        suggestions.append("✅ Great job avoiding filler words!")

    if wpm < 100:
        suggestions.append(f"🐢 Your pace is {wpm} WPM. Try to speak a little faster.")
    elif wpm > 160:
        suggestions.append(f"🐇 Your pace is {wpm} WPM. Slow down slightly for better clarity.")
    else:
        suggestions.append(f"✅ Your pace of {wpm} WPM is clear and conversational.")

    return detected_fillers, wpm, suggestions


# ==========================================
# CONCURRENT EXECUTION ENGINE
# ==========================================
def run_models_concurrently(mode, expected_text, spoken_text, audio_duration):
    with concurrent.futures.ThreadPoolExecutor() as executor:
        future_habits = executor.submit(nlp_habit_model, spoken_text, audio_duration)

        if mode == "Practice":
            future_pronunciation = executor.submit(
                nlp_pronunciation_model, expected_text, spoken_text
            )
            pron_score, pron_suggestions = future_pronunciation.result()
        else:
            pron_score, pron_suggestions = None, []

        fillers, wpm, habit_suggestions = future_habits.result()

    return {
        "score": pron_score,
        "pronunciation_feedback": pron_suggestions,
        "fillers": fillers,
        "wpm": wpm,
        "habit_feedback": habit_suggestions,
    }


# ==========================================
# AUDIO CAPTURE MODULE
# ==========================================
def record_audio(timeout_limit=10, phrase_limit=60):
    recognizer = sr.Recognizer()

    with sr.Microphone() as source:
        with st.spinner("🎙️ Listening... speak naturally."):
            recognizer.adjust_for_ambient_noise(source, duration=0.5)
            start_time = time.time()
            try:
                audio = recognizer.listen(
                    source,
                    timeout=timeout_limit,
                    phrase_time_limit=phrase_limit
                )
                duration = time.time() - start_time
                st.toast("Transcribing your speech...", icon="⏳")
                text = recognizer.recognize_google(audio)
                return text, duration, None
            except sr.WaitTimeoutError:
                return None, 0, "Listening timed out. No speech was detected."
            except sr.UnknownValueError:
                return None, 0, "Could not understand the audio clearly. Please try again."
            except Exception as e:
                return None, 0, f"Microphone error: {e}"


# ==========================================
st.set_page_config(
    page_title="SpeakEasy Coach",
    page_icon="🎙️",
    layout="centered"
)

# ==========================================
# CUSTOM STYLING — CLEAN WHITE / LIGHT REDESIGN
# ==========================================
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&display=swap');

    * { font-family: 'Inter', 'Segoe UI', sans-serif; }

    /* ── Background ── */
    .stApp {
        background: linear-gradient(150deg, #f8f9ff 0%, #eef1fb 40%, #f3f0ff 100%);
        color: #1a1a2e;
        min-height: 100vh;
    }

    .main > div { padding-top: 0.5rem; padding-bottom: 3rem; }

    /* ── Hero ── */
    .hero-wrap {
        background: linear-gradient(135deg, #4f46e5 0%, #7c3aed 50%, #ec4899 100%);
        border-radius: 32px;
        padding: 50px 36px 42px;
        margin-bottom: 30px;
        text-align: center;
        box-shadow: 0 24px 64px rgba(79,70,229,0.30);
        position: relative;
        overflow: hidden;
    }
    .hero-wrap::before {
        content: "";
        position: absolute;
        top: -80px; left: 50%;
        transform: translateX(-50%);
        width: 320px; height: 320px;
        background: radial-gradient(circle, rgba(255,255,255,0.12) 0%, transparent 65%);
        pointer-events: none;
    }
    .hero-wrap::after {
        content: "";
        position: absolute;
        bottom: -40px; right: -40px;
        width: 180px; height: 180px;
        background: radial-gradient(circle, rgba(255,255,255,0.08) 0%, transparent 70%);
        pointer-events: none;
    }

    .hero-pill {
        display: inline-flex;
        align-items: center;
        gap: 6px;
        padding: 6px 18px;
        border-radius: 999px;
        background: rgba(255,255,255,0.18);
        border: 1px solid rgba(255,255,255,0.30);
        color: #fff;
        font-size: 0.78rem;
        font-weight: 700;
        letter-spacing: 0.06em;
        margin-bottom: 20px;
        text-transform: uppercase;
        backdrop-filter: blur(8px);
    }

    .hero-title {
        font-size: 3.2rem;
        font-weight: 900;
        line-height: 1.05;
        margin-bottom: 16px;
        color: #ffffff;
        letter-spacing: -0.02em;
        text-shadow: 0 2px 20px rgba(0,0,0,0.15);
    }

    .hero-sub {
        font-size: 1.08rem;
        color: rgba(255,255,255,0.88);
        line-height: 1.75;
        max-width: 580px;
        margin: 0 auto 28px;
    }

    .hero-stats {
        display: flex;
        justify-content: center;
        gap: 0;
        flex-wrap: wrap;
        border-top: 1px solid rgba(255,255,255,0.18);
        padding-top: 22px;
        margin-top: 4px;
    }
    .hero-stat {
        display: flex;
        flex-direction: column;
        align-items: center;
        gap: 3px;
        padding: 0 28px;
        border-right: 1px solid rgba(255,255,255,0.18);
    }
    .hero-stat:last-child { border-right: none; }
    .hero-stat-val {
        font-size: 1.6rem;
        font-weight: 900;
        color: #ffffff;
    }
    .hero-stat-label {
        font-size: 0.72rem;
        color: rgba(255,255,255,0.70);
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.07em;
    }

    /* ── Mode Selector ── */
    .mode-header {
        font-size: 1.05rem;
        font-weight: 800;
        color: #1a1a2e;
        margin-bottom: 4px;
        letter-spacing: -0.01em;
    }
    .mode-sub {
        color: #64748b;
        font-size: 0.92rem;
        margin-bottom: 14px;
        line-height: 1.55;
    }
    [data-testid="stRadio"] label {
        background: #ffffff !important;
        border: 1.5px solid #e2e8f0 !important;
        border-radius: 14px !important;
        padding: 11px 22px !important;
        font-size: 0.94rem !important;
        font-weight: 600 !important;
        color: #475569 !important;
        transition: all 0.18s ease !important;
        cursor: pointer !important;
        box-shadow: 0 2px 8px rgba(0,0,0,0.05) !important;
    }
    [data-testid="stRadio"] label p,
    [data-testid="stRadio"] label div,
    [data-testid="stRadio"] label span {
        color: #475569 !important;
        font-size: 0.94rem !important;
        font-weight: 600 !important;
    }
    [data-testid="stRadio"] label:hover,
    [data-testid="stRadio"] label:hover p,
    [data-testid="stRadio"] label:hover div,
    [data-testid="stRadio"] label:hover span {
        border-color: #4f46e5 !important;
        color: #4f46e5 !important;
        background: #f5f3ff !important;
        box-shadow: 0 4px 14px rgba(79,70,229,0.14) !important;
    }


    /* ── Cards ── */
    .warm-card {
        background: #ffffff;
        border: 1.5px solid #e8eaf6;
        border-radius: 26px;
        padding: 28px 26px;
        margin-bottom: 22px;
        box-shadow: 0 8px 32px rgba(79,70,229,0.08);
    }
    .warm-card-label {
        font-size: 1.12rem;
        font-weight: 800;
        color: #1a1a2e;
        margin-bottom: 6px;
        display: flex;
        align-items: center;
        gap: 8px;
    }
    .warm-card-note {
        font-size: 0.91rem;
        color: #64748b;
        line-height: 1.65;
        margin-bottom: 18px;
    }

    /* ── Tip box ── */
    .tip-box {
        background: linear-gradient(135deg, #eff6ff, #f5f3ff);
        border: 1.5px solid #bfdbfe;
        border-radius: 16px;
        padding: 13px 18px;
        font-size: 0.91rem;
        color: #3730a3;
        line-height: 1.65;
        margin-bottom: 16px;
        display: flex;
        align-items: flex-start;
        gap: 9px;
    }

    /* ── Textarea ── */
    .stTextArea textarea {
        background: #f8faff !important;
        color: #1a1a2e !important;
        border-radius: 20px !important;
        border: 1.5px solid #e2e8f0 !important;
        font-size: 1rem !important;
        line-height: 1.85 !important;
        padding: 18px !important;
        transition: border-color 0.2s, box-shadow 0.2s !important;
    }
    .stTextArea textarea:focus {
        border-color: #4f46e5 !important;
        box-shadow: 0 0 0 3px rgba(79,70,229,0.10) !important;
        background: #ffffff !important;
    }
    .stTextArea label { color: #374151 !important; font-weight: 600 !important; font-size: 0.92rem !important; }

    /* ── Primary button ── */
    .stButton > button {
        border-radius: 999px !important;
        border: none !important;
        padding: 0.84rem 1.8rem !important;
        font-weight: 700 !important;
        font-size: 0.97rem !important;
        background: linear-gradient(90deg, #4f46e5, #7c3aed) !important;
        color: white !important;
        box-shadow: 0 10px 28px rgba(79,70,229,0.30) !important;
        transition: all 0.22s ease !important;
        letter-spacing: 0.01em !important;
    }
    .stButton > button:hover {
        transform: translateY(-2px) scale(1.015) !important;
        box-shadow: 0 16px 38px rgba(79,70,229,0.42) !important;
    }
    .stButton > button:active {
        transform: translateY(0) scale(0.99) !important;
    }

    /* ── Report header ── */
    .report-header {
        background: linear-gradient(135deg, #f0f4ff 0%, #fdf2ff 100%);
        border: 1.5px solid #e0e7ff;
        border-radius: 26px;
        padding: 28px 28px 22px;
        text-align: center;
        margin-bottom: 24px;
        box-shadow: 0 10px 36px rgba(79,70,229,0.09);
    }
    .report-title {
        font-size: 1.9rem;
        font-weight: 900;
        color: #1a1a2e;
        margin-bottom: 6px;
        letter-spacing: -0.01em;
    }
    .report-sub {
        color: #64748b;
        font-size: 0.95rem;
        line-height: 1.6;
    }

    /* ── Score display ── */
    .score-ring-wrap {
        background: #ffffff;
        border: 1.5px solid #e8eaf6;
        border-radius: 22px;
        padding: 22px 16px;
        text-align: center;
        box-shadow: 0 6px 20px rgba(0,0,0,0.06);
        transition: transform 0.2s;
    }
    .score-ring-wrap:hover { transform: translateY(-3px); }
    .score-number {
        font-size: 3rem;
        font-weight: 900;
        line-height: 1;
        margin-bottom: 4px;
    }
    .score-great  { color: #16a34a; }
    .score-medium { color: #d97706; }
    .score-low    { color: #dc2626; }
    .score-label  {
        font-size: 0.74rem;
        color: #94a3b8;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 0.08em;
        margin-bottom: 4px;
    }
    .score-msg { font-size: 0.83rem; color: #64748b; font-weight: 500; }

    /* ── Transcript card ── */
    .transcript-card {
        background: #ffffff;
        border: 1.5px solid #e8eaf6;
        border-radius: 20px;
        padding: 20px 24px;
        margin-bottom: 12px;
        box-shadow: 0 4px 16px rgba(0,0,0,0.05);
    }
    .transcript-label {
        font-size: 0.75rem;
        font-weight: 800;
        text-transform: uppercase;
        letter-spacing: 0.09em;
        color: #94a3b8;
        margin-bottom: 9px;
    }
    .transcript-text {
        color: #334155;
        font-size: 0.97rem;
        line-height: 1.78;
        font-style: italic;
    }

    /* ── Feedback cards ── */
    .feed-card {
        background: #ffffff;
        border: 1.5px solid #e8eaf6;
        border-radius: 22px;
        padding: 22px 20px;
        box-shadow: 0 6px 22px rgba(0,0,0,0.06);
        height: 100%;
    }
    .feed-card-title {
        font-size: 0.82rem;
        font-weight: 800;
        text-transform: uppercase;
        letter-spacing: 0.09em;
        color: #94a3b8;
        margin-bottom: 14px;
    }
    .feed-item {
        display: flex;
        align-items: flex-start;
        gap: 10px;
        padding: 10px 14px;
        border-radius: 12px;
        background: #f8faff;
        border: 1px solid #eef2ff;
        margin-bottom: 8px;
        font-size: 0.92rem;
        color: #334155;
        line-height: 1.55;
    }
    .feed-item-icon { font-size: 1.05rem; flex-shrink: 0; }

    /* ── Motivational quote ── */
    .motivate-box {
        background: linear-gradient(135deg, #4f46e5, #7c3aed);
        border-radius: 22px;
        padding: 26px 28px;
        text-align: center;
        margin-top: 22px;
        margin-bottom: 10px;
        box-shadow: 0 14px 40px rgba(79,70,229,0.22);
    }
    .motivate-quote {
        font-size: 1.08rem;
        color: rgba(255,255,255,0.92);
        font-style: italic;
        line-height: 1.7;
        margin-bottom: 10px;
    }
    .motivate-author {
        font-size: 0.82rem;
        color: rgba(255,255,255,0.60);
        font-weight: 600;
    }

    /* ── Divider ── */
    .soft-divider {
        border: none;
        border-top: 1.5px solid #e8eaf6;
        margin: 26px 0;
    }

    /* ── Section label ── */
    .section-label {
        font-size: 1rem;
        font-weight: 800;
        color: #1a1a2e;
        margin-bottom: 14px;
        letter-spacing: -0.01em;
    }

    /* ── Footer ── */
    .footer-bar {
        text-align: center;
        padding: 22px 0 10px;
        border-top: 1.5px solid #e8eaf6;
        margin-top: 36px;
    }
    .footer-bar p {
        color: #94a3b8;
        font-size: 0.84rem;
        line-height: 1.6;
        margin: 0;
    }
    .footer-bar span { color: #4f46e5; font-weight: 700; }

    /* hide default streamlit bits */
    #MainMenu, footer, header { visibility: hidden; }
</style>
""", unsafe_allow_html=True)


# ==========================================
# MOTIVATIONAL QUOTES
# ==========================================
QUOTES = [
    ("The human voice is the most perfect instrument of all.", "Arvo Pärt"),
    ("Speak clearly, if you speak at all.", "Oliver Wendell Holmes"),
    ("Words have energy and power with the ability to help, heal, and inspire.", "Unknown"),
    ("Practice is the best of all instructors.", "Publilius Syrus"),
    ("Your voice is your signature — make it memorable.", "Unknown"),
]

# ==========================================
# HERO SECTION
# ==========================================
st.markdown("""
<div class="hero-wrap">
    <div class="hero-pill">✨ Your Personal Speaking Coach</div>
    <div class="hero-title">SpeakEasy Coach</div>
    <div class="hero-sub">
        Practice speaking in a calm, supportive environment.<br>
        Get warm, human-style feedback on how you sound — not just scores, but real insights.
    </div>
    <div class="hero-stats">
        <div class="hero-stat">
            <div class="hero-stat-val">2</div>
            <div class="hero-stat-label">Practice Modes</div>
        </div>
        <div class="hero-stat">
            <div class="hero-stat-val">10</div>
            <div class="hero-stat-label">Curated Prompts</div>
        </div>
        <div class="hero-stat">
            <div class="hero-stat-val">AI</div>
            <div class="hero-stat-label">Powered Feedback</div>
        </div>
        <div class="hero-stat">
            <div class="hero-stat-val">🎙️</div>
            <div class="hero-stat-label">Voice Analysis</div>
        </div>
    </div>
</div>
""", unsafe_allow_html=True)


# ==========================================
# MODE SELECTION
# ==========================================
st.markdown('<div class="mode-header">🎯 How would you like to practice today?</div>', unsafe_allow_html=True)
st.markdown(
    '<div class="mode-sub">Choose guided reading for structured practice, or go freestyle if you want to speak naturally without a script.</div>',
    unsafe_allow_html=True
)

mode = st.radio(
    "practice_mode",
    ["📖  Practice a Script", "🎤  Freestyle Speaking"],
    horizontal=True,
    label_visibility="collapsed"
)
mode = mode.split("  ", 1)[-1].strip()  # strip emoji prefix for logic


# ==========================================
# PRACTICE / FREESTYLE CARD
# ==========================================

if mode == "Practice a Script":
    col1, col2 = st.columns([3, 1])
    with col1:
        st.markdown('<div class="warm-card-label">📖 Guided Reading</div>', unsafe_allow_html=True)
        st.markdown('<div class="warm-card-note">Read the prompt below out loud, naturally and confidently — as if you\'re explaining it to a curious friend over coffee.</div>', unsafe_allow_html=True)
    with col2:
        st.write("")
        st.button("🎲 New Prompt", on_click=change_fact, use_container_width=True)

    expected_text = st.text_area(
        "Your reading prompt:",
        value=st.session_state.practice_text,
        height=210,
        key="practice_text",
        help="You can also edit this text to create your own custom prompt!"
    )

else:
    st.markdown('<div class="warm-card-label">🎤 Freestyle Speaking</div>', unsafe_allow_html=True)
    st.markdown('<div class="warm-card-note">No script, no pressure. Talk about your day, a topic you love, a recent experience, or anything at all. Just let the words flow.</div>', unsafe_allow_html=True)
    st.markdown('<div class="tip-box">💡 <span><strong>Tip:</strong> Imagine you\'re chatting with a supportive friend. Breathe naturally, take your time, and trust your voice.</span></div>', unsafe_allow_html=True)
    expected_text = ""



# ==========================================
# START BUTTON
# ==========================================
st.write("")
col_l, col_m, col_r = st.columns([1, 1.8, 1])
with col_m:
    start_btn = st.button("🎙️  Start Speaking Now", use_container_width=True)


# ==========================================
# RUN ANALYSIS
# ==========================================
if start_btn:
    if mode == "Practice a Script" and not expected_text.strip():
        st.error("⚠️ Please enter or select a prompt before starting.")
    else:
        spoken_text, duration, error = record_audio(phrase_limit=60)

        if error:
            st.error(f"😔 {error}")
        elif spoken_text:
            run_mode = "Practice" if mode == "Practice a Script" else "Freestyle"
            results = run_models_concurrently(run_mode, expected_text, spoken_text, duration)

            # ── Report Header ──
            st.write("")
            st.markdown("""
            <div class="report-header">
                <div class="report-title">🌟 Your Speaking Report</div>
                <div class="report-sub">Here's a warm, honest look at how you did — and gentle nudges for where you can grow.</div>
            </div>
            """, unsafe_allow_html=True)

            # ── Transcripts ──
            if mode == "Practice a Script":
                st.markdown("""
                <div class="transcript-card">
                    <div class="transcript-label">📋 Target Prompt</div>
                    <div class="transcript-text">{}</div>
                </div>
                """.format(expected_text), unsafe_allow_html=True)

            st.markdown("""
            <div class="transcript-card">
                <div class="transcript-label">🗣️ What You Said</div>
                <div class="transcript-text">{}</div>
            </div>
            """.format(spoken_text), unsafe_allow_html=True)

            st.markdown('<hr class="soft-divider">', unsafe_allow_html=True)

            # ── Score display ──
            if mode == "Practice a Script":
                score = results['score']
                score_class = "score-great" if score >= 80 else ("score-medium" if score >= 55 else "score-low")
                score_msg = "Excellent! 🌟" if score >= 80 else ("Good effort! 💪" if score >= 55 else "Keep going! 🌱")

                met_col1, met_col2, met_col3 = st.columns(3)
                with met_col1:
                    st.markdown(f"""
                    <div class="score-ring-wrap">
                        <div class="score-label">Pronunciation</div>
                        <div class="score-number {score_class}">{score}%</div>
                        <div class="score-msg">{score_msg}</div>
                    </div>
                    """, unsafe_allow_html=True)
                with met_col2:
                    filler_count = len(results["fillers"])
                    fc_class = "score-great" if filler_count == 0 else ("score-medium" if filler_count <= 2 else "score-low")
                    fc_msg = "None! 🙌" if filler_count == 0 else f"Used: {', '.join(results['fillers'])}"
                    st.markdown(f"""
                    <div class="score-ring-wrap">
                        <div class="score-label">Filler Words</div>
                        <div class="score-number {fc_class}">{filler_count}</div>
                        <div class="score-msg">{fc_msg}</div>
                    </div>
                    """, unsafe_allow_html=True)
                with met_col3:
                    wpm = results["wpm"]
                    wpm_class = "score-great" if 100 <= wpm <= 160 else "score-medium"
                    wpm_msg = "Great pace! ✅" if 100 <= wpm <= 160 else ("Too slow 🐢" if wpm < 100 else "Too fast 🐇")
                    st.markdown(f"""
                    <div class="score-ring-wrap">
                        <div class="score-label">Words / Min</div>
                        <div class="score-number {wpm_class}">{wpm}</div>
                        <div class="score-msg">{wpm_msg}</div>
                    </div>
                    """, unsafe_allow_html=True)
            else:
                met_col1, met_col2 = st.columns(2)
                with met_col1:
                    filler_count = len(results["fillers"])
                    fc_class = "score-great" if filler_count == 0 else ("score-medium" if filler_count <= 2 else "score-low")
                    fc_msg = "Clean speech! 🙌" if filler_count == 0 else f"Used: {', '.join(results['fillers'])}"
                    st.markdown(f"""
                    <div class="score-ring-wrap">
                        <div class="score-label">Filler Words</div>
                        <div class="score-number {fc_class}">{filler_count}</div>
                        <div class="score-msg">{fc_msg}</div>
                    </div>
                    """, unsafe_allow_html=True)
                with met_col2:
                    wpm = results["wpm"]
                    wpm_class = "score-great" if 100 <= wpm <= 160 else "score-medium"
                    wpm_msg = "Great pace! ✅" if 100 <= wpm <= 160 else ("A bit slow 🐢" if wpm < 100 else "Slow down a little 🐇")
                    st.markdown(f"""
                    <div class="score-ring-wrap">
                        <div class="score-label">Words / Min</div>
                        <div class="score-number {wpm_class}">{wpm}</div>
                        <div class="score-msg">{wpm_msg}</div>
                    </div>
                    """, unsafe_allow_html=True)

            st.markdown('<hr class="soft-divider">', unsafe_allow_html=True)

            # ── Feedback Cards ──
            st.markdown('<div class="section-label">💡 Personalised Feedback</div>', unsafe_allow_html=True)

            def render_feedback_items(items):
                html = ""
                for item in items:
                    icon = "✅" if "✅" in item else ("⚠️" if "⚠️" in item else ("🐢" if "🐢" in item else ("🐇" if "🐇" in item else "💬")))
                    clean = re.sub(r'[✅⚠️🐢🐇🗣️]', '', item).strip()
                    html += f'<div class="feed-item"><span class="feed-item-icon">{icon}</span><span>{clean}</span></div>'
                return html

            if mode == "Practice a Script":
                fc1, fc2 = st.columns(2)
                with fc1:
                    pron_html = render_feedback_items(results["pronunciation_feedback"]) if results["pronunciation_feedback"] else '<div class="feed-item"><span class="feed-item-icon">✅</span><span>Your pronunciation looks solid. Keep it up!</span></div>'
                    st.markdown(f'<div class="feed-card"><div class="feed-card-title">🔤 Pronunciation</div>{pron_html}</div>', unsafe_allow_html=True)
                with fc2:
                    habit_html = render_feedback_items(results["habit_feedback"]) if results["habit_feedback"] else '<div class="feed-item"><span class="feed-item-icon">✅</span><span>No issues found. Great speech habits!</span></div>'
                    st.markdown(f'<div class="feed-card"><div class="feed-card-title">🧠 Speech Habits</div>{habit_html}</div>', unsafe_allow_html=True)
            else:
                habit_html = render_feedback_items(results["habit_feedback"]) if results["habit_feedback"] else '<div class="feed-item"><span class="feed-item-icon">✅</span><span>No issues found. Great speech habits!</span></div>'
                st.markdown(f'<div class="feed-card"><div class="feed-card-title">🧠 Speech Habits</div>{habit_html}</div>', unsafe_allow_html=True)

            # ── Motivational Quote ──
            quote_text, quote_author = random.choice(QUOTES)
            st.markdown(f"""
            <div class="motivate-box">
                <div class="motivate-quote">"{quote_text}"</div>
                <div class="motivate-author">— {quote_author}</div>
            </div>
            """, unsafe_allow_html=True)

            # ── Voice Feedback ──
            st.write("")
            st.toast("Generating your voice feedback...", icon="🔊")
            audio_buffer = generate_audio_feedback(
                run_mode,
                results["score"],
                results["pronunciation_feedback"],
                results["habit_feedback"]
            )
            st.audio(audio_buffer, format="audio/mp3", autoplay=True)
            st.success("🔊 Voice feedback is ready — listen above!")

            # ── Persist to MongoDB ──
            session_doc = {
                "mode":        run_mode,
                "spoken_text": spoken_text,
                "expected_text": expected_text if run_mode == "Practice" else "",
                "score":       int(results["score"]) if results["score"] is not None else None,
                "filler_words": results["fillers"],
                "filler_count": len(results["fillers"]),
                "wpm":          int(results["wpm"]),
            }
            if save_session(session_doc):
                st.toast("Session saved to database", icon="💾")


# ==========================================
# PROGRESS DASHBOARD
# ==========================================
st.markdown("""
<style>
    /* ── Dashboard styles ── */
    .dash-wrap {
        background: #ffffff;
        border: 1.5px solid #e8eaf6;
        border-radius: 26px;
        padding: 28px 26px 24px;
        margin-top: 28px;
        box-shadow: 0 8px 32px rgba(79,70,229,0.08);
    }
    .dash-title {
        font-size: 1.15rem;
        font-weight: 800;
        color: #1a1a2e;
        margin-bottom: 20px;
        letter-spacing: -0.01em;
    }
    .stat-grid {
        display: flex;
        gap: 14px;
        flex-wrap: wrap;
        margin-bottom: 22px;
    }
    .stat-tile {
        flex: 1;
        min-width: 130px;
        background: linear-gradient(135deg, #f0f4ff, #f5f3ff);
        border: 1.5px solid #e0e7ff;
        border-radius: 18px;
        padding: 18px 14px;
        text-align: center;
    }
    .stat-tile-val {
        font-size: 2rem;
        font-weight: 900;
        color: #4f46e5;
        line-height: 1;
        margin-bottom: 4px;
    }
    .stat-tile-label {
        font-size: 0.72rem;
        font-weight: 700;
        text-transform: uppercase;
        letter-spacing: 0.08em;
        color: #94a3b8;
    }
    .history-table {
        width: 100%;
        border-collapse: collapse;
        font-size: 0.88rem;
    }
    .history-table th {
        background: #f8faff;
        color: #64748b;
        font-weight: 700;
        font-size: 0.75rem;
        text-transform: uppercase;
        letter-spacing: 0.07em;
        padding: 10px 14px;
        border-bottom: 1.5px solid #e8eaf6;
        text-align: left;
    }
    .history-table td {
        padding: 11px 14px;
        border-bottom: 1px solid #f1f5f9;
        color: #334155;
        vertical-align: middle;
    }
    .history-table tr:last-child td { border-bottom: none; }
    .history-table tr:hover td { background: #f8faff; }
    .badge-practice { background: #eff6ff; color: #3b82f6; padding: 2px 9px; border-radius: 999px; font-size: 0.78rem; font-weight: 700; }
    .badge-freestyle { background: #f0fdf4; color: #16a34a; padding: 2px 9px; border-radius: 999px; font-size: 0.78rem; font-weight: 700; }
    .db-status-on  { color: #16a34a; font-size: 0.8rem; font-weight: 600; display: flex; align-items: center; gap: 5px; margin-bottom: 16px; }
    .db-status-off { color: #dc2626; font-size: 0.8rem; font-weight: 600; display: flex; align-items: center; gap: 5px; margin-bottom: 16px; }
</style>
""", unsafe_allow_html=True)

with st.expander("📊 Progress Dashboard — View Your History", expanded=False):
    db_ok = is_connected()

    stats = get_aggregate_stats()
    total      = stats.get("total", 0)
    avg_score  = stats.get("avg_score")
    avg_wpm    = stats.get("avg_wpm", 0)
    avg_filler = stats.get("avg_fillers", 0)

    score_disp  = f"{avg_score}%"  if avg_score is not None else "—"
    wpm_disp    = f"{avg_wpm}"     if total else "—"
    filler_disp = f"{avg_filler}"  if total else "—"

    st.markdown(f"""
    <div class="stat-grid">
        <div class="stat-tile">
            <div class="stat-tile-val">{total}</div>
            <div class="stat-tile-label">Total Sessions</div>
        </div>
        <div class="stat-tile">
            <div class="stat-tile-val">{score_disp}</div>
            <div class="stat-tile-label">Avg Pronunciation</div>
        </div>
        <div class="stat-tile">
            <div class="stat-tile-val">{wpm_disp}</div>
            <div class="stat-tile-label">Avg WPM</div>
        </div>
        <div class="stat-tile">
            <div class="stat-tile-val">{filler_disp}</div>
            <div class="stat-tile-label">Avg Fillers</div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    sessions = get_recent_sessions(10)
    if sessions:
        st.markdown('<div style="font-size:0.85rem; font-weight:700; color:#64748b; margin-bottom:10px;">Recent Sessions (latest 10)</div>', unsafe_allow_html=True)
        rows = ""
        for s in sessions:
            ts = s.get("timestamp")
            if isinstance(ts, datetime):
                date_str = ts.strftime("%d %b %Y, %I:%M %p")
            else:
                date_str = "—"
            mode_val  = s.get("mode", "—")
            badge = "badge-practice" if mode_val == "Practice" else "badge-freestyle"
            score_val  = f"{s['score']}%" if s.get("score") is not None else "—"
            wpm_val    = s.get("wpm", "—")
            filler_val = s.get("filler_count", 0)
            fillers    = ", ".join(s.get("filler_words", [])) if s.get("filler_words") else "None"
            rows += f"""
            <tr>
                <td>{date_str}</td>
                <td><span class="{badge}">{mode_val}</span></td>
                <td><strong>{score_val}</strong></td>
                <td>{wpm_val}</td>
                <td>{filler_val} &nbsp;<span style="color:#94a3b8;font-size:0.8rem;">({fillers})</span></td>
            </tr>"""
        st.markdown(f"""
        <table class="history-table">
            <thead>
                <tr>
                    <th>Date &amp; Time</th>
                    <th>Mode</th>
                    <th>Score</th>
                    <th>WPM</th>
                    <th>Fillers</th>
                </tr>
            </thead>
            <tbody>{rows}</tbody>
        </table>
        """, unsafe_allow_html=True)
    else:
        st.markdown("""
        <div style="text-align:center; padding:28px; color:#94a3b8; font-size:0.93rem;">
            🎙️ No sessions yet — complete your first practice to see history here!
        </div>
        """, unsafe_allow_html=True)

    st.write("")
    if total > 0:
        col_clr1, col_clr2, col_clr3 = st.columns([1, 1.2, 1])
        with col_clr2:
            if st.button("🗑️  Clear All History", use_container_width=True):
                n = clear_all_sessions()
                st.success(f"Cleared {n} session(s) from the database.")
                st.rerun()


# ==========================================
# FOOTER
# ==========================================
st.markdown("""
<div class="footer-bar">
    <p>Built with ❤️ to help you speak with <span>clarity, confidence, and calm</span> — one session at a time.</p>
    <p style="margin-top:6px; font-size:0.78rem;">SpeakEasy Coach • Powered by Google Speech Recognition & MongoDB</p>
</div>
""", unsafe_allow_html=True)