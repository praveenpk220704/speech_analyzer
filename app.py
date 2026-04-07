import streamlit as st
import speech_recognition as sr
import concurrent.futures
import time
import re
import random
from gtts import gTTS
import io

# ==========================================
# RANDOM FACTS DATABASE (PARAGRAPHS)
# ==========================================
FACTS = [
    "Beneath the floor of almost every forest lies a massive, complex underground system known as a mycelial network. These microscopic fungal threads connect the roots of trees and plants, allowing them to communicate and share vital resources. Through this hidden biological highway, older, more established trees can actually send nutrients to younger saplings that are struggling to survive in the shade. Some scientists even refer to this incredible, cooperative ecosystem as the Earth's natural internet.",
    "When a massive star runs out of fuel and collapses under its own gravity, it can sometimes leave behind a fascinating remnant called a neutron star. These celestial objects are incredibly dense, packing a mass greater than our entire sun into a sphere no larger than a typical city. To put that into perspective, if you could somehow scoop up just one teaspoon of material from a neutron star and bring it to Earth, it would weigh roughly six billion tons, which is about the same weight as a mountain.",
    "The Great Pyramid of Giza is not only a marvel of ancient architecture, but also a testament to incredible mathematical precision. Constructed over four thousand years ago without the use of modern machinery or computers, the base of the pyramid is remarkably level, with an error margin of less than an inch across its massive footprint. Furthermore, its four sides are almost perfectly aligned with the true compass points of north, south, east, and west, a feat that continues to baffle historians and engineers to this day.",
    "The Mariana Trench, located in the western Pacific Ocean, is the deepest oceanic trench on our planet. Its lowest known point, known as the Challenger Deep, plunges nearly eleven kilometers beneath the surface of the water. If you were to take Mount Everest, the tallest mountain on Earth, and drop it directly into the Challenger Deep, its peak would still be completely submerged under more than a mile of water. The pressure at the bottom is so immense that it is equivalent to having fifty jumbo jets piled on top of you.",
    "When we enjoy a delicious meal, we often give all the credit to our taste buds, but the reality is much more complex. Scientists estimate that up to eighty percent of what we perceive as flavor actually comes from our sense of smell. As you chew, volatile compounds travel up through the back of your throat and into your nasal cavity. If you pinch your nose while eating a gourmet jelly bean, you will likely only taste basic sweetness or sourness, completely missing the complex fruit or spice flavors until you let go."
]

# Initialize session state for the text area
if "practice_text" not in st.session_state:
    st.session_state.practice_text = FACTS[0]

def change_fact():
    """Selects a random fact that is different from the current one."""
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

    tts = gTTS(text=speech_text, lang='en', slow=False)
    audio_buffer = io.BytesIO()
    tts.write_to_fp(audio_buffer)
    audio_buffer.seek(0)
    return audio_buffer

# ==========================================
# MODEL 1: Pronunciation Evaluation
# ==========================================
def nlp_pronunciation_model(expected, spoken):
    expected_words = re.sub(r'[^\w\s]', '', expected).lower().split()
    spoken_words = re.sub(r'[^\w\s]', '', spoken).lower().split()
    
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
        suggestions.append(f"⚠️ Try to pause instead of using these filler words: **{', '.join(detected_fillers)}**.")
    else:
        suggestions.append("✅ Great job avoiding filler words!")
        
    if wpm < 100:
        suggestions.append(f"🐢 Your pace is {wpm} WPM. Try to speak a little faster.")
    elif wpm > 160:
        suggestions.append(f"🐇 Your pace is {wpm} WPM. Slow down slightly for clarity.")
    else:
        suggestions.append(f"✅ Your pace of {wpm} WPM is excellent and conversational.")
        
    return detected_fillers, wpm, suggestions

# ==========================================
# CONCURRENT EXECUTION ENGINE
# ==========================================
def run_models_concurrently(mode, expected_text, spoken_text, audio_duration):
    with concurrent.futures.ThreadPoolExecutor() as executor:
        future_habits = executor.submit(nlp_habit_model, spoken_text, audio_duration)
        
        if mode == "Practice":
            future_pronunciation = executor.submit(nlp_pronunciation_model, expected_text, spoken_text)
            pron_score, pron_suggestions = future_pronunciation.result()
        else:
            pron_score, pron_suggestions = None, []
            
        fillers, wpm, habit_suggestions = future_habits.result()
        
    return {
        "score": pron_score,
        "pronunciation_feedback": pron_suggestions,
        "fillers": fillers,
        "wpm": wpm,
        "habit_feedback": habit_suggestions
    }

# ==========================================
# AUDIO CAPTURE MODULE
# ==========================================
def record_audio(timeout_limit=10, phrase_limit=60):
    recognizer = sr.Recognizer()
    with sr.Microphone() as source:
        with st.spinner("🎙️ Listening... Speak now."):
            recognizer.adjust_for_ambient_noise(source, duration=0.5)
            start_time = time.time()
            try:
                # Increased phrase_limit to 60 to allow time to read a full paragraph
                audio = recognizer.listen(source, timeout=timeout_limit, phrase_time_limit=phrase_limit)
                duration = time.time() - start_time
                st.toast("Transcribing speech...", icon="⏳")
                text = recognizer.recognize_google(audio)
                return text, duration, None
            except sr.WaitTimeoutError:
                return None, 0, "Listening timed out. No speech detected."
            except sr.UnknownValueError:
                return None, 0, "Could not understand the audio. Please speak clearly."
            except Exception as e:
                return None, 0, f"Microphone error: {e}"

# ==========================================
# STREAMLIT USER INTERFACE
# ==========================================
st.set_page_config(page_title="AI Speaking Coach", page_icon="🎙️", layout="centered")

st.markdown("<h1 style='text-align: center; color: #4A90E2;'>🗣️ AI Speaking Coach</h1>", unsafe_allow_html=True)
st.markdown("<p style='text-align: center; color: gray;'>Practice reading scripts or speak freely to get AI feedback on your communication habits.</p>", unsafe_allow_html=True)
st.divider()

# Mode Selection
mode = st.radio("Choose your practice mode:", ["Practice a Script", "Freestyle Speaking"], horizontal=True)

with st.container(border=True):
    if mode == "Practice a Script":
        col1, col2 = st.columns([3, 1])
        with col1:
            st.markdown("### 📝 Practice Mode")
        with col2:
            st.button("🎲 Random Fact", on_click=change_fact, use_container_width=True)
            
        expected_text = st.text_area("Read this paragraph out loud:", 
                                     value=st.session_state.practice_text,
                                     height=250,  # Increased height to fit full paragraphs
                                     key="practice_text")
    else:
        st.markdown("### 🎤 Freestyle Mode")
        st.info("In this mode, just talk about any topic! The AI will transcribe your speech and analyze your speaking speed and filler words.")
        expected_text = ""

# Action Button
col_center = st.columns([1, 2, 1])
with col_center[1]:
    start_btn = st.button("🎙️ Start Recording", use_container_width=True, type="primary")

if start_btn:
    if mode == "Practice a Script" and not expected_text.strip():
        st.error("Please enter a sentence to practice first!")
    else:
        # Give 60 seconds total time to allow for the full paragraph reading
        time_limit = 60 
        spoken_text, duration, error = record_audio(phrase_limit=time_limit)
        
        if error:
            st.error(error)
        elif spoken_text:
            st.success("Analysis Complete!")
            
            run_mode = "Practice" if mode == "Practice a Script" else "Freestyle"
            results = run_models_concurrently(run_mode, expected_text, spoken_text, duration)
            
            st.divider()
            st.markdown("<h2 style='text-align: center;'>📊 Performance Report</h2>", unsafe_allow_html=True)
            
            with st.container(border=True):
                if mode == "Practice a Script":
                    st.markdown(f"**🎯 Target Text:** \n_{expected_text}_")
                st.markdown(f"**🗣️ Transcript (What we heard):** \n_{spoken_text}_")
            
            st.markdown("### 📈 Key Metrics")
            if mode == "Practice a Script":
                col1, col2, col3 = st.columns(3)
                with col1:
                    with st.container(border=True):
                        st.metric("Pronunciation Score", f"{results['score']}%")
                with col2:
                    with st.container(border=True):
                        st.metric("Filler Words", len(results['fillers']))
                with col3:
                    with st.container(border=True):
                        st.metric("Speed (WPM)", results['wpm'])
            else:
                col1, col2 = st.columns(2)
                with col1:
                    with st.container(border=True):
                        st.metric("Filler Words Used", len(results['fillers']))
                with col2:
                    with st.container(border=True):
                        st.metric("Speed (WPM)", results['wpm'])

            st.markdown("### 💡 Improvement Suggestions")
            if mode == "Practice a Script":
                sug_col1, sug_col2 = st.columns(2)
                with sug_col1:
                    with st.container(border=True):
                        st.markdown("#### Pronunciation")
                        for suggestion in results['pronunciation_feedback']:
                            st.markdown(f"- {suggestion}")
                with sug_col2:
                    with st.container(border=True):
                        st.markdown("#### Speech Habits")
                        for suggestion in results['habit_feedback']:
                            st.markdown(f"- {suggestion}")
            else:
                with st.container(border=True):
                    st.markdown("#### Speech Habits")
                    for suggestion in results['habit_feedback']:
                        st.markdown(f"- {suggestion}")
            
            st.toast("Generating Voice Feedback...", icon="🔊")
            audio_buffer = generate_audio_feedback(run_mode, 
                                                   results['score'], 
                                                   results['pronunciation_feedback'], 
                                                   results['habit_feedback'])
            
            st.audio(audio_buffer, format="audio/mp3", autoplay=True)
            st.success("🔊 Playing AI Feedback...")   