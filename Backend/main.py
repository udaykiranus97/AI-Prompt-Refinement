# main.py - FastAPI Backend for AI Prompt Generator & Chatbot

# --- Imports ---
# Standard library imports
import os
from typing import List, Dict, Union
from pydantic import EmailStr
from passlib.context import CryptContext
from jose import jwt, JWTError
from datetime import datetime, timedelta
from pathlib import Path
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from fastapi import Request, Depends, status


# Third-party library imports
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel # For data validation and serialization
from dotenv import load_dotenv # To load environment variables from a .env file
import google.generativeai as genai # Google's client library for interacting with Gemini API

# --- Configuration ---
# Load environment variables from .env file (e.g., GEMINI_API_KEY)
load_dotenv()
api_key = os.getenv("GEMINI_API_KEY")

# Check if the API key is set; raise a runtime error if not, as it's essential
if not api_key:
    raise RuntimeError("GEMINI_API_KEY is not set in the environment. Please create a .env file with your API key.")

# Configure the Google Gemini API with the loaded key
genai.configure(api_key=api_key)
# Initialize the Gemini model to be used for prompt refinement and chat responses
# "models/gemini-2.0-flash" is a fast and cost-effective model
model = genai.GenerativeModel(model_name="models/gemini-2.0-flash")

# --- FastAPI App Initialization ---
app = FastAPI(
    title="AI Prompt Refinement & Chatbot API",
    description="API for refining user prompts and providing an interactive chatbot experience using Google Gemini.",
    version="1.0.0"
)


BASE_DIR = Path(__file__).parent.parent # This points to 'AI prompt/'

# Serve Static Files (CSS, JS) from the 'frontend' directory
# Your CSS, JS files (style.css, script.js, auth.js) are directly in frontend/
# So, we mount the 'frontend' directory itself.
# Example: If your style.css is at AI prompt/frontend/style.css, it will be served at /static/style.css
app.mount(
    "/static",
    StaticFiles(directory=BASE_DIR / "frontend"),
    name="static_files"
)

# Serve HTML Templates from the 'frontend/templates' directory
# Your HTML files (index.html, login.html, register.html) are in frontend/templates/
templates = Jinja2Templates(directory=BASE_DIR / "frontend")

# --- CORS Configuration ---
# IMPORTANT: After deployment, replace "https://your-app-name.onrender.com"
# with the actual URL Render gives you for your deployed service.
# For local development, 'http://127.0.0.1:8000' is common for backend.
# If you run your frontend via a separate dev server, add its URL too.
origins = [
    "http://localhost:8000",
    "http://127.0.0.1:8000",
    # Add the actual URL of your Render service after it's deployed.
    # It will look something like: "https://your-service-name.onrender.com"
    "https://your-service-name.onrender.com", # <--- REPLACE THIS AFTER DEPLOYMENT!
    # If your frontend were hosted separately on another free service (e.g., Netlify, Vercel)
    # you would add that URL here as well:
    # "https://your-netlify-frontend.netlify.app",
]

from fastapi.middleware.cors import CORSMiddleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"], # Allows all HTTP methods (GET, POST, etc.)
    allow_headers=["*"], # Allows all headers
)

# --- Routes for your HTML files ---

# --- CORS Middleware Setup ---
# CORS (Cross-Origin Resource Sharing) is a security feature implemented in web browsers
# that prevents web pages from making requests to a different domain than the one that served the web page.
# Since our frontend (e.g., running on http://127.0.0.1:8001) will be on a different origin
# than our backend (http://127.0.0.1:8000), we need to explicitly allow requests from any origin ("*")
# during development. In a production environment, 'allow_origins' should be restricted
# to your specific frontend domain(s) for security.


# --- Pydantic Models for Request and Response Data ---
# These models define the expected structure and data types for the JSON payloads
# sent to and received from our API endpoints. This provides automatic data validation
# and clear documentation for the API.

class PromptRequest(BaseModel):
    """
    Represents the input data for generating or refining a prompt.
    """
    task_description: str
    category: str

class RefinementResponse(BaseModel):
    """
    Represents the response data after a prompt has been refined or modified.
    This is the OUTGOING format from the backend.
    """
    optimized_prompt: str
    explanation: List[str] = None
    suggestions: List[str] = None
    original_task_for_mod: str = None
    original_category_label_for_mod: str = None
    current_category_id: str = None

# --- NEW: Pydantic Model for Modifying Prompts Request ---
class ModifyPromptRequest(BaseModel):
    """
    Represents the INCOMING request data for modifying an existing refined prompt.
    This accurately reflects what the frontend sends to /api/modify-prompt.
    """
    current_refined_prompt: str          # The prompt that needs to be modified
    user_modification_instructions: str  # Instructions from the user on how to modify
    original_task_for_context: str       # Original task for context (from hidden field on frontend)
    original_category_label_for_context: str # Original category label for context
    current_category_id: str             # The ID of the category currently being used


# Models specifically for the interactive chatbot functionality
class ChatMessagePart(BaseModel):
    """
    Represents a single part within a chat message.
    For simplicity, we assume text-only parts for this application.
    """
    text: str

class ChatMessageContent(BaseModel):
    """
    Represents a single message in the chat history.
    Adheres to the format expected by Gemini's chat API.
    """
    role: str
    parts: List[ChatMessagePart]

class ChatRequest(BaseModel):
    """
    Represents the request payload for the chat API endpoint.
    Contains the entire conversation history.
    """
    history: List[ChatMessageContent]

class ChatResponse(BaseModel):
    """
    Represents the response payload from the chat API endpoint.
    """
    model_response: str

# --- Prompt Categories Definition ---
# A list of predefined prompt categories, each with an ID, a user-friendly label,
# and a specific template that guides the AI on how to refine a prompt for that category.
# The '{{user_input}}' placeholder will be replaced by the user's actual task description.
prompt_categories = [
    {
        "id": "writing",
        "label": "Writing & Content Creation",
        "template": (
            "You are a world-renowned prompt engineer specializing in crafting exceptional writing prompts. "
            "Your task is to meticulously transform the user's raw, informal, or vague input into a "
            "highly detailed, clear, and structured prompt. This refined prompt must guide an AI to generate "
            "superior quality written content. It should explicitly define or infer: "
            "1. **Content Goal/Purpose:** What should the writing achieve? "
            "2. **Topic & Core Message:** Specific subject matter and key takeaways. "
            "3. **Target Audience:** Demographics, knowledge level, and expectations. "
            "4. **Style & Voice:** (e.g., formal, academic, witty, persuasive, narrative, technical). "
            "5. **Tone:** (e.g., optimistic, critical, empathetic, urgent, humorous). "
            "6. **Format:** (e.g., blog post, essay, script, email, advertisement, technical paper, story). Include structural elements like headings, sections, or specific content blocks if applicable. "
            "7. **Length/Word Count:** (e.g., concise paragraph, 500-word article, multi-page report). "
            "8. **Keywords/SEO:** (If applicable, list primary and secondary keywords). "
            "9. **Specific Inclusions/Exclusions:** Any must-have points, data, or elements to avoid. "
            "10. **Call to Action:** (If relevant). "
            "Analyze the {{user_input}} and construct the most effective prompt possible, filling in any missing details with expert assumptions aligned with producing high-quality content. "
            "Provide only the final refined prompt as the output, without any explanations or extra text. "
            "Input: {{user_input}}"
        )
    },
    {
        "id": "ideation",
        "label": "Ideation & Brainstorming",
        "template": (
            "You are a master prompt engineer acclaimed for catalyzing groundbreaking idea generation. "
            "Convert the user's input, however informal or nebulous, into a potent and highly creative ideation prompt. "
            "This refined prompt must stimulate an AI to produce a diverse set of novel, practical, and insightful ideas. "
            "It should clearly specify: "
            "1. **Domain/Context:** The specific area or field for ideation (e.g., technology, marketing, education). "
            "2. **Core Objective/Problem:** The central goal or challenge the ideas should address. "
            "3. **Desired Number of Ideas:** A target quantity (e.g., 5 distinct concepts, 20 variations). "
            "4. **Key Criteria for Ideas:** (e.g., novelty, feasibility, impact, cost-effectiveness, sustainability). "
            "5. **Stimuli/Inspiration Points:** (Optional: suggest related concepts, analogies, or starting points if beneficial). "
            "6. **Constraints/Boundaries:** Any limitations or factors that must be considered (e.g., budget, time, technology). "
            "7. **Output Format:** (e.g., list of ideas with brief descriptions, ideas categorized by theme). "
            "Your goal is to engineer a prompt that maximizes both the breadth (diversity) and depth (ingenuity) of the generated ideas. "
            "Provide only the final refined prompt as the output, without any explanations or extra text. "
            "Input: {{user_input}}"
        )
    },
    {
        "id": "summarization",
        "label": "Summarization & Extraction",
        "template": (
            "You are an elite prompt engineer specializing in information distillation and summarization. "
            "Transform the user's potentially vague input into a precise and effective summarization/extraction prompt. "
            "This refined prompt must instruct an AI to accurately and coherently extract key information or synthesize content. "
            "It should define: "
            "1. **Source Material Type:** (e.g., article, research paper, conversation, technical document). This may be inferred from the {{user_input}} if it contains the text. "
            "2. **Summarization Goal:** (e.g., extract key findings, create a concise overview, generate bullet points of main arguments, identify action items). "
            "3. **Level of Detail/Length:** (e.g., one-sentence summary, 3 key bullet points, 200-word abstract, detailed executive summary). "
            "4. **Specific Information to Extract:** (If applicable, e.g., names, dates, locations, definitions, methodologies, conclusions, specific data points). "
            "5. **Tone of Summary:** (e.g., neutral, objective, critical, promotional – usually neutral for summaries). "
            "6. **Format of Output:** (e.g., narrative paragraph, numbered list, bullet points, table). "
            "7. **Focus:** (e.g., emphasize implications, focus on methodology, highlight discrepancies). "
            "Ensure the prompt guides the AI to preserve the core meaning and context of the original information. "
            "Provide only the final refined prompt as the output, without any explanations or extra text. "
            "Input: {{user_input}}"
        )
    },
    {
        "id": "explanation",
        "label": "Explanation & Tutoring",
        "template": (
            "You are a distinguished educational prompt engineer, expert in making complex topics understandable. "
            "Convert the user's input, often brief or unclear, into a comprehensive and well-structured prompt for explanation. "
            "This refined prompt must guide an AI to deliver a clear, concise, and step-by-step explanation of a given topic, specifically tailored for an audience with little to no prior knowledge. "
            "It should include: "
            "1. **Topic to Explain:** Clearly identified from {{user_input}}. "
            "2. **Target Audience's Assumed Knowledge Level:** (Default to absolute beginner unless specified otherwise). "
            "3. **Depth of Explanation:** (e.g., high-level overview, detailed breakdown, practical application). "
            "4. **Key Concepts to Cover:** Identify and ensure all crucial sub-topics and terminologies are explained. "
            "5. **Structure of Explanation:** (e.g., chronological, cause-and-effect, problem-solution, component-wise). Prefer a logical, step-by-step flow. "
            "6. **Use of Analogies/Examples:** Encourage the use of relatable analogies and practical examples to aid comprehension. "
            "7. **Language and Simplicity:** Emphasize the use of simple, accessible language, avoiding jargon where possible or defining it clearly. "
            "8. **Desired Learning Outcome:** What should the audience understand or be able to do after the explanation? "
            "The aim is to ensure maximum clarity, comprehension, and engagement for the learner. "
            "Provide only the final refined prompt as the output, without any explanations or extra text. "
            "Input: {{user_input}}"
        )
    },
    {
        "id": "reasoning",
        "label": "Problem Solving & Reasoning",
        "template": (
            "You are a preeminent prompt engineer, specializing in logical reasoning and complex problem-solving. "
            "Transform the user's informal question or problem statement into a precise and analytical prompt. "
            "This refined prompt must guide an AI through a rigorous, step-by-step reasoning process to arrive at a well-justified conclusion or solution. "
            "It should clearly articulate: "
            "1. **The Problem/Question:** An unambiguous definition of the issue to be addressed. "
            "2. **Known Information/Data:** List all relevant facts, premises, and data provided in {{user_input}}. "
            "3. **Assumptions:** Explicitly state any necessary assumptions (or guide the AI to state its assumptions). "
            "4. **Required Steps/Methodology:** (e.g., logical deduction, calculation, comparative analysis, hypothesis testing). Guide the AI to show its work. "
            "5. **Constraints/Rules:** Any rules, limitations, or conditions that must be adhered to. "
            "6. **Desired Output Format:** (e.g., detailed explanation of reasoning, final answer with justification, list of pros and cons, calculated value). "
            "7. **Level of Rigor:** (e.g., informal logical path, formal proof, detailed quantitative analysis). "
            "The prompt must encourage transparency in the reasoning process, making it easy to follow and verify the logical flow and calculations. "
            "Provide only the final refined prompt as the output, without any explanations or extra text. "
            "Input: {{user_input}}"
        )
    },
    {
        "id": "coding",
        "label": "Code & Development",
        "template": (
            "You are the world's leading prompt engineer for software development and code generation. "
            "Convert the user's informal or high-level coding request into an exceptionally specific, detailed, and unambiguous programming prompt. "
            "This refined prompt must enable an AI to generate accurate, efficient, and robust code. "
            "It must define: "
            "1. **Programming Language(s) & Version(s):** (e.g., Python 3.9, JavaScript ES6). "
            "2. **Core Functionality & Objectives:** Precise description of what the code should do, including inputs and expected outputs. "
            "3. **Specific Algorithms/Logic:** (If known or preferred, otherwise allow AI to select optimally). "
            "4. **Data Structures:** (e.g., arrays, dictionaries, custom classes). "
            "5. **Key Libraries/Frameworks/APIs:** Specify any to be used or avoided. "
            "6. **Error Handling & Edge Cases:** Describe how errors should be managed and specific edge cases to consider. "
            "7. **Performance Considerations:** (e.g., efficiency, memory usage, speed). "
            "8. **Code Style & Conventions:** (e.g., PEP 8 for Python, specific naming conventions, comments). "
            "9. **Examples:** Provide clear input/output examples if possible. "
            "10. **Modularity/Structure:** (e.g., functions, classes, modules). "
            "11. **Constraints & Limitations:** Any restrictions on libraries, resources, or environment. "
            "Ensure the prompt minimizes ambiguity to facilitate the generation of production-quality code. "
            "Provide only the final refined prompt as the output, without any explanations or extra text. "
            "Input: {{user_input}}"
        )
    },
    {
        "id": "data_analysis",
        "label": "Data & Analysis",
        "template": (
            "You are a premier prompt engineer for data analysis, skilled at translating vague requests into precise analytical tasks. "
            "Rewrite the user's unclear or partial request into a comprehensive and specific data analysis prompt. "
            "This refined prompt must guide an AI to perform accurate data analysis and generate insightful outputs. "
            "It should clearly state: "
            "1. **Analytical Goal/Objective:** What questions need to be answered? What insights are sought? "
            "2. **Data Description:** (If data is provided in {{user_input}} or described) Nature of the data (e.g., CSV, JSON, database table), key variables/columns, and their types. "
            "3. **Data Source:** (If applicable, e.g., specific file, API endpoint, database). "
            "4. **Specific Tasks:** (e.g., data cleaning, transformation, statistical summary, hypothesis testing, predictive modeling, visualization). "
            "5. **Methods/Techniques:** (If specific methods are required, e.g., regression analysis, clustering, time series forecasting). "
            "6. **Metrics/Calculations:** Define any specific metrics, formulas, or calculations to be performed. "
            "7. **Desired Output Format:** (e.g., textual summary of findings, tables, charts (specify type), code for queries (SQL, Python/Pandas), model parameters). "
            "8. **Assumptions for Analysis:** Clarify any assumptions to be made about the data or context. "
            "The prompt should enable the AI to execute the analysis methodically and present results clearly. "
            "Provide only the final refined prompt as the output, without any explanations or extra text. "
            "Input: {{user_input}}"
        )
    },
    {
        "id": "language",
        "label": "Translation & Language",
        "template": (
            "You are a distinguished linguistic prompt engineer, adept at handling nuanced language tasks. "
            "Convert the user's casual translation, style, or grammar request into a highly precise and context-aware linguistic prompt. "
            "This refined prompt must guide an AI to perform tasks like translation, localization, style transformation, or grammatical correction with high fidelity. "
            "It should specify: "
            "1. **Task Type:** (e.g., translation, localization, proofreading, style adaptation, paraphrasing, sentiment adjustment). "
            "2. **Source Language & Target Language:** (For translation/localization, including dialects if relevant). "
            "3. **Content for Processing:** The specific text to be worked on, derived from {{user_input}}. "
            "4. **Desired Tone/Style:** (e.g., formal, informal, academic, technical, literary, conversational, humorous). "
            "5. **Formality Level:** (e.g., T-V distinction in relevant languages). "
            "6. **Target Audience:** Who is the output for? This influences vocabulary, style, and cultural references. "
            "7. **Specific Vocabulary/Terminology:** Any domain-specific terms, jargon, or glossaries to use or avoid. "
            "8. **Cultural Nuances/Localization Needs:** (e.g., adapting idioms, date formats, measurements). "
            "9. **Emphasis:** (e.g., prioritize literal accuracy vs. natural fluency, preserve original author's voice). "
            "Ensure the prompt leads to linguistically accurate and contextually appropriate output. "
            "Provide only the final refined prompt as the output, without any explanations or extra text. "
            "Input: {{user_input}}"
        )
    },
    {
        "id": "roleplay",
        "label": "Roleplay & Simulation",
        "template": (
            "You are a master prompt engineer for creating deeply immersive and engaging roleplay and simulation experiences. "
            "Transform the user's vague or simple input into a rich, detailed, and compelling prompt that sets the stage for an AI. "
            "This refined prompt must define: "
            "1. **Scenario/Setting:** A vivid description of the environment, time period, and context. "
            "2. **User's Role:** Clearly define who the user is in this scenario. "
            "3. **AI's Role(s)/Persona(s):** Detailed character description(s) for the AI, including personality, motivations, knowledge, and relationship to the user's role. "
            "4. **Core Objective(s)/Goal(s):** What should the user and/or AI try to achieve in the simulation/roleplay? "
            "5. **Opening Situation:** How does the interaction begin? "
            "6. **Tone & Atmosphere:** (e.g., serious, adventurous, mysterious, comedic, suspenseful). "
            "7. **Rules of Engagement/Boundaries:** Any specific rules, constraints, or limitations for the interaction (e.g., no violence, specific information AI should not know). "
            "8. **Key Information/Lore:** Essential background details the AI needs to embody its role effectively. "
            "9. **Desired Interaction Style:** (e.g., narrative, dialogue-driven, choice-based). "
            "The goal is to create a dynamic and believable simulation that allows for meaningful interaction and exploration. "
            "Provide only the final refined prompt as the output, without any explanations or extra text. "
            "Input: {{user_input}}"
        )
    },
    {
        "id": "research",
        "label": "Research & Reports",
        "template": (
            "You are a leading prompt engineer specializing in academic and professional research and report generation. "
            "Rewrite the user's informal query or topic idea into a meticulously structured and comprehensive research prompt. "
            "This refined prompt must guide an AI to gather, synthesize, and present information in a scholarly or professional manner. "
            "It should specify: "
            "1. **Research Topic/Question(s):** Clearly defined scope and central research questions. "
            "2. **Report Type/Objective:** (e.g., literature review, market analysis, technical report, case study, white paper, systematic review). "
            "3. **Depth of Research:** (e.g., overview, comprehensive analysis, in-depth investigation). "
            "4. **Key Areas/Subtopics to Cover:** Outline the main sections or themes to be addressed. "
            "5. **Information Sources (Preferred/To Avoid):** (e.g., peer-reviewed journals, industry reports, specific databases, avoid blogs). "
            "6. **Methodology (if applicable):** (e.g., qualitative synthesis, quantitative summary, comparative analysis). "
            "7. **Formatting Style:** (e.g., APA, MLA, Chicago, specific corporate template guidelines). "
            "8. **Tone and Voice:** (e.g., objective, analytical, persuasive, informative). "
            "9. **Requirement for Citations/References:** Specify if and how sources should be cited. "
            "10. **Length/Structure:** Desired length, sections, and organization of the report. "
            "11. **Critical Analysis Level:** (e.g., descriptive, evaluative, critical). "
            "The prompt should empower the AI to produce a well-researched, well-structured, and credible output. "
            "Provide only the final refined prompt as the output, without any explanations or extra text. "
            "Input: {{user_input}}"
        )
    },
    {
        "id": "productivity",
        "label": "Productivity & Planning",
        "template": (
            "You are a highly sought-after prompt engineer renowned for optimizing productivity and strategic planning. "
            "Convert the user's casual goals or planning needs into a precise, actionable, and context-aware prompt. "
            "This refined prompt must guide an AI to generate clear plans, schedules, task breakdowns, or productivity strategies tailored to the user's situation. "
            "It should define: "
            "1. **Overall Goal/Objective:** What does the user want to achieve? "
            "2. **Context/Situation:** Relevant background information (e.g., project type, personal goal, team size, available resources). "
            "3. **Specific Deliverable Needed:** (e.g., detailed project plan, weekly schedule, prioritized to-do list, meeting agenda, decision-making framework). "
            "4. **Timeline/Deadlines:** Any critical start dates, end dates, or milestones. "
            "5. **Key Tasks/Activities (if known):** Initial list of tasks to be organized or expanded upon. "
            "6. **Prioritization Criteria:** How should tasks be prioritized (e.g., urgency, impact, effort)? "
            "7. **Resource Allocation:** (If applicable, e.g., time, budget, personnel). "
            "8. **Dependencies:** Are there tasks that depend on others? "
            "9. **Format of Plan/Output:** (e.g., Gantt chart outline, Kanban board structure, bulleted list with assignments, calendar entries). "
            "10. **Success Metrics:** How will the success of the plan be measured? "
            "The prompt must result in a practical, organized, and effective tool for enhancing productivity. "
            "Provide only the final refined prompt as the output, without any explanations or extra text. "
            "Input: {{user_input}}"
        )
    },
    {
        "id": "visual_generation",
        "label": "Image/Media Generation",
        "template": (
            "You are the world's foremost prompt engineer for visual and media content generation, possessing an unparalleled eye for detail and artistic nuance. "
            "Transform the user's rough idea or concept into an extraordinarily rich, evocative, and technically detailed prompt for an AI image/media generator. "
            "This refined prompt must provide comprehensive guidance to achieve a specific visual output. "
            "It should meticulously detail: "
            "1. **Primary Subject(s):** Clear description, including characteristics, actions, emotions, and attire. "
            "2. **Artistic Style:** (e.g., photorealistic, impressionistic, surreal, anime, concept art, specific artist's style like Van Gogh or Ansel Adams). "
            "3. **Composition & Framing:** (e.g., close-up, wide shot, rule of thirds, bird's-eye view, leading lines, depth of field). "
            "4. **Lighting:** (e.g., softbox, cinematic lighting, golden hour, volumetric, neon, dark and moody). "
            "5. **Color Palette:** (e.g., vibrant, monochromatic, pastel, sepia, specific color harmonies). "
            "6. **Mood & Atmosphere:** (e.g., serene, chaotic, futuristic, nostalgic, eerie, joyful). "
            "7. **Background/Environment:** Detailed description of the setting, including location, objects, and weather. "
            "8. **Level of Detail & Realism:** (e.g., highly detailed, sketchy, 4K, 8K, hyperrealistic). "
            "9. **Camera & Lens Effects:** (e.g., fisheye lens, bokeh, motion blur, shallow depth of field, specific camera angle). "
            "10. **Artistic Influences/References:** (Optional: mention specific artworks, films, or movements as inspiration). "
            "11. **Negative Prompts (What to Avoid):** Specify elements, styles, or qualities to exclude. "
            "12. **Aspect Ratio:** (e.g., 16:9, 1:1, 9:16). "
            "The goal is to leave no room for ambiguity, ensuring the AI can render the user's vision with stunning accuracy and creativity. "
            "Provide only the final refined prompt as the output, without any explanations or extra text. "
            "Input: {{user_input}}"
        )
    },
    {
        "id": "expert_domains",
        "label": "Legal, Medical, and Expert Domains",
        "template": (
            "You are a highly specialized prompt engineer with deep expertise in crafting prompts for critical expert domains such as law, medicine, finance, and engineering. "
            "Convert the user's vague, casual, or incomplete input into a precise, context-aware, and responsible prompt suitable for AI-assisted content generation in these sensitive fields. "
            "The refined prompt must carefully define: "
            "1. **Specific Domain:** (e.g., contract law, cardiology, financial forecasting, structural engineering). "
            "2. **Nature of Request:** (e.g., information retrieval, document drafting, analysis of a specific case (hypothetical if needed), explanation of a concept). "
            "3. **Jurisdiction/Regulatory Context:** (Crucial for legal, financial, and medical prompts, e.g., 'US federal law', 'EMA guidelines', 'GAAP principles'). "
            "4. **Required Level of Detail & Formality:** (e.g., layperson summary, expert-to-expert communication, formal report). "
            "5. **Key Terminology & Concepts:** Ensure accurate use and, if necessary, definition of domain-specific terms. "
            "6. **Information to Include/Consider:** Specific facts, parameters, variables, or sections that must be addressed. "
            "7. **Information to Exclude/Disclaimers:** What should be explicitly avoided? Crucially, include a directive for the AI to add standard disclaimers about its non-human status and the information not being professional advice (e.g., 'This is not legal/medical advice'). "
            "8. **Audience for the Output:** (e.g., lawyer, patient, student, investor). "
            "9. **Ethical Considerations:** (e.g., for medical: patient privacy/anonymization principles even with hypothetical data; for legal: avoiding unauthorized practice of law). "
            "10. **Desired Output Format:** (e.g., structured report, Q&A, clause for a document). "
            "Prioritize accuracy, safety, and ethical responsibility in the construction of this prompt. "
            "Provide only the final refined prompt as the output, without any explanations or extra text. "
            "Input: {{user_input}}"
        )
    },
    {
        "id": "meta_prompting",
        "label": "Meta-Prompts (Prompt Refinement & Generation)",
        "template": (
            "You are the ultimate Meta-Prompt Architect, a distinguished AI prompt engineer capable of elevating any prompt to its maximum potential. "
            "Your mission is to meticulously analyze the {{user_input}}, which may be an informal idea, a vague request, or an existing underperforming prompt. "
            "Transform it into a highly detailed, structured, and optimized Master Prompt. "
            "This Master Prompt must be engineered to elicit the highest quality, most accurate, and most nuanced response from a target AI. "
            "Your refined prompt should explicitly incorporate or instruct the inclusion of: "
            "1. **Clear Objective & Purpose:** What is the ultimate goal of the target AI's output? "
            "2. **Comprehensive Context:** All necessary background information, assumptions, and situational details. "
            "3. **Precise Role & Persona for AI:** Define the expertise, voice, and character the target AI should adopt. "
            "4. **Target Audience for AI's Output:** Specify who the AI's response is for. "
            "5. **Detailed Output Format & Structure:** Specify the desired layout, style, length, and any formatting requirements (e.g., Markdown, JSON, specific sections). "
            "6. **Key Elements to Include/Address:** Essential information, arguments, data points, or questions to cover. "
            "7. **Constraints & Boundaries:** What should the AI avoid (topics, opinions, styles, specific words)? Define limitations. "
            "8. **Tone & Style Requirements:** Specify the desired linguistic style (e.g., formal, persuasive, empathetic, technical). "
            "9. **Evaluation Criteria (Implicit or Explicit):** What makes a good response in this context? "
            "10. **Advanced Prompting Techniques (as applicable):** Consider incorporating elements like Chain-of-Thought (CoT) cues, few-shot examples (if derivable or if {{user_input}} hints at needing them), instruction for step-by-step reasoning, or asking the AI to self-critique/improve its own output. "
            "11. **Action Verbs & Unambiguous Language:** Ensure the prompt uses clear, direct language. "
            "Your output is *only* the refined Master Prompt, ready to be used. Do not include any of your own reasoning, explanations, or conversational text. "
            "\n\nUser Input: {{user_input}}\n\nRefined Prompt:"
        )
    }
]
# A special ID for the "Please select a category" option in the dropdown
NO_SELECTION_CATEGORY_ID = "please_select"

# --- Auth Setup (Smart No-DB Auth) ---
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
SECRET_KEY = "your-secret-key"  # TODO: replace with .env value in production
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60

# In-memory user store (no DB)
fake_user_db = {}

class UserRegister(BaseModel):
    email: EmailStr
    password: str

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class TokenResponse(BaseModel):
    token: str

def hash_password(pwd: str):
    return pwd_context.hash(pwd)

def verify_password(pwd: str, hashed: str):
    return pwd_context.verify(pwd, hashed)

def create_token(data: dict, expires_delta: timedelta = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)):
    to_encode = data.copy()
    expire = datetime.utcnow() + expires_delta
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

# The default category to use if no specific category is selected by the user,
# or if the selected category ID is invalid.
default_prompt_category = {
    "id": "meta_prompting",
    "label": "Meta-Prompts (Prompt Refinement & Generation)",
    "template": "You are the world's best prompt engineer assistant. Transform any unclear or informal prompt into a detailed, optimized version that adds context, format, tone, constraints, and purpose to maximize AI quality.\n\nUser Input: {{user_input}}\n\nRefined Prompt:"
}

# --- Helper Functions ---

def get_prompt_category(category_id: str) -> Dict[str, str]:
    """
    Retrieves the category dictionary based on its ID.
    Returns the default category if the ID is not found.
    """
    for category in prompt_categories:
        if category["id"] == category_id:
            return category
    return default_prompt_category

def get_category_prompt(category_id: str, user_input: str) -> str:
    """
    Constructs the full prompt for the Gemini model by inserting the user's
    input into the selected category's template.
    """
    category_info = get_prompt_category(category_id)
    # Replace the placeholder in the template with the actual user input
    return category_info["template"].replace("{{user_input}}", user_input)

def parse_bullet_list(text_content: str) -> List[str]:
    """
    Parses a string containing bulleted list items into a Python list of strings.
    Handles both '* Item' and simple new-line separated items.
    """
    if not text_content:
        return []
    lines = text_content.strip().split('\n')
    parsed_items = []
    for line in lines:
        stripped_line = line.strip()
        # Check for common bullet point prefixes like '*'
        if stripped_line.startswith('* '):
            parsed_items.append(stripped_line[2:].strip()) # Remove '* '
        elif stripped_line:
            parsed_items.append(stripped_line) # Add line as is if not bulleted but not empty
    return parsed_items if parsed_items else [text_content.strip()]

def modify_prompt_with_user_input(
    current_refined_prompt: str,
    user_modification_instructions: str,
    original_task_for_context: str,
    original_category_label_for_context: str
) -> str:
    """
    Uses the Gemini model to modify an already refined prompt based on new user instructions.
    This function creates a meta-prompt to guide the AI in performing the modification.
    """
    modification_prompt = f"""
    You are an exceptionally skilled **AI Prompt Engineer and LLM Trainer**. Your primary goal is to meticulously refine and adapt existing prompts based on precise user instructions, ensuring optimal performance and clarity for subsequent AI interactions.

    **Original Context for Reference (Do NOT modify these):**
    * **Initial Task:** "{original_task_for_context}"
    * **Task Category:** "{original_category_label_for_context}"

    **Your Core Task:**
    Carefully analyze the 'CURRENT REFINED PROMPT' provided below. Then, apply the 'USER MODIFICATION INSTRUCTIONS' to generate a **single, new, highly refined prompt**.

    **Crucial Constraints & Requirements:**
    1.  **Output Format:** Your output *must be exclusively the modified prompt string*. Do not include any conversational filler, introductory phrases (e.g., "Here is your modified prompt:"), concluding remarks, or any other extraneous text.
    2.  **Strict Adherence:** Adhere *strictly* to all aspects of the 'USER MODIFICATION INSTRUCTIONS'. If an instruction seems ambiguous, interpret it in a way that minimizes ambiguity and maximizes the utility of the prompt for an AI.
    3.  **Preservation of Core Intent:** While modifying, ensure the core objective and original intent of the 'CURRENT REFINED PROMPT' are preserved unless explicitly contradicted by the modification instructions.
    4.  **Clarity & Conciseness:** The final prompt should be as clear, unambiguous, and concise as possible, optimizing it for direct interaction with an LLM. Avoid redundancy.
    5.  **No Explanations:** Do not explain your changes or thought process. Simply output the final prompt.
    6.  **Error Handling (Implicit):** If the 'USER MODIFICATION INSTRUCTIONS' are illogical or impossible to apply without breaking the prompt's functionality, generate the most sensible prompt possible while maintaining utility. Do not generate an error message.

    ---
    **CURRENT REFINED PROMPT (for modification):**
    {current_refined_prompt}

    ---
    **USER MODIFICATION INSTRUCTIONS (to apply):**
    {user_modification_instructions}

    ---
    **MODIFIED PROMPT (Your output starts here - ONLY the prompt string):**
    """
    try:
        response = model.generate_content(modification_prompt)
        # Return the AI's modified prompt, or the original if the response is empty
        return response.text.strip() if response and hasattr(response, "text") else current_refined_prompt
    except Exception as e:
        # Log the error for debugging purposes on the server side
        print(f"Error modifying prompt with user input: {e}")
        # Return the original prompt if an error occurs during modification, to prevent data loss
        return current_refined_prompt

def get_ai_explanation_and_suggestions(generated_prompt: str, original_task: str, category_label: str) -> Dict[str, List[str]]:
    """
    Uses the Gemini model to generate concise, bulleted explanations and suggestions
    for a given refined prompt. This provides meta-information about the prompt.
    """
    # Prompt for generating an explanation of the refined prompt
    explanation_prompt = f"""
    You are an expert prompt engineer.
    Explain why the following prompt was generated in this way, considering the original user task: "{original_task}" and the category: "{category_label}".
    Highlight the key elements added or modified to make the prompt more effective for an AI.
    Provide only the explanation as a concise bulleted list with a maximum of 3-4 key points, starting each point with an asterisk (*). Do not include any introductory or concluding sentences.

    Generated Prompt:
    {generated_prompt}
    """

    # Prompt for generating suggestions on how the user could improve their initial input
    suggestion_prompt = f"""
    You are an expert prompt engineer.
    Based on the following generated prompt and the original user task: "{original_task}", suggest 2-3 actionable ways the user could have phrased their initial request to potentially get an even better or more directly relevant prompt in the future.
    Provide only the suggestions as a concise bulleted list, starting each point with an asterisk (*). Do not include any introductory or concluding sentences.

    Generated Prompt:
    {generated_prompt}
    """

    # Generate content for both explanation and suggestions concurrently
    # The 'generate_content' method is synchronous, so these run sequentially.
    explanation_response = model.generate_content(explanation_prompt)
    suggestion_response = model.generate_content(suggestion_prompt)

    # Extract text content, handling cases where response might be empty
    explanation_raw = explanation_response.text.strip() if explanation_response and hasattr(explanation_response, 'text') else ""
    suggestions_raw = suggestion_response.text.strip() if suggestion_response and hasattr(suggestion_response, 'text') else ""

    # Parse the raw text into bulleted lists
    explanation = parse_bullet_list(explanation_raw)
    suggestions = parse_bullet_list(suggestions_raw)

    return {"explanation": explanation, "suggestions": suggestions}

# --- API Endpoints ---

@app.get("/", response_class=HTMLResponse)
async def serve_index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/login.html", response_class=HTMLResponse)
async def serve_login(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})

@app.get("/register.html", response_class=HTMLResponse)
async def serve_register(request: Request):
    return templates.TemplateResponse("register.html", {"request": request})



@app.get("/api/categories", response_model=List[Dict[str, str]])
async def get_categories():
    """
    API endpoint to retrieve the list of available prompt categories.
    The frontend uses this to populate the dropdown menu.
    """
    # Return only the 'id' and 'label' for each category, as the template is internal
    return [{"id": c["id"], "label": c["label"]} for c in prompt_categories]

@app.post("/api/generate-prompt", response_model=RefinementResponse)
async def generate_prompt_api(data: PromptRequest):
    """
    API endpoint to generate a refined prompt based on user's initial task
    and selected category. Also provides AI explanations and suggestions.
    """
    try:
        # Determine the actual category ID to use, defaulting if "please_select" is chosen
        selected_category_id = data.category if data.category != NO_SELECTION_CATEGORY_ID else default_prompt_category["id"]
        category_info = get_prompt_category(selected_category_id)

        # Construct the prompt for the Gemini model using the selected category's template
        prompt_text = get_category_prompt(selected_category_id, data.task_description)

        # Send the prompt to the Gemini model for refinement
        response = model.generate_content(prompt_text)
        refined_prompt = response.text.strip() if response and hasattr(response, "text") else ""

        # Get AI-generated explanations and suggestions for the refined prompt
        ai_analysis = get_ai_explanation_and_suggestions(
            refined_prompt, data.task_description, category_info["label"]
        )

        # Return the structured response
        return RefinementResponse(
            optimized_prompt=refined_prompt,
            explanation=ai_analysis["explanation"],
            suggestions=ai_analysis["suggestions"],
            original_task_for_mod=data.task_description, # Pass original task for context in subsequent modifications
            original_category_label_for_mod=category_info["label"], # Pass original category label for context
            current_category_id=selected_category_id # Pass the selected category ID
        )
    except Exception as e:
        # Catch any unexpected errors during the process and return a 500 Internal Server Error
        print(f"Error generating prompt: {e}") # Log error for server-side debugging
        raise HTTPException(status_code=500, detail=f"Failed to generate prompt: {str(e)}")

@app.post("/api/modify-prompt", response_model=RefinementResponse)
# --- CHANGE: Changed input model from RefinementResponse to ModifyPromptRequest ---
async def modify_prompt_api(data: ModifyPromptRequest):
    """
    API endpoint to modify an already refined prompt based on user's specific instructions.
    It expects a ModifyPromptRequest payload and returns a RefinementResponse.
    """
    try:
        # Call the helper function to get the AI-modified prompt
        modified_prompt = modify_prompt_with_user_input(
            data.current_refined_prompt, # Accessing the correct field from ModifyPromptRequest
            data.user_modification_instructions,
            data.original_task_for_context,
            data.original_category_label_for_context
        )

        # Re-generate explanations and suggestions for the newly modified prompt
        ai_analysis = get_ai_explanation_and_suggestions(
            modified_prompt,
            data.original_task_for_context,
            data.original_category_label_for_context
        )

        # Return the structured response with the updated prompt and analysis
        return RefinementResponse(
            optimized_prompt=modified_prompt,
            explanation=ai_analysis["explanation"],
            suggestions=ai_analysis["suggestions"],
            original_task_for_mod=data.original_task_for_context,
            original_category_label_for_mod=data.original_category_label_for_context,
            current_category_id=data.current_category_id
        )
    except Exception as e:
        # Catch any unexpected errors and return a 500 Internal Server Error
        print(f"Error modifying prompt: {e}") # Log error for server-side debugging
        raise HTTPException(status_code=500, detail=f"Failed to modify prompt: {str(e)}")

@app.post("/api/chat", response_model=ChatResponse)
async def chat_api(data: ChatRequest):
    """
    API endpoint for interactive chatbot communication.
    Receives the full conversation history and returns the AI's next response.
    """
    try:
        # Basic validation: ensure chat history is not empty
        if not data.history:
            raise HTTPException(status_code=400, detail="Chat history cannot be empty.")

        # Transform the frontend's chat history format to Gemini's expected format.
        # Gemini's `generate_content` expects a list of dictionaries, where each dict
        # has 'role' and 'parts', and 'parts' is a list of dictionaries with 'text'.
        gemini_history = []
        for msg in data.history:
            # Assuming each part from the frontend is a single text string for simplicity
            gemini_history.append({
                "role": msg.role,
                "parts": [{"text": p.text} for p in msg.parts]
            })

        # Send the entire conversation history to the Gemini model.
        # This allows the AI to maintain context and generate relevant follow-up responses.
        response = model.generate_content(contents=gemini_history)

        # Extract the AI's response, handling cases where the response might be empty
        model_response = response.text.strip() if response and hasattr(response, "text") else "No response from AI."
        return ChatResponse(model_response=model_response)
    except Exception as e:
        # Catch any unexpected errors during chat interaction and return a 500 Internal Server Error
        print(f"Error in chat API: {e}") # Log error for server-side debugging
        raise HTTPException(status_code=500, detail=f"Failed to get chat response: {str(e)}")
    
@app.post("/api/register")
async def register(user: UserRegister):
    if user.email in fake_user_db:
        raise HTTPException(status_code=400, detail="User already exists")
    hashed_pw = hash_password(user.password)
    fake_user_db[user.email] = {"email": user.email, "password": hashed_pw}
    return {"message": "Registration successful"}

@app.post("/api/login", response_model=TokenResponse)
async def login(user: UserLogin):
    db_user = fake_user_db.get(user.email)
    if not db_user or not verify_password(user.password, db_user["password"]):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    token = create_token({"sub": user.email})
    return {"token": token}
