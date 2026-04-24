import asyncio
import logging
import uuid
import sys

# Force UTF-8 encoding for Windows terminals to handle LLM emojis (e.g. 🎉)
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

# Configure basic logging to terminal
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S"
)
logging.getLogger("httpx").setLevel(logging.WARNING)

from app.schemas.state_prompt import StatePrompt, EmotionState
from app.orchestrator import run_orchestrator

console = Console()

SCENARIO_1 = [
    {
        "description": "1. Student starts a new topic",
        "query": "What exactly are fractions? I've never done this before.",
        "emotion": "neutral",
        "gaze": "on_screen",
        "mastery": 0.0,
        "consecutive_wrong": 0,
        "is_correct": False,
    },
    {
        "description": "2. Student attempts a question but fails (confused)",
        "query": "Is the top number called the denominator?",
        "emotion": "confused",
        "gaze": "on_screen",
        "mastery": 0.1,
        "consecutive_wrong": 1,
        "is_correct": False,
    },
    {
        "description": "3. Student attempts again and fails (frustrated)",
        "query": "I don't get this at all, nothing makes sense!",
        "emotion": "frustrated",
        "gaze": "on_screen",
        "mastery": 0.1,
        "consecutive_wrong": 3,
        "is_correct": False,
    },
    {
        "description": "4. Student looks away and seems bored",
        "query": "...",
        "emotion": "bored",
        "gaze": "off_screen",
        "mastery": 0.1,
        "consecutive_wrong": 0,
        "is_correct": False,
    },
    {
        "description": "5. Student gets it right and shows high mastery",
        "query": "So 1/2 is the same as 2/4!",
        "emotion": "happy",
        "gaze": "on_screen",
        "mastery": 0.85,
        "consecutive_wrong": 0,
        "is_correct": True,
    }
]

SCENARIO_2 = [
    {
        "description": "1. Student is answering smoothly, high engagement",
        "query": "I finished the multiplication table!",
        "emotion": "happy",
        "gaze": "on_screen",
        "mastery": 0.9,
        "consecutive_wrong": 0,
        "is_correct": True,
    },
    {
        "description": "2. Student asks an advanced concept",
        "query": "How do I multiply fractions though?",
        "emotion": "curious",
        "gaze": "on_screen",
        "mastery": 0.9,
        "consecutive_wrong": 0,
        "is_correct": False,
    },
    {
        "description": "3. Student gets distracted",
        "query": "Did you see the new Spiderman movie?",
        "emotion": "happy",
        "gaze": "off_screen",
        "mastery": 0.9,
        "consecutive_wrong": 0,
        "is_correct": False,
    }
]

ALL_SCENARIOS = [
    ("Struggling Student Flow", SCENARIO_1),
    ("Advanced Student Distraction Flow", SCENARIO_2)
]

async def run_simulated_session():
    for scenario_name, scenario_flow in ALL_SCENARIOS:
        session_id = str(uuid.uuid4())
        student_id = str(uuid.uuid4())
        
        console.print(Panel(
            f"[bold cyan]Session Scenario: {scenario_name}[/bold cyan]\n"
            f"Session ID: {session_id}\n"
            f"Simulating {len(scenario_flow)} sequential interactions.",
            title="Session Start"
        ))

        # Maintain conversational history across the artificial session
        recent_responses = []

        for idx, interaction in enumerate(scenario_flow, 1):
            console.print(f"\n[bold magenta]---------- Interaction {idx}/{len(scenario_flow)} ----------[/bold magenta]")
            console.print(f"[bold]{interaction['description']}[/bold]")
            
            table = Table(show_header=False, box=None)
            table.add_row("[cyan]Query:[/cyan]", f"'{interaction['query']}'")
            table.add_row("[cyan]Emotion:[/cyan]", interaction['emotion'])
            table.add_row("[cyan]Gaze:[/cyan]", interaction['gaze'])
            table.add_row("[cyan]State:[/cyan]", f"Mastery: {interaction['mastery']} | Wrong: {interaction['consecutive_wrong']} | Correct: {interaction['is_correct']}")
            console.print(table)
            console.print("\n[dim]-- Orchestrator Logs --[/dim]")

            # Build prompt mimicking what the context_manager would do
            prompt = StatePrompt(
                student_id=student_id,
                session_id=session_id,
                query=interaction["query"],
                emotion=EmotionState(label=interaction["emotion"], confidence=0.9),
                gaze=interaction["gaze"],
                current_topic="Fractions",
                difficulty_level=1,
                mastery_score=interaction["mastery"],
                consecutive_wrong=interaction["consecutive_wrong"],
                is_correct=interaction["is_correct"],
                recent_responses=recent_responses[-3:], # Keep last 3 responses
                session_summary="Student is learning about numerators and denominators.",
                system_instructions="You are a helpful and empathetic tutor.",
            )

            # Run orchestrator
            result = await run_orchestrator(prompt)
            
            # Append response to history for the next iteration
            recent_responses.append(result.final_response)

            console.print("\n[dim]-- Output Summary --[/dim]")
            
            output_table = Table(show_header=False, style="green")
            output_table.add_row("[bold]Route:[/bold]", result.route)
            output_table.add_row("[bold]Agent:[/bold]", result.agent_used)
            output_table.add_row("[bold]Response:[/bold]", f"{result.final_response}")
            console.print(output_table)
            
            # Add a little artificial delay between testing rounds for readability
            await asyncio.sleep(1)

        console.print(Panel(f"[bold green]{scenario_name} Complete![/bold green]", border_style="green"))
        console.print("\n" + "="*80 + "\n")

if __name__ == "__main__":
    asyncio.run(run_simulated_session())
