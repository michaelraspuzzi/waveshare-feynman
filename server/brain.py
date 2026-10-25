"""The tutor: answers a spoken question in Feynman's teaching style, in the context of the lecture so far.

Uses the Anthropic API when credentials are available (ANTHROPIC_API_KEY), otherwise falls back
to the local `claude` CLI (Claude Code), which uses your existing login.
"""
import json
import os
import re
import shutil
import subprocess

MODEL = os.environ.get("FEYNMAN_MODEL", "claude-opus-5-5")

SYSTEM = """You are a tutor speaking in the voice and teaching style of Richard Feynman, \
partway through a recorded lecture to one student. The student pressed a button to interrupt \
and ask a question out loud.

How to answer:
- Talk, don't write. Your words are read aloud by a speech synthesizer and shown as subtitles.
- 2 to 5 short sentences, under 90 words. Plain words, concrete images, a little humor is fine.
- No markdown, no lists, no symbols or equations; say "phi one", "squared", "h-bar".
- Answer what they actually asked. If the question is unclear or just noise, say briefly that \
you didn't catch it.
- If it would help, pick one of the lecture's existing diagrams to show while you answer.
- Don't claim to be the real Richard Feynman; you're a tutor in his style.

Reply with JSON only: {"answer": "...", "visual": "<diagram id or null>"}"""

SCHEMA = {
    "type": "object",
    "properties": {
        "answer": {"type": "string"},
        "visual": {"type": ["string", "null"]},
    },
    "required": ["answer", "visual"],
    "additionalProperties": False,
}


def _prompt(lecture_title, heard_lines, visuals, history, question):
    so_far = "\n".join(heard_lines[-40:])
    past = "\n".join(f"Student: {q}\nTutor: {a}" for q, a in history[-4:]) or "(none)"
    return (f"Lecture: {lecture_title}\n\nDiagrams you can show: {', '.join(visuals)}\n\n"
            f"What the student has heard so far:\n{so_far}\n\n"
            f"Earlier questions in this session:\n{past}\n\n"
            f"The student asks: \"{question}\"")


def _parse(text, visuals):
    m = re.search(r"\{.*\}", text, re.S)
    try:
        data = json.loads(m.group(0) if m else text)
        answer, visual = data.get("answer", "").strip(), data.get("visual")
    except (json.JSONDecodeError, AttributeError):
        answer, visual = text.strip(), None
    return answer, visual if visual in visuals else None


def _via_api(system, prompt):
    import anthropic

    client = anthropic.Anthropic()
    resp = client.beta.messages.create(
        model=MODEL,
        max_tokens=2000,
        system=system,
        messages=[{"role": "user", "content": prompt}],
        output_config={"effort": "low", "format": {"type": "json_schema", "schema": SCHEMA}},
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
    )
    if resp.stop_reason == "refusal":
        return '{"answer": "Hmm, I can\'t help with that one. Let\'s get back to the lecture.", "visual": null}'
    return "".join(b.text for b in resp.content if b.type == "text")


def _via_cli(system, prompt):
    out = subprocess.run(
        ["claude", "-p", "--model", os.environ.get("FEYNMAN_CLI_MODEL", "sonnet"),
         "--append-system-prompt", system, "--output-format", "text"],
        input=prompt, capture_output=True, text=True, timeout=90)
    return out.stdout


def backend():
    if os.environ.get("ANTHROPIC_API_KEY"):
        return "api"
    return "cli" if shutil.which("claude") else "none"


def answer(lecture_title, heard_lines, visuals, history, question):
    prompt = _prompt(lecture_title, heard_lines, visuals, history, question)
    b = backend()
    if b == "api":
        raw = _via_api(SYSTEM, prompt)
    elif b == "cli":
        raw = _via_cli(SYSTEM, prompt)
    else:
        raw = '{"answer": "I don\'t have a brain connected yet. Set an Anthropic API key.", "visual": null}'
    return _parse(raw, visuals)
