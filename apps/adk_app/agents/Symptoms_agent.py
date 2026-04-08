"""
Symptoms Agent — CareOrchestra (ADK + Groq)
Complete standalone agent with all logic integrated
"""

from __future__ import annotations

import json
import logging
import os
from typing import Optional, List, Dict, Tuple
import time
import threading
import hashlib
from enum import Enum

from google.adk.agents import Agent
from openai import OpenAI
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

class Severity(str, Enum):
    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"
    CRITICAL = "critical"

class EscalationAction(str, Enum):
    REASSURE = "reassure"
    MONITOR = "monitor"
    SCHEDULE_48H = "schedule_within_48h"
    SCHEDULE_URGENT = "schedule_urgent"
    EMERGENCY = "call_emergency"

class PatientContext(BaseModel):
    patient_id: str
    age: int
    conditions: List[str] = Field(default_factory=list)
    baseline_bp_systolic: Optional[int] = None
    baseline_bp_diastolic: Optional[int] = None
    current_medications: List[str] = Field(default_factory=list)
    vitals_severity_flag: Optional[str] = None

class SymptomsAgentInput(BaseModel):
    raw_message: str
    patient_context: PatientContext
    conversation_history: List[dict] = Field(default_factory=list)

class ExtractedSymptom(BaseModel):
    name: str
    raw_text: str
    negated: bool = False
    duration_hint: Optional[str] = None

class RedFlagMatch(BaseModel):
    flag_name: str
    matched_symptom: str
    condition: str
    weight: float

class SymptomsAgentOutput(BaseModel):
    extracted_symptoms: List[ExtractedSymptom]
    symptom_summary: str
    severity: Severity
    red_flags_matched: List[RedFlagMatch]
    risk_score: int = Field(ge=0, le=100)
    confidence: str
    escalation: EscalationAction
    escalation_reason: str
    agent_id: str = "symptoms_agent_v1"
    model_used: str = "llama-3.3-70b-versatile"

RED_FLAGS: Dict[str, List[dict]] = {
    "hypertension": [
        {"flag_name": "HTN_SEVERE_HEADACHE", "keywords": ["worst headache", "thunderclap", "severe headache"], "weight": 0.35, "auto_escalate": False},
        {"flag_name": "HTN_CHEST_PAIN", "keywords": ["chest pain", "chest tightness", "chest pressure"], "weight": 0.40, "auto_escalate": False},
        {"flag_name": "HTN_NEURO_SIGNS", "keywords": ["face drooping", "arm weakness", "slurred speech", "confusion"], "weight": 0.50, "auto_escalate": True},
    ],
    "type2_diabetes": [
        {"flag_name": "DM_HYPOGLYCEMIA", "keywords": ["shaking", "sweating", "feel faint", "fainting"], "weight": 0.35, "auto_escalate": False},
        {"flag_name": "DM_DKA_SIGNS", "keywords": ["fruity breath", "vomiting", "stomach pain"], "weight": 0.45, "auto_escalate": True},
    ],
    "heart_disease": [
        {"flag_name": "CVD_CHEST_PAIN", "keywords": ["chest pain", "chest tightness", "crushing chest"], "weight": 0.50, "auto_escalate": True},
    ],
    "_general": [
        {"flag_name": "GEN_ALTERED_CONSCIOUSNESS", "keywords": ["passed out", "fainted", "unconscious"], "weight": 0.50, "auto_escalate": True},
    ],
}

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")

if not GROQ_API_KEY:
    logger.warning("GROQ_API_KEY not set")
client = (
    OpenAI(api_key=GROQ_API_KEY, base_url="https://api.groq.com/openai/v1")
    if GROQ_API_KEY
    else None
)

class ResponseCache:
    def __init__(self, ttl_seconds: int = 3600):
        self.ttl_seconds = ttl_seconds
        self.cache: Dict[str, Tuple[str, float]] = {}
        self.lock = threading.RLock()
    
    def _hash_key(self, system: str, user_content: str) -> str:
        combined = f"{system}||{user_content}"
        return hashlib.sha256(combined.encode()).hexdigest()
    
    def get(self, system: str, user_content: str) -> Optional[str]:
        key = self._hash_key(system, user_content)
        with self.lock:
            if key in self.cache:
                response, timestamp = self.cache[key]
                if time.time() - timestamp < self.ttl_seconds:
                    return response
                else:
                    del self.cache[key]
        return None
    
    def set(self, system: str, user_content: str, response: str):
        key = self._hash_key(system, user_content)
        with self.lock:
            self.cache[key] = (response, time.time())

_response_cache = ResponseCache(ttl_seconds=3600)


def _fallback_llm_response(system: str, user_content: str) -> str:
    """Return a deterministic local response when Groq/OpenAI is unavailable."""
    if "Extract symptoms" in system:
        message = user_content.split("Message:", 1)[-1].strip().lower()
        greeting_tokens = ("hello", "hi", "hey", "good morning", "good afternoon")
        if any(token in message for token in greeting_tokens):
            return json.dumps({"intent": "greeting", "symptoms": []})

        symptom_terms = [
            "chest pain",
            "chest tightness",
            "headache",
            "shortness of breath",
            "dizziness",
            "vomiting",
            "nausea",
            "fever",
            "cough",
            "fatigue",
            "pain",
            "swelling",
        ]
        symptoms = []
        for term in symptom_terms:
            if term in message:
                symptoms.append({
                    "name": term.replace(" ", "_"),
                    "raw_text": term,
                    "negated": False,
                    "duration_hint": None,
                })

        return json.dumps({
            "intent": "symptom" if symptoms else "other",
            "symptoms": symptoms,
        })

    if "Assess clinical risk" in system:
        is_auto = "Auto-escalate: True" in user_content or "Auto-escalate: true" in user_content
        red_flag_count = 0
        for line in user_content.splitlines():
            if line.startswith("Red flags:"):
                try:
                    red_flag_count = int(line.split(":", 1)[1].strip())
                except Exception:
                    red_flag_count = 0
                break

        if is_auto:
            severity = "critical"
            risk_score = 90
            escalation = "call_emergency"
            reason = "Local fallback detected an auto-escalation condition."
        elif red_flag_count > 0:
            severity = "high"
            risk_score = 70
            escalation = "schedule_urgent"
            reason = "Local fallback detected red-flag symptoms."
        else:
            severity = "moderate"
            risk_score = 35
            escalation = "monitor"
            reason = "Local fallback could not detect a critical pattern."

        return json.dumps({
            "severity": severity,
            "risk_score": risk_score,
            "confidence": "medium",
            "escalation": escalation,
            "escalation_reason": reason,
        })

    return "{}"

def _call_llm(system: str, user_content: str, use_cache: bool = True) -> str:
    if use_cache:
        cached = _response_cache.get(system, user_content)
        if cached:
            return cached

    if client is None:
        return _fallback_llm_response(system, user_content)
    
    response = client.chat.completions.create(
        model=GROQ_MODEL,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user_content},
        ],
        temperature=0.3,
        timeout=60,
    )
    
    output = response.choices[0].message.content
    if use_cache:
        _response_cache.set(system, user_content, output)
    return output

def _build_patient_summary(ctx: PatientContext) -> str:
    lines = [f"Patient ID: {ctx.patient_id}", f"Age: {ctx.age}"]
    if ctx.conditions:
        lines.append(f"Conditions: {', '.join(ctx.conditions)}")
    if ctx.current_medications:
        lines.append(f"Medications: {', '.join(ctx.current_medications)}")
    return "\n".join(lines)

_EXTRACTION_SYSTEM = """Extract symptoms from patient message. Respond ONLY with JSON:
{
  "intent": "greeting|symptom|other",
  "symptoms": [{"name": "symptom_name", "raw_text": "text", "negated": false, "duration_hint": null}]
}"""

def extract_intent_and_symptoms(raw_message: str, patient_context: PatientContext) -> Tuple[str, List[ExtractedSymptom]]:
    user_prompt = f"Patient: {_build_patient_summary(patient_context)}\n\nMessage: {raw_message}"
    raw = _call_llm(_EXTRACTION_SYSTEM, user_prompt, use_cache=True)
    try:
        result = json.loads(raw)
    except json.JSONDecodeError:
        cleaned = raw.strip()
        if "```json" in cleaned:
            cleaned = cleaned.split("```json")[1].split("```")[0]
        result = json.loads(cleaned)
    
    intent = result.get("intent", "other").lower()
    symptoms = [ExtractedSymptom(**item) for item in result.get("symptoms", [])]
    return intent, symptoms

def match_red_flags(symptoms: List[ExtractedSymptom], patient_context: PatientContext, raw_message: str) -> Tuple[List[RedFlagMatch], bool]:
    matched: List[RedFlagMatch] = []
    auto_escalate = False
    message_lower = raw_message.lower()
    
    for condition in list(patient_context.conditions) + ["_general"]:
        for flag in RED_FLAGS.get(condition, []):
            for keyword in flag["keywords"]:
                if keyword.lower() in message_lower:
                    matched.append(RedFlagMatch(flag_name=flag["flag_name"], matched_symptom=keyword, condition=condition, weight=flag["weight"]))
                    if flag.get("auto_escalate"):
                        auto_escalate = True
                    break
    
    return matched, auto_escalate

_RISK_SYSTEM = """Assess clinical risk. Respond ONLY with JSON:
{
  "severity": "low|moderate|high|critical",
  "risk_score": 0,
  "confidence": "low|medium|high",
  "escalation": "reassure|monitor|schedule_within_48h|schedule_urgent|call_emergency",
  "escalation_reason": "brief reason"
}"""

def score_risk(symptoms: List[ExtractedSymptom], red_flags: List[RedFlagMatch], patient_context: PatientContext, auto_escalate: bool) -> dict:
    symptom_list = ", ".join(s.name for s in symptoms if not s.negated) or "none"
    user_prompt = f"Patient: {_build_patient_summary(patient_context)}\nSymptoms: {symptom_list}\nRed flags: {len(red_flags)}\nAuto-escalate: {auto_escalate}"
    raw = _call_llm(_RISK_SYSTEM, user_prompt, use_cache=False)
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        cleaned = raw.strip()
        if "```json" in cleaned:
            cleaned = cleaned.split("```json")[1].split("```")[0]
        return json.loads(cleaned)

def run_symptoms_agent(agent_input: SymptomsAgentInput) -> SymptomsAgentOutput:
    ctx = agent_input.patient_context
    message = agent_input.raw_message
    
    try:
        intent, extracted = extract_intent_and_symptoms(message, ctx)
        
        if intent == "greeting":
            return SymptomsAgentOutput(
                extracted_symptoms=[], symptom_summary="no symptoms provided", severity=Severity.LOW,
                red_flags_matched=[], risk_score=0, confidence="low", escalation=EscalationAction.REASSURE,
                escalation_reason="Hi! Tell me what symptoms you're experiencing."
            )
        
        if intent == "other":
            return SymptomsAgentOutput(
                extracted_symptoms=[], symptom_summary="unclear input", severity=Severity.LOW,
                red_flags_matched=[], risk_score=0, confidence="low", escalation=EscalationAction.REASSURE,
                escalation_reason="Could you describe any symptoms?"
            )
        
        active_symptoms = [s for s in extracted if not s.negated]
        symptom_summary = ", ".join(s.name for s in active_symptoms) or "no specific symptoms"
        red_flags, auto_escalate = match_red_flags(extracted, ctx, message)
        risk_result = score_risk(extracted, red_flags, ctx, auto_escalate)
        
        escalation_str = risk_result.get("escalation", "monitor")
        if auto_escalate and escalation_str != "call_emergency":
            escalation_str = "call_emergency"
        
        return SymptomsAgentOutput(
            extracted_symptoms=extracted, symptom_summary=symptom_summary,
            severity=Severity(risk_result["severity"]), red_flags_matched=red_flags,
            risk_score=int(risk_result["risk_score"]), confidence=risk_result.get("confidence", "medium"),
            escalation=EscalationAction(escalation_str),
            escalation_reason=risk_result.get("escalation_reason", ""),
        )
    except Exception as e:
        logger.error(f"Error: {e}")
        return SymptomsAgentOutput(
            extracted_symptoms=[], symptom_summary="error", severity=Severity.LOW,
            red_flags_matched=[], risk_score=0, confidence="low", escalation=EscalationAction.REASSURE,
            escalation_reason=f"Error: {str(e)[:80]}"
        )

def assess_symptoms(
    raw_message: str, patient_id: str, age: int, conditions: str, medications: str,
    vitals_flag: str = "normal", baseline_bp_systolic: Optional[int] = None,
    baseline_bp_diastolic: Optional[int] = None,
) -> str:
    """Assess patient symptoms and return clinical advice."""
    
    conditions_list = [c.strip() for c in conditions.split(",") if c.strip()]
    medications_list = [m.strip() for m in medications.split(",") if m.strip()]
    
    patient_context = PatientContext(
        patient_id=patient_id, age=age, conditions=conditions_list,
        current_medications=medications_list, vitals_severity_flag=vitals_flag,
        baseline_bp_systolic=baseline_bp_systolic or 120,
        baseline_bp_diastolic=baseline_bp_diastolic or 80,
    )
    
    result = run_symptoms_agent(SymptomsAgentInput(raw_message=raw_message, patient_context=patient_context))
    
    advice = ""
    if result.risk_score < 30:
        advice = "✅ Low Risk: Rest, hydrate, monitor. No urgent care needed."
    elif result.risk_score < 50:
        advice = "⚠️ Moderate Risk: Schedule appointment within 24 hours. Monitor symptoms."
    elif result.risk_score < 70:
        advice = "🔴 High Risk: Seek urgent care TODAY. Do not delay."
    else:
        advice = "🚨 CRITICAL: Call 911 immediately. Emergency care required."
    
    response = f"""CLINICAL ASSESSMENT
Patient: {patient_id} | Age: {age}
Symptom: {result.symptom_summary}
Risk Score: {result.risk_score}/100
Severity: {result.severity.value.upper()}
Escalation: {result.escalation.value.upper()}

{advice}

Reason: {result.escalation_reason}"""
    
    return response

root_agent = Agent(
    model="groq/llama-3.3-70b-versatile",
    name="symptoms_agent",
    description="CareOrchestra Symptoms Agent - Clinical risk assessment",
    instruction="Call assess_symptoms with patient details to get clinical assessment.",
    tools=[assess_symptoms],
)
