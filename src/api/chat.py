import os
import json
import logging
import uuid
import time
import base64
import shutil
import warnings
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from gemini_cli_headless import run_gemini_cli_headless
from src.utils.config import get_config, PATHS
from src.utils.calc_stats import parse_session_stats, calculate_cost
from src.services.storage import storage

with warnings.catch_warnings():
    warnings.simplefilter("ignore", category=FutureWarning)
    import google.generativeai as genai

router = APIRouter()
logger = logging.getLogger("chat_api")

from typing import Optional

class ChatRequest(BaseModel):
    question: Optional[str] = None
    audio: Optional[str] = None
    chatId: str

@router.post("/ask")
async def ask_question(request: ChatRequest):
    try:
        user_query = request.question
        audio_base64 = request.audio
        chat_id = request.chatId
        
        if not user_query and not audio_base64:
            raise HTTPException(status_code=400, detail="Missing input")

        config = get_config()
        model = config["answer_model"]
        master_session_file = PATHS['master_session_file']
        
        # 1. Resolve User Session
        with storage.chat_mapping_lock:
            gemini_session_id = storage.chat_mapping.get(chat_id)
        
        user_session_file = None
        if gemini_session_id:
            user_session_file = os.path.join(PATHS['sessions_dir'], "answering", f"session-{gemini_session_id}.json")
            if not os.path.exists(user_session_file):
                user_session_file = None
        
        if not user_session_file:
            gemini_session_id = str(uuid.uuid4())
            user_session_file = os.path.join(PATHS['sessions_dir'], "answering", f"session-{gemini_session_id}.json")
            os.makedirs(os.path.dirname(user_session_file), exist_ok=True)
            
            with open(master_session_file, 'r', encoding='utf-8') as f:
                session_data = json.load(f)
            
            session_data['sessionId'] = gemini_session_id
            with open(user_session_file, 'w', encoding='utf-8') as f:
                json.dump(session_data, f, indent=2, ensure_ascii=False)
            
            with storage.chat_mapping_lock:
                storage.chat_mapping[chat_id] = gemini_session_id
            storage.save_chat_mapping()
        else:
            # Load existing session to get the instruction
            with open(user_session_file, 'r', encoding='utf-8') as f:
                session_data = json.load(f)

        # 2. Handle Audio Transcription (EXCEPTION: Using google-generativeai SDK)
        audio_url = None
        transcription = None
        if audio_base64:
            audio_dir = PATHS['user_audio_dir']
            os.makedirs(audio_dir, exist_ok=True)
            audio_filename = f"{time.strftime('%Y-%m-%d_%H-%M-%S')}_{chat_id}.wav"
            audio_path = os.path.join(audio_dir, audio_filename)
            
            with open(audio_path, "wb") as f:
                f.write(base64.b64decode(audio_base64))
            
            audio_url = f"/audio/{audio_filename}?chatId={chat_id}"
            
            try:
                api_key = os.environ.get("GEMINI_API_KEY")
                genai.configure(api_key=api_key)
                
                logger.info(f"Uploading audio file for transcription: {audio_path}")
                uploaded = genai.upload_file(path=audio_path)
                
                # Wait for the file to be processed by Google AI
                # This prevents 'file is not active' errors.
                for _ in range(10):
                    file_info = genai.get_file(uploaded.name)
                    if file_info.state.name == "ACTIVE":
                        break
                    if file_info.state.name == "FAILED":
                        raise RuntimeError("Audio file processing failed on Google side.")
                    time.sleep(1)
                
                m = genai.GenerativeModel("gemini-1.5-flash")
                res = m.generate_content(["Transcribe this audio strictly. Return only the text in Polish.", uploaded])
                transcription = res.text.strip()
                
                if transcription:
                    logger.info(f"Transcription successful: {transcription[:50]}...")
                    user_query = f"{transcription}\n\n{user_query}" if user_query else transcription
                else:
                    logger.warning("Transcription returned empty text.")
                
                genai.delete_file(uploaded.name)
            except Exception as e:
                logger.error(f"Transcription fail: {e}")
                if not user_query:
                    # If we have no text AND transcription failed, we cannot continue
                    return {
                        "answer": "Przepraszam, nie udało mi się przetworzyć Twojej wiadomości głosowej. Spróbuj zadać pytanie tekstowo lub nagrać się jeszcze raz.",
                        "stats": {"duration": "0s", "input": 0, "output": 0, "cost": 0},
                        "audioUrl": audio_url,
                        "transcription": None
                    }

        # 3. Headless Question Answering
        start_time = time.time()
        
        # Load System Instruction from the compiled artifact
        instruction_path = PATHS['master_system_instruction']
        system_instruction = ""
        if os.path.exists(instruction_path):
            with open(instruction_path, 'r', encoding='utf-8') as f:
                system_instruction = f.read()

        session = run_gemini_cli_headless(
            prompt=user_query,
            model_id=model,
            session_to_resume=user_session_file,
            system_instruction_override=system_instruction,
            stream_output=False,
            allowed_tools=[],
            isolate_from_hierarchical_pollution=True
        )
        
        # Persist session
        shutil.copy2(session.session_path, user_session_file)
        
        s = parse_session_stats(session.stats, model)
        duration = time.time() - start_time
        
        final_answer = storage.translate_doc_links(session.text)
        
        # Calculate cost
        actual_cost = calculate_cost(
            model, 
            s.get("input", 0), 
            s.get("output", 0), 
            s.get("cached", 0)
        )

        return {
            "answer": final_answer,
            "stats": {
                "duration": f"{duration:.1f}s",
                "input": s.get("input", 0),
                "output": s.get("output", 0),
                "cached": s.get("cached", 0),
                "thoughts": s.get("thoughts", 0),
                "cost": actual_cost
            },
            "audioUrl": audio_url,
            "transcription": transcription
        }
    except Exception as e:
        logger.exception("Chat API Error")
        raise HTTPException(status_code=500, detail=str(e))
