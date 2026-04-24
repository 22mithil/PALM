import asyncio
import argparse
import logging
import uuid
import sys

# Force UTF-8 encoding for Windows terminals to handle LLM emojis
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

from rich.console import Console
from rich.panel import Panel

# Configure basic logging to terminal so we can see the backend logs
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S"
)

# Suppress noisy third-party logs
logging.getLogger("httpx").setLevel(logging.WARNING)

from app.schemas.state_prompt import StatePrompt, EmotionState
from app.orchestrator import run_orchestrator

console = Console()

async def main():
    parser = argparse.ArgumentParser(description="Test PALM Orchestrator Core Logic (Brain)")
    parser.add_argument("--query", type=str, default="I don't understand how to do this.", help="Student's text query or transcript")
    parser.add_argument("--emotion", type=str, default="confused", help="Mock emotion label (e.g. happy, confused, frustrated, bored)")
    parser.add_argument("--gaze", type=str, default="on_screen", help="Mock gaze (e.g. on_screen, off_screen)")
    parser.add_argument("--mastery", type=float, default=0.5, help="Mock mastery score (0.0 to 1.0)")
    parser.add_argument("--wrong", type=int, default=0, help="Number of consecutive wrong answers")
    
    args = parser.parse_args()

    session_id = str(uuid.uuid4())
    student_id = str(uuid.uuid4())

    console.print(Panel(
        f"[bold cyan]Testing Orchestrator Brain[/bold cyan]\n"
        f"Session ID: {session_id}\n"
        f"Query:      '{args.query}'\n"
        f"Emotion:    {args.emotion} | Gaze: {args.gaze}\n"
        f"Mastery:    {args.mastery} | Wrong: {args.wrong}",
        title="Test Initialization"
    ))

    # Build a mock StatePrompt
    prompt = StatePrompt(
        student_id=student_id,
        session_id=session_id,
        query=args.query,
        emotion=EmotionState(label=args.emotion, confidence=0.9),
        gaze=args.gaze,
        current_topic="Fractions",
        difficulty_level=1,
        mastery_score=args.mastery,
        consecutive_wrong=args.wrong,
        is_correct=False,
        recent_responses=["Let's start with fractions."],
        session_summary="Student is starting to learn fractions.",
        system_instructions="You are a helpful tutor.",
    )

    console.print("\n[bold yellow]Calling Orchestrator... (Check standard logs above/below)[/bold yellow]\n")

    result = await run_orchestrator(prompt)

    console.print("\n" + "="*60)
    console.print(Panel(
        f"[bold green]Final Result[/bold green]\n\n"
        f"[bold]Route Used:[/bold] {result.route}\n"
        f"[bold]Agent Used:[/bold] {result.agent_used}\n"
        f"[bold]Latency:[/bold]    {result.metadata.get('latency_ms')} ms\n\n"
        f"[bold]Response:[/bold]\n{result.final_response}",
        title="Orchestration Complete",
        border_style="green"
    ))

if __name__ == "__main__":
    asyncio.run(main())
