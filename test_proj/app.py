# Adventure Game
import os
# os.environ['SDL_VIDEODRIVER'] = 'X11'  # Use native macOS window system
# os.environ['PYGAME_HIDE_SUPPORT_PROMPT'] = "hide"

import pygame
from pygame.locals import *
from OpenGL.GL import *
from OpenGL.GLU import *
import math
import numpy as np
import sys
import textwrap
from openai import OpenAI
from dotenv import load_dotenv
import time
import os
import tempfile
import io
from pygame import mixer

# new
import pyaudio
import asyncio
import websockets
import json
import base64
import ssl
import queue
import threading
import speech_recognition as sr

# Load environment variables
load_dotenv()
# Ensure OpenAI API Key is loaded
api_key =os.getenv('OPENAI_API_KEY')
if not api_key:
    print("[OpenAI] API key not found. Please set OPENAI_API_KEY in your .env file.")
    sys.exit(1)
client = OpenAI(api_key=api_key)
print("[OpenAI] API key loaded successfully.")

# Initialize Pygame with macOS specific settings
pygame.init()

display = (800, 600)
pygame.display.gl_set_attribute(pygame.GL_CONTEXT_MAJOR_VERSION, 2)
pygame.display.gl_set_attribute(pygame.GL_CONTEXT_MINOR_VERSION, 1)
pygame.display.set_mode(display, DOUBLEBUF|OPENGL)
screen = pygame.display.get_surface()

# Set up the camera and perspective
glEnable(GL_DEPTH_TEST)
glMatrixMode(GL_PROJECTION)
glLoadIdentity()
gluPerspective(45, (display[0]/display[1]), 0.1, 50.0)
glMatrixMode(GL_MODELVIEW)

# Set up basic lighting
glEnable(GL_LIGHTING)
glEnable(GL_LIGHT0)
glLightfv(GL_LIGHT0, GL_POSITION, [0, 5, 5, 1])
glLightfv(GL_LIGHT0, GL_AMBIENT, [0.5, 0.5, 0.5, 1])
glLightfv(GL_LIGHT0, GL_DIFFUSE, [1.0, 1.0, 1.0, 1])

# Enable blending for transparency
glEnable(GL_BLEND)
glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)

# Initial camera position
glTranslatef(0.0, 0.0, -5)

# Constants
WINDOW_WIDTH = 800
WINDOW_HEIGHT = 600
TILE_SIZE = 32
FPS = 60

# Colors
BLACK = (0, 0, 0)
WHITE = (255, 255, 255)
BLUE = (0, 0, 255)
GREEN = (0, 255, 0)
BROWN = (139, 69, 19)
RED = (255, 0, 0)
GRAY = (128, 128, 128)

# Game map
GAME_MAP = [
    "WWWWWWWWWWWWWWWWWWWW",
    "W..................W",
    "W..................W",
    "W........N.........W",
    "W..................W",
    "W..................W",
    "W..................W",
    "W....P.............W",
    "W..................W",
    "W..................W",
    "W..................W",
    "W..................W",
    "WWWWWWWWWWWWWWWWWWWW"
]

# Add these constants near the other constants
TITLE = "Venture Builder AI"
SUBTITLE = "Our Digital Employees"
MENU_BG_COLOR = (0, 0, 0)  # Black background
MENU_TEXT_COLOR = (0, 255, 0)  # Matrix-style green
MENU_HIGHLIGHT_COLOR = (0, 200, 0)  # Slightly darker green for effects

def draw_cube():
    vertices = [
        # Front face
        [-0.5, -0.5,  0.5],
        [ 0.5, -0.5,  0.5],
        [ 0.5,  0.5,  0.5],
        [-0.5,  0.5,  0.5],
        # Back face
        [-0.5, -0.5, -0.5],
        [-0.5,  0.5, -0.5],
        [ 0.5,  0.5, -0.5],
        [ 0.5, -0.5, -0.5],
    ]
    
    surfaces = [
        [0, 1, 2, 3],  # Front
        [3, 2, 6, 5],  # Top
        [0, 3, 5, 4],  # Left
        [1, 7, 6, 2],  # Right
        [4, 5, 6, 7],  # Back
        [0, 4, 7, 1],  # Bottom
    ]
    
    glBegin(GL_QUADS)
    for surface in surfaces:
        glNormal3f(0, 0, 1)  # Simple normal for lighting
        for vertex in surface:
            glVertex3fv(vertices[vertex])
    glEnd()

def draw_sphere(radius, slices, stacks):
    for i in range(stacks):
        lat0 = math.pi * (-0.5 + float(i) / stacks)
        z0 = math.sin(lat0)
        zr0 = math.cos(lat0)
        
        lat1 = math.pi * (-0.5 + float(i + 1) / stacks)
        z1 = math.sin(lat1)
        zr1 = math.cos(lat1)
        
        glBegin(GL_QUAD_STRIP)
        for j in range(slices + 1):
            lng = 2 * math.pi * float(j) / slices
            x = math.cos(lng)
            y = math.sin(lng)
            
            glNormal3f(x * zr0, y * zr0, z0)
            glVertex3f(x * zr0 * radius, y * zr0 * radius, z0 * radius)
            glNormal3f(x * zr1, y * zr1, z1)
            glVertex3f(x * zr1 * radius, y * zr1 * radius, z1 * radius)
        glEnd()

class DialogueSystem:
    def __init__(self):
        self.active = False
        self.user_input = ""
        # self.speech_input_active = True # Replaced by background listening
        try:
            pygame.font.init()
            self.font = pygame.font.Font(None, 24)
            print("[DialogueSystem] Font loaded successfully")
        except Exception as e:
            print("[DialogueSystem] Font loading failed:", e)
        self.npc_message = ""
        self.input_active = False
        self.last_npc_text = ""     # Track NPC text separately
        self.last_input_text = ""   # Track input text separately
        self.conversation_history = []  # Maintain conversation history

        # Create a surface for the UI
        self.ui_surface = pygame.Surface((WINDOW_WIDTH, WINDOW_HEIGHT), pygame.SRCALPHA).convert_alpha()
        self.ui_texture = glGenTextures(1)
        self.current_npc = None  # Track which NPC we're talking to
        self.initial_player_pos = None  # Store initial position when dialogue starts

        # Initialize pygame mixer for audio playback
        if not pygame.mixer.get_init():
            pygame.mixer.init()

        # Initialize STT recognizer
        self.stt_recognizer = sr.Recognizer()
        self.mic = sr.Microphone()
        
        # For interruption handling and background listening
        self.is_npc_speaking = False
        self.npc_speech_interrupted = False
        self.stop_background_listening_thread = None # Function to stop listen_in_background
        self.user_audio_queue = queue.Queue()
        self.recognized_text_queue = queue.Queue()
        self.stt_thread = None
        self.stt_thread_stop_event = threading.Event()

    def _background_listen_callback(self, recognizer, audio):
        """Callback for listen_in_background. Puts audio data on a queue."""
        # This runs in a separate thread (created by speech_recognition)
        # print("[DialogueSystem] Background callback: Speech detected.") # Too verbose
        if self.is_npc_speaking:
            self.npc_speech_interrupted = True # Signal interruption
            pygame.mixer.music.stop() # Immediately stop music
            print("[DialogueSystem] Interruption detected! NPC speech stopped.") # Keep this important one
        self.user_audio_queue.put(audio)

    def _stt_processing_thread_func(self):
        """Processes audio from user_audio_queue, converts to text, puts on recognized_text_queue."""
        # print("[DialogueSystem] STT processing thread started.") # Too verbose
        while not self.stt_thread_stop_event.is_set():
            try:
                audio = self.user_audio_queue.get(timeout=0.5) # Timeout to check stop_event
            except queue.Empty:
                continue

            if audio is None: # Sentinel to stop thread
                self.user_audio_queue.task_done()
                break

            # print("[DialogueSystem] STT Thread: Processing audio...") # Too verbose
            try:
                text = self.stt_recognizer.recognize_google(audio)
                # print(f"[DialogueSystem] STT Thread: Recognized: {text}") # Too verbose
                self.recognized_text_queue.put(text)
            except sr.UnknownValueError:
                # print("[DialogueSystem] STT Thread: Google Speech Recognition could not understand audio") # Let NPC handle this
                self.recognized_text_queue.put("[AudioNotUnderstood]")
            except sr.RequestError as e:
                print(f"[DialogueSystem] STT Thread: Could not request results from Google; {e}") # Keep error
                self.recognized_text_queue.put("[STTError]")
            finally:
                self.user_audio_queue.task_done()
        # print("[DialogueSystem] STT processing thread stopped.") # Too verbose

    def render_text(self, surface, text, x, y):
        max_width = WINDOW_WIDTH - 40
        line_height = 25
        
        words = text.split()
        lines = []
        current_line = []
        current_width = 0
        
        # Always use pure white with full opacity
        text_color = (255, 255, 255)
        
        for word in words:
            word_surface = self.font.render(word + ' ', True, text_color)
            word_width = word_surface.get_width()
            
            if current_width + word_width <= max_width:
                current_line.append(word)
                current_width += word_width
            else:
                lines.append(' '.join(current_line))
                current_line = [word]
                current_width = word_width
        
        if current_line:
            lines.append(' '.join(current_line))
        
        # Render each line in pure white
        for i, line in enumerate(lines):
            text_surface = self.font.render(line, True, (255, 255, 255))  # Force white color
            surface.blit(text_surface, (x, y + i * line_height))
        
        return len(lines) * line_height
    def speak(self, text):
        """Convert text to speech using OpenAI's TTS API."""
        if text is None or not text.strip():
            return
            
        try:
            # Generate speech using OpenAI's API
            # print("[DialogueSystem] Generating speech with OpenAI TTS...") # Too verbose
            
            # Select appropriate voice based on the NPC role
            if self.current_npc == "HR":
                voice = "nova"     # Professional, warm female voice for HR
            elif self.current_npc == "CEO":
                voice = "echo"     # Authoritative, confident voice for CEO
            else:
                voice = "alloy"    # Default neutral voice
            
            response = client.audio.speech.create(
                model="tts-1",
                voice=voice,
                input=text
            )
            
            temp_filename = None # Initialize to ensure it's defined for finally block
            with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as temp_file:
                temp_filename = temp_file.name
                response.stream_to_file(temp_filename)

            # Listener management removed from here; listener should remain active.
            # The _background_listen_callback will handle stopping NPC audio if player speaks.

            self.is_npc_speaking = True
            self.npc_speech_interrupted = False # Reset before speaking this segment

            pygame.mixer.music.load(temp_filename)
            pygame.mixer.music.play()
            # print(f"[DialogueSystem] NPC speaking: {text[:60]}...") # Too verbose

            while pygame.mixer.music.get_busy():
                # We still check npc_speech_interrupted here as a failsafe,
                # in case an interruption was detected just before the listener was stopped.
                if self.npc_speech_interrupted:
                    # pygame.mixer.music.stop() # Already stopped in callback
                    # print("[DialogueSystem] NPC speech interrupted by player's voice (during speak loop).") # Covered by callback
                    break
                pygame.time.Clock().tick(30) # Yield/check frequently

            # if not self.npc_speech_interrupted and not pygame.mixer.music.get_busy():
                # print("[DialogueSystem] NPC finished speaking naturally.") # Too verbose
                
        except Exception as e:
            print(f"[DialogueSystem] TTS Error: {e}") # Keep error
        finally:
            self.is_npc_speaking = False # NPC is no longer trying to speak this segment
            
            # Listener management removed from here. Listener is not stopped/restarted by speak().
            # It's assumed to be continuously running during the conversation.

            if temp_filename and os.path.exists(temp_filename):
                try:
                    os.unlink(temp_filename)
                except Exception as e_unlink:
                    print(f"[DialogueSystem] Error unlinking temp file: {e_unlink}") # Keep error

    def listen(self):
        """Convert user speech to text. (Primarily for non-dialogue use or fallback)"""
        try:
            with self.mic as source:
                print("[DialogueSystem] Listening...")
                audio = self.stt_recognizer.listen(source)
            user_input = self.stt_recognizer.recognize_google(audio)
            print(f"[DialogueSystem] Recognized speech: {user_input}")
            return user_input
        except sr.UnknownValueError:
            print("[DialogueSystem] Could not understand audio")
            return "Sorry, I didn't catch that."
        except sr.RequestError as e:
            print(f"[DialogueSystem] STT service error: {e}")
            return "Sorry, the speech recognition service is unavailable."
        


    def start_conversation(self, npc_role="HR", player_pos=None):
        self.active = True
        self.input_active = True
        self.current_npc = npc_role
        self.initial_player_pos = [player_pos[0], player_pos[1], player_pos[2]] if player_pos else [0, 0.5, 0]
        
        self.is_npc_speaking = False
        self.npc_speech_interrupted = False

        # Clear queues from any previous conversation
        while not self.user_audio_queue.empty(): self.user_audio_queue.get_nowait()
        while not self.recognized_text_queue.empty(): self.recognized_text_queue.get_nowait()

        # Start STT processing thread
        self.stt_thread_stop_event.clear()
        self.stt_thread = threading.Thread(target=self._stt_processing_thread_func, daemon=True)
        self.stt_thread.start()
        # print("[DialogueSystem] STT processing thread started for conversation.") # Too verbose

        # Start background listening
        try:
            with self.mic as source:
                self.stt_recognizer.adjust_for_ambient_noise(source, duration=1.5) # Keep this duration for good ambient noise sampling
            print(f"[DialogueSystem] Initial dynamic energy threshold: {self.stt_recognizer.energy_threshold}")
            self.stt_recognizer.energy_threshold = 1700 # Manually set a higher threshold
            self.stt_recognizer.dynamic_energy_threshold = False # Disable dynamic energy when manually setting
            print(f"[DialogueSystem] Manually set energy threshold to: {self.stt_recognizer.energy_threshold}")
            self.stt_recognizer.pause_threshold = 1.2
            self.stt_recognizer.non_speaking_duration = 0.7


            self.stop_background_listening_thread = self.stt_recognizer.listen_in_background(
                self.mic, self._background_listen_callback
            )
            # print("[DialogueSystem] Background audio listener started for conversation.") # Too verbose
        except Exception as e:
            print(f"[DialogueSystem] Failed to start background listening: {e}") # Keep error
            self.stop_background_listening_thread = None

        print(f"[DialogueSystem] Dialogue started with {npc_role}. Listening for voice input...") # Keep this
        # print("[DialogueSystem] You can also type and press Enter to talk.") # Redundant
        # print("[DialogueSystem] Using OpenAI TTS for voice synthesis.") # Implied

        # Base personality framework for consistent behavior
        base_prompt = """Interaction Framework:
            - Maintain consistent personality throughout conversation
            - Remember previous context within the dialogue
            - Use natural speech patterns with occasional filler words
            - Show emotional intelligence in responses
            - Keep responses concise but meaningful (2-3 sentences)
            - React appropriately to both positive and negative interactions
            """

        if npc_role == "HR":
            system_prompt = f"""{base_prompt}
                You are Sarah Chen, HR Director at Venture Builder AI. Core traits:
                
                PERSONALITY:
                - Warm but professional demeanor
                - Excellent emotional intelligence
                - Strong ethical boundaries
                - Protective of confidential information
                - Quick to offer practical solutions
                
                BACKGROUND:
                - 15 years HR experience in tech
                - Masters in Organizational Psychology
                - Certified in Conflict Resolution
                - Known for fair handling of sensitive issues
                
                SPEAKING STYLE:
                - Uses supportive language: "I understand that..." "Let's explore..."
                - References policies with context: "According to our wellness policy..."
                - Balances empathy with professionalism
                
                CURRENT COMPANY INITIATIVES:
                - AI Talent Development Program
                - Global Remote Work Framework
                - Venture Studio Culture Development
                - Innovation Leadership Track
                
                BEHAVIORAL GUIDELINES:
                - Never disclose confidential information
                - Always offer clear next steps
                - Maintain professional boundaries
                - Document sensitive conversations
                - Escalate serious concerns appropriately"""

        else:  # CEO
            system_prompt = f"""{base_prompt}
                You are Michael Chen, CEO of Venture Builder AI. Core traits:
                
                PERSONALITY:
                - Visionary yet approachable
                - Strategic thinker
                - Passionate about venture building
                - Values transparency
                - Leads by example
                
                BACKGROUND:
                - Founded Venture Builder AI 5 years ago
                - Successfully launched 15+ venture-backed startups
                - MIT Computer Science graduate
                - Pioneer in AI-powered venture building
                
                SPEAKING STYLE:
                - Uses storytelling: "When we launched our first venture..."
                - References data: "Our portfolio metrics show..."
                - Balances optimism with realism
                
                KEY FOCUSES:
                - AI-powered venture creation
                - Portfolio company growth
                - Startup ecosystem development
                - Global venture studio expansion
                
                CURRENT INITIATIVES:
                - AI Venture Studio Framework
                - European Market Entry
                - Startup Success Methodology
                - Founder-in-Residence Program
                
                BEHAVIORAL GUIDELINES:
                - Share venture building vision
                - Highlight portfolio successes
                - Address startup challenges
                - Maintain investor confidence
                - Balance transparency with discretion"""

        # Fix the initial message to be from the NPC to the user
        initial_message = {
            "HR": "Hello! I'm Sarah, the HR Director at Venture Builder AI. How can I assist you today?",
            "CEO": "Hello! I'm Michael, the CEO of Venture Builder AI. What can I do for you today?"
        }

            
        # Set the NPC's greeting as the current message
        self.npc_message = initial_message[npc_role]
        
        # Initialize conversation history with system prompt only
        self.conversation_history = [{
            "role": "system",
            "content": system_prompt
        }]
        
        print(f"[DialogueSystem] Dialogue started with {npc_role}")

    def send_message(self):
        if not self.conversation_history:
            print("[DialogueSystem] No conversation history to send.")
            return

        try:
            response = client.chat.completions.create(
                model="gpt-4-0125-preview",  # or your current model
                messages=self.conversation_history,
                temperature=0.85,
                max_tokens=150,
                response_format={ "type": "text" },
                top_p=0.95,
                frequency_penalty=0.2,
                presence_penalty=0.1
            )
            ai_message = response.choices[0].message.content
            
            # Store the message in conversation history
            self.conversation_history.append({
                "role": "assistant",
                "content": ai_message
            })
            
            # Set the NPC message with white text color
            self.npc_message = ai_message
            
            print(f"[DialogueSystem] NPC says: {self.npc_message}")
            self.speak(self.npc_message)
        except Exception as e:
            self.npc_message = "I apologize, but I'm having trouble connecting to our systems right now."

    def render(self):
        if not self.active:
            return

        self.ui_surface.fill((0, 0, 0, 0))

        if self.active:
            box_height = 200
            box_y = WINDOW_HEIGHT - box_height - 20
            
            # Make the background MUCH darker - almost black with some transparency
            box_color = (0, 0, 0, 230)  # Changed to very dark, mostly opaque background
            pygame.draw.rect(self.ui_surface, box_color, (20, box_y, WINDOW_WIDTH - 40, box_height))
            
            # White border
            pygame.draw.rect(self.ui_surface, (255, 255, 255, 255), (20, box_y, WINDOW_WIDTH - 40, box_height), 2)

            # Render ALL text in pure white (255, 255, 255)
            # Quit instruction
            quit_text_surface = self.font.render("Press Shift+Q to exit", True, (255, 255, 255))
            self.ui_surface.blit(quit_text_surface, (40, box_y + 10))

            # NPC message in white
            if self.npc_message:
                self.render_text(self.ui_surface, self.npc_message, 40, box_y + 40)

            # Input prompt in white
            if self.input_active:
                input_prompt = "> " + self.user_input + "_"
                input_surface = self.font.render(input_prompt, True, (255, 255, 255))
                self.ui_surface.blit(input_surface, (40, box_y + box_height - 40))

        # Convert surface to OpenGL texture
        texture_data = pygame.image.tostring(self.ui_surface, "RGBA", True)

        # Save current OpenGL state
        glPushAttrib(GL_ALL_ATTRIB_BITS)
        glMatrixMode(GL_PROJECTION)
        glPushMatrix()
        glLoadIdentity()
        glOrtho(0, WINDOW_WIDTH, 0, WINDOW_HEIGHT, -1, 1)
        glMatrixMode(GL_MODELVIEW)
        glPushMatrix()
        glLoadIdentity()

        # Setup for 2D rendering
        glDisable(GL_DEPTH_TEST)
        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
        glEnable(GL_TEXTURE_2D)

        # Bind and update texture
        glBindTexture(GL_TEXTURE_2D, self.ui_texture)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR)
        glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA, WINDOW_WIDTH, WINDOW_HEIGHT, 0, GL_RGBA, GL_UNSIGNED_BYTE, texture_data)

        # Draw the UI texture
        glBegin(GL_QUADS)
        glTexCoord2f(0, 0); glVertex2f(0, 0)
        glTexCoord2f(1, 0); glVertex2f(WINDOW_WIDTH, 0)
        glTexCoord2f(1, 1); glVertex2f(WINDOW_WIDTH, WINDOW_HEIGHT)
        glTexCoord2f(0, 1); glVertex2f(0, WINDOW_HEIGHT)
        glEnd()

        # Restore OpenGL state
        glMatrixMode(GL_PROJECTION)
        glPopMatrix()
        glMatrixMode(GL_MODELVIEW)
        glPopMatrix()
        glPopAttrib()

    def handle_input(self, event):
        if not self.active or not self.input_active:
            return

        if event.type == pygame.KEYDOWN:
            # Check for Shift+Q to exit chat
            keys = pygame.key.get_pressed()
            if keys[pygame.K_LSHIFT] and event.key == pygame.K_q:
                self.active = False
                self.input_active = False

                # Stop background audio listener
                if self.stop_background_listening_thread:
                    self.stop_background_listening_thread(wait_for_stop=False) # Non-blocking stop
                    self.stop_background_listening_thread = None

                # Stop STT processing thread
                if self.stt_thread and self.stt_thread.is_alive():
                    self.stt_thread_stop_event.set()
                    self.user_audio_queue.put(None)  # Sentinel to unblock queue.get
                    self.stt_thread.join(timeout=2.0) # Wait for thread to finish
                    if self.stt_thread.is_alive():
                        print("[DialogueSystem] STT thread did not stop in time.")
                    else:
                        print("[DialogueSystem] STT thread joined successfully.")
                self.stt_thread = None
                
                # Clear queues
                while not self.user_audio_queue.empty():
                    try: self.user_audio_queue.get_nowait()
                    except queue.Empty: break
                while not self.recognized_text_queue.empty():
                    try: self.recognized_text_queue.get_nowait()
                    except queue.Empty: break
                print("[DialogueSystem] Queues cleared.")
                
                # Return both the command and the initial position
                return {"command": "move_player_back", "position": self.initial_player_pos}

            # Voice input is now handled by background listener, K_v is removed for active dialogue
            # if event.key == pygame.K_v: (Removed for active dialogue)
            
            if event.key == pygame.K_RETURN:  # Capture text input on Enter key
                if self.user_input.strip(): # Ensure there's input to process
                    self.process_user_input(self.user_input)
                self.user_input = ""  # Reset input after sending
            elif event.key == pygame.K_BACKSPACE:
                self.user_input = self.user_input[:-1]  # Remove last character
            elif event.unicode.isprintable(): # Only add printable characters
                self.user_input += event.unicode  # Append typed character
            return

    def process_user_input(self, user_input):
        """Process user input (text or speech)."""
        if user_input and user_input.strip(): # Check if user_input is not None and not just whitespace
            print(f"[DialogueSystem] User said: {user_input}")
            self.conversation_history.append({"role": "user", "content": user_input})
            self.npc_speech_interrupted = False # Allow NPC to respond now
            self.send_message()

    def generate_npc_response(self, user_input):
        """Simulate AI response (replace with actual API call if needed)."""
        return f"I heard you say: {user_input}. How can I help further?"

    def process_recognized_text(self):
        """Checks queue for recognized text and processes it."""
        if not self.active: # Don't process if dialogue is not active
            return

        try:
            text = self.recognized_text_queue.get_nowait()
            
            # Important: Check the interruption flag *before* processing this text.
            # This tells us if the NPC was speaking *just before* this text was recognized.
            npc_was_speaking_when_interrupted = self.npc_speech_interrupted
            
            if text == "[AudioNotUnderstood]":
                if not npc_was_speaking_when_interrupted: # If NPC was silent, it's a genuine player non-understanding
                    self.process_user_input("Sorry, I didn't quite catch that. Could you please repeat?")
                # If NPC was interrupted and then audio not understood, just wait for clearer player input.
                # Reset the flag so the next valid speech from player is processed.
                self.npc_speech_interrupted = False
            elif text == "[STTError]":
                if not npc_was_speaking_when_interrupted:
                    self.process_user_input("My apologies, I'm having trouble with speech services right now. Could you try typing?")
                # In either case of STTError (interrupted or not), reset the flag.
                self.npc_speech_interrupted = False
            elif text: # Successfully recognized text
                # If we got valid text, it means the interruption (if any) is now being handled.
                # So, clear the flag before sending this new text to the AI.
                self.npc_speech_interrupted = False
                self.process_user_input(text)
            else: # text is None or empty string
                if npc_was_speaking_when_interrupted:
                    # If NPC was interrupted and we got empty text (e.g. silence after interruption),
                    # reset the flag. The player is expected to speak again.
                    self.npc_speech_interrupted = False
            
            self.recognized_text_queue.task_done()

        except queue.Empty:
            pass # No new recognized text
    
class World:
    def __init__(self):
        self.size = 5
        # Define office furniture colors
        self.colors = {
            'floor': (0.76, 0.6, 0.42),  
            'walls': (0.85, 0.85, 0.85),  
            'desk': (0.6, 0.4, 0.2),  # Brown wood
            'chair': (0.2, 0.2, 0.2),  # Dark grey
            'computer': (0.1, 0.1, 0.1),  # Black
            'plant': (0.2, 0.5, 0.2),  # Green
            'partition': (0.3, 0.3, 0.3)  # Darker solid gray for booth walls
        }
        
    def draw_desk(self, x, z, rotation=0):
        glPushMatrix()
        glTranslatef(x, 0, z)  # Start at floor level
        glRotatef(rotation, 0, 1, 0)
        
        # Desk top (reduced size)
        glColor3f(*self.colors['desk'])
        glBegin(GL_QUADS)
        glVertex3f(-0.4, 0.4, -0.3)
        glVertex3f(0.4, 0.4, -0.3)
        glVertex3f(0.4, 0.4, 0.3)
        glVertex3f(-0.4, 0.4, 0.3)
        glEnd()
        
        # Desk legs (adjusted for new height)
        for x_offset, z_offset in [(-0.35, -0.25), (0.35, -0.25), (-0.35, 0.25), (0.35, 0.25)]:
            glBegin(GL_QUADS)
            glVertex3f(x_offset-0.02, 0, z_offset-0.02)
            glVertex3f(x_offset+0.02, 0, z_offset-0.02)
            glVertex3f(x_offset+0.02, 0.4, z_offset-0.02)
            glVertex3f(x_offset-0.02, 0.4, z_offset-0.02)
            glEnd()
        
        # Computer monitor (smaller)
        glColor3f(*self.colors['computer'])
        glTranslatef(-0.15, 0.4, 0)
        glBegin(GL_QUADS)
        glVertex3f(-0.1, 0, -0.05)
        glVertex3f(0.1, 0, -0.05)
        glVertex3f(0.1, 0.2, -0.05)
        glVertex3f(-0.1, 0.2, -0.05)
        glEnd()
        
        glPopMatrix()
    
    def draw_chair(self, x, z, rotation=0):
        glPushMatrix()
        glTranslatef(x, 0, z)
        glRotatef(rotation, 0, 1, 0)
        glColor3f(*self.colors['chair'])
        
        # Seat (lowered and smaller)
        glBegin(GL_QUADS)
        glVertex3f(-0.15, 0.25, -0.15)
        glVertex3f(0.15, 0.25, -0.15)
        glVertex3f(0.15, 0.25, 0.15)
        glVertex3f(-0.15, 0.25, 0.15)
        glEnd()
        
        # Back (adjusted height)
        glBegin(GL_QUADS)
        glVertex3f(-0.15, 0.25, -0.15)
        glVertex3f(0.15, 0.25, -0.15)
        glVertex3f(0.15, 0.5, -0.15)
        glVertex3f(-0.15, 0.5, -0.15)
        glEnd()
        
        # Chair legs (adjusted height)
        for x_offset, z_offset in [(-0.12, -0.12), (0.12, -0.12), (-0.12, 0.12), (0.12, 0.12)]:
            glBegin(GL_QUADS)
            glVertex3f(x_offset-0.02, 0, z_offset-0.02)
            glVertex3f(x_offset+0.02, 0, z_offset-0.02)
            glVertex3f(x_offset+0.02, 0.25, z_offset-0.02)
            glVertex3f(x_offset-0.02, 0.25, z_offset-0.02)
            glEnd()
            
        glPopMatrix()
    
    def draw_plant(self, x, z):
        glPushMatrix()
        glTranslatef(x, 0, z)
        
        # Plant pot (smaller)
        glColor3f(0.4, 0.2, 0.1)  # Brown pot
        pot_radius = 0.1
        pot_height = 0.15
        segments = 8
        
        # Draw the pot sides
        glBegin(GL_QUADS)
        for i in range(segments):
            angle1 = (i / segments) * 2 * math.pi
            angle2 = ((i + 1) / segments) * 2 * math.pi
            x1 = math.cos(angle1) * pot_radius
            z1 = math.sin(angle1) * pot_radius
            x2 = math.cos(angle2) * pot_radius
            z2 = math.sin(angle2) * pot_radius
            glVertex3f(x1, 0, z1)
            glVertex3f(x2, 0, z2)
            glVertex3f(x2, pot_height, z2)
            glVertex3f(x1, pot_height, z1)
        glEnd()
        
        # Plant leaves (smaller)
        glColor3f(*self.colors['plant'])
        glTranslatef(0, pot_height, 0)
        leaf_size = 0.15
        num_leaves = 6
        for i in range(num_leaves):
            angle = (i / num_leaves) * 2 * math.pi
            x = math.cos(angle) * leaf_size
            z = math.sin(angle) * leaf_size
            glBegin(GL_TRIANGLES)
            glVertex3f(0, 0, 0)
            glVertex3f(x, leaf_size, z)
            glVertex3f(z, leaf_size/2, -x)
            glEnd()
        
        glPopMatrix()
        
    def draw(self):
        # Set material properties
        glEnable(GL_COLOR_MATERIAL)
        glColorMaterial(GL_FRONT_AND_BACK, GL_AMBIENT_AND_DIFFUSE)
        
        # Draw floor at Y=0
        glBegin(GL_QUADS)
        glColor3f(*self.colors['floor'])
        glNormal3f(0, 1, 0)
        glVertex3f(-self.size, 0, -self.size)
        glVertex3f(-self.size, 0, self.size)
        glVertex3f(self.size, 0, self.size)
        glVertex3f(self.size, 0, -self.size)
        glEnd()
        
        # Draw walls starting from floor level
        glBegin(GL_QUADS)
        glColor3f(*self.colors['walls'])
        
        # Front wall
        glVertex3f(-self.size, 0, -self.size)
        glVertex3f(self.size, 0, -self.size)
        glVertex3f(self.size, 2, -self.size)
        glVertex3f(-self.size, 2, -self.size)
        
        # Back wall
        glVertex3f(-self.size, 0, self.size)
        glVertex3f(self.size, 0, self.size)
        glVertex3f(self.size, 2, self.size)
        glVertex3f(-self.size, 2, self.size)
        
        # Left wall
        glVertex3f(-self.size, 0, -self.size)
        glVertex3f(-self.size, 0, self.size)
        glVertex3f(-self.size, 2, self.size)
        glVertex3f(-self.size, 2, -self.size)
        
        # Right wall
        glVertex3f(self.size, 0, -self.size)
        glVertex3f(self.size, 0, self.size)
        glVertex3f(self.size, 2, self.size)
        glVertex3f(self.size, 2, -self.size)
        glEnd()
        
        # Draw office furniture in a more realistic arrangement
        # HR Area (left side)
        self.draw_desk(-4, -2, 90)
        self.draw_chair(-3.5, -2, 90)
        self.draw_partition_walls(-4, -2)  # Add booth walls for HR
        
        # CEO Area (right side)
        self.draw_desk(4, 1, -90)
        self.draw_chair(3.5, 1, -90)
        self.draw_partition_walls(4, 1)  # Add booth walls for CEO
        
        # Plants in corners (moved closer to walls)
        self.draw_plant(-4.5, -4.5)
        self.draw_plant(4.5, -4.5)
        self.draw_plant(-4.5, 4.5)
        self.draw_plant(4.5, 4.5)

    def draw_partition_walls(self, x, z):
        """Draw booth partition walls - all surfaces in solid gray"""
        glColor3f(0.3, 0.3, 0.3)  # Solid gray for all walls
        
        # Back wall (smaller and thinner)
        glPushMatrix()
        glTranslatef(x, 0, z)
        glScalef(0.05, 1.0, 1.0)  # Thinner wall, normal height, shorter length
        draw_cube()  # Replace glutSolidCube with draw_cube
        glPopMatrix()
        
        # Side wall (smaller and thinner)
        glPushMatrix()
        glTranslatef(x, 0, z + 0.5)  # Moved closer
        glRotatef(90, 0, 1, 0)
        glScalef(0.05, 1.0, 0.8)  # Thinner wall, normal height, shorter length
        draw_cube()  # Replace glutSolidCube with draw_cube
        glPopMatrix()

class Player:
    def __init__(self):
        self.pos = [0, 0.5, 0]  # Lowered Y position to be just above floor
        self.rot = [0, 0, 0]
        self.speed = 0.3
        self.mouse_sensitivity = 0.5
        
    def move(self, dx, dz):
        # Convert rotation to radians (negative because OpenGL uses clockwise rotation)
        angle = math.radians(-self.rot[1])
        
        # Calculate movement vector
        move_x = (dx * math.cos(angle) + dz * math.sin(angle)) * self.speed
        move_z = (-dx * math.sin(angle) + dz * math.cos(angle)) * self.speed
        
        # Calculate new position
        new_x = self.pos[0] + move_x
        new_z = self.pos[2] + move_z
        
        # Wall collision check (room is 10x10)
        room_limit = 4.5  # Slightly less than room size/2 to prevent wall clipping
        if abs(new_x) < room_limit:
            self.pos[0] = new_x
        if abs(new_z) < room_limit:
            self.pos[2] = new_z

    def update_rotation(self, dx, dy):
        # Multiply mouse movement by sensitivity for faster turning
        self.rot[1] += dx * self.mouse_sensitivity

class NPC:
    def __init__(self, x, y, z, role="HR"):
        self.scale = 0.6  # Make NPCs smaller (about 60% of current size)
        # Position them beside the desks, at ground level
        # Adjust Y position to be half their height (accounting for scale)
        self.pos = [x, 0.65, z]  # This puts their feet on the ground
        self.size = 0.5
        self.role = role
        
        # Enhanced color palette
        self.skin_color = (0.8, 0.7, 0.6)  # Neutral skin tone
        self.hair_color = (0.2, 0.15, 0.1) if role == "HR" else (0.3, 0.3, 0.3)  # Dark brown vs gray
        
        # Updated clothing colors
        if role == "HR":
            self.clothes_primary = (0.8, 0.2, 0.2)    # Bright red
            self.clothes_secondary = (0.6, 0.15, 0.15) # Darker red
        else:  # CEO
            self.clothes_primary = (0.2, 0.3, 0.8)    # Bright blue
            self.clothes_secondary = (0.15, 0.2, 0.6)  # Darker blue

    def draw(self):
        glPushMatrix()
        glTranslatef(self.pos[0], self.pos[1], self.pos[2])
        glScalef(self.scale, self.scale, self.scale)
        
        # Head
        glColor3f(*self.skin_color)
        draw_sphere(0.12, 16, 16)
        
        # Hair (slightly larger than head)
        glColor3f(*self.hair_color)
        glPushMatrix()
        glTranslatef(0, 0.05, 0)  # Slightly above head
        draw_sphere(0.13, 16, 16)
        glPopMatrix()
        
        # Body (torso)
        glColor3f(*self.clothes_primary)
        glPushMatrix()
        glTranslatef(0, -0.3, 0)  # Move down from head
        glScalef(0.3, 0.4, 0.2)   # Make it rectangular
        draw_cube()
        glPopMatrix()
        
        # Arms
        glColor3f(*self.clothes_secondary)
        for x_offset in [-0.2, 0.2]:  # Left and right arms
            glPushMatrix()
            glTranslatef(x_offset, -0.3, 0)
            glScalef(0.1, 0.4, 0.1)
            draw_cube()
            glPopMatrix()
        
        # Legs
        glColor3f(*self.clothes_secondary)
        for x_offset in [-0.1, 0.1]:  # Left and right legs
            glPushMatrix()
            glTranslatef(x_offset, -0.8, 0)
            glScalef(0.1, 0.5, 0.1)
            draw_cube()
            glPopMatrix()
        
        glPopMatrix()

class MenuScreen:
    def __init__(self):
        self.font_large = pygame.font.Font(None, 74)
        self.font_medium = pygame.font.Font(None, 48)
        self.font_small = pygame.font.Font(None, 36)
        self.active = True
        self.start_time = time.time()
        
    def render(self):
        glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
        
        # Create a surface for 2D rendering
        surface = pygame.Surface((WINDOW_WIDTH, WINDOW_HEIGHT), pygame.SRCALPHA)
        
        # Calculate vertical positions
        center_y = WINDOW_HEIGHT // 2
        title_y = center_y - 100
        subtitle_y = center_y - 20
        prompt_y = center_y + 100
        
        # Render title with "typing" effect
        elapsed_time = time.time() - self.start_time
        title_chars = int(min(len(TITLE), elapsed_time * 15))  # Type 15 chars per second
        partial_title = TITLE[:title_chars]
        title_surface = self.font_large.render(partial_title, True, MENU_TEXT_COLOR)
        title_x = (WINDOW_WIDTH - title_surface.get_width()) // 2
        surface.blit(title_surface, (title_x, title_y))
        
        # Render subtitle with fade-in effect
        if elapsed_time > len(TITLE) / 15:  # Start after title is typed
            subtitle_alpha = min(255, int((elapsed_time - len(TITLE) / 15) * 255))
            subtitle_surface = self.font_medium.render(SUBTITLE, True, MENU_TEXT_COLOR)
            subtitle_surface.set_alpha(subtitle_alpha)
            subtitle_x = (WINDOW_WIDTH - subtitle_surface.get_width()) // 2
            surface.blit(subtitle_surface, (subtitle_x, subtitle_y))
        
        # Render "Press ENTER" with blinking effect
        if elapsed_time > (len(TITLE) / 15 + 1):  # Start after subtitle fade
            if int(elapsed_time * 2) % 2:  # Blink every 0.5 seconds
                prompt_text = "Press ENTER to start"
                prompt_surface = self.font_small.render(prompt_text, True, MENU_TEXT_COLOR)
                prompt_x = (WINDOW_WIDTH - prompt_surface.get_width()) // 2
                surface.blit(prompt_surface, (prompt_x, prompt_y))
        
        # Add some retro effects (scanlines)
        for y in range(0, WINDOW_HEIGHT, 4):
            pygame.draw.line(surface, (0, 50, 0), (0, y), (WINDOW_WIDTH, y))
        
        # Convert surface to OpenGL texture
        texture_data = pygame.image.tostring(surface, "RGBA", True)
        
        # Set up orthographic projection for 2D rendering
        glMatrixMode(GL_PROJECTION)
        glLoadIdentity()
        glOrtho(0, WINDOW_WIDTH, WINDOW_HEIGHT, 0, -1, 1)
        glMatrixMode(GL_MODELVIEW)
        glLoadIdentity()

        # Render the texture in OpenGL
        texture = glGenTextures(1)
        glBindTexture(GL_TEXTURE_2D, texture)
        glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA, WINDOW_WIDTH, WINDOW_HEIGHT, 0, GL_RGBA, GL_UNSIGNED_BYTE, texture_data)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR)
        
        # Draw the texture
        glEnable(GL_TEXTURE_2D)
        glBegin(GL_QUADS)
        glTexCoord2f(0, 1); glVertex2f(0, 0)
        glTexCoord2f(1, 1); glVertex2f(WINDOW_WIDTH, 0)
        glTexCoord2f(1, 0); glVertex2f(WINDOW_WIDTH, WINDOW_HEIGHT)
        glTexCoord2f(0, 0); glVertex2f(0, WINDOW_HEIGHT)
        glEnd()
        glDisable(GL_TEXTURE_2D)
        
        # Reset OpenGL state for 3D rendering
        glMatrixMode(GL_PROJECTION)
        glLoadIdentity()
        gluPerspective(45, (WINDOW_WIDTH / WINDOW_HEIGHT), 0.1, 50.0)
        glMatrixMode(GL_MODELVIEW)
        glLoadIdentity()
        glEnable(GL_DEPTH_TEST)

        pygame.display.flip()
     
  
# Modify the Game3D class to include the menu
class Game3D:
    def __init__(self):
        self.menu = MenuScreen()
        self.player = Player()
        self.world = World()
        self.dialogue = DialogueSystem()
        self.hr_npc = NPC(-3.3, 0, -2, "HR")  # Moved beside the desk
        self.ceo_npc = NPC(3.3, 0, 1, "CEO")  # Moved beside the desk
        self.interaction_distance = 2.0
        self.last_interaction_time = 0

    def move_player_away_from_npc(self, npc_pos):
        # Calculate direction vector from NPC to player
        dx = self.player.pos[0] - npc_pos[0]
        dz = self.player.pos[2] - npc_pos[2]
        
        # Normalize the vector
        distance = math.sqrt(dx*dx + dz*dz)
        if distance > 0:
            dx /= distance
            dz /= distance
        
        # Move player back by 3 units
        self.player.pos[0] = npc_pos[0] + (dx * 3)
        self.player.pos[2] = npc_pos[2] + (dz * 3)

    def run(self):
        running = True
        while running:
            if self.menu.active:
                # Menu loop
                for event in pygame.event.get():
                    if event.type == pygame.QUIT:
                        running = False
                    elif event.type == pygame.KEYDOWN:
                        if event.key == pygame.K_RETURN and time.time() - self.menu.start_time > (len(TITLE) / 15 + 1):
                            self.menu.active = False
                            pygame.mouse.set_visible(False)
                            pygame.event.set_grab(True)
                        elif event.key == pygame.K_ESCAPE:
                            running = False
                
                self.menu.render()
            else:
                # Main game loop
                for event in pygame.event.get():
                    if event.type == pygame.QUIT:
                        running = False
                    elif event.type == pygame.KEYDOWN:
                        if event.key == pygame.K_ESCAPE:
                            pygame.mouse.set_visible(True)
                            pygame.event.set_grab(False)
                            running = False
                        
                        # Handle dialogue input and check for exit command
                        if self.dialogue.active:
                            result = self.dialogue.handle_input(event) # Handles text input and Shift+Q
                            if isinstance(result, dict) and result.get("command") == "move_player_back":
                                # Move player away from the current NPC
                                current_npc = self.hr_npc if self.dialogue.current_npc == "HR" else self.ceo_npc
                                self.move_player_away_from_npc(current_npc.pos)
                                # Dialogue becomes inactive from handle_input
                                pygame.mouse.set_visible(False) # Re-hide mouse
                                pygame.event.set_grab(True) # Re-grab mouse
                    elif event.type == pygame.MOUSEMOTION and not self.dialogue.active: # Only allow mouse look if not in dialogue
                        x, y = event.rel
                        self.player.update_rotation(x, y)

                # Process any recognized speech from the background listener
                if self.dialogue.active:
                    self.dialogue.process_recognized_text()

                # Handle keyboard input for movement (keep this blocked during dialogue)
                if not self.dialogue.active:
                    keys = pygame.key.get_pressed()
                    moved_this_frame = False
                    if keys[pygame.K_w]:
                        self.player.move(0, -1)
                        moved_this_frame = True
                    if keys[pygame.K_s]:
                        self.player.move(0, 1)
                        moved_this_frame = True
                    if keys[pygame.K_a]:
                        self.player.move(-1, 0)
                        moved_this_frame = True
                    if keys[pygame.K_d]:
                        self.player.move(1, 0)
                        moved_this_frame = True
                   


                # Check NPC interactions
                current_time = time.time()
                if current_time - self.last_interaction_time > 0.5:  # Cooldown on interactions
                    
                    # Check distance to HR NPC
                    dx_hr = self.player.pos[0] - self.hr_npc.pos[0]
                    dz_hr = self.player.pos[2] - self.hr_npc.pos[2]
                    hr_distance = math.sqrt(dx_hr*dx_hr + dz_hr*dz_hr)
                    
                    # Check distance to CEO NPC
                    dx_ceo = self.player.pos[0] - self.ceo_npc.pos[0]
                    dz_ceo = self.player.pos[2] - self.ceo_npc.pos[2]
                    ceo_distance = math.sqrt(dx_ceo*dx_ceo + dz_ceo*dz_ceo)

                    if hr_distance < self.interaction_distance and not self.dialogue.active:
                        self.dialogue.start_conversation("HR", self.player.pos)
                        pygame.mouse.set_visible(True) # Show mouse during dialogue
                        pygame.event.set_grab(False)   # Release mouse grab
                        self.last_interaction_time = current_time
                    elif ceo_distance < self.interaction_distance and not self.dialogue.active:
                        self.dialogue.start_conversation("CEO", self.player.pos)
                        pygame.mouse.set_visible(True) # Show mouse during dialogue
                        pygame.event.set_grab(False)   # Release mouse grab
                        self.last_interaction_time = current_time

                # Clear the screen and depth buffer
                glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)

                # Save the current matrix
                glPushMatrix()

                # Apply player rotation and position
                glRotatef(self.player.rot[0], 1, 0, 0)
                glRotatef(self.player.rot[1], 0, 1, 0)
                glTranslatef(-self.player.pos[0], -self.player.pos[1], -self.player.pos[2])

                # Draw the world and NPCs
                self.world.draw()
                self.hr_npc.draw()
                self.ceo_npc.draw()

                # Restore the matrix
                glPopMatrix()

                # Render dialogue system (if active)
                self.dialogue.render()

                # Swap the buffers
                pygame.display.flip()

                # Maintain 60 FPS
                pygame.time.Clock().tick(60)

        pygame.quit()

# Create and run game
if __name__ == "__main__":
    game = Game3D()
    game.run()
